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
    # Time window with gap protection
    # ------------------------------------------------------------------
    gap_seconds = args.stride * 2  # conservative gap between val/train
    total_seconds = int(args.hours * 3600)
    usable_seconds = total_seconds - gap_seconds
    val_seconds = int(usable_seconds * args.val_frac)
    train_seconds = usable_seconds - val_seconds

    end_time   = datetime.now(timezone.utc)
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
    model_cfg.dropout             = 0.2
    model_cfg.trading_tcn_blocks  = 8
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
    logger.info("Fitting feature normalizer on training set...")
    train_vectors = np.stack(train_dataset.vectors)  # (n_samples, feat_dim)
    feat_mean = train_vectors.mean(axis=0, keepdims=True).astype(np.float32)
    feat_std  = train_vectors.std(axis=0, keepdims=True).astype(np.float32) + 1e-8
    feat_mask = np.ones(train_vectors.shape[1], dtype=bool)

    # Normalize training vectors in-place
    train_vectors_norm = (train_vectors - feat_mean) / feat_std
    train_dataset.vectors = [train_vectors_norm[i] for i in range(len(train_vectors_norm))]
    train_dataset.mean = feat_mean
    train_dataset.std  = feat_std
    train_dataset.feature_mask = feat_mask
    logger.info(f"  Feature mean: {feat_mean.mean():.4f}, std: {feat_std.mean():.4f}")

    # ── Validation dataset — reuse training scaler (no leakage) ───────
    val_dataset = TradingDataset(
        db_config         = DatabaseConfig(),
        data_config       = DataConfig(target_symbol=args.symbol, prediction_horizon=args.horizon),
        start_time        = val_start,
        end_time          = val_end,
        sequence_length   = 1,
        normalize_returns = args.normalize_returns,
        clip_returns      = args.clip_returns,
        return_stride     = args.stride,
        mean              = feat_mean,   # ← reuse training statistics
        std               = feat_std,
        feature_mask      = feat_mask,
    )

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

    # Loss selection
    loss_map = {
        'risk_adjusted': lambda r, risk, y: risk_adjusted_loss(r, risk, y, risk_penalty=0.1),
        'pnl'         : lambda r, risk, y: pnl_loss(r, y, cost=0.0005),
        'sharpe'      : lambda r, risk, y: sharpe_loss(r, y),
    }
    loss_fn = loss_map[args.loss]

    # ------------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------------
    logger.info(f"Starting TradingTCN training — loss={args.loss}")
    best_sharpe = -float('inf')
    patience    = 10
    no_improve  = 0
    best_path   = None

    for epoch in range(args.epochs):
        train_loss = train_epoch(model, train_loader, optimizer, loss_fn, device)
        val_loss, val_pnl, val_sharpe = eval_epoch(model, val_loader, loss_fn, device)

        logger.info(
            f"Epoch {epoch+1:3d}/{args.epochs}  "
            f"train_loss={train_loss:.6f}  "
            f"val_loss={val_loss:.6f}  "
            f"val_pnl={val_pnl:.6f}  "
            f"val_sharpe={val_sharpe:.3f}"
        )

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
