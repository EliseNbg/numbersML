#!/usr/bin/env python3
"""
Training script for Entry Point Classification Model.

Run:
  python train_entry_model.py --symbol BTC/USDC --hours 720
"""

import argparse
import logging
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


def main():
    parser = argparse.ArgumentParser(description='Train Entry Point Classification Model')
    parser.add_argument('--symbol', type=str, default='BTC/USDC', help='Target symbol')
    parser.add_argument('--hours', type=int, default=720, help='Train on last N hours')
    parser.add_argument('--profit', type=float, default=0.06, help='Profit target (0.06 = 6.0%)')
    parser.add_argument('--stop', type=float, default=0.0035, help='Stop loss (0.0035 = 0.35%)')
    parser.add_argument('--lookahead', type=int, default=28800, help='Look ahead bars')
    parser.add_argument('--output', type=str, help='Output model path (auto generated if not set)')

    args = parser.parse_args()

    db_config = DatabaseConfig()
    data_config = DataConfig()
    data_config.target_symbol = args.symbol
    data_config.train_hours = args.hours

    logger.info(f"Starting Entry Point Model training:")
    logger.info(f"  Symbol: {args.symbol}")
    logger.info(f"  Training window: {args.hours} hours")
    logger.info(f"  Profit target: {args.profit*100:.2f}%")
    logger.info(f"  Stop loss: {args.stop*100:.2f}%")
    logger.info(f"  Look ahead: {args.lookahead/60:.1f} minutes")

    # Calculate time ranges
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=args.hours)

    # Load full dataset
    dataset = EntryPointDataset(
        db_config=db_config,
        data_config=data_config,
        start_time=start_time,
        end_time=end_time,
        profit_target=args.profit,
        stop_loss=args.stop,
        look_ahead=args.lookahead,
        balance_classes=True,
        sequence_length=data_config.sequence_length
    )

    # Time based split (80% train, 20% val)
    split_idx = int(len(dataset) * 0.8)

    X = np.vstack(dataset.vectors)
    y = np.array(dataset.targets)

    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    # Train model
    model = EntryPointModel()
    metrics = model.train(X_train, y_train, X_val, y_val)

    # Auto generate model filename with symbol and date if not provided
    if not args.output:
        safe_symbol = args.symbol.replace('/', '_')
        profit_val = int(round(args.profit * 10000))
        stop_val = int(round(args.stop * 10000))
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')
        args.output = f'entry_model_{safe_symbol}_p{profit_val}_s{stop_val}_{timestamp}.pkl'

    # Save model
    model.save(args.output)
    logger.info(f"Model saved to: {args.output}")

    logger.info("Training complete!")


if __name__ == "__main__":
    main()
