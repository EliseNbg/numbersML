#!/usr/bin/env python3
"""
Training script for TradingTCN — a PnL‑optimized model.

This script:
  • Loads raw future returns (not sigmoid‑scaled labels)
  • Builds temporal sequences from 1‑second wide_vectors
  • Trains TradingTCN with a differentiable PnL / Sharpe loss
  • Validates and saves the best model by val_sharpe

Usage (defaults target 15‑min horizon):
  .venv/bin/python train_trading_tcn.py \\
      --symbol DASH/USDC \\
      --hours 360 \\
      --seq-length 120 \\
      --horizon 900 \\
      --stride 60 \\
      --loss risk_adjusted

Key defaults:
  --lr 0.0003   (safe LR for normalized features)
  --clip-returns 0.02  (clip extreme moves to ±2%)
  --batch-size 128
  --epochs 60  (early stopping on Sharpe)
"""

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import numpy as np
import psycopg2
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

from ml.config import DatabaseConfig, DataConfig, PipelineConfig, ModelConfig, TrainingConfig
from ml.model import TradingTCN, create_model
from ml.losses import risk_adjusted_loss, pnl_loss, sharpe_loss
from ml.trading_dataset import TradingDataset, build_sequences
from torch.utils.data import Dataset


class SequenceDataset(Dataset):
    """Wrapper for a list of (sequence, target) tuples."""
    def __init__(self, sequences: list):
        self.sequences = sequences

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.sequences[idx]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    loss_fn,
    device: torch.device,
    grad_clip: float = 1.0,
) -> float:
    model.train()
    total_loss = 0.0
    n_batches = 0
    for batch_idx, (X, y) in enumerate(loader):
        X, y = X.to(device), y.to(device)

        # NaN check on inputs
        if torch.isnan(X).any() or torch.isnan(y).any():
            logger.warning(f"NaN in input batch {batch_idx} — skipping")
            continue

        optimizer.zero_grad()
        pred_ret, pred_risk = model(X)

        # NaN check on outputs
        if torch.isnan(pred_ret).any() or torch.isnan(pred_risk).any():
            logger.warning(f"NaN in model output batch {batch_idx} — skipping")
            continue

        loss = loss_fn(pred_ret, pred_risk, y)

        if torch.isnan(loss) or torch.isinf(loss):
            logger.warning(f"Invalid loss ({loss.item()}) batch {batch_idx} — skipping")
            continue

        loss.backward()

        # Check gradients for NaN / Inf
        GradsOK = True
        for p in model.parameters():
            if p.grad is not None:
                if not torch.isfinite(p.grad).all():
                    GradsOK = False
                    break
        if not GradsOK:
            logger.warning(f"NaN/Inf gradient detected batch {batch_idx} — skipping update")
            optimizer.zero_grad()
            continue

        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1

    if n_batches == 0:
        logger.error("All batches were skipped! Data contains NaNs or model collapsed.")
        return float('nan')
    return total_loss / n_batches


def eval_epoch(
    model: nn.Module,
    loader: DataLoader,
    loss_fn,
    device: torch.device,
) -> Tuple[float, float, float]:
    """Return (loss, mean_pnl, sharpe) on validation set."""
    model.eval()
    all_ret, all_risk, all_y = [], [], []
    total_loss = 0.0
    n_batches = 0

    with torch.no_grad():
        for X, y in loader:
            X, y = X.to(device), y.to(device)

            if torch.isnan(X).any() or torch.isnan(y).any():
                continue

            pred_ret, pred_risk = model(X)

            if torch.isnan(pred_ret).any() or torch.isnan(pred_risk).any():
                continue

            loss = loss_fn(pred_ret, pred_risk, y)

            if torch.isnan(loss) or torch.isinf(loss):
                continue

            total_loss += loss.item()
            all_ret.append(pred_ret.cpu())
            all_risk.append(pred_risk.cpu())
            all_y.append(y.cpu())
            n_batches += 1

    if n_batches == 0:
        logger.warning("eval_epoch: all batches were invalid")
        return float('nan'), 0.0, 0.0

    pred_ret_all  = torch.cat(all_ret)
    pred_risk_all = torch.cat(all_risk)
    y_all         = torch.cat(all_y)

    position = torch.tanh(pred_ret_all / (pred_risk_all + 1e-6))
    pnl = position * y_all
    mean_pnl = pnl.mean().item()
    sharpe = (pnl.mean() / (pnl.std() + 1e-8)).item()

    return total_loss / n_batches, mean_pnl, sharpe


def main():
    parser = argparse.ArgumentParser(description='Train TradingTCN with PnL-aligned loss')
    parser.add_argument('--symbol', type=str, default='DASH/USDC')
    parser.add_argument('--hours', type=int, default=360, help='Total data window (hours)')
    parser.add_argument('--seq-length', type=int, default=120, help='Sequence length (timesteps)')
    parser.add_argument('--batch-size', type=int, default=128)
    parser.add_argument('--epochs', type=int, default=60)
    parser.add_argument('--lr', type=float, default=0.0003,
                        help='Learning rate (default: 0.0003, safe for normalized features)')
    parser.add_argument('--loss', type=str, default='pnl',
                        choices=['risk_adjusted', 'pnl', 'sharpe'],
                        help='Loss type: pnl (simple), sharpe (risk-adjusted), risk_adjusted (with penalty)')
    parser.add_argument('--stride', type=int, default=60,
                        help='Stride for sequence building (reduce autocorrelation)')
    parser.add_argument('--val-frac', type=float, default=0.2)
    parser.add_argument('--output', type=str, help='Output model path (auto if not set)')
    parser.add_argument('--clip-returns', type=float, default=0.02,
                        help='Clip raw returns to ±X (default 0.02 = ±2%%)')
    parser.add_argument('--normalize-returns', action='store_true',
                        help='Standardize return distribution (zero mean, unit var)')
    parser.add_argument('--horizon', type=int, default=900,
                        help='Prediction horizon in seconds (default: 900 = 15 min)')
    parser.add_argument('--risk-penalty', type=float, default=0.05,
                        help='Penalty weight for risk underestimation in risk_adjusted loss (default: 0.05)')
    args = parser.parse_args()

    device = torch.device('cpu')  # Change to 'cuda' if GPU available
    logger.info(f"Using device: {device}")

    # ------------------------------------------------------------------
    # Time window from latest DB data (not wall-clock time)
    # ------------------------------------------------------------------
    db_cfg = DatabaseConfig()
    conn_tmp = psycopg2.connect(
        host=db_cfg.host, port=db_cfg.port, dbname=db_cfg.dbname,
        user=db_cfg.user, password=db_cfg.password,
    )
    with conn_tmp.cursor() as cur:
        cur.execute("SELECT MAX(time) FROM wide_vectors")
        row = cur.fetchone()
        latest_time = row[0] if row and row[0] else datetime.now(timezone.utc)
    conn_tmp.close()
    logger.info(f"Latest DB timepoint: {latest_time}")

    gap_seconds = args.stride * 2  # conservative gap between val/train
    total_seconds = int(args.hours * 3600)
    usable_seconds = total_seconds - gap_seconds
    val_seconds = int(usable_seconds * args.val_frac)
    train_seconds = usable_seconds - val_seconds

    end_time   = latest_time
    val_end    = end_time
    val_start  = end_time - timedelta(seconds=val_seconds)
    train_end  = val_start - timedelta(seconds=gap_seconds)
    train_start = train_end - timedelta(seconds=train_seconds)

    logger.info("TradingTCN training windows:")
    logger.info(f"  Train: {train_start} → {train_end}  ({train_seconds/3600:.1f}h)")
    logger.info(f"  Gap:   {gap_seconds}s  ({gap_seconds/60:.0f}m)")
    logger.info(f"  Val:   {val_start} → {val_end}    ({val_seconds/3600:.1f}h)")

    # ------------------------------------------------------------------
    # Load raw‑return datasets
    # ------------------------------------------------------------------
    model_cfg = ModelConfig()
    model_cfg.hidden_dims         = [128]          # d_model
    model_cfg.dropout             = 0.3            # higher dropout for small dataset
    model_cfg.trading_tcn_blocks  = 6              # slightly smaller, faster training
    model_cfg.trading_tcn_dilations = None         # use default [1,2,4,8,16,32,4,1]

    # ── Train dataset (raw, no feature norm yet) ─────────────────────
    train_dataset = TradingDataset(
        db_config         = DatabaseConfig(),
        data_config       = DataConfig(target_symbol=args.symbol, prediction_horizon=args.horizon),
        start_time        = train_start,
        end_time          = train_end,
        sequence_length   = 1,
        normalize_returns = args.normalize_returns,
        clip_returns      = args.clip_returns,
        return_stride     = args.stride,
        mean              = None,
        std               = None,
        feature_mask      = None,
    )

    # ── Fit feature normalizer on TRAINING set only ──────────────────
    logger.info("Fitting per-feature ROBUST normalizer (median + IQR) on training set...")
    train_vectors = np.stack(train_dataset.vectors)  # (n_samples, feat_dim)

    # Robust scaling: median + interquartile range (much more stable across
    # train/val splits than mean+std, especially for price/volume features
    # with heavy tails and distribution shifts).
    feat_median = np.median(train_vectors, axis=0, keepdims=True).astype(np.float32)
    feat_q25    = np.percentile(train_vectors, 25, axis=0, keepdims=True).astype(np.float32)
    feat_q75    = np.percentile(train_vectors, 75, axis=0, keepdims=True).astype(np.float32)
    feat_iqr    = (feat_q75 - feat_q25)

    # IQR can be zero for constant features; floor it so they don't explode
    # For constant features this produces near-zero values, letting the model ignore them
    feat_iqr_safe = np.maximum(feat_iqr, 1.0)

    # Normalize training vectors
    train_vectors_norm = (train_vectors - feat_median) / feat_iqr_safe
    train_vectors_norm = np.clip(train_vectors_norm, -5.0, 5.0)
    train_dataset.vectors = [train_vectors_norm[i] for i in range(len(train_vectors_norm))]
    train_dataset.mean = feat_median      # stored as 'mean' for back-compat
    train_dataset.std  = feat_iqr_safe    # stored as 'std'  for back-compat
    train_dataset.feature_mask = np.ones(train_vectors.shape[1], dtype=bool)  # keep all

    # Log per-feature stats for diagnostics
    n_features = feat_median.shape[1]
    logger.info(f"  Features: {n_features}")
    logger.info(f"  Raw feature median range: [{np.median(train_vectors, axis=0).min():.2f}, {np.median(train_vectors, axis=0).max():.2f}]")
    logger.info(f"  Raw feature IQR  range: [{(feat_q75-feat_q25).min():.2f}, {(feat_q75-feat_q25).max():.2f}]")
    logger.info(f"  Norm feature mean range: [{train_vectors_norm.mean(axis=0).min():.4f}, {train_vectors_norm.mean(axis=0).max():.4f}]")
    logger.info(f"  Norm feature std  range: [{train_vectors_norm.std(axis=0).min():.4f}, {train_vectors_norm.std(axis=0).max():.4f}]")

    # Identify top scale features (likely price-dependent)
    train_medians = np.median(train_vectors, axis=0)
    train_iqrs = (feat_q75 - feat_q25).flatten()
    top_scale_idx = np.argsort(train_iqrs)[-10:][::-1]
    col_names = train_dataset.column_names if hasattr(train_dataset, 'column_names') and train_dataset.column_names else [f"feat_{i}" for i in range(n_features)]
    logger.info("  Top 10 features by raw IQR (likely price-dependent):")
    for idx in top_scale_idx:
        name = col_names[idx] if idx < len(col_names) else f"feat_{idx}"
        logger.info(f"    Feature {idx:3d} ({name:35s}): median={train_medians[idx]:10.2f}, iqr={train_iqrs[idx]:10.2f}")

    # ── Validation dataset — load raw, then apply identical normalization ──
    val_dataset = TradingDataset(
        db_config         = DatabaseConfig(),
        data_config       = DataConfig(target_symbol=args.symbol, prediction_horizon=args.horizon),
        start_time        = val_start,
        end_time          = val_end,
        sequence_length   = 1,
        normalize_returns = args.normalize_returns,
        clip_returns      = args.clip_returns,
        return_stride     = args.stride,
        mean              = None,
        std               = None,
        feature_mask      = None,
    )
    val_vectors = np.stack(val_dataset.vectors)
    logger.info(f"  Val raw shape: {val_vectors.shape}, mean={val_vectors.mean():.4f}, std={val_vectors.std():.4f}")
    logger.info(f"  feat_median shape: {feat_median.shape}, dtype: {feat_median.dtype}")
    logger.info(f"  feat_iqr    shape: {feat_iqr_safe.shape}, dtype: {feat_iqr_safe.dtype}")

    # Per-feature val diagnostics before normalization
    val_means = val_vectors.mean(axis=0)
    val_stds = val_vectors.std(axis=0)
    logger.info(f"  Val raw per-feature mean range: [{val_means.min():.2f}, {val_means.max():.2f}]")
    logger.info(f"  Val raw per-feature std  range: [{val_stds.min():.2f}, {val_stds.max():.2f}]")

    # Per-feature z-scores after robust normalization (pre-clip)
    val_vectors_norm = (val_vectors - feat_median) / feat_iqr_safe
    val_norm_means = val_vectors_norm.mean(axis=0)
    val_norm_stds = val_vectors_norm.std(axis=0)
    val_norm_max = np.abs(val_vectors_norm).max(axis=0)

    # Find features with largest post-norm deviations
    worst_idx = np.argsort(val_norm_max)[-10:][::-1]
    logger.info("  Top 10 features by max abs z-score in validation (pre-clip):")
    for idx in worst_idx:
        name = col_names[idx] if idx < len(col_names) else f"feat_{idx}"
        logger.info(
            f"    Feature {idx:3d} ({name:35s}): val_mean={val_means[idx]:10.2f}, "
            f"train_median={feat_median[0,idx]:10.2f}, train_iqr={feat_iqr_safe[0,idx]:10.2f}, "
            f"z_mean={val_norm_means[idx]:7.2f}, z_std={val_norm_stds[idx]:7.2f}, z_max={val_norm_max[idx]:8.2f}"
        )

    # Count how many values get clipped per feature
    n_clipped = ((val_vectors_norm < -5.0) | (val_vectors_norm > 5.0)).sum(axis=0)
    most_clipped = np.argsort(n_clipped)[-10:][::-1]
    logger.info("  Top 10 features by clip count in validation:")
    for idx in most_clipped:
        if n_clipped[idx] > 0:
            name = col_names[idx] if idx < len(col_names) else f"feat_{idx}"
            logger.info(f"    Feature {idx:3d} ({name:35s}): {n_clipped[idx]} values clipped ({100*n_clipped[idx]/len(val_vectors):.1f}%)")

    logger.info(f"  Val after norm (pre-clip): mean={val_vectors_norm.mean():.4f}, std={val_vectors_norm.std():.4f}, min={val_vectors_norm.min():.4f}, max={val_vectors_norm.max():.4f}")
    val_vectors_norm = np.clip(val_vectors_norm, -5.0, 5.0)
    logger.info(f"  Val after clip: mean={val_vectors_norm.mean():.4f}, std={val_vectors_norm.std():.4f}")
    val_dataset.vectors = [val_vectors_norm[i] for i in range(len(val_vectors_norm))]
    val_dataset.mean = feat_median
    val_dataset.std = feat_iqr_safe
    val_dataset.feature_mask = np.ones(val_vectors.shape[1], dtype=bool)

    # ── Build sliding‑window sequences (after normalization) ─────────
    train_seqs = build_sequences(train_dataset, args.seq_length)
    val_seqs   = build_sequences(val_dataset,   args.seq_length)

    logger.info(f"Sequences — train: {len(train_seqs)}, val: {len(val_seqs)}")

    if len(train_seqs) < 100 or len(val_seqs) < 50:
        logger.error("Insufficient sequences — increase --hours or decrease --seq-length")
        return

    # ------------------------------------------------------------------
    # Dataset-wide NaN detection (before stacking)
    # ------------------------------------------------------------------
    for i, (seq, tgt) in enumerate(train_seqs):
        if torch.isnan(seq).any() or torch.isnan(tgt).any():
            logger.error(f"NaN in training sequence {i} — aborting")
            return
    for i, (seq, tgt) in enumerate(val_seqs):
        if torch.isnan(seq).any() or torch.isnan(tgt).any():
            logger.error(f"NaN in validation sequence {i} — aborting")
            return

    # ------------------------------------------------------------------
    # Data sanity check (statistics)
    # ------------------------------------------------------------------
    train_X = torch.stack([s[0] for s in train_seqs])
    train_y = torch.stack([s[1] for s in train_seqs])
    val_X   = torch.stack([s[0] for s in val_seqs])
    val_y   = torch.stack([s[1] for s in val_seqs])

    logger.info("Dataset sanity check:")
    logger.info(f"  Train X:  mean={train_X.mean():.6f}, std={train_X.std():.6f}, min={train_X.min():.6f}, max={train_X.max():.6f}")
    logger.info(f"  Train y:  mean={train_y.mean():.6f}, std={train_y.std():.6f}, min={train_y.min():.6f}, max={train_y.max():.6f}")
    logger.info(f"  Val X:    mean={val_X.mean():.6f}, std={val_X.std():.6f}, min={val_X.min():.6f}, max={val_X.max():.6f}")
    logger.info(f"  Val y:    mean={val_y.mean():.6f}, std={val_y.std():.6f}, min={val_y.min():.6f}, max={val_y.max():.6f}")

    if torch.isnan(train_X).any() or torch.isnan(train_y).any() or torch.isnan(val_X).any() or torch.isnan(val_y).any():
        logger.error("NaN detected in datasets — cannot train")
        return

    train_dataset_seq = SequenceDataset(train_seqs)
    val_dataset_seq   = SequenceDataset(val_seqs)

    # DataLoaders
    train_loader = DataLoader(
        train_dataset_seq,
        batch_size = args.batch_size,
        shuffle    = True,
        num_workers= 0,
        drop_last  = True,
    )
    val_loader = DataLoader(
        val_dataset_seq,
        batch_size = args.batch_size,
        shuffle    = False,
        num_workers= 0,
        drop_last  = False,
    )

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------
    sample_X, _ = train_seqs[0]
    input_dim = sample_X.shape[-1]
    logger.info(f"Input feature dimension: {input_dim}")

    model = TradingTCN(input_dim, model_cfg).to(device)
    logger.info(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

    # Check for NaNs in initial parameters (sanity)
    for name, p in model.named_parameters():
        if torch.isnan(p).any():
            logger.error(f"NaN in initial parameter {name} — aborting")
            return

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    # Cosine LR scheduler with linear warmup
    warmup_epochs = 3
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs - warmup_epochs, eta_min=args.lr * 0.01
    )

    # Loss selection
    loss_map = {
        'risk_adjusted': lambda r, risk, y: risk_adjusted_loss(r, risk, y, risk_penalty=args.risk_penalty),
        'pnl'         : lambda r, risk, y: pnl_loss(r, y, cost=0.0005),
        'sharpe'      : lambda r, risk, y: sharpe_loss(r, y),
    }
    loss_fn = loss_map[args.loss]

    # ------------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------------
    logger.info(f"Starting TradingTCN training — loss={args.loss}")
    best_sharpe = -float('inf')
    patience    = 8
    no_improve  = 0
    best_path   = None

    for epoch in range(args.epochs):
        # Linear warmup for first few epochs
        if epoch < warmup_epochs:
            lr_scale = (epoch + 1) / warmup_epochs
            for param_group in optimizer.param_groups:
                param_group['lr'] = args.lr * lr_scale

        train_loss = train_epoch(model, train_loader, optimizer, loss_fn, device)
        val_loss, val_pnl, val_sharpe = eval_epoch(model, val_loader, loss_fn, device)

        current_lr = optimizer.param_groups[0]['lr']
        logger.info(
            f"Epoch {epoch+1:3d}/{args.epochs}  "
            f"train_loss={train_loss:.6f}  "
            f"val_loss={val_loss:.6f}  "
            f"val_pnl={val_pnl:.6f}  "
            f"val_sharpe={val_sharpe:.3f}  "
            f"lr={current_lr:.2e}"
        )

        # Step scheduler after warmup
        if epoch >= warmup_epochs:
            scheduler.step()

        # Save best model by Sharpe
        if val_sharpe > best_sharpe + 1e-4:
            best_sharpe = val_sharpe
            no_improve  = 0
            os.makedirs('ml/models/trading_tcn', exist_ok=True)
            safe_sym = args.symbol.replace('/', '_')
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')
            best_path = f'ml/models/trading_tcn/trading_tcn_{safe_sym}_{timestamp}.pt'
            torch.save({
                'model_state_dict': model.state_dict(),
                'model_cfg'       : model_cfg,
                'epoch'           : epoch,
                'val_sharpe'      : val_sharpe,
                'val_pnl'         : val_pnl,
                'feat_mean'       : feat_median,
                'feat_std'        : feat_iqr_safe,
                'feat_mask'       : np.ones(train_vectors.shape[1], dtype=bool),
                'symbol'          : args.symbol,
                'horizon'         : args.horizon,
            }, best_path)
            logger.info(f"  ✓ New best model saved (Sharpe={val_sharpe:.3f})")
        else:
            no_improve += 1
            if no_improve >= patience:
                logger.info(f"Early stopping after {epoch+1} epochs")
                break

    logger.info(f"✅ Training complete — best val_sharpe={best_sharpe:.3f}  model={best_path}")
    logger.info(
        "Trade‑selection tip: at inference, score = pred_ret / (pred_risk + 1e-6) "
        "and take top‑K or threshold."
    )


if __name__ == "__main__":
    main()
