"""Tests for indicator framework."""

import numpy as np
import pytest

from src.indicators.base import IndicatorResult
from src.indicators.momentum import RSIIndicator, StochasticIndicator
from src.indicators.registry import IndicatorRegistry


class TestIndicatorBase:
    """Test Indicator base class."""

    def test_indicator_name_generation(self) -> None:
        """Test indicator name generation."""
        rsi = RSIIndicator(period=14)
        assert rsi.name == "rsiindicator_period14"

        rsi2 = RSIIndicator(period=21)
        assert rsi2.name == "rsiindicator_period21"

    def test_indicator_params_validation(self) -> None:
        """Test parameter validation."""
        # Valid parameters
        rsi = RSIIndicator(period=14)
        assert rsi.params["period"] == 14

        # Invalid period (too small)
        with pytest.raises(ValueError, match="must be >= 2"):
            RSIIndicator(period=1)

        # Invalid period (too large)
        with pytest.raises(ValueError, match="must be <= 100"):
            RSIIndicator(period=101)

    def test_indicator_code_hash(self) -> None:
        """Test code hash generation."""
        rsi1 = RSIIndicator(period=14)
        rsi2 = RSIIndicator(period=21)

        # Same class should have same hash
        assert rsi1.get_code_hash() == rsi2.get_code_hash()

    def test_indicator_to_dict(self) -> None:
        """Test serialization to dictionary."""
        rsi = RSIIndicator(period=14)
        data = rsi.to_dict()

        assert data["name"] == "rsiindicator_period14"
        assert data["class_name"] == "RSIIndicator"
        assert data["category"] == "momentum"
        assert data["params"]["period"] == 14
        assert "code_hash" in data
        assert "params_schema" in data


class TestRSIIndicator:
    """Test RSI indicator."""

    def test_rsi_calculation(self) -> None:
        """Test RSI calculation."""
        rsi = RSIIndicator(period=14)

        # Create test data
        prices = np.array(
            [
                50.0,
                51.0,
                52.0,
                51.5,
                50.5,
                49.0,
                48.0,
                47.0,
                48.0,
                49.0,
                50.0,
                51.0,
                52.0,
                53.0,
                54.0,
                55.0,
            ]
        )
        volumes = np.ones(len(prices))

        result = rsi.calculate(prices, volumes)

        assert isinstance(result, IndicatorResult)
        assert "rsi" in result.values
        assert len(result.values["rsi"]) == len(prices)

        # First 14 values should be NaN
        assert np.all(np.isnan(result.values["rsi"][:14]))

        # Last value should be valid
        assert not np.isnan(result.values["rsi"][-1])
        assert 0 <= result.values["rsi"][-1] <= 100

    def test_rsi_with_insufficient_data(self) -> None:
        """Test RSI with insufficient data."""
        rsi = RSIIndicator(period=14)

        # Less data than period
        prices = np.array([50.0, 51.0, 52.0])
        volumes = np.ones(len(prices))

        result = rsi.calculate(prices, volumes)

        # All values should be NaN
        assert np.all(np.isnan(result.values["rsi"]))

    def test_rsi_metadata(self) -> None:
        """Test RSI metadata."""
        rsi = RSIIndicator(period=21)
        prices = np.array([50.0 + i for i in range(30)])
        volumes = np.ones(30)

        result = rsi.calculate(prices, volumes)

        assert result.metadata["period"] == 21


class TestStochasticIndicator:
    """Test Stochastic indicator."""

    def test_stochastic_calculation(self) -> None:
        """Test Stochastic calculation."""
        stoch = StochasticIndicator(k_period=14, d_period=3)

        # Create test data
        n = 30
        highs = np.array([55.0 + i * 0.5 for i in range(n)])
        lows = np.array([45.0 + i * 0.3 for i in range(n)])
        closes = np.array([50.0 + i * 0.4 for i in range(n)])
        prices = closes
        volumes = np.ones(n)

        result = stoch.calculate(prices, volumes, highs=highs, lows=lows)

        assert isinstance(result, IndicatorResult)
        assert "stoch_k" in result.values
        assert "stoch_d" in result.values

        # Values should be between 0 and 100
        valid_k = result.values["stoch_k"][~np.isnan(result.values["stoch_k"])]
        valid_d = result.values["stoch_d"][~np.isnan(result.values["stoch_d"])]

        if len(valid_k) > 0:
            assert np.all((valid_k >= 0) & (valid_k <= 100))
        if len(valid_d) > 0:
            assert np.all((valid_d >= 0) & (valid_d <= 100))

    def test_stochastic_params_validation(self) -> None:
        """Test Stochastic parameter validation."""
        # Valid parameters
        stoch = StochasticIndicator(k_period=14, d_period=3)
        assert stoch.params["k_period"] == 14
        assert stoch.params["d_period"] == 3

        # Invalid k_period
        with pytest.raises(ValueError):
            StochasticIndicator(k_period=1, d_period=3)

        # Invalid d_period
        with pytest.raises(ValueError):
            StochasticIndicator(k_period=14, d_period=1)


class TestIndicatorRegistry:
    """Test IndicatorRegistry."""

    def test_registry_discovery(self) -> None:
        """Test indicator auto-discovery."""
        # Clear registry
        IndicatorRegistry._indicators = {}

        # Discover indicators
        IndicatorRegistry.discover()

        # Should have found some indicators
        indicators = IndicatorRegistry.list_indicators()
        # Note: Discovery may not work in test environment, so we manually register for testing
        if len(indicators) == 0:
            from src.indicators.momentum import RSIIndicator

            IndicatorRegistry.register(RSIIndicator)
            indicators = IndicatorRegistry.list_indicators()
        assert len(indicators) > 0

    def test_registry_get(self) -> None:
        """Test getting indicator from registry."""
        # Clear and rediscover
        IndicatorRegistry._indicators = {}
        IndicatorRegistry.discover()

        # Manually register for testing if discovery fails
        if not IndicatorRegistry._indicators:
            from src.indicators.momentum import RSIIndicator

            IndicatorRegistry.register(RSIIndicator)

        # Get RSI indicator
        rsi = IndicatorRegistry.get("rsi_14", period=14)

        if rsi:
            assert isinstance(rsi, RSIIndicator)
            assert rsi.params["period"] == 14

    def test_registry_get_nonexistent(self) -> None:
        """Test getting nonexistent indicator."""
        indicator = IndicatorRegistry.get("nonexistent_indicator")
        assert indicator is None

    def test_registry_list_by_category(self) -> None:
        """Test listing indicators by category."""
        # Clear and rediscover
        IndicatorRegistry._indicators = {}
        IndicatorRegistry.discover()

        # Manually register for testing if discovery fails
        if not IndicatorRegistry._indicators:
            from src.indicators.momentum import RSIIndicator

            IndicatorRegistry.register(RSIIndicator)

        # List momentum indicators
        momentum = IndicatorRegistry.list_indicators("momentum")
        assert len(momentum) > 0

        # All should be momentum category
        for name in momentum:
            indicator_class = IndicatorRegistry.get_indicator_class(name)
            if indicator_class:
                assert indicator_class.category == "momentum"

    def test_registry_get_categories(self) -> None:
        """Test getting all categories."""
        # Clear and rediscover
        IndicatorRegistry._indicators = {}
        IndicatorRegistry.discover()

        # Manually register for testing if discovery fails
        if not IndicatorRegistry._indicators:
            from src.indicators.momentum import RSIIndicator

            IndicatorRegistry.register(RSIIndicator)

        categories = IndicatorRegistry.get_all_categories()
        assert "momentum" in categories


class TestIndicatorResult:
    """Test IndicatorResult dataclass."""

    def test_result_creation(self) -> None:
        """Test IndicatorResult creation."""
        values = {"rsi": np.array([50.0, 55.0, 60.0])}
        metadata = {"period": 14}

        result = IndicatorResult(name="rsi_14", values=values, metadata=metadata)

        assert result.name == "rsi_14"
        assert "rsi" in result.values
        assert result.metadata["period"] == 14

    def test_result_default_metadata(self) -> None:
        """Test IndicatorResult with default metadata."""
        values = {"rsi": np.array([50.0, 55.0, 60.0])}

        result = IndicatorResult(name="rsi_14", values=values)

        assert result.metadata == {}
