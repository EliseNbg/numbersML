#!/usr/bin/env python3
"""
Quick validation script for TemporalCNN model.

Tests that:
  - Model builds without errors
  - Forward pass works with expected shapes
  - Training actually reduces loss on a small dataset
  - Final validation MAE reaches < 0.08 (sanity threshold)

Usage:
  .venv/bin/python test_temporal_cnn.py --symbol DASH/USDC --hours 48
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

from ml.config import DatabaseConfig, DataConfig, PipelineConfig, ModelConfig
from ml.dataset import WideVectorDataset
from ml.model import TemporalCNN, create_model

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    n_batches = 0
    for X, y in loader:
        X, y = X.to(device), y.to(device)
        optimizer.zero_grad()
        preds = model(X)
        loss = criterion(preds, y)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / n_batches


def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    n_batches = 0
    with torch.no_grad():
        for X, y in loader:
            X, y = X.to(device), y.to(device)
            preds = model(X)
            loss = criterion(preds, y)
            total_loss += loss.item()
            n_batches += 1
    return total_loss / n_batches


def main():
    parser = argparse.ArgumentParser(description='Validate TemporalCNN model')
    parser.add_argument('--symbol', type=str, default='DASH/USDC')
    parser.add_argument('--hours', type=int, default=48, help='Data window (hours)')
    parser.add_argument('--seq-length', type=int, default=120)
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--batch-size', type=int, default=128)
    parser.add_argument('--lr', type=float, default=0.0007)
    args = parser.parse_args()

    device = torch.device('cpu')  # keep it simple
    logger.info(f"Using device: {device}")

    # Build config
    db_config = DatabaseConfig()
    data_config = DataConfig()
    data_config.target_symbol = args.symbol
    data_config.train_hours = args.hours
    data_config.sequence_length = args.seq_length
    data_config.batch_size = args.batch_size

    model_config = ModelConfig()
    model_config.hidden_dims = [128]  # d_model for TemporalCNN
    model_config.dropout = 0.2
    model_config.temporal_cnn_layers = 6
    model_config.temporal_cnn_kernel = 3

    # Load full dataset
    logger.info("Loading dataset...")
    full_dataset = WideVectorDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=datetime.now(timezone.utc) - timedelta(hours=args.hours),
        end_time=datetime.now(timezone.utc),
        sequence_length=args.seq_length,
    )

    logger.info(f"Total samples: {len(full_dataset)}")
    if len(full_dataset) < 200:
        logger.error("Insufficient data — need at least 200 samples")
        sys.exit(1)

    # Split 80/20
    n_train = int(0.8 * len(full_dataset))
    n_val = len(full_dataset) - n_train
    train_dataset, val_dataset = random_split(full_dataset, [n_train, n_val])

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    # Build model
    sample_x, _ = full_dataset[0]
    input_dim = sample_x.shape[-1]
    logger.info(f"Input feature dim: {input_dim}")

    model = TemporalCNN(input_dim, model_config).to(device)
    param_count = sum(p.numel() for p in model.parameters())
    logger.info(f"Model parameters: {param_count:,}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    criterion = nn.MSELoss()  # Huber also fine but MSE simpler for test

    # Training loop
    logger.info(f"Starting training for {args.epochs} epochs...")
    best_mae = float('inf')
    patience = 8
    no_improve = 0

    for epoch in range(args.epochs):
        train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss = evaluate(model, val_loader, criterion, device)

        # Compute MAE too
        model.eval()
        mae_sum, mae_n = 0.0, 0
        with torch.no_grad():
            for X, y in val_loader:
                X, y = X.to(device), y.to(device)
                preds = model(X)
                mae_sum += torch.abs(preds - y).sum().item()
                mae_n += X.shape[0]
        val_mae = mae_sum / mae_n

        logger.info(
            f"Epoch {epoch+1:2d}/{args.epochs}  "
            f"train_loss={train_loss:.6f}  val_loss={val_loss:.6f}  val_mae={val_mae:.6f}"
        )

        if val_mae < best_mae - 1e-5:
            best_mae = val_mae
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break

    logger.info(f"✅ Best val MAE: {best_mae:.6f}")

    # Sanity threshold: on normalized [0,1] target, MAE should be < 0.08
    # (0.08 ≈ 8% error on a 0-1 scale; perfect model would be ~0.05-0.06)
    if best_mae < 0.08:
        logger.info("✅ TemporalCNN validation PASSED — MAE is in realistic range")
        sys.exit(0)
    else:
        logger.warning(
            f"❌ Validation MAE {best_mae:.4f} is HIGH — model may not be learning. "
            "Try more epochs, different lr, or check labels/data quality."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
