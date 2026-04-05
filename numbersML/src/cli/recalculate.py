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
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
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
    """
    Recalculate indicators for unprocessed candles.

    Uses sliding window approach: loads all candles per symbol into memory,
    maintains a 200-candle window, and calculates indicators for each candle
    without repeated DB queries.
    """
    import numpy as np
    from src.pipeline.indicator_calculator import IndicatorCalculator

    calc = IndicatorCalculator(db_pool)
    await calc.load_definitions()

    total_count = 0

    async with db_pool.acquire() as conn:
        # Get symbol info
        sym_rows = await conn.fetch(
            "SELECT id, symbol FROM symbols WHERE id = ANY($1) ORDER BY id",
            symbol_ids,
        )

        for sym_row in sym_rows:
            sid = sym_row['id']
            sname = sym_row['symbol']

            # Load ALL candles for this symbol (including history for indicator window)
            history_start = from_time - timedelta(seconds=300)
            all_candles = await conn.fetch(
                """
                SELECT time, open, high, low, close, volume
                FROM candles_1s
                WHERE symbol_id = $1 AND time >= $2
                ORDER BY time
                """,
                sid, history_start,
            )

            if not all_candles:
                logger.warning(f"No candles for {sname}")
                continue

            logger.info(f"Processing {sname}: {len(all_candles)} candles")

            # Sliding window arrays (max 200)
            window_size = 200
            prices: List[float] = []
            volumes: List[float] = []
            highs: List[float] = []
            lows: List[float] = []
            opens: List[float] = []

            indicator_batch: List[tuple] = []
            count = 0

            for c in all_candles:
                # Add to window
                prices.append(float(c['close']))
                volumes.append(float(c['volume']))
                highs.append(float(c['high']))
                lows.append(float(c['low']))
                opens.append(float(c['open']))

                # Trim window
                if len(prices) > window_size:
                    prices.pop(0)
                    volumes.pop(0)
                    highs.pop(0)
                    lows.pop(0)
                    opens.pop(0)

                # Need at least 50 data points for indicators
                if len(prices) < 50:
                    continue

                # Calculate all indicators using in-memory data
                np_prices = np.array(prices, dtype=np.float64)
                np_volumes = np.array(volumes, dtype=np.float64)
                np_highs = np.array(highs, dtype=np.float64)
                np_lows = np.array(lows, dtype=np.float64)
                np_opens = np.array(opens, dtype=np.float64)

                results: dict = {}
                indicator_keys: list = []

                for defn in calc._definitions:
                    try:
                        cls = calc._get_indicator_class(defn['class_name'], defn['module_path'])
                        if cls is None:
                            continue
                        indicator = cls(**defn['params'])
                        result = indicator.calculate(
                            prices=np_prices, volumes=np_volumes,
                            highs=np_highs, lows=np_lows,
                            opens=np_opens, closes=np_prices,
                        )
                        # Use full indicator name as prefix
                        prefix = result.name
                        for key, values in result.values.items():
                            if len(values) > 0:
                                val = values[-1]
                                if not np.isnan(val) and not np.isinf(val):
                                    full_key = f"{prefix}_{key}"
                                    results[full_key] = float(val)
                                    indicator_keys.append(full_key)
                    except Exception:
                        continue

                if results:
                    indicator_batch.append((
                        c['time'],
                        sid,
                        float(c['close']),
                        float(c['volume']),
                        json.dumps(results),
                        indicator_keys,
                    ))
                    count += 1

                # Batch insert every 5000
                if len(indicator_batch) >= 5000:
                    await conn.executemany(
                        """
                        INSERT INTO candle_indicators (time, symbol_id, price, volume, values, indicator_keys)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                        ON CONFLICT (symbol_id, time) DO UPDATE SET
                            price = EXCLUDED.price,
                            volume = EXCLUDED.volume,
                            values = EXCLUDED.values,
                            indicator_keys = EXCLUDED.indicator_keys,
                            updated_at = NOW()
                        """,
                        indicator_batch,
                    )
                    logger.info(f"  {sname}: {count} indicators written...")
                    indicator_batch = []

            # Insert remaining
            if indicator_batch:
                await conn.executemany(
                    """
                    INSERT INTO candle_indicators (time, symbol_id, price, volume, values, indicator_keys)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                    ON CONFLICT (symbol_id, time) DO UPDATE SET
                        price = EXCLUDED.price,
                        volume = EXCLUDED.volume,
                        values = EXCLUDED.values,
                        indicator_keys = EXCLUDED.indicator_keys,
                        updated_at = NOW()
                    """,
                    indicator_batch,
                )

            logger.info(f"  {sname}: {count} total indicators")
            total_count += count

    return total_count


async def recalculate_wide_vectors(
    db_pool: asyncpg.Pool,
    symbol_ids: List[int],
    from_time: datetime,
    to_time: Optional[datetime],
    batch_hours: int = 1,
) -> int:
    """
    Regenerate wide vectors for unprocessed candles.

    Uses time-batched processing to avoid OOM:
    - Processes data in batch_hours chunks (default: 1 hour)
    - Loads only current batch into memory
    - Builds and inserts wide vectors per batch
    """
    from src.pipeline.wide_vector_service import WideVectorService

    service = WideVectorService(db_pool)
    await service.load_symbols()

    active_symbols = service._active_symbols
    if not active_symbols:
        return 0

    symbol_id_set = {sid for sid, _ in active_symbols}
    symbol_names = [sname for _, sname in active_symbols]

    # Determine time range
    if to_time is None:
        to_time = datetime.now(timezone.utc)

    # Process in batch_hours chunks to avoid OOM
    batch_size = timedelta(hours=batch_hours)
    current_start = from_time
    total_count = 0

    logger.info(f"Processing wide vectors in {batch_hours}h batches from {from_time} to {to_time}")

    while current_start < to_time:
        current_end = min(current_start + batch_size, to_time)
        logger.info(f"Processing batch: {current_start} to {current_end}")

        # Load indicator data for this batch only
        async with db_pool.acquire() as conn:
            indicator_rows = await conn.fetch(
                """
                SELECT ci.symbol_id, s.symbol, ci.time, ci.values, ci.indicator_keys
                FROM candle_indicators ci
                JOIN symbols s ON s.id = ci.symbol_id
                WHERE ci.symbol_id = ANY($1) AND ci.time >= $2 AND ci.time < $3
                ORDER BY ci.time, ci.symbol_id
                """,
                symbol_ids, current_start, current_end,
            )

        if not indicator_rows:
            logger.warning(f"No indicator data in {current_start} - {current_end}, skipping")
            current_start = current_end
            continue

        # Group by time (only for this batch)
        by_time: dict = {}
        all_keys: set = set()
        for r in indicator_rows:
            t = r['time']
            if t not in by_time:
                by_time[t] = {}
            values_raw = r['values']
            if isinstance(values_raw, str):
                values = json.loads(values_raw)
            elif isinstance(values_raw, dict):
                values = values_raw
            else:
                values = {}
            by_time[t][r['symbol']] = values
            if r['indicator_keys']:
                all_keys.update(r['indicator_keys'])

        sorted_indicator_keys = sorted(all_keys)
        logger.info(f"  Found {len(by_time)} time points with indicators")

        # Load candle data for this batch only
        async with db_pool.acquire() as conn:
            candle_rows = await conn.fetch(
                """
                SELECT c.symbol_id, s.symbol, c.time, c.close, c.volume
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE c.symbol_id = ANY($1) AND c.time >= $2 AND c.time < $3
                ORDER BY c.time, c.symbol_id
                """,
                symbol_ids, current_start, current_end,
            )

        candle_by_time: dict = {}
        for r in candle_rows:
            t = r['time']
            if t not in candle_by_time:
                candle_by_time[t] = {}
            candle_by_time[t][r['symbol']] = {
                'close': float(r['close']),
                'volume': float(r['volume']),
            }

        # Build and insert wide vectors for this batch
        vector_batch = []
        batch_count = 0

        for t in sorted(by_time.keys()):
            ind_data = by_time[t]
            cd_data = candle_by_time.get(t, {})

            vector = []
            column_names = []

            for sid, sname in active_symbols:
                cd = cd_data.get(sname, {})
                ind = ind_data.get(sname, {})
                col_sname = sname.replace('/', '_')

                # Candle features
                for feat in ['close', 'volume']:
                    vector.append(cd.get(feat, 0.0))
                    column_names.append(f"{col_sname}_{feat}")

                # Indicator features
                for ikey in sorted_indicator_keys:
                    vector.append(ind.get(ikey, 0.0))
                    column_names.append(f"{col_sname}_{ikey}")

            if vector:
                vector_batch.append((
                    t,
                    json.dumps(vector),
                    column_names,
                    symbol_names,
                    len(vector),
                    len(active_symbols),
                    len(sorted_indicator_keys),
                ))
                batch_count += 1

                # Insert every 5000 vectors
                if len(vector_batch) >= 5000:
                    async with db_pool.acquire() as conn:
                        await conn.executemany(
                            """
                            INSERT INTO wide_vectors (time, vector, column_names, symbols,
                                vector_size, symbol_count, indicator_count)
                            VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7)
                            ON CONFLICT (time) DO NOTHING
                            """,
                            vector_batch,
                        )
                    logger.info(f"  {batch_count} wide vectors written...")
                    vector_batch = []

        # Insert remaining vectors for this batch
        if vector_batch:
            async with db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO wide_vectors (time, vector, column_names, symbols,
                        vector_size, symbol_count, indicator_count)
                    VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7)
                    ON CONFLICT (time) DO NOTHING
                    """,
                    vector_batch,
                )

        total_count += batch_count
        logger.info(f"  Batch complete: {batch_count} vectors (total: {total_count})")

        # Clear memory
        del by_time
        del candle_by_time
        del indicator_rows
        del candle_rows

        current_start = current_end

    # Set processed flag for all symbols
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE candles_1s SET processed = true
            WHERE symbol_id = ANY($1) AND time >= $2 AND time <= $3
            """,
            symbol_ids, from_time, to_time,
        )

    return total_count


async def main() -> None:
    parser = argparse.ArgumentParser(description="Recalculate indicators and wide vectors")
    parser.add_argument('--reset', action='store_true', help='Reset processed flag')
    parser.add_argument('--indicators', action='store_true', help='Recalculate indicators')
    parser.add_argument('--vectors', action='store_true', help='Recalculate wide vectors')
    parser.add_argument('--all', action='store_true', help='Reset + indicators + vectors')
    parser.add_argument('--vectors-only', action='store_true', 
                        help='Recalculate wide vectors only (skip indicators, assumes they exist)')
    parser.add_argument('--from', dest='from_time', required=True,
                        help='Start time (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--to', dest='to_time', default=None,
                        help='End time (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--symbols', dest='symbols', default=None,
                        help='Comma-separated symbol list (e.g., BTC/USDC,ETH/USDC)')
    parser.add_argument('--batch-hours', dest='batch_hours', type=int, default=1,
                        help='Batch size in hours for wide vector processing (default: 1)')

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

    if args.vectors_only:
        args.vectors = True

    async def _set_utc(conn):
        await conn.execute("SET timezone = 'UTC'")

    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5, init=_set_utc)

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
        count = await recalculate_wide_vectors(pool, symbol_ids, from_time, to_time, 
                                              batch_hours=args.batch_hours)
        logger.info(f"Generated {count} wide vectors")

    if not args.reset and not args.indicators and not args.vectors:
        logger.error("No action specified. Use --reset, --indicators, --vectors, --all, or --vectors-only")
        sys.exit(1)

    await pool.close()
    logger.info("Done")


if __name__ == '__main__':
    asyncio.run(main())
