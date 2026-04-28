"""
Unit tests for IndicatorsBuffer class.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from src.pipeline.indicators_buffer import IndicatorsBuffer


class TestIndicatorsBuffer:
    """Tests for IndicatorsBuffer."""

    @pytest.fixture
    def mock_dbconn(self) -> MagicMock:
        """Create a mock database connection."""
        conn = MagicMock()
        conn.fetch = AsyncMock()
        conn.fetchval = AsyncMock()
        return conn

    @pytest.fixture
    def mock_dbpool(self) -> MagicMock:
        """Create a mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    def test_initialization(self, mock_dbconn: MagicMock) -> None:
        """Test buffer initialization with correct parameters."""
        symbol = "BTC/USDC"
        max_period = 2050
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)
        assert buffer.symbol == symbol
        assert buffer.max_indicator_period == max_period
        assert buffer.closes_buff.maxlen == max_period
        assert buffer.volumes_buff.maxlen == max_period
        assert buffer.opens_buff.maxlen == max_period
        assert buffer.highs_buff.maxlen == max_period
        assert buffer.lows_buff.maxlen == max_period
        # Buffers should be empty initially
        assert len(buffer.closes_buff) == 0

    @pytest.mark.asyncio
    async def test_initialization_with_enough_candles(self, mock_dbconn: MagicMock) -> None:
        """Test initialization when enough historical candles exist."""
        symbol = "ETH/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        # Mock DB to return exactly max_period candles
        rows = [
            {
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 10.0 + i,
            }
            for i in range(max_period)
        ]
        mock_dbconn.fetch = AsyncMock(return_value=rows)
        mock_dbconn.fetchval = AsyncMock(return_value=42)  # symbol_id

        current_time = datetime(2026, 4, 27, 23, 0, 0, tzinfo=timezone.utc)
        current_candle = {
            "open": 200.0,
            "high": 201.0,
            "low": 199.0,
            "close": 200.5,
            "volume": 20.0,
        }

        await buffer.initialization(current_time, current_candle)

        # All buffers should be full
        assert len(buffer.closes_buff) == max_period
        assert len(buffer.volumes_buff) == max_period
        # Values should match the fetched rows (chronological order)
        np.testing.assert_array_almost_equal(buffer.closes_buff, [r["close"] for r in rows])
        np.testing.assert_array_almost_equal(buffer.volumes_buff, [r["volume"] for r in rows])
        # Symbol ID should be cached
        assert buffer._symbol_id == 42

    @pytest.mark.asyncio
    async def test_initialization_with_insufficient_candles(self, mock_dbconn: MagicMock) -> None:
        """Test initialization when not enough candles; should fill with current candle."""
        symbol = "BTC/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        # Mock DB to return only 10 candles (less than max_period)
        rows = [
            {
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 10.0 + i,
            }
            for i in range(10)
        ]
        mock_dbconn.fetch = AsyncMock(return_value=rows)
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        current_time = datetime(2026, 4, 27, 23, 0, 0, tzinfo=timezone.utc)
        current_candle = {
            "open": 200.0,
            "high": 201.0,
            "low": 199.0,
            "close": 200.5,
            "volume": 20.0,
        }

        await buffer.initialization(current_time, current_candle)

        # Buffers should be full with repeated current candle
        assert len(buffer.closes_buff) == max_period
        assert len(buffer.volumes_buff) == max_period
        # All values should be the current candle's values
        np.testing.assert_array_almost_equal(
            buffer.closes_buff, np.full(max_period, current_candle["close"])
        )
        np.testing.assert_array_almost_equal(
            buffer.volumes_buff, np.full(max_period, current_candle["volume"])
        )

    @pytest.mark.asyncio
    async def test_initialization_with_no_candles(self, mock_dbconn: MagicMock) -> None:
        """Test initialization when DB returns zero candles."""
        symbol = "BTC/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        mock_dbconn.fetch = AsyncMock(return_value=[])
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        current_time = datetime(2026, 4, 27, 23, 0, 0, tzinfo=timezone.utc)
        current_candle = {
            "open": 200.0,
            "high": 201.0,
            "low": 199.0,
            "close": 200.5,
            "volume": 20.0,
        }

        await buffer.initialization(current_time, current_candle)

        assert len(buffer.closes_buff) == max_period
        np.testing.assert_array_almost_equal(
            buffer.closes_buff, np.full(max_period, current_candle["close"])
        )

    @pytest.mark.asyncio
    async def test_add_candle(self, mock_dbconn: MagicMock) -> None:
        """Test adding a new candle to buffers."""
        symbol = "BTC/USDC"
        max_period = 5
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        # Fill buffer with some initial data
        initial_candles = [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0},
            {"open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 11.0},
        ]
        for c in initial_candles:
            await buffer.add_candle(c)

        assert len(buffer.closes_buff) == 2
        np.testing.assert_array_almost_equal(buffer.closes_buff, [100.5, 101.5])

        # Add a third candle
        new_candle = {
            "open": 102.0,
            "high": 103.0,
            "low": 101.0,
            "close": 102.5,
            "volume": 12.0,
        }
        await buffer.add_candle(new_candle)

        assert len(buffer.closes_buff) == 3
        np.testing.assert_array_almost_equal(buffer.closes_buff, [100.5, 101.5, 102.5])
        np.testing.assert_array_almost_equal(buffer.volumes_buff, [10.0, 11.0, 12.0])

    @pytest.mark.asyncio
    async def test_add_candle_exceeds_capacity(self, mock_dbconn: MagicMock) -> None:
        """Test that adding beyond capacity drops oldest values (ring buffer)."""
        symbol = "BTC/USDC"
        max_period = 3
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        # Fill buffer to capacity
        for i in range(max_period):
            await buffer.add_candle(
                {
                    "open": 100.0 + i,
                    "high": 101.0 + i,
                    "low": 99.0 + i,
                    "close": 100.5 + i,
                    "volume": 10.0 + i,
                }
            )
        assert len(buffer.closes_buff) == 3
        np.testing.assert_array_almost_equal(buffer.closes_buff, [100.5, 101.5, 102.5])

        # Add one more, oldest should be dropped
        await buffer.add_candle(
            {
                "open": 200.0,
                "high": 201.0,
                "low": 199.0,
                "close": 200.5,
                "volume": 20.0,
            }
        )
        assert len(buffer.closes_buff) == 3
        # Now buffer should contain [101.5, 102.5, 200.5]
        np.testing.assert_array_almost_equal(buffer.closes_buff, [101.5, 102.5, 200.5])

    def test_fill_with_candle_internal(self, mock_dbconn: MagicMock) -> None:
        """Test internal method that repeats a candle."""
        symbol = "BTC/USDC"
        max_period = 7
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        candle = {
            "open": 50.0,
            "high": 51.0,
            "low": 49.0,
            "close": 50.5,
            "volume": 5.0,
        }
        buffer._fill_with_candle(candle)

        assert len(buffer.closes_buff) == max_period
        np.testing.assert_array_almost_equal(
            buffer.closes_buff, np.full(max_period, candle["close"])
        )
        np.testing.assert_array_almost_equal(buffer.opens_buff, np.full(max_period, candle["open"]))
        np.testing.assert_array_almost_equal(
            buffer.volumes_buff, np.full(max_period, candle["volume"])
        )
