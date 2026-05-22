"""Tests for SymbolPriceStatistics — get_avg_price must never return None."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.domain.strategies.price_statistics import SymbolPriceStatistics


class TestGetAvgPriceNeverReturnsNone:
    """get_avg_price must always return Decimal, never None."""

    def test_no_data_for_symbol_returns_zero(self) -> None:
        """No buffer exists for the symbol → Decimal('0')."""
        stats = SymbolPriceStatistics()
        result = stats.get_avg_price("UNKNOWN/USDC", "day")
        assert result == Decimal("0")

    def test_no_data_for_symbol_week_window(self) -> None:
        """No buffer exists for the symbol, week window → Decimal('0')."""
        stats = SymbolPriceStatistics()
        result = stats.get_avg_price("UNKNOWN/USDC", "week")
        assert result == Decimal("0")

    def test_empty_buffer_returns_zero(self) -> None:
        """Buffer exists but has no prices → Decimal('0')."""
        stats = SymbolPriceStatistics()
        stats.load_historical_prices("ETH/USDC", [])
        result = stats.get_avg_price("ETH/USDC", "day")
        assert result == Decimal("0")

    def test_buffer_with_prices_returns_average(self) -> None:
        """Buffer has prices → returns computed average."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        prices = [(now - timedelta(hours=i), Decimal(str(100 - i))) for i in range(24)]
        stats.load_historical_prices("BTC/USDC", prices, now=now)

        avg = stats.get_avg_price("BTC/USDC", "day")
        assert avg is not None
        assert avg > Decimal("0")
        # average of 100, 99, ..., 77 ≈ 88.5
        assert 80 < avg < 100

    def test_week_average_with_partial_data(self) -> None:
        """Only 3 days of data → returns average of available samples, not None."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        prices = [(now - timedelta(hours=i), Decimal("100")) for i in range(72)]
        stats.load_historical_prices("BTC/USDC", prices, now=now)

        avg = stats.get_avg_price("BTC/USDC", "week")
        assert avg is not None
        assert avg == Decimal("100")

    def test_single_price_returns_that_price(self) -> None:
        """Single price sample → returns that price."""
        stats = SymbolPriceStatistics()
        stats.record_price("BTC/USDC", Decimal("42000"), datetime.now(UTC))
        stats.refresh(datetime.now(UTC))

        avg = stats.get_avg_price("BTC/USDC", "day")
        assert avg == Decimal("42000")

    def test_cached_avg_persists_after_refresh(self) -> None:
        """Average persists when cache is still valid."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        prices = [(now - timedelta(hours=i), Decimal("100")) for i in range(100)]
        stats.load_historical_prices("BTC/USDC", prices, now=now)

        avg1 = stats.get_avg_price("BTC/USDC", "day")

        # Add more price data but cache is still valid
        stats.record_price("BTC/USDC", Decimal("200"), now)
        avg2 = stats.get_avg_price("BTC/USDC", "day")

        assert avg1 == avg2

    def test_multiple_symbols_isolated(self) -> None:
        """Each symbol has independent averages."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        stats.load_historical_prices(
            "BTC/USDC", [(now, Decimal("50000"))], now=now
        )
        stats.load_historical_prices(
            "ETH/USDC", [(now, Decimal("3000"))], now=now
        )

        assert stats.get_avg_price("BTC/USDC", "day") == Decimal("50000")
        assert stats.get_avg_price("ETH/USDC", "day") == Decimal("3000")

    def test_invalid_window_raises_value_error(self) -> None:
        """Invalid window parameter raises ValueError, never returns None."""
        stats = SymbolPriceStatistics()
        with pytest.raises(ValueError, match="Unknown window"):
            stats.get_avg_price("BTC/USDC", "month")

    def test_load_historical_prices_twice_skips_second(self) -> None:
        """Second call to load_historical_prices for same symbol is idempotent."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        stats.load_historical_prices(
            "BTC/USDC", [(now, Decimal("50000"))], now=now
        )
        stats.load_historical_prices(
            "BTC/USDC", [(now, Decimal("99999"))], now=now
        )

        # Should have first load's value
        assert stats.get_avg_price("BTC/USDC", "day") == Decimal("50000")

    def test_refresh_updates_after_cache_expiry(self) -> None:
        """Forcing a refresh with later time updates the cached average."""
        stats = SymbolPriceStatistics()
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        prices = [(start + timedelta(hours=i), Decimal("100")) for i in range(24)]
        stats.load_historical_prices("BTC/USDC", prices, now=start)

        avg_before = stats.get_avg_price("BTC/USDC", "day")
        assert avg_before == Decimal("100")

        # Add new prices and refresh with time well past cache expiry
        later = start + timedelta(hours=2)
        stats.record_price("BTC/USDC", Decimal("200"), later)
        stats.refresh(later)

        avg_after = stats.get_avg_price("BTC/USDC", "day")
        # avg should now include the new price
        assert avg_after is not None
        assert avg_after > avg_before


class TestGetAvgPriceWithPartialData:
    """When the cache is empty but price data exists, compute from available data."""

    def test_two_hours_of_data_computes_day_avg(self) -> None:
        """Only 2 hours of data → 'day' returns the average of those 2 hours, not 0."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        prices = [(now - timedelta(minutes=i), Decimal(str(100 + i))) for i in range(120)]
        stats.load_historical_prices("BTC/USDC", prices, now=now)

        avg = stats.get_avg_price("BTC/USDC", "day")
        assert avg > Decimal("0")

    def test_record_without_refresh_falls_back_to_available_data(self) -> None:
        """record_price without refresh → cache is None → computes from buffer."""
        stats = SymbolPriceStatistics()
        stats.record_price("BTC/USDC", Decimal("50000"), datetime.now(UTC))
        stats.record_price("BTC/USDC", Decimal("51000"), datetime.now(UTC))

        avg = stats.get_avg_price("BTC/USDC", "day")
        assert avg == Decimal("50500")

    def test_week_average_from_three_days_of_data(self) -> None:
        """Only 3 days of data → 'week' returns average of those 3 days, not 0."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        prices = [(now - timedelta(hours=i), Decimal(str(100))) for i in range(72)]
        stats.load_historical_prices("BTC/USDC", prices, now=now)

        avg = stats.get_avg_price("BTC/USDC", "week")
        assert avg == Decimal("100")

    def test_partial_data_single_price(self) -> None:
        """Single recorded price without refresh → returns that price."""
        stats = SymbolPriceStatistics()
        stats.record_price("BTC/USDC", Decimal("42000"), datetime.now(UTC))

        avg = stats.get_avg_price("BTC/USDC", "day")
        assert avg == Decimal("42000")

    def test_multiple_prices_uneven_average(self) -> None:
        """Multiple prices with different values → returns correct average."""
        stats = SymbolPriceStatistics()
        now = datetime.now(UTC)
        for i in range(1, 11):
            stats.record_price("BTC/USDC", Decimal(str(1000 * i)), now)

        avg = stats.get_avg_price("BTC/USDC", "day")
        # average of 1000, 2000, ..., 10000 = 5500
        assert avg == Decimal("5500")
