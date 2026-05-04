#!/usr/bin/env python3
"""
Simplified integration test for recalculation service.

Tests the complete chain from synthetic data generation through indicator calculation
with deterministic results and comprehensive validation.
Uses consolidated fixtures from conftest.py.
"""

import logging
import subprocess
import sys
from datetime import datetime

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.integration
async def test_recalculation_service_integration(db_pool, test_usdt_with_candles):
    """Test the complete recalculation service integration."""
    symbol_id, min_time = test_usdt_with_candles

    # Run recalculation via CLI
    result = await run_recalculation(min_time)
    assert result.returncode == 0, f"Recalculation failed: {result.stderr}"

    # Validate results
    async with db_pool.acquire() as conn:
        await validate_row_counts(conn, symbol_id)
        await validate_time_alignment(conn, symbol_id)
        await validate_indicator_values(conn, symbol_id)

    logger.info("Integration test completed successfully")


async def run_recalculation(from_time: datetime) -> subprocess.CompletedProcess:
    """Run the recalculation CLI."""
    from datetime import datetime

    cmd = [
        sys.executable,
        "-m",
        "src.cli.recalculate",
        "--indicators",
        "--symbols",
        "TEST/USDT",
        "--from",
        from_time.isoformat(),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 minute timeout
    )

    return result


async def validate_row_counts(conn, symbol_id: int):
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
        import json
        values_dict = sample_row["values"]
        if isinstance(values_dict, str):
            values_dict = json.loads(values_dict)

        total_values = len(values_dict)

        # Log the indicator keys for verification
        logger.info(f"Indicator keys per candle: {total_values}")
        logger.info(f"Indicator keys: {sorted(values_dict.keys())}")

        # Validate we have a reasonable number of indicator values
        assert total_values >= 10, f"Expected at least 10 indicator values, got {total_values}"
        assert total_values <= 50, f"Expected at most 50 indicator values, got {total_values}"


async def validate_time_alignment(conn, symbol_id: int):
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


async def validate_indicator_values(conn, symbol_id: int):
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
        import json
        values = row["values"]
        if isinstance(values, str):
            values = json.loads(values)

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
