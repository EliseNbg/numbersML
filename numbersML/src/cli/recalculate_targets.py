#!/usr/bin/env python3
"""
Recalculate target values for all candles with new JSONB structure.

This script:
1. Loads all candles for each symbol
2. Runs Kalman filter on the full history
3. Updates target_value column with rich JSONB structure:
   {
       "filtered_value": 105.5,       // Smooth Kalman trend (WAVES)
       "close": 103.2,                // Current candle close
       "diff": -2.3,                  // Deviation from trend
       "trend": "up",                 // or "down", "flat"
       "velocity": 0.15,              // Rate of change (trend direction)
       "normalized_value": 0.65,      // Local normalized [0..1] - ML target
       "norm_min": 99.5,              // Local min for normalization
       "norm_max": 101.8              // Local max for normalization
   }

Usage:
    # Recalculate all symbols
    python3 -m src.cli.recalculate_targets --all

    # Recalculate specific symbols
    python3 -m src.cli.recalculate_targets --symbols "BTC/USDC,ETH/USDC"

    # Recalculate last 24 hours only
    python3 -m src.cli.recalculate_targets --hours 24

    # Dry run (show what would be updated)
    python3 -m src.cli.recalculate_targets --all --dry-run
"""

import argparse
import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np

from src.pipeline.target_value import batch_calculate_target_data

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


async def get_symbol_ids(
    conn: asyncpg.Connection,
    symbols: Optional[List[str]],
) -> List[int]:
    """Get symbol IDs from names or all active."""
    if symbols:
        rows = await conn.fetch(
            "SELECT id FROM symbols WHERE symbol = ANY($1) AND is_active = true",
            symbols,
        )
    else:
        rows = await conn.fetch(
            "SELECT id FROM symbols WHERE is_active = true AND is_allowed = true",
        )
    return [r['id'] for r in rows]


async def recalculate_targets(
    db_pool: asyncpg.Pool,
    symbol_ids: List[int],
    hours: Optional[int] = None,
    dry_run: bool = False,
    response_time: float = 200.0,
) -> dict:
    """
    Recalculate target values with JSONB structure.
    
    Args:
        db_pool: Database connection pool
        symbol_ids: List of symbol IDs to process
        hours: Only update last N hours (uses full history for Kalman)
        dry_run: If True, only show statistics without updating
        response_time: Kalman response time in samples
    
    Returns:
        Dictionary with processing statistics
    """
    from src.pipeline.target_value import batch_calculate_target_data
    
    total_updated = 0
    total_processed = 0
    trend_counts = {'up': 0, 'down': 0, 'flat': 0, 'unknown': 0}
    
    async with db_pool.acquire() as conn:
        # Get symbol info
        sym_rows = await conn.fetch(
            "SELECT id, symbol FROM symbols WHERE id = ANY($1) ORDER BY id",
            symbol_ids,
        )
        
        for sym_row in sym_rows:
            sid = sym_row['id']
            sname = sym_row['symbol']
            
            # Determine time range
            now = datetime.now(timezone.utc)
            if hours is not None:
                from_dt = now - timedelta(hours=hours)
            else:
                from_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
            
            # Load ALL candles (needed for Kalman continuity)
            all_candles = await conn.fetch(
                """
                SELECT time, close
                FROM candles_1s
                WHERE symbol_id = $1
                ORDER BY time
                """,
                sid,
            )
            
            if not all_candles:
                logger.warning(f"No candles for {sname}")
                continue
            
            logger.info(f"Processing {sname}: {len(all_candles)} candles total")
            
            # Calculate target data for ALL candles
            prices = [float(c['close']) for c in all_candles]
            target_data_list = batch_calculate_target_data(
                prices, response_time=response_time, use_kalman=True
            )
            
            # Update only candles in the time range
            batch = []
            for i, (candle, target_data) in enumerate(zip(all_candles, target_data_list)):
                if candle['time'] >= from_dt and target_data is not None:
                    batch.append((json.dumps(target_data), candle['time']))
                    
                    # Count trends
                    trend_counts[target_data.get('trend', 'unknown')] = \
                        trend_counts.get(target_data.get('trend', 'unknown'), 0) + 1
            
            if dry_run:
                logger.info(f"  {sname}: Would update {len(batch)} candles")
                total_updated += len(batch)
            else:
                # Update in batches of 5000
                batch_size = 5000
                for i in range(0, len(batch), batch_size):
                    sub_batch = batch[i:i+batch_size]
                    await conn.executemany(
                        """
                        UPDATE candles_1s SET target_value = $1::jsonb
                        WHERE symbol_id = $2 AND time = $3
                        """,
                        [(b[0], sid, b[1]) for b in sub_batch],
                    )
                logger.info(f"  {sname}: Updated {len(batch)} candles")
                total_updated += len(batch)
            
            total_processed += len(all_candles)
    
    return {
        'total_processed': total_processed,
        'total_updated': total_updated,
        'trend_counts': trend_counts,
        'dry_run': dry_run,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Recalculate target values with JSONB structure")
    parser.add_argument('--all', action='store_true', help='Process all active symbols')
    parser.add_argument('--symbols', dest='symbols', default=None,
                        help='Comma-separated symbol list (e.g., BTC/USDC,ETH/USDC)')
    parser.add_argument('--hours', type=int, default=None,
                        help='Only update last N hours (default: all)')
    parser.add_argument('--response-time', type=float, default=200.0,
                        help='Kalman response time in samples (default: 200)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be updated without making changes')
    
    args = parser.parse_args()
    
    if not args.all and not args.symbols:
        parser.error("Must specify --all or --symbols")
    
    symbols = [s.strip() for s in args.symbols.split(',')] if args.symbols else None
    
    async def _set_utc(conn):
        await conn.execute("SET timezone = 'UTC'")
    
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5, init=_set_utc)
    
    try:
        async with pool.acquire() as conn:
            symbol_ids = await get_symbol_ids(conn, symbols)
            logger.info(f"Processing {len(symbol_ids)} symbols")
            if args.dry_run:
                logger.info("DRY RUN - no changes will be made")
        
        result = await recalculate_targets(
            pool,
            symbol_ids,
            hours=args.hours,
            dry_run=args.dry_run,
            response_time=args.response_time,
        )
        
        logger.info("\n" + "="*60)
        logger.info("RECALCULATION SUMMARY")
        logger.info("="*60)
        logger.info(f"Total candles processed: {result['total_processed']:,}")
        logger.info(f"Total candles updated:   {result['total_updated']:,}")
        logger.info(f"Dry run:                 {result['dry_run']}")
        logger.info(f"\nTrend distribution:")
        for trend, count in result['trend_counts'].items():
            if count > 0:
                logger.info(f"  {trend.upper():8s}: {count:,} ({100*count/result['total_updated']:.1f}%)")
        logger.info("="*60)
        
        if result['dry_run']:
            logger.info("\nTo actually update, remove the --dry-run flag")
    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
