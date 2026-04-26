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
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


async def get_symbol_ids(
    conn: asyncpg.Connection,
    symbols: Optional[list[str]],
) -> list[int]:
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
    symbol_ids: list[int],
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
    logger.info(f"Reset processed flag for {count} candles")
    return count


async def recalculate_indicators(
    db_pool: asyncpg.Pool,
    symbol_ids: list[int],
    from_time: datetime,
    to_time: Optional[datetime] = None,
) -> int:
    """
    Recalculate indicators for unprocessed candles.

    Uses time-batched processing to avoid OOM:
    - Processes data in 1-hour chunks
    - Loads only current batch into memory
    """
    from src.pipeline.indicator_calculator import IndicatorCalculator

    calc = IndicatorCalculator(db_pool)
    await calc.load_definitions()

    if not calc._definitions:
        logger.warning("No active indicator definitions found")
        return 0

    # Determine time range
    if to_time is None:
        to_time = datetime.now(UTC)

    # Process in 1-hour chunks
    batch_size = timedelta(hours=1)
    current_start = from_time
    total_count = 0

    logger.info(f"Processing indicators in 1h batches from {from_time} to {to_time}")

    while current_start < to_time:
        current_end = min(current_start + batch_size, to_time)

        async with db_pool.acquire() as conn:
            # Get unprocessed candles for this batch with symbol info
            unprocessed = await conn.fetch(
                """
                SELECT c.time, c.symbol_id, s.symbol
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE c.symbol_id = ANY($1)
                  AND c.time >= $2 AND c.time < $3
                  AND c.processed = false
                ORDER BY c.time, c.symbol_id
                """,
                symbol_ids, current_start, current_end,
            )

        if not unprocessed:
            current_start = current_end
            continue

        # Group by time
        by_time: dict = {}
        for r in unprocessed:
            t = r['time']
            if t not in by_time:
                by_time[t] = []
            by_time[t].append({'symbol_id': r['symbol_id'], 'symbol': r['symbol']})

        logger.info(f"Processing {len(unprocessed)} unprocessed candle(s) across {len(by_time)} time points in batch")

        # Calculate indicators for each time point and symbol
        for t, symbols_at_time in by_time.items():
            for si in symbols_at_time:
                count = await calc.calculate_with_candle(
                    symbol=si['symbol'],
                    time=t,
                    open=0, high=0, low=0, close=0, volume=0,
                    symbol_id=si['symbol_id'],
                )
                total_count += count

        current_start = current_end

    return total_count


async def load_indicator_schema(db_pool: asyncpg.Pool) -> list[str]:
    """Load fixed global indicator key list from DB (run once).

    Uses the superset of all indicator keys ever stored in candle_indicators
    so the wide-vector schema never shifts between batches.
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT unnest(indicator_keys) AS k
            FROM candle_indicators
            WHERE indicator_keys IS NOT NULL AND array_length(indicator_keys, 1) > 0
            ORDER BY k
            """
        )
        schema = [r['k'] for r in rows if r['k']]
    logger.info(f"Loaded fixed indicator schema: {len(schema)} keys")
    return schema


async def recalculate_wide_vectors(
    db_pool: asyncpg.Pool,
    symbol_ids: list[int],
    active_symbols: list[tuple[int, str]],
    from_time: datetime,
    to_time: Optional[datetime] = None,
    batch_hours: int = 1,
) -> int:
    """
    Regenerate wide vectors with gap-filling.

    Uses IN-MEMORY forward-fill to avoid N+1 queries.
    Loads all historical data ONCE per batch (2 queries), then fills gaps in memory.
    This reduces processing time from hours to seconds per batch.
    """
    if not active_symbols:
        return 0

    symbol_names = [sname for _, sname in active_symbols]

    if to_time is None:
        to_time = datetime.now(UTC)

    # Load fixed global schema ONCE before processing batches
    # Prevents column index shifts when different batches have different keys
    fixed_indicator_keys = await load_indicator_schema(db_pool)
    if not fixed_indicator_keys:
        logger.warning("No indicator keys found in database, aborting wide vector recalculation")
        return 0

    batch_size = timedelta(hours=batch_hours)
    current_start = from_time
    total_count = 0

    logger.info(f"Processing wide vectors in {batch_hours}h batches from {from_time} to {to_time}")

    while current_start < to_time:
        current_end = min(current_start + batch_size, to_time)
        logger.info(f"Processing batch: {current_start} to {current_end}")

        # Load indicator data for this batch
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

        # Group by time (using fixed global schema, not per-batch dynamic keys)
        by_time: dict = {}
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

        sorted_indicator_keys = fixed_indicator_keys  # Use fixed schema, not per-batch
        logger.info(f"  Found {len(by_time)} time points with indicators")

        # Load candle data for this batch
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

        # === FILL GAPS: Load ALL historical data ONCE, then forward-fill in memory ===
        # OLD: 7200 queries per batch (2 per time point × 3600 time points)
        # NEW: 2 queries per batch (load all history once)
        missing_count = 0

        all_times_set = set(by_time.keys()) | set(candle_by_time.keys())
        if all_times_set:
            async with db_pool.acquire() as conn:
                # Get last known data for each symbol BEFORE batch start
                all_symbol_ids = [sid for sid, _ in active_symbols]

                last_candles = await conn.fetch(
                    """
                    SELECT DISTINCT ON (c.symbol_id) c.symbol_id, s.symbol,
                           c.close, c.volume
                    FROM candles_1s c
                    JOIN symbols s ON s.id = c.symbol_id
                    WHERE c.symbol_id = ANY($1) AND c.time < $2
                    ORDER BY c.symbol_id, c.time DESC
                    """,
                    all_symbol_ids, current_start,
                )

                last_indicators = await conn.fetch(
                    """
                    SELECT DISTINCT ON (ci.symbol_id) ci.symbol_id, s.symbol,
                           ci.values, ci.indicator_keys
                    FROM candle_indicators ci
                    JOIN symbols s ON s.id = ci.symbol_id
                    WHERE ci.symbol_id = ANY($1) AND ci.time < $2
                    ORDER BY ci.symbol_id, ci.time DESC
                    """,
                    all_symbol_ids, current_start,
                )

            # Build forward-fill cache from last known data
            last_candle_cache = {}
            for r in last_candles:
                last_candle_cache[r['symbol']] = {
                    'close': float(r['close']),
                    'volume': 0.0,
                }

            last_indicator_cache = {}
            for r in last_indicators:
                values_raw = r['values']
                if isinstance(values_raw, str):
                    values = json.loads(values_raw)
                elif isinstance(values_raw, dict):
                    values = values_raw
                else:
                    values = {}
                last_indicator_cache[r['symbol']] = {
                    k: float(v) if v is not None else 0.0
                    for k, v in values.items()
                }

            # Forward-fill gaps in MEMORY (no more DB queries!)
            for t in sorted(all_times_set):
                symbols_at_time = set()
                if t in candle_by_time:
                    symbols_at_time.update(candle_by_time[t].keys())
                if t in by_time:
                    symbols_at_time.update(by_time[t].keys())

                missing = [sname for _, sname in active_symbols
                           if sname not in symbols_at_time]

                if missing:
                    # Use last known candle (from cache)
                    for sname in missing:
                        if sname in last_candle_cache:
                            if t not in candle_by_time:
                                candle_by_time[t] = {}
                            candle_by_time[t][sname] = dict(last_candle_cache[sname])
                            missing_count += 1
                        if sname in last_indicator_cache:
                            if t not in by_time:
                                by_time[t] = {}
                            by_time[t][sname] = dict(last_indicator_cache[sname])

        if missing_count > 0:
            logger.info(f"  Filled {missing_count} symbol-time gaps with forward-filled data")

        # Build and insert wide vectors for this batch
        vector_batch = []
        batch_count = 0

        # Try to load external data provider
        external_provider = None
        try:
            from src.external.data_provider import get_features
            external_provider = get_features
            logger.info("External data provider loaded for recalculation")
        except (ImportError, AttributeError):
            pass

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
                # Call external provider if available
                if external_provider:
                    try:
                        provider_candles = {
                            sname.replace('/', '_'): cd
                            for sname, cd in cd_data.items()
                        }
                        ext_features = external_provider(provider_candles, ind_data, t)

                        if ext_features:
                            # Build external features separately to avoid O(n²) insert(0,)
                            ext_values = []
                            ext_names = []
                            for key, value in sorted(ext_features.items()):
                                if value is not None:
                                    ext_values.append(float(value))
                                    ext_names.append(key)
                            # Prepend: external + existing vector/column_names
                            vector = ext_values + vector
                            column_names = ext_names + column_names
                    except Exception as e:
                        logger.warning(f"External provider error at {t}: {e}")

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

                # Insert every 6000 vectors (reduced from 5000 for better batch efficiency)
                if len(vector_batch) >= 6000:
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

        # Insert remaining vectors
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

    return total_count


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recalculate indicators and wide vectors"
    )
    parser.add_argument(
        '--symbols', type=str, default=None,
        help='Comma-separated symbol list (e.g., "BTC/USDC,ETH/USDC")'
    )
    parser.add_argument(
        '--from', dest='from_time', type=str, required=True,
        help='Start time (YYYY-MM-DD HH:MM:SS)'
    )
    parser.add_argument(
        '--to', dest='to_time', type=str, default=None,
        help='End time (YYYY-MM-DD HH:MM:SS), default: now'
    )
    parser.add_argument(
        '--reset', action='store_true',
        help='Reset processed flag only'
    )
    parser.add_argument(
        '--indicators', action='store_true',
        help='Recalculate indicators only'
    )
    parser.add_argument(
        '--vectors-only', action='store_true',
        help='Recalculate wide vectors only'
    )
    parser.add_argument(
        '--all', action='store_true',
        help='Recalculate both indicators and wide vectors'
    )

    args = parser.parse_args()

    if not any([args.reset, args.indicators, args.vectors_only, args.all]):
        parser.error("Must specify --reset, --indicators, --vectors-only, or --all")

    from_time = datetime.fromisoformat(args.from_time)
    if from_time.tzinfo is None:
        from_time = from_time.replace(tzinfo=UTC)
    to_time = datetime.fromisoformat(args.to_time) if args.to_time else None
    if to_time and to_time.tzinfo is None:
        to_time = to_time.replace(tzinfo=UTC)
    symbols = [s.strip() for s in args.symbols.split(',')] if args.symbols else None

    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)

    try:
        async with pool.acquire() as conn:
            symbol_ids = await get_symbol_ids(conn, symbols)
            logger.info(f"Processing {len(symbol_ids)} symbols")

            if args.reset:
                count = await reset_processed(conn, symbol_ids, from_time, to_time)
                logger.info(f"Reset {count} candles")

            if args.indicators or args.all:
                count = await recalculate_indicators(pool, symbol_ids, from_time, to_time)
                logger.info(f"Recalculated {count} indicators")

            if args.vectors_only or args.all:
                # Load active symbols
                service_from_wvs = __import__('src.pipeline.wide_vector_service', fromlist=['WideVectorService']).WideVectorService(pool)
                await service_from_wvs.load_symbols()
                active = service_from_wvs._active_symbols
                count = await recalculate_wide_vectors(
                    pool, symbol_ids, active, from_time, to_time, batch_hours=1
                )
                logger.info(f"Generated {count} wide vectors")

    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
