#!/usr/bin/env python3
"""
Integration test for recalculation service.

Tests the complete chain from synthetic data generation through indicator calculation
with deterministic results and comprehensive validation.
"""

import asyncio
import asyncpg
import numpy as np
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import subprocess
import sys
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Test configuration
TEST_SYMBOL = "TEST/USDT"
TEST_CANDLE_COUNT = 5000
DETERMINISTIC_SEED = 42
EXPECTED_INDICATOR_VALUES = 31  # Approximate, accounting for multi-value indicators


class TestRecalculationIntegration:
    """Integration test for recalculation service."""

    @pytest.fixture(scope="function")
    async def cleanup_test_data(self, db_pool):
        """Clean up test data before and after each test."""
        # Cleanup before test
        async with db_pool.acquire() as conn:
            # Get symbol ID if it exists
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL
            )
            
            if symbol_id:
                # Clean up existing data
                await conn.execute(
                    "DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id
                )
                await conn.execute(
                    "DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id
                )
        
        yield
        
        # Cleanup after test (data cleanup only, symbol disallowing handled by conftest)
        async with db_pool.acquire() as conn:
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL
            )
            
            if symbol_id:
                await conn.execute(
                    "DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id
                )
                await conn.execute(
                    "DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id
                )

    async def setup_test_symbol(self, conn: asyncpg.Connection) -> int:
        """Set up TEST/USDT symbol for testing."""
        # Create or update symbol
        await conn.execute(
            """
            INSERT INTO symbols (symbol, base_asset, quote_asset, tick_size, step_size, min_notional, is_active, is_allowed)
            VALUES ($1, 'TEST', 'USDT', 0.00001, 0.000001, 1.0, true, true)
            ON CONFLICT (symbol) DO UPDATE SET is_active = true, is_allowed = true
            """,
            TEST_SYMBOL,
        )
        
        symbol_id = await conn.fetchval(
            "SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL
        )
        
        if not symbol_id:
            raise ValueError(f"Failed to create symbol {TEST_SYMBOL}")
        
        return symbol_id

    def generate_deterministic_candles(self, symbol_id: int, start_time: datetime) -> List[tuple]:
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
            rows.append((
                symbol_id,
                timestamp,
                Decimal(str(round(opens[i], 5))),
                Decimal(str(round(highs[i], 5))),
                Decimal(str(round(lows[i], 5))),
                Decimal(str(round(closes[i], 5))),
                Decimal(str(round(volumes[i], 6))),
                Decimal(str(round(volumes[i] * closes[i], 6))),
                1,  # trade_count
            ))
        
        return rows

    async def insert_candles(self, conn: asyncpg.Connection, symbol_id: int) -> datetime:
        """Insert synthetic candles into database."""
        start_time = datetime.now(timezone.utc).replace(microsecond=0)
        rows = self.generate_deterministic_candles(symbol_id, start_time)
        
        # Insert in batches
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            await conn.executemany(
                """
                INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (symbol_id, time) DO NOTHING
                """,
                batch,
            )
        
        # Verify count
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
        )
        assert count == TEST_CANDLE_COUNT, f"Expected {TEST_CANDLE_COUNT} candles, got {count}"
        
        # Get time range
        time_range = await conn.fetchrow(
            """
            SELECT MIN(time) as min_time, MAX(time) as max_time 
            FROM candles_1s WHERE symbol_id = $1
            """,
            symbol_id,
        )
        
        logger.info(f"Inserted {count} candles from {time_range['min_time']} to {time_range['max_time']}")
        return time_range['min_time']

    async def run_recalculation(self, from_time: datetime) -> subprocess.CompletedProcess:
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

    async def validate_row_counts(self, conn: asyncpg.Connection, symbol_id: int):
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
        assert indicator_count == candle_count, (
            f"Expected {candle_count} indicator rows, got {indicator_count}"
        )
        
        # Get total indicator values (accounting for multi-value indicators)
        sample_row = await conn.fetchrow(
            "SELECT values FROM candle_indicators WHERE symbol_id = $1 LIMIT 1", symbol_id
        )
        
        if sample_row:
            values_dict = sample_row['values']
            total_values = len(values_dict)
            
            # Expected total values across all candles
            expected_total = candle_count * total_values
            logger.info(f"Candles: {candle_count}, Indicators per candle: {total_values}, Total values: {expected_total}")
            
            # Validate we have the expected number of values
            assert total_values >= 25, f"Expected at least 25 indicator values, got {total_values}"
            assert total_values <= 40, f"Expected at most 40 indicator values, got {total_values}"

    async def validate_time_alignment(self, conn: asyncpg.Connection, symbol_id: int):
        """Validate that candles and indicators have perfect time alignment."""
        # Get all timestamps
        candle_times = await conn.fetch(
            "SELECT time FROM candles_1s WHERE symbol_id = $1 ORDER BY time", symbol_id
        )
        indicator_times = await conn.fetch(
            "SELECT time FROM candle_indicators WHERE symbol_id = $1 ORDER BY time", symbol_id
        )
        
        assert len(candle_times) == len(indicator_times), (
            f"Candle count ({len(candle_times)}) != Indicator count ({len(indicator_times)})"
        )
        
        # Check 1:1 time alignment
        for i, (candle, indicator) in enumerate(zip(candle_times, indicator_times)):
            assert candle['time'] == indicator['time'], (
                f"Time mismatch at index {i}: candle={candle['time']}, indicator={indicator['time']}"
            )
        
        logger.info(f"Perfect time alignment validated for {len(candle_times)} timestamps")

    async def validate_indicator_values(self, conn: asyncpg.Connection, symbol_id: int):
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
            values = row['values']
            
            # Validate SMA/EMA indicators (should be around 100)
            for key in ['sma_20', 'sma_2000', 'sma_450', 'ema_12', 'ema_26', 'ema_2000', 'ema_450']:
                if key in values:
                    val = float(values[key])
                    assert 90.0 <= val <= 110.0, f"{key}={val} outside expected range [90, 110]"
            
            # Validate RSI indicators (should be 0-100)
            for key in ['rsi_14', 'rsi_54']:
                if key in values:
                    val = float(values[key])
                    assert 0.0 <= val <= 100.0, f"{key}={val} outside RSI range [0, 100]"
            
            # Validate ATR indicators (should be positive)
            for key in ['atr_14', 'atr_99', 'atr_999']:
                if key in values:
                    val = float(values[key])
                    assert 0.0 < val <= 5.0, f"{key}={val} outside ATR range (0, 5]"
            
            # Validate MACD (can be positive or negative)
            for key in ['macd_12_26_9', 'macd_120_260_29', 'macd_400_860_300']:
                if key in values:
                    macd_val = values[key]
                    if isinstance(macd_val, dict):
                        # MACD has multiple components
                        for subkey in ['macd', 'signal', 'histogram']:
                            if subkey in macd_val:
                                val = float(macd_val[subkey])
                                assert -10.0 <= val <= 10.0, f"{key}.{subkey}={val} outside MACD range [-10, 10]"
                    else:
                        val = float(macd_val)
                        assert -10.0 <= val <= 10.0, f"{key}={val} outside MACD range [-10, 10]"
            
            # Validate Bollinger Bands
            for key in ['bb_20_2', 'bb_200_2', 'bb_900_2']:
                if key in values:
                    bb_val = values[key]
                    if isinstance(bb_val, dict):
                        upper = float(bb_val.get('upper', 0))
                        middle = float(bb_val.get('middle', 0))
                        lower = float(bb_val.get('lower', 0))
                        
                        assert upper > middle > lower, f"{key} bands not in correct order: upper={upper}, middle={middle}, lower={lower}"
                        assert 90.0 <= middle <= 110.0, f"{key} middle={middle} outside expected range [90, 110]"
        
        logger.info("Indicator value ranges validated successfully")

    @pytest.mark.integration
    async def test_full_recalculation_chain(self, db_pool, allow_test_usdt):
        """Test the complete recalculation chain from data generation to validation."""
        async with db_pool.acquire() as conn:
            # 1. Symbol is already set up by allow_test_usdt fixture
            symbol_id = allow_test_usdt
            
            # 2. Insert synthetic candles
            min_time = await self.insert_candles(conn, symbol_id)
            
            # 3. Run recalculation
            result = await self.run_recalculation(min_time)
            
            # Check that recalculation succeeded
            assert result.returncode == 0, f"Recalculation failed: {result.stderr}"
            
            # 4. Validate results
            await self.validate_row_counts(conn, symbol_id)
            await self.validate_time_alignment(conn, symbol_id)
            await self.validate_indicator_values(conn, symbol_id)
        
        logger.info("Full recalculation chain test completed successfully")

    @pytest.mark.integration
    async def test_deterministic_results(self, db_pool, allow_test_usdt):
        """Test that results are deterministic across multiple runs."""
        async with db_pool.acquire() as conn:
            symbol_id = allow_test_usdt
            min_time = await self.insert_candles(conn, symbol_id)
            
            # Run recalculation twice
            result1 = await self.run_recalculation(min_time)
            result2 = await self.run_recalculation(min_time)
            
            assert result1.returncode == 0, f"First run failed: {result1.stderr}"
            assert result2.returncode == 0, f"Second run failed: {result2.stderr}"
            
            # Get indicator values from both runs (should be identical)
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
                assert row1['time'] == row3['time'], f"Time mismatch at row {i}"
                assert row1['values'] == row3['values'], f"Values mismatch at row {i}"
        
        logger.info("Deterministic results test passed")

    @pytest.mark.integration
    async def test_indicator_validation(self, db_pool, allow_test_usdt):
        """Test specific indicator validation scenarios."""
        async with db_pool.acquire() as conn:
            symbol_id = allow_test_usdt
            min_time = await self.insert_candles(conn, symbol_id)
            
            # Run recalculation
            result = await self.run_recalculation(min_time)
            assert result.returncode == 0, f"Recalculation failed: {result.stderr}"
            
            # Test specific indicators
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
    async def test_cleanup_procedures(self, db_pool, allow_test_usdt):
        """Test cleanup procedures work correctly."""
        async with db_pool.acquire() as conn:
            symbol_id = allow_test_usdt
            min_time = await self.insert_candles(conn, symbol_id)
            
            # Run recalculation
            result = await self.run_recalculation(min_time)
            assert result.returncode == 0, f"Recalculation failed: {result.stderr}"
            
            # Verify data exists
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
                TEST_SYMBOL,
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
                "SELECT is_allowed FROM symbols WHERE symbol = $1", TEST_SYMBOL
            )
            assert symbol_allowed is False, "Symbol not disallowed after cleanup"
        
        logger.info("Cleanup procedures test passed")
