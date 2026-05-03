"""
Tests for Enhanced Gap Detection and Binance REST Client.

Tests gap detection, gap filling with Binance API integration,
and rate limiting.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.services.gap_detector import (
    DataGap,
    GapDetector,
    GapFiller,
    GapFillResult,
)


class TestGapDetector:
    """Test GapDetector."""

    def test_gap_detector_initialization(self) -> None:
        """Test gap detector initializes correctly."""
        detector = GapDetector(max_gap_seconds=5)

        assert detector.max_gap_seconds == 5
        assert detector._last_tick_time == {}
        assert detector._gaps == []

    def test_start_monitoring(self) -> None:
        """Test starting to monitor a symbol."""
        detector = GapDetector()
        detector.start_monitoring(1, "BTC/USDT")

        assert 1 in detector._last_tick_time

    def test_check_tick_no_gap(self) -> None:
        """Test check_tick with no gap."""
        detector = GapDetector(max_gap_seconds=5)
        detector.start_monitoring(1, "BTC/USDT")

        # Next tick within threshold
        tick_time = datetime.now(UTC)
        gap = detector.check_tick(1, tick_time)

        assert gap is None

    def test_check_tick_gap_detected(self) -> None:
        """Test check_tick detects gap."""
        detector = GapDetector(max_gap_seconds=5)

        # First tick
        time1 = datetime.now(UTC) - timedelta(seconds=10)
        detector.check_tick(1, time1)

        # Second tick with gap
        time2 = datetime.now(UTC)
        gap = detector.check_tick(1, time2)

        assert gap is not None
        assert gap.gap_seconds > 5
        assert gap.symbol_id == 1

    def test_check_tick_critical_gap(self) -> None:
        """Test critical gap detection (>60 seconds)."""
        detector = GapDetector(max_gap_seconds=5)

        # First tick
        time1 = datetime.now(UTC) - timedelta(seconds=70)
        detector.check_tick(1, time1)

        # Second tick
        time2 = datetime.now(UTC)
        gap = detector.check_tick(1, time2)

        assert gap is not None
        assert gap.is_critical is True

    def test_get_unfilled_gaps(self) -> None:
        """Test getting unfilled gaps."""
        detector = GapDetector(max_gap_seconds=5)

        # Create gap
        time1 = datetime.now(UTC) - timedelta(seconds=10)
        detector.check_tick(1, time1)
        time2 = datetime.now(UTC)
        detector.check_tick(1, time2)

        unfilled = detector.get_unfilled_gaps()
        assert len(unfilled) == 1
        assert unfilled[0].is_filled is False

    def test_mark_gap_filled(self) -> None:
        """Test marking gap as filled."""
        detector = GapDetector(max_gap_seconds=5)

        # Create gap
        time1 = datetime.now(UTC) - timedelta(seconds=10)
        detector.check_tick(1, time1)
        time2 = datetime.now(UTC)
        gap = detector.check_tick(1, time2)

        assert gap is not None

        # Mark as filled
        detector.mark_gap_filled(gap)

        assert gap.is_filled is True
        assert gap.filled_at is not None

        # Should not appear in unfilled list
        unfilled = detector.get_unfilled_gaps()
        assert len(unfilled) == 0


class TestGapFiller:
    """Test GapFiller with Binance API integration."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    def test_gap_filler_initialization(self, mock_db_pool: MagicMock) -> None:
        """Test gap filler initializes correctly."""
        filler = GapFiller(db_pool=mock_db_pool)

        assert filler.db_pool == mock_db_pool
        assert filler.binance_api_key is None
        assert filler._rest_client is None
        assert filler._stats == {
            "gaps_filled": 0,
            "ticks_fetched": 0,
            "errors": 0,
        }

    def test_gap_filler_with_api_key(self, mock_db_pool: MagicMock) -> None:
        """Test gap filler with API key."""
        filler = GapFiller(
            db_pool=mock_db_pool,
            binance_api_key="test_api_key",
        )

        assert filler.binance_api_key == "test_api_key"

    @pytest.mark.asyncio
    async def test_fill_gap_success(self, mock_db_pool: MagicMock) -> None:
        """Test successful gap filling."""
        filler = GapFiller(db_pool=mock_db_pool)

        # Create test gap
        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=10),
            gap_end=datetime.now(UTC),
            gap_seconds=10,
        )

        # Mock REST client
        mock_trades = [
            {
                "trade_id": "123",
                "price": Decimal("50000.00"),
                "quantity": Decimal("0.001"),
                "time": datetime.now(UTC),
                "is_buyer_maker": False,
                "side": "BUY",
            }
        ]

        # Mock database
        mock_conn = AsyncMock()
        mock_conn.executemany = AsyncMock()

        acquire_ctx = MagicMock()
        acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_db_pool.acquire = MagicMock(return_value=acquire_ctx)

        # Mock _fetch_historical_data
        with patch.object(filler, "_fetch_historical_data", return_value=mock_trades):
            result = await filler.fill_gap(gap)

        assert result.success is True
        assert result.ticks_filled == 1
        assert gap.is_filled is True
        assert filler._stats["gaps_filled"] == 1

    @pytest.mark.asyncio
    async def test_fill_gap_no_data(self, mock_db_pool: MagicMock) -> None:
        """Test gap filling with no data available."""
        filler = GapFiller(db_pool=mock_db_pool)

        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=10),
            gap_end=datetime.now(UTC),
            gap_seconds=10,
        )

        # Mock _fetch_historical_data to return empty
        with patch.object(filler, "_fetch_historical_data", return_value=[]):
            result = await filler.fill_gap(gap)

        assert result.success is False
        assert result.ticks_filled == 0
        assert result.error == "No historical data found"

    @pytest.mark.asyncio
    async def test_fill_gap_error(self, mock_db_pool: MagicMock) -> None:
        """Test gap filling with error."""
        filler = GapFiller(db_pool=mock_db_pool)

        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=10),
            gap_end=datetime.now(UTC),
            gap_seconds=10,
        )

        # Mock _fetch_historical_data to raise error
        with patch.object(filler, "_fetch_historical_data", side_effect=Exception("API error")):
            result = await filler.fill_gap(gap)

        assert result.success is False
        assert result.ticks_filled == 0
        assert "API error" in result.error
        assert filler._stats["errors"] == 1

    @pytest.mark.asyncio
    async def test_fill_gaps_batch(self, mock_db_pool: MagicMock) -> None:
        """Test batch gap filling."""
        filler = GapFiller(db_pool=mock_db_pool)

        # Create test gaps
        gaps = [
            DataGap(
                symbol_id=1,
                symbol="BTC/USDT",
                gap_start=datetime.now(UTC) - timedelta(seconds=10),
                gap_end=datetime.now(UTC),
                gap_seconds=10,
            ),
            DataGap(
                symbol_id=2,
                symbol="ETH/USDT",
                gap_start=datetime.now(UTC) - timedelta(seconds=15),
                gap_end=datetime.now(UTC),
                gap_seconds=15,
            ),
        ]

        # Mock database
        mock_conn = AsyncMock()
        mock_conn.executemany = AsyncMock()

        acquire_ctx = MagicMock()
        acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_db_pool.acquire = MagicMock(return_value=acquire_ctx)

        # Mock _fetch_historical_data
        async def mock_fetch(symbol, start, end):
            return [
                {
                    "trade_id": "123",
                    "price": Decimal("50000.00"),
                    "quantity": Decimal("0.001"),
                    "time": datetime.now(UTC),
                    "is_buyer_maker": False,
                    "side": "BUY",
                }
            ]

        with patch.object(filler, "_fetch_historical_data", mock_fetch):
            results = await filler.fill_gaps_batch(gaps, max_concurrent=2)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert filler._stats["gaps_filled"] == 2

    def test_get_stats(self, mock_db_pool: MagicMock) -> None:
        """Test getting statistics."""
        filler = GapFiller(db_pool=mock_db_pool)
        filler._stats = {
            "gaps_filled": 5,
            "ticks_fetched": 1000,
            "errors": 1,
        }

        stats = filler.get_stats()

        assert stats["gaps_filled"] == 5
        assert stats["ticks_fetched"] == 1000
        assert stats["errors"] == 1


class TestDataGap:
    """Test DataGap dataclass."""

    def test_data_gap_creation(self) -> None:
        """Test creating data gap."""
        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=10),
            gap_end=datetime.now(UTC),
            gap_seconds=10,
        )

        assert gap.symbol_id == 1
        assert gap.symbol == "BTC/USDT"
        assert gap.gap_seconds == 10
        assert gap.is_filled is False
        assert gap.is_critical is False  # < 60 seconds

    def test_data_gap_critical(self) -> None:
        """Test critical gap detection."""
        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=70),
            gap_end=datetime.now(UTC),
            gap_seconds=70,
        )

        assert gap.is_critical is True

    def test_data_gap_not_critical(self) -> None:
        """Test non-critical gap."""
        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=30),
            gap_end=datetime.now(UTC),
            gap_seconds=30,
        )

        assert gap.is_critical is False


class TestGapFillResult:
    """Test GapFillResult dataclass."""

    def test_gap_fill_result_success(self) -> None:
        """Test successful gap fill result."""
        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=10),
            gap_end=datetime.now(UTC),
            gap_seconds=10,
        )

        result = GapFillResult(
            gap=gap,
            ticks_filled=100,
            success=True,
        )

        assert result.success is True
        assert result.ticks_filled == 100
        assert result.error is None

    def test_gap_fill_result_failure(self) -> None:
        """Test failed gap fill result."""
        gap = DataGap(
            symbol_id=1,
            symbol="BTC/USDT",
            gap_start=datetime.now(UTC) - timedelta(seconds=10),
            gap_end=datetime.now(UTC),
            gap_seconds=10,
        )

        result = GapFillResult(
            gap=gap,
            ticks_filled=0,
            success=False,
            error="API error",
        )

        assert result.success is False
        assert result.ticks_filled == 0
        assert result.error == "API error"


class TestBinanceRESTClientIntegration:
    """Integration tests for Binance REST client."""

    @pytest.mark.asyncio
    async def test_binance_rest_client_creation(self) -> None:
        """Test creating Binance REST client."""
        from src.infrastructure.exchanges.binance_rest_client import BinanceRESTClient

        client = BinanceRESTClient()

        assert client.api_key is None
        assert client.timeout == 30
        assert client._session is None

    @pytest.mark.asyncio
    async def test_binance_rest_client_with_api_key(self) -> None:
        """Test creating client with API key."""
        from src.infrastructure.exchanges.binance_rest_client import BinanceRESTClient

        client = BinanceRESTClient(api_key="test_key")

        assert client.api_key == "test_key"

    @pytest.mark.asyncio
    async def test_binance_rest_client_context_manager(self) -> None:
        """Test using client as context manager."""
        from src.infrastructure.exchanges.binance_rest_client import BinanceRESTClient

        async with BinanceRESTClient() as client:
            assert client._session is not None
            assert not client._session.closed

        # Session should be closed after context
        assert client._session is None or client._session.closed

    def test_parse_trade_data(self) -> None:
        """Test parsing trade data from Binance."""
        from src.infrastructure.exchanges.binance_rest_client import parse_trade_data

        raw_trade = {
            "a": 123456,
            "p": "50000.00",
            "q": "0.001",
            "T": 1711036800000,  # timestamp in ms
            "m": True,
        }

        parsed = parse_trade_data(raw_trade)

        assert parsed["trade_id"] == "123456"
        assert parsed["price"] == Decimal("50000.00")
        assert parsed["quantity"] == Decimal("0.001")
        assert parsed["is_buyer_maker"] is True
        assert parsed["side"] == "SELL"

    def test_parse_kline_data(self) -> None:
        """Test parsing kline data from Binance."""
        from src.infrastructure.exchanges.binance_rest_client import parse_kline_data

        raw_kline = [
            1711036800000,  # open time
            "50000.00",  # open
            "50100.00",  # high
            "49900.00",  # low
            "50050.00",  # close
            "1000.5",  # volume
            1711036860000,  # close time
            "50050000.00",  # quote volume
            12345,  # trades count
        ]

        parsed = parse_kline_data(raw_kline)

        assert parsed["open"] == Decimal("50000.00")
        assert parsed["high"] == Decimal("50100.00")
        assert parsed["low"] == Decimal("49900.00")
        assert parsed["close"] == Decimal("50050.00")
        assert parsed["volume"] == Decimal("1000.5")
        assert parsed["trades_count"] == 12345


class TestRateLimiter:
    """Test rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_requests(self) -> None:
        """Test rate limiter allows requests within limit."""
        from src.infrastructure.exchanges.binance_rest_client import RateLimiter

        limiter = RateLimiter(max_weight=1200, window_seconds=60)

        # Should allow requests initially
        await limiter.wait(weight=1)
        await limiter.wait(weight=1)
        await limiter.wait(weight=1)

        # Should not raise or block

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_excess(self) -> None:
        """Test rate limiter blocks excess requests."""
        from src.infrastructure.exchanges.binance_rest_client import RateLimiter

        limiter = RateLimiter(max_weight=10, window_seconds=60)

        # Use up tokens
        for _ in range(10):
            await limiter.wait(weight=1)

        # Next request should wait
        import time

        start = time.time()
        await limiter.wait(weight=5)
        elapsed = time.time() - start

        # Should have waited (at least a little)
        assert elapsed > 0.01
