#!/usr/bin/env python3
"""
Recalculation CLI for indicators and wide vectors.

Recalculates indicators and/or wide vectors for the specified time range.
Usage:

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
from typing import Any

import asyncpg
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


async def get_symbol_ids(
    conn: asyncpg.Connection,
    symbols: list[str] | None,
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
    return [r["id"] for r in rows]


async def load_indicator_schema(db_pool: asyncpg.Pool) -> list[str]:
    """Load fixed global indicator key list from DB (run once).

    Uses the superset of all indicator keys ever stored in candle_indicators
    by extracting keys from the values JSONB column. This avoids storing
    redundant indicator_keys array and ensures schema consistency.
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT jsonb_object_keys(values) AS k
            FROM candle_indicators
            WHERE values IS NOT NULL
            ORDER BY k
            """
        )
        schema = [r["k"] for r in rows if r["k"]]
    logger.info(f"Loaded fixed indicator schema: {len(schema)} keys")
    return schema


async def recalculate_indicators(
    db_pool: asyncpg.Pool,
    symbol_ids: list[int],
    from_time: datetime,
    to_time: datetime | None = None,
    with_quality_guard: bool = False,
) -> int:
    """
    Recalculate indicators for candles in time range using ring buffer per symbol.

    Optimized version:
    - Pre-creates indicator instances (not per-candle)
    - Reuses numpy arrays from RingBuffer (no conversion overhead)
    - Processes candles with minimal object creation
    """
    from src.infrastructure.repositories.indicator_repo import IndicatorRepository
    from src.pipeline.indicator_calculator import IndicatorCalculator, IndicatorResult
    from src.pipeline.indicators_buffer import IndicatorsBuffer

    calc = IndicatorCalculator(db_pool)
    await calc.load_definitions()

    if not calc._definitions:
        logger.warning("No active indicator definitions found")
        return 0

    if not symbol_ids:
        logger.info("No symbols to process")
        return 0

    # Determine time range
    if to_time is None:
        to_time = datetime.now(UTC)

    # Maximum period needed across all active indicators (in seconds)
    max_period = calc._max_indicator_period
    logger.info(f"Max indicator period: {max_period} seconds")

    # OPTIMIZATION 1: Pre-create all indicator instances once
    indicators = []
    for defn in calc._definitions:
        cls = calc._get_indicator_class(defn["class_name"], defn["module_path"])
        if cls:
            indicator = cls(**defn["params"])
            indicators.append((defn, indicator))
    
    logger.info(f"Pre-created {len(indicators)} indicator instances")

    batch_results: list[tuple] = []
    repo = IndicatorRepository(db_pool)

    # Chunk size for fetching candles (keeps memory bounded)
    CHUNK_SIZE = 5000
    
    # OPTIMIZATION 3: Larger batch insert size (was 1000, now 5000)
    BATCH_INSERT_SIZE = 5000
    
    # OPTIMIZATION 4: Parallel symbol processing
    MAX_CONCURRENT_SYMBOLS = 4  # Process 4 symbols concurrently
    
    logger.info(f"Processing {len(symbol_ids)} symbols with {MAX_CONCURRENT_SYMBOLS} concurrent workers")
    
    # Thread-safe batch collection
    batch_lock = asyncio.Lock()
    
    async def insert_batch_if_needed() -> None:
        """Insert batch if size exceeds threshold (thread-safe)."""
        nonlocal batch_results
        async with batch_lock:
            if len(batch_results) >= BATCH_INSERT_SIZE:
                await repo.store_indicator_results_batch(batch_results)
                batch_results = []
    
    async def process_symbol(sid: int) -> tuple[int, int]:
        """Process a single symbol. Returns (processed_count, total_indicator_count)."""
        nonlocal batch_results
        
        # Get symbol name
        async with db_pool.acquire() as conn:
            symbol = await conn.fetchval("SELECT symbol FROM symbols WHERE id = $1", sid)
        if not symbol:
            logger.warning(f"Symbol {sid} not found")
            return 0, 0

        logger.info(f"Start processed {symbol} from {from_time} max_period:{max_period}.")

        buffer = IndicatorsBuffer(db_pool, symbol, max_period)
        symbol_processed = 0
        symbol_indicators = 0

        # We will fetch candles from lookback_start to to_time in chunks.
        # lookback_start ensures we have enough history for the first target candle.
        lookback_start = from_time - timedelta(seconds=max_period)

        # Use keyset pagination: fetch rows where time >= cursor, ordered by time ASC.
        cursor = lookback_start
        first_target_candle_seen = False

        while cursor < to_time:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT time, open, high, low, close, volume
                    FROM candles_1s
                    WHERE symbol_id = $1
                      AND time >= $2 AND time < $3
                    ORDER BY time ASC
                    LIMIT $4
                    """,
                    sid,
                    cursor,
                    to_time,
                    CHUNK_SIZE,
                )
            if not rows:
                break

            # Process rows in chronological order (they already are ASC)
            for row in rows:
                t = row["time"]
                # Update cursor for next keyset page
                cursor = t + timedelta(seconds=1)

                # If this candle is before the target range, just add as history
                if t < from_time:
                    await buffer.add_candle(row)
                    continue

                # First candle in target range: ensure buffer has history
                if not first_target_candle_seen:
                    await buffer.initialization(t, row)
                    first_target_candle_seen = True

                # OPTIMIZATION 2: RingBuffer already stores numpy arrays
                # Use asarray to avoid copy and deprecation warning with numpy 2.0
                # Note: opens_buff is not used - no indicator requires open prices
                closes_arr = np.asarray(buffer.closes_buff)
                volumes_arr = np.asarray(buffer.volumes_buff)
                highs_arr = np.asarray(buffer.highs_buff)
                lows_arr = np.asarray(buffer.lows_buff)

                # Calculate indicators using pre-created instances
                results: dict[str, Any] = {}
                for defn, indicator in indicators:
                    try:
                        result: IndicatorResult = indicator.calculate(
                            prices=closes_arr,
                            volumes=volumes_arr,
                            highs=highs_arr,
                            lows=lows_arr,
                        )

                        for sub_key, values in result.values.items():
                            if len(result.values) == 1 or sub_key == "value":
                                flat_key = defn["name"]
                            else:
                                flat_key = f"{defn['name']}_{sub_key}"

                            if len(values) > 0:
                                val = values[-1]
                                if not np.isnan(val) and not np.isinf(val):
                                    results[flat_key] = float(val)
                                else:
                                    results[flat_key] = None
                            else:
                                results[flat_key] = None

                    except Exception as e:
                        logger.error(f"Error calculating {defn['name']} for {symbol}: {e}")

                if results:
                    # Data quality check
                    if with_quality_guard:
                        quality_report = calc._quality_guard.validate_indicator_values(
                            symbol_id=sid,
                            symbol=symbol,
                            time=t,
                            values=results,
                        )

                        if quality_report.is_critical:
                            logger.error(
                                f"CRITICAL quality issue for {symbol} at {t}: "
                                f"{quality_report.issue_count} issues, score={quality_report.quality_score}"
                            )
                            # Add to buffer and continue without storing results
                            await buffer.add_candle(row)
                            continue

                    batch_results.append(
                        (
                            t,
                            sid,
                            float(row["close"]),
                            float(row["volume"]),
                            results,
                        )
                    )

                # Update counters (local to symbol)
                symbol_processed += 1
                symbol_indicators += len(results)

                # Add current candle to buffer for future calculations
                await buffer.add_candle(row)

                # Progress indicator: print '.' every 100 candles (per symbol)
                if symbol_processed % 100 == 0:
                    print(".", end="", flush=True)

                # Periodically insert batch results (thread-safe)
                await insert_batch_if_needed()

        logger.info(f"Finished symbol {symbol}: {symbol_processed} candles, {symbol_indicators} indicators")
        return symbol_processed, symbol_indicators
    
    # Process symbols with limited concurrency
    from asyncio import Semaphore, gather
    sem = Semaphore(MAX_CONCURRENT_SYMBOLS)
    
    async def process_with_limit(sid: int) -> tuple[int, int]:
        async with sem:
            return await process_symbol(sid)
    
    # Run all symbols in parallel with concurrency limit
    import time
    start_time = time.time()
    results = await gather(*[process_with_limit(sid) for sid in symbol_ids])
    
    # Aggregate results
    total_processed = sum(r[0] for r in results)
    total_indicators = sum(r[1] for r in results)
    elapsed = time.time() - start_time
    
    logger.info(f"Processed {total_processed} candles across {len(symbol_ids)} symbols in {elapsed:.1f}s")
    logger.info(f"Rate: {total_processed/elapsed:.0f} candles/second")

    # Insert remaining batch results
    if batch_results:
        await repo.store_indicator_results_batch(batch_results)
        batch_results = []

    return total_indicators


async def recalculate_wide_vectors(
    db_pool: asyncpg.Pool,
    symbol_ids: list[int],
    active_symbols: list[tuple[int, str]],
    from_time: datetime,
    to_time: datetime | None = None,
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
                SELECT ci.symbol_id, s.symbol, ci.time, ci.values
                FROM candle_indicators ci
                JOIN symbols s ON s.id = ci.symbol_id
                WHERE ci.symbol_id = ANY($1) AND ci.time >= $2 AND ci.time < $3
                ORDER BY ci.time, ci.symbol_id
                """,
                symbol_ids,
                current_start,
                current_end,
            )

        if not indicator_rows:
            logger.warning(f"No indicator data in {current_start} - {current_end}, skipping")
            current_start = current_end
            continue

        # Group by time (using fixed global schema, not per-batch dynamic keys)
        by_time: dict = {}
        for r in indicator_rows:
            t = r["time"]
            if t not in by_time:
                by_time[t] = {}
            values_raw = r["values"]
            if isinstance(values_raw, str):
                values = json.loads(values_raw)
            elif isinstance(values_raw, dict):
                values = values_raw
            else:
                values = {}
            by_time[t][r["symbol"]] = values

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
                symbol_ids,
                current_start,
                current_end,
            )

        candle_by_time: dict = {}
        for r in candle_rows:
            t = r["time"]
            if t not in candle_by_time:
                candle_by_time[t] = {}
            candle_by_time[t][r["symbol"]] = {
                "close": float(r["close"]),
                "volume": float(r["volume"]),
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
                    all_symbol_ids,
                    current_start,
                )

                last_indicators = await conn.fetch(
                    """
                    SELECT DISTINCT ON (ci.symbol_id) ci.symbol_id, s.symbol,
                           ci.values
                    FROM candle_indicators ci
                    JOIN symbols s ON s.id = ci.symbol_id
                    WHERE ci.symbol_id = ANY($1) AND ci.time < $2
                    ORDER BY ci.symbol_id, ci.time DESC
                    """,
                    all_symbol_ids,
                    current_start,
                )

            # Build forward-fill cache from last known data
            last_candle_cache = {}
            for r in last_candles:
                last_candle_cache[r["symbol"]] = {
                    "close": float(r["close"]),
                    "volume": 0.0,
                }

            last_indicator_cache = {}
            for r in last_indicators:
                values_raw = r["values"]
                if isinstance(values_raw, str):
                    values = json.loads(values_raw)
                elif isinstance(values_raw, dict):
                    values = values_raw
                else:
                    values = {}
                last_indicator_cache[r["symbol"]] = {
                    k: float(v) if v is not None else 0.0 for k, v in values.items()
                }

            # Forward-fill gaps in MEMORY (no more DB queries!)
            for t in sorted(all_times_set):
                symbols_at_time = set()
                if t in candle_by_time:
                    symbols_at_time.update(candle_by_time[t].keys())
                if t in by_time:
                    symbols_at_time.update(by_time[t].keys())

                missing = [sname for _, sname in active_symbols if sname not in symbols_at_time]

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

            for _sid, sname in active_symbols:
                cd = cd_data.get(sname, {})
                ind = ind_data.get(sname, {})
                col_sname = sname.replace("/", "_")

                # Candle features
                for feat in ["close", "volume"]:
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
                            sname.replace("/", "_"): cd for sname, cd in cd_data.items()
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

                vector_batch.append(
                    (
                        t,
                        json.dumps(vector),
                        column_names,
                        symbol_names,
                        len(vector),
                        len(active_symbols),
                        len(sorted_indicator_keys),
                    )
                )
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
    parser = argparse.ArgumentParser(description="Recalculate indicators and wide vectors")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help='Comma-separated symbol list (e.g., "BTC/USDC,ETH/USDC")',
    )
    parser.add_argument(
        "--from", dest="from_time", type=str, required=True, help="Start time (YYYY-MM-DD HH:MM:SS)"
    )
    parser.add_argument(
        "--to",
        dest="to_time",
        type=str,
        default=None,
        help="End time (YYYY-MM-DD HH:MM:SS), default: now",
    )
    parser.add_argument("--indicators", action="store_true", help="Recalculate indicators only")
    parser.add_argument("--vectors-only", action="store_true", help="Recalculate wide vectors only")
    parser.add_argument(
        "--all", action="store_true", help="Recalculate both indicators and wide vectors"
    )
    parser.add_argument(
        "--with-quality-guard",
        action="store_true",
        help="Run data quality guard validation during recalculation",
    )

    args = parser.parse_args()

    from_time = datetime.fromisoformat(args.from_time)
    if from_time.tzinfo is None:
        from_time = from_time.replace(tzinfo=UTC)
    to_time = datetime.fromisoformat(args.to_time) if args.to_time else None
    if to_time and to_time.tzinfo is None:
        to_time = to_time.replace(tzinfo=UTC)
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None

    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)

    try:
        async with pool.acquire() as conn:
            symbol_ids = await get_symbol_ids(conn, symbols)
            logger.info(f"Processing {len(symbol_ids)} symbols")

        if args.indicators or args.all:
            count = await recalculate_indicators(
                pool, symbol_ids, from_time, to_time, with_quality_guard=args.with_quality_guard
            )
            logger.info(f"Recalculated {count} indicators")

        if args.vectors_only or args.all:
            # Load active symbols
            service_from_wvs = __import__(
                "src.pipeline.wide_vector_service", fromlist=["WideVectorService"]
            ).WideVectorService(pool)
            await service_from_wvs.load_symbols()
            active = service_from_wvs._active_symbols
            count = await recalculate_wide_vectors(
                pool, symbol_ids, active, from_time, to_time, batch_hours=1
            )
            logger.info(f"Generated {count} wide vectors")

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
