#!/usr/bin/env python3
"""
Count valid entry points for given symbol and time window.
"""

import argparse
import logging
import numpy as np
from datetime import datetime, timedelta, timezone

from ml.entry_labeling import label_entry_points
from ml.dataset import WideVectorDataset
from ml.config import DatabaseConfig, DataConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Count valid entry points for symbol')
    parser.add_argument('--symbol', type=str, default='DASH/USDC', help='Target symbol')
    parser.add_argument('--hours', type=int, default=160, help='Analyze last N hours')
    parser.add_argument('--profit', type=float, default=0.009, help='Profit target')
    parser.add_argument('--stop', type=float, default=0.007, help='Stop loss')
    parser.add_argument('--lookahead', type=int, default=3600, help='Look ahead bars')

    args = parser.parse_args()

    db_config = DatabaseConfig()
    data_config = DataConfig()
    data_config.target_symbol = args.symbol

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=args.hours)

    logger.info(f"Analyzing entry points for {args.symbol}")
    logger.info(f"  Time window: {args.hours} hours")
    logger.info(f"  Profit target: {args.profit*100:.2f}%")
    logger.info(f"  Stop loss: {args.stop*100:.2f}%")
    logger.info(f"  Look ahead: {args.lookahead/60:.1f} minutes")
    logger.info("")

    # Load dataset
    dataset = WideVectorDataset(db_config, data_config, start_time, end_time)

    # Extract closes manually from dataset
    conn = dataset.db_config.connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT close FROM candles_1s
        WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = %s)
          AND time >= %s AND time <= %s
        ORDER BY time ASC
    """, (args.symbol, start_time, end_time))
    closes = np.array([float(row[0]) for row in cur.fetchall()])
    conn.close()

    logger.info(f'Loaded {len(closes)} candles')
    logger.info("")

    # Calculate labels
    labels, scores = label_entry_points(
        closes,
        profit_target=args.profit,
        stop_loss=args.stop,
        look_ahead=args.lookahead
    )

    valid = np.sum(labels != -1)
    good = np.sum(labels == 1)
    bad = np.sum(labels == 0)

    logger.info("=" * 50)
    logger.info("ENTRY POINT STATISTICS:")
    logger.info("=" * 50)
    logger.info(f"  Total valid points: {valid:7d}")
    logger.info(f"  ✅ Good entries:     {good:7d}")
    logger.info(f"  ❌ Bad entries:      {bad:7d}")
    logger.info("")
    logger.info(f"  Win rate:            {good/valid*100:.1f}%")
    logger.info(f"  Entries per hour:    {good/args.hours:.1f}")
    logger.info(f"  One entry every:     {args.hours*3600 / good / 60:.1f} minutes on average")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
