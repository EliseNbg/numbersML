#!/usr/bin/env python3
"""
Command-line TradingTCN backtest runner with detailed debug output.

Usage:
  python backtest_trading_tcn.py --symbol DASH/USDC --model trading_tcn_DASH_USDC_20260421_0509.pt --hours 24 --score-threshold 0.001 --debug
"""

import argparse
import logging
import time
import psutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import torch
import asyncpg

from ml.model import TradingTCN
from ml.config import ModelConfig
from src.infrastructure.database import get_db_pool_async, set_db_pool, _init_utc

# Database configuration
DATABASE_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_memory_usage():
    """Get current memory usage in MB."""
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024  # MB


async def run_backtest(args):
    """Run TradingTCN backtest with detailed logging."""
    start_time = time.time()
    logger.info(f"🚀 Starting TradingTCN backtest for {args.symbol}")
    logger.info(f"   Model: {args.model}")
    logger.info(f"   Hours: {args.hours}")
    logger.info(f"   Score threshold: {args.score_threshold}")
    logger.info(f"   Debug: {args.debug}")

    # Phase 1: Database setup
    phase_start = time.time()
    logger.info("📊 Phase 1: Database setup...")

    # Initialize database pool
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        timeout=30,
        init=_init_utc,
    )
    set_db_pool(db_pool)

    pool = await get_db_pool_async()

    # Determine time range from latest available data
    async with pool.acquire() as conn:
        latest_time_result = await conn.fetchrow("SELECT MAX(time) FROM wide_vectors")
        if latest_time_result and latest_time_result['max']:
            latest_time = latest_time_result['max']
            logger.info(f"   Latest data timepoint: {latest_time}")
        else:
            logger.error("No wide_vectors data found")
            return

    db_start_time = latest_time - timedelta(hours=args.hours)
    db_end_time = latest_time
    logger.info(f"   Backtest time range: {db_start_time} to {db_end_time}")
    logger.info(f"   Duration: {args.hours} hours")

    phase_time = time.time() - phase_start
    logger.info(f"   Phase time: {phase_time:.3f}s")

    # Phase 2: Load data
    phase_start = time.time()
    logger.info("📊 Phase 2: Loading data...")

    async with pool.acquire() as conn:
        # Get candles
        logger.info("   Loading candles..." if args.debug else "")
        candle_query_start = time.time()
        candles = await conn.fetch("""
            SELECT time, close FROM candles_1s
            WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = $1)
            AND time >= $2 AND time < $3
            ORDER BY time ASC
        """, args.symbol, db_start_time, db_end_time)

        candle_time = time.time() - candle_query_start
        logger.info(f"   Candle query time: {candle_time:.3f}s")
        logger.info(f"   Candles loaded: {len(candles)}" if args.debug else "")

        if not candles:
            logger.error("No candle data found!")
            return

        # Convert to arrays
        closes = np.array([float(r['close']) for r in candles])
        timestamps = np.array([int(r['time'].timestamp()) for r in candles])

        # Load wide vectors
        logger.info("   Loading wide vectors..." if args.debug else "")
        vector_query_start = time.time()
        vector_rows = await conn.fetch("""
            SELECT time, vector FROM wide_vectors
            WHERE time >= $1 AND time < $2
            ORDER BY time ASC
        """, db_start_time, db_end_time)

        vector_time = time.time() - vector_query_start
        logger.info(f"   Vector query time: {vector_time:.3f}s")
        logger.info(f"   Vectors loaded: {len(vector_rows)}" if args.debug else "")

    phase_time = time.time() - phase_start
    logger.info(f"   Phase time: {phase_time:.3f}s")
    logger.info(f"   Memory usage: {get_memory_usage():.1f} MB")

    # Phase 3: Process wide vectors
    phase_start = time.time()
    logger.info("📊 Phase 3: Processing wide vectors...")

    vectors = []
    for i, row in enumerate(vector_rows):
        if args.debug and i % 1000 == 0:
            logger.info(f"   Processing vector {i}/{len(vector_rows)}...")

        import json
        if isinstance(row['vector'], str):
            vec = np.array(json.loads(row['vector']), dtype=np.float32)
        else:
            vec = np.array(row['vector'], dtype=np.float32)

        # Sanitize NaN values
        if np.isnan(vec).any():
            vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)

        vectors.append(vec)

    vectors = np.array(vectors)
    logger.info(f"   Vectors shape: {vectors.shape}")
    logger.info(f"   Memory usage: {get_memory_usage():.1f} MB")

    phase_time = time.time() - phase_start
    logger.info(f"   Phase time: {phase_time:.3f}s")

    # Phase 4: Load model
    phase_start = time.time()
    logger.info("📊 Phase 4: Loading TradingTCN model...")

    if Path(args.model).is_absolute() or '/' in args.model:
        model_path = Path(args.model)
    else:
        model_path = Path('ml/models/trading_tcn') / args.model
    if not model_path.exists():
        logger.error(f"Model file not found: {model_path}")
        return

    logger.info(f"   Loading from: {model_path}")

    # Load checkpoint
    checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)

    # Reconstruct model
    cfg = checkpoint.get('model_cfg', ModelConfig())
    cfg.hidden_dims = [128]
    cfg.dropout = 0.2
    cfg.trading_tcn_blocks = 8

    model = TradingTCN(vectors.shape[1], cfg)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()

    logger.info(f"   Model loaded: {sum(p.numel() for p in model.parameters()):,} parameters")

    # Apply training normalization if available
    if 'feat_mean' in checkpoint and 'feat_std' in checkpoint:
        feat_mean = checkpoint['feat_mean']
        feat_std = checkpoint['feat_std']
        vectors = (vectors - feat_mean) / feat_std
        logger.info(f"   Applied training normalization (mean shape: {feat_mean.shape})")
    else:
        logger.warning("   No normalization stats in checkpoint — using raw vectors (model may not generalize)")

    phase_time = time.time() - phase_start
    logger.info(f"   Phase time: {phase_time:.3f}s")
    logger.info(f"   Memory usage: {get_memory_usage():.1f} MB")

    # Phase 5: Create sequences and run inference
    phase_start = time.time()
    logger.info("📊 Phase 5: Creating sequences and running inference...")

    seq_length = 120
    stride = 1

    logger.info(f"   Sequence length: {seq_length}")
    logger.info(f"   Stride: {stride}")

    # For backtest, we need to align with available data
    max_start_idx = len(vectors) - seq_length
    if max_start_idx <= 0:
        logger.error(f"Not enough data for sequences. Need at least {seq_length} samples, got {len(vectors)}")
        return

    predictions_ret = []
    predictions_risk = []
    inference_times = []

    with torch.no_grad():
        for i in range(0, max_start_idx, stride):
            # Create sequence
            seq = vectors[i:i+seq_length]
            seq_tensor = torch.from_numpy(seq).unsqueeze(0).float()  # Add batch dim

            if args.debug and i % 50 == 0:
                logger.info(f"   Processing sequence {i+1}...")

            # Run inference
            batch_start = time.time()
            pred_ret, pred_risk = model(seq_tensor)
            batch_time = time.time() - batch_start

            predictions_ret.append(pred_ret.item())
            predictions_risk.append(pred_risk.item())
            inference_times.append(batch_time)

    # Align predictions with timestamps
    predictions_ret = np.array(predictions_ret)
    predictions_risk = np.array(predictions_risk)

    # Create aligned arrays (predictions correspond to timestamps[seq_length::stride])
    aligned_timestamps = timestamps[seq_length::stride][:len(predictions_ret)]
    aligned_closes = closes[seq_length::stride][:len(predictions_ret)]

    n_common = min(len(predictions_ret), len(aligned_timestamps), len(aligned_closes))
    if n_common < len(predictions_ret):
        logger.warning(
            f"   Data mismatch: predictions={len(predictions_ret)}, "
            f"timestamps={len(aligned_timestamps)}, closes={len(aligned_closes)}. "
            f"Truncating to {n_common}."
        )
        predictions_ret = predictions_ret[:n_common]
        predictions_risk = predictions_risk[:n_common]
        aligned_timestamps = aligned_timestamps[:n_common]
        aligned_closes = aligned_closes[:n_common]

    logger.info(f"   Predictions shape: ret={predictions_ret.shape}, risk={predictions_risk.shape}")
    logger.info(f"   Average inference time: {np.mean(inference_times):.3f}s per batch")

    phase_time = time.time() - phase_start
    logger.info(f"   Phase time: {phase_time:.3f}s")

    # Phase 6: Calculate scores and simulate trading
    phase_start = time.time()
    logger.info("📊 Phase 6: Simulating trading...")

    scores = predictions_ret / (predictions_risk + 1e-6)

    logger.info(f"   Score range: min={scores.min():.6f}, max={scores.max():.6f}")
    logger.info(f"   Score threshold: {args.score_threshold}")

    # Diagnostics: score distribution
    pctiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    score_pct = np.percentile(scores, pctiles)
    for p, v in zip(pctiles, score_pct):
        logger.info(f"   Score p{p}: {v:.6f}")

    above_threshold = (scores >= args.score_threshold).sum()
    positive_ret = (predictions_ret > 0).sum()
    logger.info(f"   Scores >= threshold: {above_threshold}/{len(scores)}")
    logger.info(f"   Positive pred_ret: {positive_ret}/{len(predictions_ret)}")
    logger.info(f"   Pred_ret range: min={predictions_ret.min():.6f}, max={predictions_ret.max():.6f}")
    logger.info(f"   Pred_risk range: min={predictions_risk.min():.6f}, max={predictions_risk.max():.6f}")

    # Simulate trading
    trades = []
    position = 0
    entry_price = 0.0
    entry_time = 0
    missed_due_to_position = 0
    missed_due_to_low_score = 0

    for i in range(len(scores)):
        current_price = aligned_closes[i]
        current_time = aligned_timestamps[i]
        score = scores[i]

        # ENTER LONG POSITION
        if score >= args.score_threshold and position == 0:
            position = 1
            entry_price = current_price
            entry_time = current_time
        elif score >= args.score_threshold and position == 1:
            missed_due_to_position += 1
        elif score < args.score_threshold and position == 0:
            missed_due_to_low_score += 1

        # EXIT POSITION after fixed time (10 minutes = 600 seconds)
        if position == 1 and (current_time - entry_time >= 600 or i == len(scores)-1):
            position = 0
            pnl = (current_price - entry_price) / entry_price - 0.002  # minus fees

            trades.append({
                'entry_time': int(entry_time),
                'exit_time': int(current_time),
                'entry_price': float(entry_price),
                'exit_price': float(current_price),
                'pnl': float(pnl),
                'duration': int(current_time - entry_time),
                'score': float(score)
            })

    logger.info(f"   Simulated {len(trades)} trades")
    logger.info(f"   Missed entries (score high, in position): {missed_due_to_position}")
    logger.info(f"   Missed entries (score low, flat): {missed_due_to_low_score}")

    phase_time = time.time() - phase_start
    logger.info(f"   Phase time: {phase_time:.3f}s")

    # Phase 7: Calculate metrics
    phase_start = time.time()
    logger.info("📊 Phase 7: Calculating metrics...")

    if trades:
        wins = sum(1 for t in trades if t['pnl'] > 0)
        win_rate = wins / len(trades)
        total_return = sum(t['pnl'] for t in trades)

        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        avg_duration = sum(t['duration'] for t in trades) / len(trades)
    else:
        win_rate = total_return = profit_factor = avg_duration = 0.0

    phase_time = time.time() - phase_start
    logger.info(f"   Phase time: {phase_time:.3f}s")

    # Final summary
    total_time = time.time() - start_time
    logger.info("🎉 BACKTEST COMPLETE")
    logger.info(f"   Total runtime: {total_time:.1f}s")
    logger.info(f"   Total trades: {len(trades)}")
    logger.info(f"   Win rate: {win_rate:.1f}%")
    logger.info(f"   Total return: {total_return:.3f}")
    logger.info(f"   Profit factor: {profit_factor:.3f}")
    logger.info(f"   Avg duration: {avg_duration/60:.1f} min")

    # Show sample trades
    if trades and args.debug:
        logger.info("   Sample trades:")
        for i, trade in enumerate(trades[:3]):
            logger.info(f"     {i+1}: PnL={trade['pnl']*100:.2f}%, Score={trade['score']:.4f}, Duration={trade['duration']/60:.1f}min")

    await pool.close()


def main():
    parser = argparse.ArgumentParser(description='Run TradingTCN backtest with detailed debugging')
    parser.add_argument('--symbol', type=str, required=True, help='Trading symbol (e.g., DASH/USDC)')
    parser.add_argument('--model', type=str, required=True, help='Model filename')
    parser.add_argument('--hours', type=int, default=24, help='Hours of historical data to backtest from the latest available timepoint')
    parser.add_argument('--score-threshold', type=float, default=0.001, help='Risk-adjusted score threshold')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debug output')
    parser.add_argument('--batch-size', type=int, default=64, help='Inference batch size')

    args = parser.parse_args()

    # Run async backtest
    import asyncio
    asyncio.run(run_backtest(args))


if __name__ == "__main__":
    main()