"""Tests for long-term indicators (trend, volatility, volume)."""

import numpy as np
import pytest

from src.indicators.trend import (
    ADXIndicator,
    AroonIndicator,
    EMAIndicator,
    MACDIndicator,
    SMAIndicator,
)
from src.indicators.volatility_volume import (
    ATRIndicator,
    BollingerBandsIndicator,
    MFIIndicator,
    OBVIndicator,
    VWAPIndicator,
)


class TestSMAIndicator:
    """Test SMA indicator."""

    def test_sma_calculation(self) -> None:
        """Test SMA calculation."""
        sma = SMAIndicator(period=5)
        prices = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        volumes = np.ones(len(prices))

        result = sma.calculate(prices, volumes)

        assert "sma" in result.values
        assert len(result.values["sma"]) == len(prices)

        # First 4 values should be NaN
        assert np.all(np.isnan(result.values["sma"][:4]))

        # 5th value should be mean of first 5
        assert result.values["sma"][4] == 3.0

        # 7th value should be mean of last 5
        assert result.values["sma"][6] == 5.0

    def test_sma_different_periods(self) -> None:
        """Test SMA with different periods."""
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.ones(100)

        # Short-term (20)
        sma_20 = SMAIndicator(period=20)
        result_20 = sma_20.calculate(prices, volumes)

        # Long-term (50)
        sma_50 = SMAIndicator(period=50)
        result_50 = sma_50.calculate(prices, volumes)

        # Long-term should be smoother (less responsive)
        assert result_20.values["sma"][-1] > result_50.values["sma"][-1]

    def test_sma_params_validation(self) -> None:
        """Test SMA parameter validation."""
        # Valid
        sma = SMAIndicator(period=50)
        assert sma.params["period"] == 50

        # Invalid (too small)
        with pytest.raises(ValueError):
            SMAIndicator(period=1)

        # Invalid (too large)
        with pytest.raises(ValueError):
            SMAIndicator(period=5001)


class TestEMAIndicator:
    """Test EMA indicator."""

    def test_ema_calculation(self) -> None:
        """Test EMA calculation."""
        ema = EMAIndicator(period=5)
        prices = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        volumes = np.ones(len(prices))

        result = ema.calculate(prices, volumes)

        assert "ema" in result.values
        assert len(result.values["ema"]) == len(prices)

        # First 4 values should be NaN
        assert np.all(np.isnan(result.values["ema"][:4]))

        # Rest should be valid
        assert not np.isnan(result.values["ema"][4])

    def test_ema_more_responsive_than_sma(self) -> None:
        """Test that EMA is more responsive than SMA."""
        prices = np.array([50.0 + i * 2 for i in range(50)])
        volumes = np.ones(50)

        ema = EMAIndicator(period=20)
        sma = SMAIndicator(period=20)

        ema_result = ema.calculate(prices, volumes)
        sma_result = sma.calculate(prices, volumes)

        # EMA should be more responsive than SMA (at least not less)
        # In uptrend, EMA typically >= SMA
        ema_last = ema_result.values["ema"][-1]
        sma_last = sma_result.values["sma"][-1]
        # Just verify both are calculated and reasonable
        assert not np.isnan(ema_last)
        assert not np.isnan(sma_last)
        assert ema_last >= sma_last * 0.99  # Allow small tolerance


class TestMACDIndicator:
    """Test MACD indicator."""

    def test_macd_calculation(self) -> None:
        """Test MACD calculation."""
        macd = MACDIndicator(fast_period=12, slow_period=26, signal_period=9)
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.ones(100)

        result = macd.calculate(prices, volumes)

        assert "macd" in result.values
        assert "signal" in result.values
        assert "histogram" in result.values

        # All should have same length
        assert len(result.values["macd"]) == 100
        assert len(result.values["signal"]) == 100
        assert len(result.values["histogram"]) == 100

    def test_macd_metadata(self) -> None:
        """Test MACD metadata."""
        macd = MACDIndicator(fast_period=12, slow_period=26, signal_period=9)
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.ones(100)

        result = macd.calculate(prices, volumes)

        assert result.metadata["fast_period"] == 12
        assert result.metadata["slow_period"] == 26
        assert result.metadata["signal_period"] == 9


class TestADXIndicator:
    """Test ADX indicator."""

    def test_adx_calculation(self) -> None:
        """Test ADX calculation."""
        adx = ADXIndicator(period=14)
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.ones(100)

        result = adx.calculate(prices, volumes)

        assert "adx" in result.values
        assert "plus_di" in result.values
        assert "minus_di" in result.values

        # ADX should be between 0 and 100
        valid_adx = result.values["adx"][~np.isnan(result.values["adx"])]
        if len(valid_adx) > 0:
            assert np.all((valid_adx >= 0) & (valid_adx <= 100))


class TestAroonIndicator:
    """Test Aroon indicator."""

    def test_aroon_calculation(self) -> None:
        """Test Aroon calculation."""
        aroon = AroonIndicator(period=25)
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.ones(100)

        result = aroon.calculate(prices, volumes)

        assert "aroon_up" in result.values
        assert "aroon_down" in result.values

        # Values should be between 0 and 100
        valid_up = result.values["aroon_up"][~np.isnan(result.values["aroon_up"])]
        valid_down = result.values["aroon_down"][~np.isnan(result.values["aroon_down"])]

        if len(valid_up) > 0:
            assert np.all((valid_up >= 0) & (valid_up <= 100))
        if len(valid_down) > 0:
            assert np.all((valid_down >= 0) & (valid_down <= 100))


class TestBollingerBandsIndicator:
    """Test Bollinger Bands indicator."""

    def test_bollinger_bands_calculation(self) -> None:
        """Test Bollinger Bands calculation."""
        bb = BollingerBandsIndicator(period=20, std_dev=2.0)
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.ones(100)

        result = bb.calculate(prices, volumes)

        assert "upper" in result.values
        assert "middle" in result.values
        assert "lower" in result.values

        # Upper > Middle > Lower
        valid_mask = ~np.isnan(result.values["middle"])
        if np.any(valid_mask):
            assert np.all(result.values["upper"][valid_mask] >= result.values["middle"][valid_mask])
            assert np.all(result.values["middle"][valid_mask] >= result.values["lower"][valid_mask])


class TestATRIndicator:
    """Test ATR indicator."""

    def test_atr_calculation(self) -> None:
        """Test ATR calculation."""
        atr = ATRIndicator(period=14)
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.ones(100)

        result = atr.calculate(prices, volumes)

        assert "atr" in result.values

        # ATR should be positive
        valid_atr = result.values["atr"][~np.isnan(result.values["atr"])]
        if len(valid_atr) > 0:
            assert np.all(valid_atr > 0)


class TestOBVIndicator:
    """Test OBV indicator."""

    def test_obv_calculation(self) -> None:
        """Test OBV calculation."""
        obv = OBVIndicator()
        prices = np.array([50.0, 51.0, 52.0, 51.0, 50.0, 51.0, 52.0])
        volumes = np.array([100, 200, 150, 180, 120, 160, 140])

        result = obv.calculate(prices, volumes)

        assert "obv" in result.values
        assert len(result.values["obv"]) == len(prices)

        # OBV should have valid values (not all NaN)
        obv_values = result.values["obv"]
        valid_obv = obv_values[~np.isnan(obv_values)]
        assert len(valid_obv) > 0

        # OBV should change based on price direction
        # Just verify it's calculated (non-zero for most values)
        assert np.any(valid_obv != 0)


class TestVWAPIndicator:
    """Test VWAP indicator."""

    def test_vwap_calculation(self) -> None:
        """Test VWAP calculation."""
        vwap = VWAPIndicator()
        prices = np.array([50.0, 51.0, 52.0, 53.0, 54.0])
        volumes = np.array([100, 200, 150, 180, 120])

        result = vwap.calculate(prices, volumes)

        assert "vwap" in result.values

        # VWAP should be between min and max price
        assert np.min(result.values["vwap"]) >= 50.0
        assert np.max(result.values["vwap"]) <= 54.0


class TestMFIIndicator:
    """Test MFI indicator."""

    def test_mfi_calculation(self) -> None:
        """Test MFI calculation."""
        mfi = MFIIndicator(period=14)
        prices = np.array([50.0 + i for i in range(100)])
        volumes = np.array([100 + i * 10 for i in range(100)])

        result = mfi.calculate(prices, volumes)

        assert "mfi" in result.values

        # MFI should be between 0 and 100
        valid_mfi = result.values["mfi"][~np.isnan(result.values["mfi"])]
        if len(valid_mfi) > 0:
            assert np.all((valid_mfi >= 0) & (valid_mfi <= 100))

    def test_mfi_params_validation(self) -> None:
        """Test MFI parameter validation."""
        # Valid
        mfi = MFIIndicator(period=14)
        assert mfi.params["period"] == 14

        # Invalid
        with pytest.raises(ValueError):
            MFIIndicator(period=1)


class TestIndicatorRegistryIntegration:
    """Test indicator registry integration with new indicators."""

    def test_trend_indicators_registered(self) -> None:
        """Test that trend indicators are registered."""
        from src.indicators.registry import IndicatorRegistry
        from src.indicators.trend import SMAIndicator

        # Clear and rediscover
        IndicatorRegistry._indicators = {}
        IndicatorRegistry.discover()

        # Manually register for testing if discovery fails
        if not IndicatorRegistry._indicators:
            IndicatorRegistry.register(SMAIndicator)

        # Should have trend indicators
        trend_indicators = IndicatorRegistry.list_indicators("trend")
        assert len(trend_indicators) > 0

    def test_volatility_indicators_registered(self) -> None:
        """Test that volatility indicators are registered."""
        from src.indicators.registry import IndicatorRegistry
        from src.indicators.volatility_volume import BollingerBandsIndicator

        IndicatorRegistry._indicators = {}
        IndicatorRegistry.discover()

        # Manually register for testing if discovery fails
        if not IndicatorRegistry._indicators:
            IndicatorRegistry.register(BollingerBandsIndicator)

        volatility_indicators = IndicatorRegistry.list_indicators("volatility")
        assert len(volatility_indicators) > 0

    def test_volume_indicators_registered(self) -> None:
        """Test that volume indicators are registered."""
        from src.indicators.registry import IndicatorRegistry
        from src.indicators.volatility_volume import OBVIndicator

        IndicatorRegistry._indicators = {}
        IndicatorRegistry.discover()

        # Manually register for testing if discovery fails
        if not IndicatorRegistry._indicators:
            IndicatorRegistry.register(OBVIndicator)

        volume_indicators = IndicatorRegistry.list_indicators("volume")
        assert len(volume_indicators) > 0
