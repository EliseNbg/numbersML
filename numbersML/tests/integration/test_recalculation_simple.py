#!/usr/bin/env python3
"""
Simplified integration test for recalculation service.

Tests the complete chain from synthetic data generation through indicator calculation
with deterministic results and comprehensive validation.
"""

import logging
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import numpy as np
import pytest

logger = logging.getLogger(__name__)

# Test configuration
TEST_SYMBOL = "TEST/USDT"
TEST_CANDLE_COUNT = 5000
DETERMINISTIC_SEED = 42


@pytest.mark.integration
async def test_recalculation_service_integration():
    """Test the complete recalculation service integration."""
    # Create database connection
    pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=2,
        max_size=10,
    )

    try:
        async with pool.acquire() as conn:
            # 1. Clean up any existing data
            await cleanup_existing_data(conn)

            # 2. Set up test symbol
            symbol_id = await setup_test_symbol(conn)

            # 3. Generate and insert synthetic candles
            min_time = await insert_synthetic_candles(conn, symbol_id)

            # 4. Run recalculation
            result = await run_recalculation(min_time)
            assert result.returncode == 0, f"Recalculation failed: {result.stderr}"

            # 5. Validate results
            await validate_row_counts(conn, symbol_id)
            await validate_time_alignment(conn, symbol_id)
            await validate_indicator_values(conn, symbol_id)

            logger.info("Integration test completed successfully")

    finally:
        # Clean up
        async with pool.acquire() as conn:
            await cleanup_existing_data(conn)
            await conn.execute(
                "UPDATE symbols SET is_active = false, is_allowed = false WHERE symbol = $1",
                TEST_SYMBOL,
            )
        await pool.close()


async def cleanup_existing_data(conn: asyncpg.Connection):
    """Clean up any existing test data."""
    symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

    if symbol_id:
        await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
        await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)


async def setup_test_symbol(conn: asyncpg.Connection) -> int:
    """Set up TEST/USDT symbol for testing."""
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

    return symbol_id


def generate_deterministic_candles(symbol_id: int, start_time: datetime) -> list[tuple]:
    """Generate deterministic synthetic candle data."""
    np.random.seed(DETERMINISTIC_SEED)

    # Generate 5000 candles going backward from start_time
    indices = np.arange(TEST_CANDLE_COUNT)

    # Base price with sine wave oscillation
    prices = 100.0 + 5.0 * np.sin(2 * np.pi * indices / (15 * 60))
    prices += np.random.normal(0, 0.1, TEST_CANDLE_COUNT)

    # Generate OHLCV values
    opens = prices + np.random.uniform(-0.05, 0.05, TEST_CANDLE_COUNT)
    highs = np.maximum(opens, prices) + np.random.uniform(0, 0.1, TEST_CANDLE_COUNT)
    lows = np.minimum(opens, prices) - np.random.uniform(0, 0.1, TEST_CANDLE_COUNT)
    closes = prices
    volumes = np.random.uniform(0.1, 10.0, TEST_CANDLE_COUNT)

    # Create rows for insertion (going backward in time)
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
    """Insert synthetic candles into database."""
    start_time = datetime.now(UTC).replace(microsecond=0)
    rows = generate_deterministic_candles(symbol_id, start_time)

    # Insert in batches
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

    # Verify count
    count = await conn.fetchval("SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id)
    assert count == TEST_CANDLE_COUNT, f"Expected {TEST_CANDLE_COUNT} candles, got {count}"

    # Get time range
    time_range = await conn.fetchrow(
        """
        SELECT MIN(time) as min_time, MAX(time) as max_time
        FROM candles_1s WHERE symbol_id = $1
        """,
        symbol_id,
    )

    logger.info(
        f"Inserted {count} candles from {time_range['min_time']} to {time_range['max_time']}"
    )
    return time_range["min_time"]


async def run_recalculation(from_time: datetime) -> subprocess.CompletedProcess:
    """Run the recalculation CLI."""
    cmd = [
        sys.executable,
        "-m",
        "src.cli.recalculate",
        "--indicators",
        "--symbols",
        TEST_SYMBOL,
        "--from",
        from_time.isoformat(),
        "--with-quality-guard",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 minute timeout
    )

    return result


async def validate_row_counts(conn: asyncpg.Connection, symbol_id: int):
    """Validate that the correct number of indicator rows were created."""
    # Get candle count
    candle_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
    )

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
            f"Candles: {candle_count}, Indicators per candle: {total_values}, Total values: {expected_total}"
        )

        # Validate we have the expected number of values
        assert total_values >= 25, f"Expected at least 25 indicator values, got {total_values}"
        assert total_values <= 40, f"Expected at most 40 indicator values, got {total_values}"


async def validate_time_alignment(conn: asyncpg.Connection, symbol_id: int):
    """Validate that candles and indicators have perfect time alignment."""
    # Get all timestamps
    candle_times = await conn.fetch(
        "SELECT time FROM candles_1s WHERE symbol_id = $1 ORDER BY time", symbol_id
    )
    indicator_times = await conn.fetch(
        "SELECT time FROM candle_indicators WHERE symbol_id = $1 ORDER BY time", symbol_id
    )

    assert len(candle_times) == len(
        indicator_times
    ), f"Candle count ({len(candle_times)}) != Indicator count ({len(indicator_times)})"

    # Check 1:1 time alignment
    for i, (candle, indicator) in enumerate(zip(candle_times, indicator_times)):
        assert (
            candle["time"] == indicator["time"]
        ), f"Time mismatch at index {i}: candle={candle['time']}, indicator={indicator['time']}"

    logger.info(f"Perfect time alignment validated for {len(candle_times)} timestamps")


async def validate_indicator_values(conn: asyncpg.Connection, symbol_id: int):
    """Validate that indicator values are within expected ranges."""
    # Get sample indicator data
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

    for row in indicators:
        values = row["values"]

        # Validate SMA/EMA indicators (should be around 100)
        for key in ["sma_20", "sma_2000", "sma_450", "ema_12", "ema_26", "ema_2000", "ema_450"]:
            if key in values:
                val = float(values[key])
                assert 90.0 <= val <= 110.0, f"{key}={val} outside expected range [90, 110]"

        # Validate RSI indicators (should be 0-100)
        for key in ["rsi_14", "rsi_54"]:
            if key in values:
                val = float(values[key])
                assert 0.0 <= val <= 100.0, f"{key}={val} outside RSI range [0, 100]"

        # Validate ATR indicators (should be positive)
        for key in ["atr_14", "atr_99", "atr_999"]:
            if key in values:
                val = float(values[key])
                assert 0.0 < val <= 5.0, f"{key}={val} outside ATR range (0, 5]"

        # Validate MACD (can be positive or negative)
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
                else:
                    val = float(macd_val)
                    assert -10.0 <= val <= 10.0, f"{key}={val} outside MACD range [-10, 10]"

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

    logger.info("Indicator value ranges validated successfully")
