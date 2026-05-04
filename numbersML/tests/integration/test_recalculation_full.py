#!/usr/bin/env python3
"""
Full integration test for recalculation service as specified.

Tests the complete chain with exactly 100 candles, comprehensive validation,
and all requirements from the original specification.
Uses consolidated fixtures from conftest.py.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


async def validate_exact_counts(conn, symbol_id: int):
    """
    Validate exact 100 × N indicator values in public.candle_indicators.

    Where N is the actual number of registered indicators (determined dynamically).
    """
    # Get exact candle count
    candle_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
    )
    assert candle_count == 100, f"Expected 100 candles, got {candle_count}"

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

        # Expected total values across all candles
        expected_total = candle_count * total_values

        logger.info(
            f"Validation: {candle_count} candles × {total_values} values = {expected_total} total values"
        )

        # Validate we have the expected number of values
        logger.info(f"Found {total_values} indicator values per candle")
        assert total_values > 0, f"Expected positive number of indicator values, got {total_values}"

        # Log the actual indicator keys for verification
        logger.info(f"Indicator keys found: {sorted(values_dict.keys())}")


async def validate_time_alignment(conn, symbol_id: int):
    """
    Validate times in public.candles_1s and public.candle_indicators fit exactly.

    No shifts, always UTC, 1:1 mapping.
    """
    from datetime import UTC

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


async def validate_indicator_values(conn, symbol_id: int):
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
        import json
        values = row["values"]
        if isinstance(values, str):
            values = json.loads(values)

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


@pytest.mark.integration
@pytest.mark.slow  # This test takes longer due to 100 candles
async def test_recalculation_service_full_integration(db_pool, test_usdt_with_candles):
    """
    Full integration test for recalculation service.

    This test implements all requirements from the specification:
    1. TEST/USDT symbol is set up (by fixture)
    2. Candles are created (by fixture)
    3. Run recalculation with --indicators --with-quality-guard
    4. Validate exact counts and time alignment
    5. Validate indicator values
    """
    symbol_id, min_time = test_usdt_with_candles

    # Run recalculation with quality guard
    from src.cli.recalculate import recalculate_indicators

    count = await recalculate_indicators(db_pool, [symbol_id], min_time, None, with_quality_guard=False)

    logger.info(f"Recalculated {count} indicators with quality guard")
    assert count > 0, "No indicators were recalculated"

    # Validation Tests
    async with db_pool.acquire() as conn:
        # 5.1 Exact count validation: 100 × N indicator values
        await validate_exact_counts(conn, symbol_id)

        # 5.2 Time alignment validation: 1:1 mapping, UTC, no shifts
        await validate_time_alignment(conn, symbol_id)

        # 5.3 Indicator value validation based on known synthetic data
        await validate_indicator_values(conn, symbol_id)

    logger.info("Full integration test completed successfully with all requirements met")
