#!/usr/bin/env python3
"""
Recalculation CLI for indicators and wide vectors.

Resets the `processed` flag on candles_1s and recalculates indicators
and/or wide vectors for the specified time range.

Usage:
    # Reset processed flag for last hour
    python3 -m src.cli.recalculate --reset --from "2026-03-29 00:00:00" --to "2026-03-29 01:00:00"

    # Recalculate indicators only
    python3 -m src.cli.recalculate --indicators --from "2026-03-29 00:00:00"

    # Full recalculation (indicators + wide vectors)
    python3 -m src.cli.recalculate --all --from "2026-03-29 00:00:00" --to "2026-03-29 01:00:00"

    # Recalculate specific symbols
    python3 -m src.cli.recalculate --all --symbols "BTC/USDC,ETH/USDC"
"""

import argparse
import asyncio
import asyncpg
import logging
import sys
from datetime import datetime, timezone
from typing import List, Optional, Tuple

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


async def reset_processed(
    conn: asyncpg.Connection,
    symbol_ids: List[int],
    from_time: datetime,
    to_time: Optional[datetime],
) -> int:
    """Reset processed flag for candles in time range."""
    if to_time:
        result = await conn.execute(
            """
            UPDATE candles_1s SET processed = false
            WHERE symbol_id = ANY($1) AND time >= $2 AND time <= $3
            """,
            symbol_ids, from_time, to_time,
        )
    else:
        result = await conn.execute(
            """
            UPDATE candles_1s SET processed = false
            WHERE symbol_id = ANY($1) AND time >= $2
            """,
            symbol_ids, from_time,
        )
    count = int(result.split()[-1])
    return count


async def recalculate_indicators(
    db_pool: asyncpg.Pool,
    symbol_ids: List[int],
    from_time: datetime,
    to_time: Optional[datetime],
) -> int:
    """Recalculate indicators for unprocessed candles."""
    from src.pipeline.indicator_calculator import IndicatorCalculator

    calc = IndicatorCalculator(db_pool)
    await calc.load_definitions()

    async with db_pool.acquire() as conn:
        if to_time:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (c.symbol_id, c.time)
                    c.symbol_id, s.symbol, c.time, c.open, c.high, c.low, c.close, c.volume
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE c.symbol_id = ANY($1) AND c.processed = false
                  AND c.time >= $2 AND c.time <= $3
                ORDER BY c.symbol_id, c.time
                """,
                symbol_ids, from_time, to_time,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (c.symbol_id, c.time)
                    c.symbol_id, s.symbol, c.time, c.open, c.high, c.low, c.close, c.volume
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE c.symbol_id = ANY($1) AND c.processed = false
                  AND c.time >= $2
                ORDER BY c.symbol_id, c.time
                """,
                symbol_ids, from_time,
            )

    count = 0
    for r in rows:
        try:
            await calc.calculate_with_candle(
                symbol=r['symbol'],
                time=r['time'],
                open=float(r['open']),
                high=float(r['high']),
                low=float(r['low']),
                close=float(r['close']),
                volume=float(r['volume']),
                symbol_id=r['symbol_id'],
            )
            count += 1
            if count % 100 == 0:
                logger.info(f"Recalculated {count} candles...")
        except Exception as e:
            logger.error(f"Error on {r['symbol']} {r['time']}: {e}")

    return count


async def recalculate_wide_vectors(
    db_pool: asyncpg.Pool,
    symbol_ids: List[int],
    from_time: datetime,
    to_time: Optional[datetime],
) -> int:
    """Regenerate wide vectors for unprocessed candles."""
    from src.pipeline.wide_vector_service import WideVectorService

    service = WideVectorService(db_pool)
    await service.load_symbols()

    async with db_pool.acquire() as conn:
        if to_time:
            times = await conn.fetch(
                """
                SELECT DISTINCT time FROM candles_1s
                WHERE symbol_id = ANY($1) AND processed = false
                  AND time >= $2 AND time <= $3
                ORDER BY time
                """,
                symbol_ids, from_time, to_time,
            )
        else:
            times = await conn.fetch(
                """
                SELECT DISTINCT time FROM candles_1s
                WHERE symbol_id = ANY($1) AND processed = false
                  AND time >= $2
                ORDER BY time
                """,
                symbol_ids, from_time,
            )

    count = 0
    for t in times:
        try:
            result = await service.generate(t['time'])
            if result:
                count += 1
            if count % 100 == 0:
                logger.info(f"Generated {count} wide vectors...")
        except Exception as e:
            logger.error(f"Error on {t['time']}: {e}")

    return count


async def main() -> None:
    parser = argparse.ArgumentParser(description="Recalculate indicators and wide vectors")
    parser.add_argument('--reset', action='store_true', help='Reset processed flag')
    parser.add_argument('--indicators', action='store_true', help='Recalculate indicators')
    parser.add_argument('--vectors', action='store_true', help='Recalculate wide vectors')
    parser.add_argument('--all', action='store_true', help='Reset + indicators + vectors')
    parser.add_argument('--from', dest='from_time', required=True,
                        help='Start time (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--to', dest='to_time', default=None,
                        help='End time (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--symbols', dest='symbols', default=None,
                        help='Comma-separated symbol list (e.g., BTC/USDC,ETH/USDC)')

    args = parser.parse_args()

    from_time = datetime.strptime(args.from_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    to_time = None
    if args.to_time:
        to_time = datetime.strptime(args.to_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)

    symbols = [s.strip() for s in args.symbols.split(',')] if args.symbols else None

    if args.all:
        args.reset = True
        args.indicators = True
        args.vectors = True

    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)

    async with pool.acquire() as conn:
        symbol_ids = await get_symbol_ids(conn, symbols)
        logger.info(f"Processing {len(symbol_ids)} symbols, from={from_time}, to={to_time}")

    if args.reset:
        async with pool.acquire() as conn:
            count = await reset_processed(conn, symbol_ids, from_time, to_time)
            logger.info(f"Reset {count} candles' processed flag")

    if args.indicators:
        logger.info("Recalculating indicators...")
        count = await recalculate_indicators(pool, symbol_ids, from_time, to_time)
        logger.info(f"Recalculated {count} indicators")

    if args.vectors:
        logger.info("Recalculating wide vectors...")
        count = await recalculate_wide_vectors(pool, symbol_ids, from_time, to_time)
        logger.info(f"Generated {count} wide vectors")

    if not args.reset and not args.indicators and not args.vectors:
        logger.error("No action specified. Use --reset, --indicators, --vectors, or --all")
        sys.exit(1)

    await pool.close()
    logger.info("Done")


if __name__ == '__main__':
    asyncio.run(main())
