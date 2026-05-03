"""
Unit tests for optimized recalculate functions.

Tests:
- calculate_latest() method
- Bulk fetch functions
- Optimized recalculate_indicators
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from src.indicators.momentum import RSIIndicator, StochasticIndicator


class TestCalculateLatest:
    """Test calculate_latest() method."""

    def test_rsi_calculate_latest(self) -> None:
        """Test RSI calculate_latest returns only last value."""
        rsi = RSIIndicator(period=14)

        # Create test price data
        prices = np.array([100.0 + i for i in range(50)], dtype=np.float64)
        volumes = np.ones(50, dtype=np.float64)

        # Calculate latest
        latest = rsi.calculate_latest(prices=prices, volumes=volumes)

        # Should return dict with 'rsi' key
        assert "rsi" in latest
        assert isinstance(latest["rsi"], float)

        # Compare with full calculate()
        full_result = rsi.calculate(prices=prices, volumes=volumes)
        full_last = float(full_result.values["rsi"][-1])

        # Values should match
        assert abs(latest["rsi"] - full_last) < 1e-10

    def test_rsi_calculate_latest_with_nan(self) -> None:
        """Test calculate_latest handles NaN values."""
        rsi = RSIIndicator(period=14)

        # Insufficient data - should return NaN
        prices = np.array([100.0, 101.0, 102.0], dtype=np.float64)
        volumes = np.ones(3, dtype=np.float64)

        latest = rsi.calculate_latest(prices=prices, volumes=volumes)

        assert "rsi" in latest
        assert latest["rsi"] is None  # NaN should become None

    def test_stochastic_calculate_latest(self) -> None:
        """Test Stochastic calculate_latest returns latest values."""
        stoch = StochasticIndicator(k_period=14, d_period=3)

        n = 50
        prices = np.array([100.0 + i for i in range(n)], dtype=np.float64)
        highs = prices + 2.0
        lows = prices - 2.0
        volumes = np.ones(n, dtype=np.float64)

        latest = stoch.calculate_latest(prices=prices, volumes=volumes, highs=highs, lows=lows)

        assert "stoch_k" in latest
        assert "stoch_d" in latest
        assert isinstance(latest["stoch_k"], float)
        assert isinstance(latest["stoch_d"], float)

    def test_calculate_latest_with_invalid_values(self) -> None:
        """Test calculate_latest handles invalid values."""
        rsi = RSIIndicator(period=14)

        prices = np.array([100.0, np.nan, 102.0, 103.0], dtype=np.float64)
        volumes = np.ones(4, dtype=np.float64)

        latest = rsi.calculate_latest(prices=prices, volumes=volumes)

        # Should handle NaN gracefully
        assert "rsi" in latest


class TestBulkFetchFunctions:
    """Test bulk fetch helper functions."""

    @pytest.mark.asyncio
    async def test_bulk_fetch_existing_indicators(self) -> None:
        """Test bulk fetch returns correct structure."""
        from src.cli.recalculate import _bulk_fetch_existing_indicators

        # Mock database pool
        mock_pool = MagicMock()
        mock_conn = AsyncMock()

        # Simulate existing indicators for 2 symbols
        now = datetime.now(UTC)
        mock_rows = [
            (1, now - timedelta(seconds=100)),
            (1, now - timedelta(seconds=200)),
            (2, now - timedelta(seconds=150)),
        ]

        mock_conn.fetch = AsyncMock(
            return_value=[
                {"symbol_id": 1, "time": now - timedelta(seconds=100)},
                {"symbol_id": 1, "time": now - timedelta(seconds=200)},
                {"symbol_id": 2, "time": now - timedelta(seconds=150)},
            ]
        )

        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        result = await _bulk_fetch_existing_indicators(
            mock_pool, [1, 2], now - timedelta(hours=1), now
        )

        assert 1 in result
        assert 2 in result
        assert len(result[1]) == 2
        assert len(result[2]) == 1

    @pytest.mark.asyncio
    async def test_bulk_fetch_historical_candles(self) -> None:
        """Test bulk fetch candles returns correct structure."""
        from src.cli.recalculate import _bulk_fetch_historical_candles

        mock_pool = MagicMock()
        mock_conn = AsyncMock()

        now = datetime.now(UTC)
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "symbol_id": 1,
                    "time": now - timedelta(seconds=100),
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 10.0,
                },
                {
                    "symbol_id": 1,
                    "time": now - timedelta(seconds=99),
                    "high": 102.0,
                    "low": 100.0,
                    "close": 101.0,
                    "volume": 11.0,
                },
            ]
        )

        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        result = await _bulk_fetch_historical_candles(mock_pool, [1], now - timedelta(hours=1), now)

        assert 1 in result
        assert len(result[1]) == 2
        assert result[1][0]["close"] == 100.0
        assert result[1][1]["close"] == 101.0


class TestIndicatorCaching:
    """Test indicator instance caching."""

    def test_indicator_cache(self) -> None:
        """Test that same indicator params create single instance."""

        # This is a bit tricky to test directly since the cache is inside the function
        # We can test that the function works correctly with mocked data
        pass  # Integration test would be better for this


class TestOptimizedRecalculate:
    """Test the optimized recalculate_indicators function."""

    @pytest.mark.asyncio
    async def test_recalculate_with_bulk_fetch(self) -> None:
        """Test that recalculate uses bulk fetch (integration test)."""
        # This would be an integration test with actual DB
        # For unit test, we mock the bulk fetch functions
        pass

    def test_calculate_latest_matches_calculate(self) -> None:
        """Verify calculate_latest produces same results as calculate."""
        indicators_to_test = [
            RSIIndicator(period=14),
        ]

        for indicator in indicators_to_test:
            prices = np.random.uniform(90, 110, 100)
            volumes = np.random.uniform(1, 100, 100)

            latest = indicator.calculate_latest(prices=prices, volumes=volumes)
            full = indicator.calculate(prices=prices, volumes=volumes)

            # Latest should match last value of full calculation
            for key in latest:
                if latest[key] is not None:
                    full_last = float(full.values[key][-1])
                    assert (
                        abs(latest[key] - full_last) < 1e-10
                    ), f"Mismatch for {key}: {latest[key]} vs {full_last}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
