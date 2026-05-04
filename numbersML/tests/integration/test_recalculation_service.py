#!/usr/bin/env python3
"""
Integration test for recalculation service.

Tests the complete chain from synthetic data generation through indicator calculation
with deterministic results and comprehensive validation.
Uses consolidated fixtures from conftest.py.
"""

import logging
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

logger = logging.getLogger(__name__)


class TestRecalculationIntegration:
    """Integration test for recalculation service."""

    async def run_recalculation(self, from_time: datetime) -> subprocess.CompletedProcess:
        """Run the recalculation CLI."""
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

    async def validate_row_counts(self, conn, symbol_id: int):
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

    async def validate_time_alignment(self, conn, symbol_id: int):
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

    async def validate_indicator_values(self, conn, symbol_id: int):
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

    @pytest.mark.integration
    async def test_full_recalculation_chain(self, db_pool, test_usdt_with_candles):
        """Test the complete recalculation chain from data generation to validation."""
        symbol_id, min_time = test_usdt_with_candles

        # Run recalculation
        result = await self.run_recalculation(min_time)

        # Check that recalculation succeeded
        assert result.returncode == 0, f"Recalculation failed: {result.stderr}"

        # Validate results
        async with db_pool.acquire() as conn:
            await self.validate_row_counts(conn, symbol_id)
            await self.validate_time_alignment(conn, symbol_id)
            await self.validate_indicator_values(conn, symbol_id)

        logger.info("Full recalculation chain test completed successfully")

    @pytest.mark.integration
    async def test_deterministic_results(self, db_pool, test_usdt_with_candles):
        """Test that results are deterministic across multiple runs."""
        symbol_id, min_time = test_usdt_with_candles

        # Run recalculation twice
        result1 = await self.run_recalculation(min_time)
        result2 = await self.run_recalculation(min_time)

        assert result1.returncode == 0, f"First run failed: {result1.stderr}"
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"

        # Get indicator values from both runs (should be identical)
        async with db_pool.acquire() as conn:
            indicators1 = await conn.fetch(
                "SELECT time, values FROM candle_indicators WHERE symbol_id = $1 ORDER BY time",
                symbol_id,
            )

            # Clear and run again
            await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
            result3 = await self.run_recalculation(min_time)

            assert result3.returncode == 0, f"Third run failed: {result3.stderr}"

            indicators3 = await conn.fetch(
                "SELECT time, values FROM candle_indicators WHERE symbol_id = $1 ORDER BY time",
                symbol_id,
            )

            # Compare results
            assert len(indicators1) == len(indicators3), "Different number of indicator rows"

            for i, (row1, row3) in enumerate(zip(indicators1, indicators3)):
                assert row1["time"] == row3["time"], f"Time mismatch at row {i}"
                assert row1["values"] == row3["values"], f"Values mismatch at row {i}"

        logger.info("Deterministic results test passed")

    @pytest.mark.integration
    async def test_indicator_validation(self, db_pool, test_usdt_with_candles):
        """Test specific indicator validation scenarios."""
        symbol_id, min_time = test_usdt_with_candles

        # Run recalculation
        result = await self.run_recalculation(min_time)
        assert result.returncode == 0, f"Recalculation failed: {result.stderr}"

        # Test specific indicators
        async with db_pool.acquire() as conn:
            await self.validate_indicator_values(conn, symbol_id)

            # Additional validation: check for NaN or infinite values
            invalid_rows = await conn.fetch(
                """
                SELECT time, values
                FROM candle_indicators
                WHERE symbol_id = $1
                AND (
                    values::text LIKE '%NaN%' OR
                    values::text LIKE '%Infinity%' OR
                    values::text LIKE '%null%'
                )
                LIMIT 5
                """,
                symbol_id,
            )

            assert len(invalid_rows) == 0, f"Found invalid indicator values: {invalid_rows}"

        logger.info("Indicator validation test passed")

    @pytest.mark.integration
    async def test_cleanup_procedures(self, db_pool, test_usdt_symbol):
        """Test cleanup procedures work correctly."""
        symbol_id = test_usdt_symbol

        # Insert candles manually for this test
        from tests.integration.conftest import generate_deterministic_candles

        async with db_pool.acquire() as conn:
            # Clean up any existing data
            await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
            await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)

            # Insert candles
            start_time = datetime.now(UTC).replace(microsecond=0)
            rows = generate_deterministic_candles(symbol_id, start_time, 3000)

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

            # Calculate min_time (earliest candle time)
            min_time = start_time - timedelta(seconds=2999)

        # Run recalculation
        result = await self.run_recalculation(min_time)
        assert result.returncode == 0, f"Recalculation failed: {result.stderr}"

        # Verify data exists
        async with db_pool.acquire() as conn:
            candle_count = await conn.fetchval(
                "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
            )
            indicator_count = await conn.fetchval(
                "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1", symbol_id
            )

            assert candle_count > 0, "No candles found before cleanup"
            assert indicator_count > 0, "No indicators found before cleanup"

            # Perform cleanup (simulating test cleanup)
            await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
            await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
            await conn.execute(
                "UPDATE symbols SET is_active = false, is_allowed = false WHERE symbol = $1",
                "TEST/USDT",
            )

            # Verify cleanup worked
            candle_count_after = await conn.fetchval(
                "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
            )
            indicator_count_after = await conn.fetchval(
                "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1", symbol_id
            )

            assert candle_count_after == 0, "Candles not cleaned up properly"
            assert indicator_count_after == 0, "Indicators not cleaned up properly"

            symbol_allowed = await conn.fetchval(
                "SELECT is_allowed FROM symbols WHERE symbol = $1", "TEST/USDT"
            )
            assert symbol_allowed is False, "Symbol not disallowed after cleanup"

        logger.info("Cleanup procedures test passed")
