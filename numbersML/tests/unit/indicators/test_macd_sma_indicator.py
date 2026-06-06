"""Tests for MACDSMAIndicator — SMA-based MACD."""

import numpy as np
import pytest

from src.indicators.trend import MACDSMAIndicator


class TestMACDSMAIndicator:
    """Test MACDSMA indicator."""

    def test_macd_sma_basic_structure(self) -> None:
        """Basic output structure — three value arrays of correct length."""
        macd = MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=9)
        prices = np.array([50.0 + i for i in range(200)])
        volumes = np.ones(200)

        result = macd.calculate(prices, volumes)

        assert "macd" in result.values
        assert "signal" in result.values
        assert "histogram" in result.values

        assert len(result.values["macd"]) == 200
        assert len(result.values["signal"]) == 200
        assert len(result.values["histogram"]) == 200

    def test_macd_sma_metadata(self) -> None:
        """Metadata contains periods and no buffer_insufficient flag."""
        macd = MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=9)
        result = macd.calculate(
            np.array([50.0 + i for i in range(200)]),
            np.ones(200),
        )

        assert result.metadata["fast_period"] == 12
        assert result.metadata["slow_period"] == 26
        assert result.metadata["signal_period"] == 9
        assert "buffer_insufficient" not in result.metadata

    def test_macd_sma_nan_before_slow_period(self) -> None:
        """Values before slow_period should be NaN."""
        macd = MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=9)
        prices = np.array([50.0 + i for i in range(50)])
        volumes = np.ones(50)

        result = macd.calculate(prices, volumes)

        # First 25 values (slow_period - 1) should be NaN for macd line
        assert np.all(np.isnan(result.values["macd"][:25]))
        # Value at index 25 (0-based, slow_period-1) should be valid
        assert not np.isnan(result.values["macd"][25])

    def test_macd_sma_known_values(self) -> None:
        """MACD SMA on a simple sequence matches hand-computed values."""
        period = 3
        macd = MACDSMAIndicator(fast_period=period, slow_period=period + 2, signal_period=2)
        prices = np.array([10.0, 20.0, 10.0, 30.0, 50.0])
        volumes = np.ones(5)

        result = macd.calculate(prices, volumes)

        # fast SMA(3): [NaN, NaN, (10+20+10)/3≈13.3, (20+10+30)/3=20, (10+30+50)/3=30]
        # slow SMA(5): [NaN, NaN, NaN, NaN, (10+20+10+30+50)/5=24]
        # MACD line at idx 4: 30 - 24 = 6.0
        assert not np.isnan(result.values["macd"][4])
        assert result.values["macd"][4] == pytest.approx(6.0, abs=1e-10)

    def test_macd_sma_constant_prices(self) -> None:
        """All prices equal → MACD line and histogram should be zero."""
        macd = MACDSMAIndicator(fast_period=5, slow_period=10, signal_period=3)
        prices = np.full(50, 100.0)
        volumes = np.ones(50)

        result = macd.calculate(prices, volumes)

        valid_idx = 9  # slow_period - 1, macd_line valid
        signal_valid = valid_idx + macd.params["signal_period"] - 1  # first index where signal is valid
        assert result.values["macd"][valid_idx] == pytest.approx(0.0, abs=1e-10)
        assert result.values["histogram"][signal_valid] == pytest.approx(0.0, abs=1e-10)

        # All later values should also be 0 (starting from signal-valid index)
        signal_valid = valid_idx + macd.params["signal_period"] - 1
        assert np.allclose(result.values["macd"][signal_valid:], 0.0)
        assert np.allclose(result.values["histogram"][signal_valid:], 0.0)

    def test_macd_sma_uptrend_macd_positive(self) -> None:
        """In a sustained uptrend, MACD line should be positive."""
        macd = MACDSMAIndicator(fast_period=5, slow_period=10, signal_period=3)
        prices = np.array([float(i) for i in range(100)])  # 0, 1, 2, ... 99
        volumes = np.ones(100)

        result = macd.calculate(prices, volumes)

        # Last MACD value should be positive (fast SMA > slow SMA in uptrend)
        assert result.values["macd"][-1] > 0

    def test_macd_sma_insufficient_data(self) -> None:
        """Data shorter than slow_period → all NaN."""
        macd = MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=9)
        prices = np.array([50.0 + i for i in range(10)])
        volumes = np.ones(10)

        result = macd.calculate(prices, volumes)

        assert np.all(np.isnan(result.values["macd"]))
        assert np.all(np.isnan(result.values["signal"]))
        assert np.all(np.isnan(result.values["histogram"]))

    def test_macd_sma_params_validation(self) -> None:
        """Parameter boundaries are enforced."""
        # Valid
        macd = MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=9)
        assert macd.params["fast_period"] == 12
        assert macd.params["slow_period"] == 26
        assert macd.params["signal_period"] == 9

        # Invalid: fast_period too small
        with pytest.raises(ValueError):
            MACDSMAIndicator(fast_period=1, slow_period=26, signal_period=9)

        # Invalid: fast_period too large
        with pytest.raises(ValueError):
            MACDSMAIndicator(fast_period=200000, slow_period=26, signal_period=9)

        # Invalid: slow_period too small
        with pytest.raises(ValueError):
            MACDSMAIndicator(fast_period=12, slow_period=1, signal_period=9)

        # Invalid: signal_period too small
        with pytest.raises(ValueError):
            MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=1)

    def test_macd_sma_name_generation(self) -> None:
        """Name follows auto-naming convention."""
        macd = MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=9)
        assert "macdsmaindicator" in macd.name
        assert "fast_period12" in macd.name
        assert "slow_period26" in macd.name
        assert "signal_period9" in macd.name

    def test_macd_sma_large_periods(self) -> None:
        """Large periods (simulating 4h/24h on 1s data) should work."""
        macd = MACDSMAIndicator(fast_period=14400, slow_period=86400, signal_period=100)
        prices = np.array([50.0 + np.sin(i * 0.001) * 10 for i in range(86400 + 500)])
        volumes = np.ones(len(prices))

        result = macd.calculate(prices, volumes)

        assert not np.isnan(result.values["macd"][-1])
        assert not np.isnan(result.values["signal"][-1])
        assert not np.isnan(result.values["histogram"][-1])

    def test_macd_sma_signal_is_sma_of_macd(self) -> None:
        """Signal line should be SMA(signal_period) of MACD line."""
        macd = MACDSMAIndicator(fast_period=5, slow_period=10, signal_period=3)
        prices = np.array([float(i) for i in range(50)])
        volumes = np.ones(50)

        result = macd.calculate(prices, volumes)
        macd_line = result.values["macd"]
        signal_line = result.values["signal"]

        # Manually compute SMA of MACD line
        valid_macd = macd_line[~np.isnan(macd_line)]
        if len(valid_macd) >= 3:
            expected_signal_end = np.mean(valid_macd[-3:])
            valid_signal = signal_line[~np.isnan(signal_line)]
            assert valid_signal[-1] == pytest.approx(expected_signal_end, abs=1e-10)

    def test_macd_sma_vectorized_matches_loop(self) -> None:
        """Vectorized SMA should match explicit loop SMA."""
        macd = MACDSMAIndicator(fast_period=12, slow_period=26, signal_period=9)
        prices = np.array([50.0 + np.random.RandomState(42).randn() * 2 for _ in range(500)])
        volumes = np.ones(500)

        result = macd.calculate(prices, volumes)

        # Compute fast SMA via explicit Python loop
        def loop_sma(data: np.ndarray, period: int) -> np.ndarray:
            out = np.full(len(data), np.nan)
            for i in range(period - 1, len(data)):
                out[i] = np.mean(data[i - period + 1 : i + 1])
            return out

        fast_sma_loop = loop_sma(prices, 12)
        slow_sma_loop = loop_sma(prices, 26)

        macd_loop = fast_sma_loop - slow_sma_loop

        macd_vec = result.values["macd"]
        np.testing.assert_array_almost_equal(macd_vec[25:], macd_loop[25:])
