#!/usr/bin/env python3
"""
Training script for Entry Point Classification Model.

Run:
  python train_entry_model.py --symbol BTC/USDC --hours 720

Leakage-free design
-------------------
Three forms of leakage existed in the original single-dataset approach:

1. Random shuffle in filter_entry_samples destroyed temporal order, so
   "early" training samples contained data from the future.
2. Feature normalization (StandardScaler) was fit on the full dataset before
   the train/val split, so the scaler saw future validation statistics.
3. There was no gap between train and val, meaning the look-ahead labels of
   the last training bars overlapped with the first validation bars.

All three are fixed here:
  - balance_classes=False: temporal order is preserved; class imbalance is
    handled by scale_pos_weight (computed dynamically inside EntryPointModel).
  - Two separate EntryPointDataset instances are created for train and val,
    each covering its own time window.  The val dataset receives the training
    scaler (mean/std/feature_mask) so no val statistics leak into the scaler.
  - A gap of `look_ahead` seconds separates the end of the training window
    from the start of the validation window.
"""

import argparse
import logging
import os
import numpy as np
from datetime import datetime, timedelta, timezone

from ml.config import DatabaseConfig, DataConfig
from ml.entry_dataset import EntryPointDataset
from ml.entry_model import EntryPointModel

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def run_leakage_check(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> None:
    """Sanity-check for label leakage by training on shuffled labels.

    If AUC after shuffling is still high (> 0.65) the features contain
    future information — stop and investigate.  A clean model should produce
    AUC close to 0.5 on shuffled labels.
    """
    from sklearn.metrics import roc_auc_score
    import lightgbm as lgb

    logger.info("Running leakage check (shuffle test) ...")
    y_shuffled = y_train.copy()
    rng = np.random.default_rng(seed=0)
    rng.shuffle(y_shuffled)

    probe = lgb.LGBMClassifier(
        n_estimators=100,
        num_leaves=31,
        learning_rate=0.05,
        verbose=-1,
        random_state=42,
    )
    probe.fit(X_train, y_shuffled)
    y_val_binary = (y_val >= 0.5).astype(int)
    probs = probe.predict_proba(X_val)[:, 1]
    auc = roc_auc_score(y_val_binary, probs)

    if auc > 0.65:
        logger.warning(
            f"LEAKAGE CHECK FAILED: AUC={auc:.4f} on shuffled labels (expected ~0.50). "
            "Features likely contain future information — investigate before trusting results."
        )
    else:
        logger.info(f"Leakage check passed: AUC={auc:.4f} on shuffled labels (expected ~0.50).")


def main() -> None:
    parser = argparse.ArgumentParser(description='Train Entry Point Classification Model')
    parser.add_argument('--symbol', type=str, default='BTC/USDC', help='Target symbol')
    parser.add_argument('--hours', type=int, default=720, help='Total data window in hours')
    parser.add_argument('--profit', type=float, default=0.06, help='Profit target (0.06 = 6.0%)')
    parser.add_argument('--stop', type=float, default=0.0035, help='Stop loss (0.0035 = 0.35%)')
    parser.add_argument('--lookahead', type=int, default=28800, help='Look-ahead bars (seconds)')
    parser.add_argument('--val-frac', type=float, default=0.2, help='Fraction of data used for validation')
    parser.add_argument(
        '--stride', type=int, default=1,
        help=(
            'Stride for downsampling training/val vectors (default 1 = no downsampling). '
            'Use e.g. --stride 60 to reduce overlap between consecutive 1-second samples.'
        )
    )
    parser.add_argument(
        '--leakage-check', action='store_true',
        help='Run shuffle-label leakage diagnostic before training (adds ~30s)'
    )
    parser.add_argument('--output', type=str, help='Output model path (auto-generated if not set)')

    args = parser.parse_args()

    db_config = DatabaseConfig()
    data_config = DataConfig()
    data_config.target_symbol = args.symbol
    data_config.train_hours = args.hours

    # ------------------------------------------------------------------
    # Time window calculation
    # ------------------------------------------------------------------
    # Layout (chronological):
    #   [train_start ... train_end] <-- gap --> [val_start ... val_end]
    #
    # The gap is exactly `look_ahead` seconds so that no label computed
    # from price data inside the training window can "see into" the
    # validation window.
    #
    # We carve the gap out of the total requested window so that the sum
    # of train + gap + val still fits within `hours`.
    # ------------------------------------------------------------------
    gap_seconds = args.lookahead
    total_seconds = int(args.hours * 3600)

    # Reserve the gap from the total so we never under-deliver on useful data.
    usable_seconds = total_seconds - gap_seconds
    if usable_seconds <= 0:
        raise ValueError(
            f"--hours ({args.hours}h) is too small to fit a gap of "
            f"{gap_seconds}s ({gap_seconds/3600:.1f}h).  "
            "Increase --hours or decrease --lookahead."
        )

    val_seconds = int(usable_seconds * args.val_frac)
    train_seconds = usable_seconds - val_seconds

    end_time = datetime.now(timezone.utc)
    val_end = end_time
    val_start = end_time - timedelta(seconds=val_seconds)
    train_end = val_start - timedelta(seconds=gap_seconds)
    train_start = train_end - timedelta(seconds=train_seconds)

    logger.info("Starting Entry Point Model training (leakage-free split):")
    logger.info(f"  Symbol:           {args.symbol}")
    logger.info(f"  Profit target:    {args.profit * 100:.2f}%")
    logger.info(f"  Stop loss:        {args.stop * 100:.2f}%")
    logger.info(f"  Look-ahead:       {args.lookahead / 60:.1f} min ({args.lookahead}s)")
    logger.info(f"  Train window:     {train_start:%Y-%m-%d %H:%M} → {train_end:%Y-%m-%d %H:%M}  "
                f"({train_seconds / 3600:.1f}h)")
    logger.info(f"  Gap:              {gap_seconds / 3600:.1f}h  "
                f"({val_start - timedelta(seconds=gap_seconds):%H:%M} → {val_start:%H:%M})")
    logger.info(f"  Val window:       {val_start:%Y-%m-%d %H:%M} → {val_end:%Y-%m-%d %H:%M}  "
                f"({val_seconds / 3600:.1f}h)")

    # ------------------------------------------------------------------
    # Load training dataset  — computes scaler on training data only.
    # balance_classes=False: class imbalance is handled by the model's
    # scale_pos_weight (computed dynamically in EntryPointModel.train).
    # ------------------------------------------------------------------
    logger.info("Loading TRAINING dataset ...")
    train_dataset = EntryPointDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=train_start,
        end_time=train_end,
        profit_target=args.profit,
        stop_loss=args.stop,
        look_ahead=args.lookahead,
        balance_classes=False,
        sequence_length=data_config.sequence_length,
    )

    # ------------------------------------------------------------------
    # Load validation dataset — re-uses training scaler (no val leakage).
    # ------------------------------------------------------------------
    logger.info("Loading VALIDATION dataset (using training scaler) ...")
    val_dataset = EntryPointDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=val_start,
        end_time=val_end,
        profit_target=args.profit,
        stop_loss=args.stop,
        look_ahead=args.lookahead,
        balance_classes=False,
        sequence_length=data_config.sequence_length,
        # Pass training normalization so val is not used to fit the scaler.
        mean=train_dataset.mean,
        std=train_dataset.std,
        feature_mask=train_dataset.feature_mask,
    )

    X_train = np.vstack(train_dataset.vectors)
    y_train = np.array(train_dataset.targets)
    X_val = np.vstack(val_dataset.vectors)
    y_val = np.array(val_dataset.targets)

    # Optional: reduce density of overlapping samples via striding.
    if args.stride > 1:
        X_train = X_train[::args.stride]
        y_train = y_train[::args.stride]
        X_val = X_val[::args.stride]
        y_val = y_val[::args.stride]
        logger.info(
            f"Stride {args.stride} applied — "
            f"train: {len(X_train)} samples, val: {len(X_val)} samples"
        )
    else:
        logger.info(f"Train: {len(X_train)} samples, Val: {len(X_val)} samples")

    # ------------------------------------------------------------------
    # Optional leakage diagnostic
    # ------------------------------------------------------------------
    if args.leakage_check:
        run_leakage_check(X_train, y_train, X_val, y_val)

    # ------------------------------------------------------------------
    # Train model
    # ------------------------------------------------------------------
    model = EntryPointModel()
    model.profit_target = args.profit
    model.stop_loss = args.stop
    metrics = model.train(X_train, y_train, X_val, y_val)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    if not args.output:
        os.makedirs('ml/models/entry_point', exist_ok=True)
        safe_symbol = args.symbol.replace('/', '_')
        profit_val = int(round(args.profit * 10000))
        stop_val = int(round(args.stop * 10000))
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')
        args.output = (
            f'ml/models/entry_point/'
            f'entry_model_{safe_symbol}_p{profit_val:04d}_s{stop_val:04d}_{timestamp}.pkl'
        )

    model.save(args.output, feature_mask=train_dataset.feature_mask)
    logger.info(f"Model saved to: {args.output}")
    logger.info(
        f"Training complete — "
        f"ROC AUC: {metrics['roc_auc']:.4f}  "
        f"Threshold: {metrics['threshold']:.4f}  "
        f"F1: {metrics['f1']:.4f}"
    )


if __name__ == "__main__":
    main()
