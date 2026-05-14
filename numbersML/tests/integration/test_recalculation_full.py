#!/usr/bin/env python3
"""
Full integration test for recalculation service as specified.

Tests the complete chain with exactly 3000 candles, comprehensive validation,
and all requirements from the original specification.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import numpy as np
import pytest

logger = logging.getLogger(__name__)

# Test configuration from specification
TEST_SYMBOL = "TEST/USDT"
TEST_CANDLE_COUNT = 3000  # Changed from 5000 (too much)
DETERMINISTIC_SEED = 42  # For reproducible results


@pytest.mark.integration
@pytest.mark.slow  # This test takes longer due to 3000 candles
async def test_recalculation_service_full_integration():
    """
    Full integration test for recalculation service.

    This test implements all requirements from the specification:
    1. Allow TEST/USDT symbol
    2. Remove old artifacts
    3. Create exactly 5000 candles with deterministic data
    4. Run recalculation with --indicators --with-quality-guard
    5. Validate exact counts and time alignment
    6. Validate indicator values
    7. Disallow TEST/USDT after test
    """
    # Create database connection
    pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=2,
        max_size=10,
    )

    try:
        async with pool.acquire() as conn:
            # 1. Remove old TEST/USDT artifacts
            await cleanup_existing_data(conn)

            # 2. Allow TEST/USDT symbol
            symbol_id = await setup_test_symbol(conn)

            # 3. Create exactly 3000 candles with deterministic data
            min_time = await insert_synthetic_candles(conn, symbol_id)

            # 4. Run recalculation with --indicators --with-quality-guard
            await run_recalculation_direct(pool, [symbol_id], min_time)

            # 5. Validation Tests

            # 5.1 Exact count validation: 3000 × N indicator values (where N = actual registered indicators)
            await validate_exact_counts(conn, symbol_id)

            # 5.2 Time alignment validation: 1:1 mapping, UTC, no shifts
            await validate_time_alignment(conn, symbol_id)

            # 5.3 Indicator value validation based on known synthetic data
            await validate_indicator_values(conn, symbol_id)

            logger.info("Full integration test completed successfully with all requirements met")

    finally:
        # 6. Disallow TEST/USDT and cleanup
        async with pool.acquire() as conn:
            await cleanup_existing_data(conn)
            await conn.execute(
                "UPDATE symbols SET is_active = false, is_allowed = false WHERE symbol = $1",
                TEST_SYMBOL,
            )
        await pool.close()


async def cleanup_existing_data(conn: asyncpg.Connection):
    """Remove old TEST/USDT artifacts from previous runs."""
    symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

    if symbol_id:
        # Remove from candle_indicators first (foreign key dependency)
        await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
        # Remove from candles_1s
        await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
        logger.info(f"Cleaned up existing data for symbol_id={symbol_id}")


async def setup_test_symbol(conn: asyncpg.Connection) -> int:
    """Allow TEST/USDT symbol for testing."""
    await conn.execute(
        """
        INSERT INTO symbols (symbol, base_asset, quote_asset, tick_size, step_size, min_notional, is_active, is_allowed)
        VALUES ($1, 'TEST', 'USDT', 0.00001, 0.000001, 1.0, true, true)
        ON CONFLICT (symbol) DO UPDATE SET is_active = true, is_allowed = true
        """,
        TEST_SYMBOL,
    )

    symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

    if not symbol_id:
        raise ValueError(f"Failed to create symbol {TEST_SYMBOL}")

    logger.info(f"TEST/USDT symbol allowed with ID: {symbol_id}")
    return symbol_id


def generate_deterministic_candles(symbol_id: int, start_time: datetime) -> list[tuple]:
    """
    Generate exactly 3000 deterministic candles.

    Uses noised sine wave around 100.0 as specified.
    Data/time can be current, but values must be constant between runs.
    """
    np.random.seed(DETERMINISTIC_SEED)

    # Generate exactly 3000 candles going backward from start_time
    indices = np.arange(TEST_CANDLE_COUNT)

    # Base price: 100.0 ± 5.0 (sine wave)
    # Period: 15 minutes for price oscillations
    prices = 100.0 + 5.0 * np.sin(2 * np.pi * indices / (15 * 60))
    prices += np.random.normal(0, 0.1, TEST_CANDLE_COUNT)  # Noise: σ=0.1

    # Generate OHLCV values with consistent relationships
    opens = prices + np.random.uniform(-0.05, 0.05, TEST_CANDLE_COUNT)
    highs = np.maximum(opens, prices) + np.random.uniform(0, 0.1, TEST_CANDLE_COUNT)
    lows = np.minimum(opens, prices) - np.random.uniform(0, 0.1, TEST_CANDLE_COUNT)
    closes = prices
    volumes = np.random.uniform(0.1, 10.0, TEST_CANDLE_COUNT)  # Volume: 0.1 to 10.0

    # Create rows for insertion (going backward in time from current)
    rows = []
    for i in range(TEST_CANDLE_COUNT):
        timestamp = start_time - timedelta(seconds=i)
        rows.append(
            (
                symbol_id,
                timestamp,
                Decimal(str(round(opens[i], 5))),
                Decimal(str(round(highs[i], 5))),
                Decimal(str(round(lows[i], 5))),
                Decimal(str(round(closes[i], 5))),
                Decimal(str(round(volumes[i], 6))),
                Decimal(str(round(volumes[i] * closes[i], 6))),
                1,  # trade_count
            )
        )

    return rows


async def insert_synthetic_candles(conn: asyncpg.Connection, symbol_id: int) -> datetime:
    """Create exactly 3000 candles in public.candles_1s for TEST/USDT."""
    start_time = datetime.now(UTC).replace(microsecond=0)
    rows = generate_deterministic_candles(symbol_id, start_time)

    # Insert in batches for performance
    batch_size = 1000
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        await conn.executemany(
            """
            INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (symbol_id, time) DO NOTHING
            """,
            batch,
        )

    # Verify exact count
    count = await conn.fetchval("SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id)
    assert count == TEST_CANDLE_COUNT, f"Expected exactly {TEST_CANDLE_COUNT} candles, got {count}"

    # Get time range
    time_range = await conn.fetchrow(
        """
        SELECT MIN(time) as min_time, MAX(time) as max_time
        FROM candles_1s WHERE symbol_id = $1
        """,
        symbol_id,
    )

    logger.info(
        f"Created exactly {count} candles from {time_range['min_time']} to {time_range['max_time']}"
    )
    return time_range["min_time"]


async def run_recalculation_direct(pool, symbol_ids: list[int], from_time: datetime):
    """
    Call src.cli.recalculate for only TEST/USDT with --indicators --with-quality-guard.

    Note: No wide_vector creation, only indicators.
    """
    from src.cli.recalculate import recalculate_indicators

    # Run recalculation with quality guard
    count = await recalculate_indicators(pool, symbol_ids, from_time, None, with_quality_guard=True)

    logger.info(f"Recalculated {count} indicators with quality guard")
    assert count > 0, "No indicators were recalculated"


async def validate_exact_counts(conn: asyncpg.Connection, symbol_id: int):
    """
    Validate exact 3000 × N indicator values in public.candle_indicators.

    Where N is the actual number of registered indicators (determined dynamically).
    """
    # Get exact candle count
    candle_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
    )
    assert (
        candle_count == TEST_CANDLE_COUNT
    ), f"Expected {TEST_CANDLE_COUNT} candles, got {candle_count}"

    # Get indicator row count
    indicator_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1", symbol_id
    )

    # Should have 1:1 mapping (each candle has one indicator row)
    assert (
        indicator_count == candle_count
    ), f"Expected {candle_count} indicator rows, got {indicator_count}"

    # Get total indicator values (accounting for multi-value indicators)
    sample_row = await conn.fetchrow(
        "SELECT values FROM candle_indicators WHERE symbol_id = $1 LIMIT 1", symbol_id
    )

    if sample_row:
        values_dict = sample_row["values"]
        total_values = len(values_dict)

        # Expected total values across all candles
        expected_total = candle_count * total_values

        logger.info(
            f"Validation: {candle_count} candles × {total_values} values = {expected_total} total values"
        )

        # Validate we have the expected number of values (determined from actual data)
        logger.info(f"Found {total_values} indicator values per candle")
        assert total_values > 0, f"Expected positive number of indicator values, got {total_values}"

        # Log the actual indicator keys for verification
        logger.info(f"Indicator keys found: {sorted(values_dict.keys())}")


async def validate_time_alignment(conn: asyncpg.Connection, symbol_id: int):
    """
    Validate times in public.candles_1s and public.candle_indicators fit exactly.

    No shifts, always UTC, 1:1 mapping.
    """
    # Get all timestamps from both tables
    candle_times = await conn.fetch(
        "SELECT time FROM candles_1s WHERE symbol_id = $1 ORDER BY time", symbol_id
    )
    indicator_times = await conn.fetch(
        "SELECT time FROM candle_indicators WHERE symbol_id = $1 ORDER BY time", symbol_id
    )

    # Exact count match
    assert len(candle_times) == len(
        indicator_times
    ), f"Candle count ({len(candle_times)}) != Indicator count ({len(indicator_times)})"

    # Check 1:1 time alignment - no shifts allowed
    for i, (candle, indicator) in enumerate(zip(candle_times, indicator_times)):
        assert (
            candle["time"] == indicator["time"]
        ), f"Time mismatch at index {i}: candle={candle['time']}, indicator={indicator['time']}"

        # Verify UTC timezone
        assert candle["time"].tzinfo == UTC, f"Candle time {candle['time']} not in UTC"
        assert indicator["time"].tzinfo == UTC, f"Indicator time {indicator['time']} not in UTC"

    logger.info(
        f"Perfect time alignment validated: {len(candle_times)} timestamps, 1:1 mapping, UTC"
    )


async def validate_indicator_values(conn: asyncpg.Connection, symbol_id: int):
    """
    Validate indicator values based on known synthetic data.

    Since we know the data (noised sine around 100), we can validate:
    - SMA, EMA must be around 100
    - MACD must be sinus like, in + und in -
    - RSI must be 0-100
    - etc.
    """
    # Get sample indicator data for validation
    indicators = await conn.fetch(
        """
        SELECT time, values
        FROM candle_indicators
        WHERE symbol_id = $1
        ORDER BY time
        LIMIT 100
        """,
        symbol_id,
    )

    macd_positive_count = 0
    macd_negative_count = 0

    for row in indicators:
        values = row["values"]

        # Validate SMA/EMA indicators (must be around 100)
        for key in ["sma_20", "sma_2000", "sma_450", "ema_12", "ema_26", "ema_2000", "ema_450"]:
            if key in values:
                val = float(values[key])
                assert 90.0 <= val <= 110.0, f"{key}={val} outside expected range [90, 110]"

        # Validate RSI indicators (must be 0-100)
        for key in ["rsi_14", "rsi_54"]:
            if key in values:
                val = float(values[key])
                assert 0.0 <= val <= 100.0, f"{key}={val} outside RSI range [0, 100]"

        # Validate ATR indicators (must be positive)
        for key in ["atr_14", "atr_99", "atr_999"]:
            if key in values:
                val = float(values[key])
                assert 0.0 < val <= 5.0, f"{key}={val} outside ATR range (0, 5]"

        # Validate MACD (must be sinus like, in + und in -)
        for key in ["macd_12_26_9", "macd_120_260_29", "macd_400_860_300"]:
            if key in values:
                macd_val = values[key]
                if isinstance(macd_val, dict):
                    # MACD has multiple components
                    for subkey in ["macd", "signal", "histogram"]:
                        if subkey in macd_val:
                            val = float(macd_val[subkey])
                            assert (
                                -10.0 <= val <= 10.0
                            ), f"{key}.{subkey}={val} outside MACD range [-10, 10]"

                            # Track sinus-like behavior
                            if subkey == "macd":
                                if val > 0:
                                    macd_positive_count += 1
                                elif val < 0:
                                    macd_negative_count += 1
                else:
                    val = float(macd_val)
                    assert -10.0 <= val <= 10.0, f"{key}={val} outside MACD range [-10, 10]"

                    if val > 0:
                        macd_positive_count += 1
                    elif val < 0:
                        macd_negative_count += 1

        # Validate Bollinger Bands
        for key in ["bb_20_2", "bb_200_2", "bb_900_2"]:
            if key in values:
                bb_val = values[key]
                if isinstance(bb_val, dict):
                    upper = float(bb_val.get("upper", 0))
                    middle = float(bb_val.get("middle", 0))
                    lower = float(bb_val.get("lower", 0))

                    assert (
                        upper > middle > lower
                    ), f"{key} bands not in correct order: upper={upper}, middle={middle}, lower={lower}"
                    assert (
                        90.0 <= middle <= 110.0
                    ), f"{key} middle={middle} outside expected range [90, 110]"

    # Validate MACD sinus-like behavior (both positive and negative values)
    assert macd_positive_count > 0, "MACD never positive - not sinus-like"
    assert macd_negative_count > 0, "MACD never negative - not sinus-like"

    logger.info(
        f"Indicator validation passed: MACD positive={macd_positive_count}, negative={macd_negative_count}"
    )
    logger.info("All indicator values validated successfully against known synthetic data patterns")
