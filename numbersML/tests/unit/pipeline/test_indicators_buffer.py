"""
Unit tests for IndicatorsBuffer class.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.pipeline.indicators_buffer import IndicatorsBuffer


def _make_binance_kline(
    open_time: int, o: float, h: float, lo: float, c: float, v: float
) -> list:
    """Build a Binance kline row in the raw API format."""
    return [
        open_time,
        str(o),
        str(h),
        str(lo),
        str(c),
        str(v),
        open_time + 999,
        str(v * 100.0),  # quote volume
        10,  # trades
        str(v * 60.0),  # taker buy base
        str(v * 6000.0),  # taker buy quote
        "0",
    ]


def _make_klines(count: int, start_ts: int = 1500000000000) -> list[list]:
    """Generate *count* consecutive fake Binance klines."""
    klines = []
    for i in range(count):
        close = 50000.0 + i * 0.1
        klines.append(
            _make_binance_kline(
                open_time=start_ts + i * 1000,
                o=close - 0.5,
                h=close + 0.5,
                lo=close - 1.0,
                c=close,
                v=10.0 + i * 0.01,
            )
        )
    return klines


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

    # ── helpers used by Binance-fallback tests ──────────────────────

    @staticmethod
    def _build_binance_mock(klines: list[list]):
        """Return a configured ``AsyncMock`` suitable for
        ``aiohttp.ClientSession.get``."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=klines)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_resp
        mock_session = AsyncMock()
        mock_session.get.return_value = mock_ctx
        return mock_session

    def test_initialization(self, mock_dbconn: MagicMock) -> None:
        """Test buffer initialization with correct parameters."""
        symbol = "BTC/USDC"
        max_period = 2050
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)
        assert buffer.symbol == symbol
        assert buffer.max_indicator_period == max_period
        assert buffer.closes_buff.maxlen == max_period
        assert buffer.volumes_buff.maxlen == max_period
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

        current_time = datetime(2026, 4, 27, 23, 0, 0, tzinfo=UTC)
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
        """Test initialization when not enough candles; uses partial DB + repeat."""
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

        # Mock Binance to return empty (so we fall through to partial-DB path)
        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=AsyncMock(return_value=[])):
            current_time = datetime(2026, 4, 27, 23, 0, 0, tzinfo=UTC)
            current_candle = {
                "open": 200.0,
                "high": 201.0,
                "low": 199.0,
                "close": 200.5,
                "volume": 20.0,
            }

            await buffer.initialization(current_time, current_candle)

        # Buffers should be full: 10 DB rows + 90 repeated current candle
        assert len(buffer.closes_buff) == max_period
        assert len(buffer.volumes_buff) == max_period
        # First 10 entries come from DB rows
        np.testing.assert_array_almost_equal(
            buffer.closes_buff[:10], [r["close"] for r in rows]
        )
        # Remaining 90 are the current candle repeated
        np.testing.assert_array_almost_equal(
            buffer.closes_buff[10:], np.full(90, current_candle["close"])
        )
        np.testing.assert_array_almost_equal(
            buffer.volumes_buff[10:], np.full(90, current_candle["volume"])
        )

    @pytest.mark.asyncio
    async def test_initialization_with_no_candles(self, mock_dbconn: MagicMock) -> None:
        """Test initialization when DB returns zero candles (and Binance empty)."""
        symbol = "BTC/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        mock_dbconn.fetch = AsyncMock(return_value=[])
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        # Mock Binance to return empty (so we fall through to fill-with-candle)
        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=AsyncMock(return_value=[])):
            current_time = datetime(2026, 4, 27, 23, 0, 0, tzinfo=UTC)
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
        np.testing.assert_array_almost_equal(
            buffer.volumes_buff, np.full(max_period, candle["volume"])
        )

    # ── Binance klines fallback tests ──────────────────────────────

    @pytest.mark.asyncio
    async def test_initialization_fetches_from_binance_when_db_insufficient(
        self, mock_dbconn: MagicMock
    ) -> None:
        """Binance fallback used when DB returns < max_period candles."""
        symbol = "ETH/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        # DB returns only 10 candles (insufficient)
        db_rows = [
            {"open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
             "close": 100.5 + i, "volume": 10.0 + i}
            for i in range(10)
        ]
        mock_dbconn.fetch = AsyncMock(return_value=db_rows)
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        klines = _make_klines(max_period)

        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=AsyncMock(return_value=klines)):
            current_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            current_candle = {
                "open": 200.0, "high": 201.0, "low": 199.0,
                "close": 200.5, "volume": 20.0,
            }
            await buffer.initialization(current_time, current_candle)

        assert len(buffer.closes_buff) == max_period
        # All values come from the parsed Binance klines
        expected_close = [50000.0 + i * 0.1 for i in range(max_period)]
        np.testing.assert_array_almost_equal(buffer.closes_buff, expected_close)

    @pytest.mark.asyncio
    async def test_initialization_fetches_from_binance_when_db_empty(
        self, mock_dbconn: MagicMock
    ) -> None:
        """Binance fallback used when DB returns zero candles."""
        symbol = "BTC/USDC"
        max_period = 50
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        mock_dbconn.fetch = AsyncMock(return_value=[])
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        klines = _make_klines(max_period)

        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=AsyncMock(return_value=klines)):
            current_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            current_candle = {
                "open": 200.0, "high": 201.0, "low": 199.0,
                "close": 200.5, "volume": 20.0,
            }
            await buffer.initialization(current_time, current_candle)

        assert len(buffer.closes_buff) == max_period
        expected_close = [50000.0 + i * 0.1 for i in range(max_period)]
        np.testing.assert_array_almost_equal(buffer.closes_buff, expected_close)

    @pytest.mark.asyncio
    async def test_initialization_falls_back_to_candle_when_binance_fails(
        self, mock_dbconn: MagicMock
    ) -> None:
        """Fall back to fill-with-candle when Binance API raises."""
        symbol = "BTC/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        mock_dbconn.fetch = AsyncMock(return_value=[])
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=AsyncMock(side_effect=Exception("API error"))):
            current_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            current_candle = {
                "open": 200.0, "high": 201.0, "low": 199.0,
                "close": 200.5, "volume": 20.0,
            }
            await buffer.initialization(current_time, current_candle)

        assert len(buffer.closes_buff) == max_period
        np.testing.assert_array_almost_equal(
            buffer.closes_buff, np.full(max_period, current_candle["close"])
        )

    @pytest.mark.asyncio
    async def test_initialization_falls_back_to_candle_when_binance_empty(
        self, mock_dbconn: MagicMock
    ) -> None:
        """Fall back to fill-with-candle when Binance returns empty list."""
        symbol = "BTC/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        mock_dbconn.fetch = AsyncMock(return_value=[])
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=AsyncMock(return_value=[])):
            current_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            current_candle = {
                "open": 200.0, "high": 201.0, "low": 199.0,
                "close": 200.5, "volume": 20.0,
            }
            await buffer.initialization(current_time, current_candle)

        assert len(buffer.closes_buff) == max_period
        np.testing.assert_array_almost_equal(
            buffer.closes_buff, np.full(max_period, current_candle["close"])
        )

    @pytest.mark.asyncio
    async def test_initialization_binance_insufficient_klines_falls_back(
        self, mock_dbconn: MagicMock
    ) -> None:
        """Fall back to fill-with-candle when Binance returns fewer klines than
        ``max_indicator_period`` (e.g., very new symbol with sparse history)."""
        symbol = "BTC/USDC"
        max_period = 200
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        mock_dbconn.fetch = AsyncMock(return_value=[])
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        # Binance only returns 50 klines — not enough
        klines = _make_klines(50)

        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=AsyncMock(return_value=klines)):
            current_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            current_candle = {
                "open": 200.0, "high": 201.0, "low": 199.0,
                "close": 200.5, "volume": 20.0,
            }
            await buffer.initialization(current_time, current_candle)

        # Should fall back to fill-with-candle since 50 < 200
        assert len(buffer.closes_buff) == max_period
        np.testing.assert_array_almost_equal(
            buffer.closes_buff, np.full(max_period, current_candle["close"])
        )

    @pytest.mark.asyncio
    async def test_initialization_still_uses_db_when_sufficient(
        self, mock_dbconn: MagicMock
    ) -> None:
        """When DB has enough candles, Binance fallback is NOT called."""
        symbol = "BTC/USDC"
        max_period = 100
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_period)

        rows = [
            {"open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
             "close": 100.5 + i, "volume": 10.0 + i}
            for i in range(max_period)
        ]
        mock_dbconn.fetch = AsyncMock(return_value=rows)
        mock_dbconn.fetchval = AsyncMock(return_value=42)

        binance_mock = AsyncMock()

        with patch.object(IndicatorsBuffer, "_fetch_klines_from_binance",
                          new=binance_mock):
            current_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            current_candle = {
                "open": 200.0, "high": 201.0, "low": 199.0,
                "close": 200.5, "volume": 20.0,
            }
            await buffer.initialization(current_time, current_candle)

        assert len(buffer.closes_buff) == max_period
        np.testing.assert_array_almost_equal(
            buffer.closes_buff, [r["close"] for r in rows]
        )
        # Binance should NOT have been called
        binance_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_parse_klines_to_rows(self, mock_dbconn: MagicMock) -> None:
        """Verify Binance raw kline → row dict conversion."""
        symbol = "BTC/USDC"
        buffer = IndicatorsBuffer(mock_dbconn, symbol, max_indicator_period=10)

        klines = _make_klines(3, start_ts=1500000000000)
        rows = buffer._parse_klines_to_rows(klines)

        assert len(rows) == 3
        for i, row in enumerate(rows):
            close = 50000.0 + i * 0.1
            assert row["open"] == close - 0.5
            assert row["high"] == close + 0.5
            assert row["low"] == close - 1.0
            assert row["close"] == close
            assert row["volume"] == 10.0 + i * 0.01
