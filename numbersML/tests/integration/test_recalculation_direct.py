#!/usr/bin/env python3
"""
Direct integration test for recalculation service.

Tests the recalculation by directly calling the functions instead of subprocess.
Uses consolidated fixtures from conftest.py.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.integration
async def test_recalculation_direct_integration(db_pool, test_usdt_with_candles):
    """Test the recalculation service with direct function calls."""
    symbol_id, min_time = test_usdt_with_candles

    # Run recalculation directly
    from src.cli.recalculate import recalculate_indicators

    count = await recalculate_indicators(db_pool, [symbol_id], min_time, None, with_quality_guard=False)

    logger.info(f"Recalculated {count} indicators")
    assert count > 0, "No indicators were recalculated"

    # Validate results
    async with db_pool.acquire() as conn:
        await validate_results(conn, symbol_id)

    logger.info("Direct integration test completed successfully")


@pytest.mark.integration
async def test_recalculation_skips_existing_time_ranges(db_pool, test_usdt_with_candles):
    """Test that recalculation skips time ranges where all symbols have indicators."""
    symbol_id, min_time = test_usdt_with_candles

    from src.cli.recalculate import recalculate_indicators
    from datetime import timedelta

    # Pre-calculate indicators for first 50 candles (time range [min_time, min_time + 50s))
    first_part_end = min_time + timedelta(seconds=50)

    count_first = await recalculate_indicators(
        db_pool, [symbol_id], min_time, first_part_end, with_quality_guard=False
    )
    logger.info(f"Pre-calculated {count_first} indicators for first 50 candles")

    # Verify first part has indicators
    async with db_pool.acquire() as conn:
        first_part_count = await conn.fetchval(
            "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1 AND time >= $2 AND time < $3",
            symbol_id,
            min_time,
            first_part_end,
        )
        assert first_part_count == 50, f"Expected 50 indicators in first part, got {first_part_count}"

    # Now run recalculation on full range (min_time to end)
    count_full = await recalculate_indicators(
        db_pool, [symbol_id], min_time, None, with_quality_guard=False
    )
    logger.info(f"Recalculated {count_full} indicators for full range")

    # Should have calculated indicators for remaining ~50 candles
    assert count_full >= 40, f"Expected ~50 indicators, got {count_full}"

    # Verify total indicators match total candles
    async with db_pool.acquire() as conn:
        total_indicators = await conn.fetchval(
            "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1", symbol_id
        )
        total_candles = await conn.fetchval(
            "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
        )
        assert (
            total_indicators == total_candles
        ), f"Mismatch: {total_indicators} indicators vs {total_candles} candles"

    logger.info("Skip existing time ranges test passed")


async def validate_results(conn, symbol_id: int):
    """Validate the recalculation results."""
    # Get candle count
    candle_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
    )

    # Get indicator row count
    indicator_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1", symbol_id
    )

    # Should have 1:1 mapping
    assert (
        indicator_count == candle_count
    ), f"Expected {candle_count} indicator rows, got {indicator_count}"

    # Check time alignment
    candle_times = await conn.fetch(
        "SELECT time FROM candles_1s WHERE symbol_id = $1 ORDER BY time LIMIT 10", symbol_id
    )
    indicator_times = await conn.fetch(
        "SELECT time FROM candle_indicators WHERE symbol_id = $1 ORDER BY time LIMIT 10", symbol_id
    )

    assert len(candle_times) == len(indicator_times), "Time count mismatch"

    for i, (candle, indicator) in enumerate(zip(candle_times, indicator_times, strict=True)):
        assert candle["time"] == indicator["time"], f"Time mismatch at index {i}"

    # Check indicator values exist
    sample_row = await conn.fetchrow(
        "SELECT values FROM candle_indicators WHERE symbol_id = $1 LIMIT 1", symbol_id
    )

    assert sample_row is not None, "No indicator data found"
    values = sample_row["values"]
    assert len(values) > 0, "No indicator values found"

    logger.info(
        f"Validation passed: {candle_count} candles, {indicator_count} indicators, {len(values)} values per candle"
    )
