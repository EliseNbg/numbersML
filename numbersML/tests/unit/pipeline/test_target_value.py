"""
Tests for target value calculator.

Tests:
    - Kalman Filter implementation
    - Hanning window generation (backward compatibility)
    - Single target value calculation
    - Batch calculation
    - Edge cases (empty, single element, partial window)
    - Numpy vectorized calculation
    - Kalman vs Hanning comparison
"""

import numpy as np

from src.pipeline.target_value import (
    KalmanFilter1D,
    batch_calculate,
    batch_calculate_numpy,
    calculate_target_value,
    hanning_window,
    kalman_filter_prices,
)


class TestKalmanFilter:
    """Test Kal Filter implementation."""

    def test_constant_prices(self) -> None:
        """Kalman Filter converges to constant value."""
        prices = np.array([100.0] * 100, dtype=np.float64)
        filtered = kalman_filter_prices(prices)
        # After warmup, filtered should be close to 100
        assert abs(filtered[-1] - 100.0) < 0.1
        # Filtered values should be stable
        assert np.std(filtered[50:]) < 0.01

    def test_increasing_prices(self) -> None:
        """Kalman Filter tracks trend with minimal lag."""
        prices = np.arange(0.0, 100.0, dtype=np.float64)
        filtered = kalman_filter_prices(prices)
        # Filtered should follow trend
        assert filtered[-1] > filtered[0]
        # Lag should be less than Hanning (would be ~50 for window=100)
        # Kalman lag is typically 5-10 samples
        assert filtered[-1] > 85.0  # Should be close to current value

    def test_noise_reduction(self) -> None:
        """Kalman Filter reduces noise in price signal."""
        np.random.seed(42)
        true_signal = np.linspace(100, 110, 500)
        noisy_prices = true_signal + np.random.randn(500) * 2.0
        filtered = kalman_filter_prices(noisy_prices)
        # Filtered should have lower variance than original
        assert np.std(np.diff(filtered)) < np.std(np.diff(noisy_prices))

    def test_kalman_filter_1d_class(self) -> None:
        """Test KalmanFilter1D class directly."""
        kf = KalmanFilter1D(process_noise=0.01, measurement_noise=1.0)
        measurements = [100.0, 101.0, 102.0, 103.0, 104.0]
        filtered = kf.filter(np.array(measurements))
        assert len(filtered) == len(measurements)
        # Should track the trend
        assert filtered[-1] > filtered[0]


class TestHanningWindow:
    """Test Hanning window generation."""

    def test_window_size_1(self) -> None:
        """Window of size 1 returns [1.0]."""
        w = hanning_window(1)
        assert len(w) == 1
        assert abs(w.sum() - 1.0) < 1e-10

    def test_window_size_10(self) -> None:
        """Window of size 10 is normalized."""
        w = hanning_window(10)
        assert len(w) == 10
        assert abs(w.sum() - 1.0) < 1e-10

    def test_window_size_300(self) -> None:
        """Window of size 300 (default) is bell-shaped and normalized."""
        w = hanning_window(300)
        assert len(w) == 300
        assert abs(w.sum() - 1.0) < 1e-10
        # Center has highest weight
        assert w[150] > w[0]
        assert w[150] > w[299]

    def test_window_symmetric(self) -> None:
        """Hanning window is symmetric."""
        w = hanning_window(100)
        for i in range(50):
            assert abs(w[i] - w[99 - i]) < 1e-10


class TestCalculateTargetValue:
    """Test single target value calculation."""

    def test_constant_prices_kalman(self) -> None:
        """Constant prices return zero with Kalman (no deviation)."""
        prices = np.array([100.0] * 100, dtype=np.float64)
        target = calculate_target_value(prices, center=50, use_kalman=True)
        assert abs(target - 0.0) < 0.1

    def test_constant_prices_hanning(self) -> None:
        """Constant prices return zero with Hanning (no deviation)."""
        prices = np.array([100.0] * 100, dtype=np.float64)
        target = calculate_target_value(prices, center=50, window_size=20, use_kalman=False)
        assert abs(target - 0.0) < 1e-6

    def test_increasing_prices_kalman(self) -> None:
        """Increasing prices return small deviation with Kalman (tracks trend well)."""
        prices = np.arange(0.0, 100.0, dtype=np.float64)
        target = calculate_target_value(prices, center=50, use_kalman=True)
        # Kalman tracks trend so well that deviation is near zero
        # (much smaller than Hanning which has lag)
        assert abs(target) < 1.0

    def test_single_price(self) -> None:
        """Single price returns 0 (no history)."""
        prices = np.array([42.0], dtype=np.float64)
        target = calculate_target_value(prices, center=0, use_kalman=True)
        assert abs(target - 0.0) < 1e-6

    def test_empty_prices(self) -> None:
        """Empty prices returns 0."""
        prices = np.array([], dtype=np.float64)
        target = calculate_target_value(prices, center=0, use_kalman=True)
        assert target == 0.0


class TestBatchCalculate:
    """Test batch target value calculation."""

    def test_constant_series_kalman(self) -> None:
        """Constant series returns all zeros with Kalman."""
        prices = [50.0] * 500
        targets = batch_calculate(prices, use_kalman=True)
        assert len(targets) == 500
        for t in targets:
            assert abs(t - 0.0) < 0.1

    def test_constant_series_hanning(self) -> None:
        """Constant series returns all zeros with Hanning."""
        prices = [50.0] * 500
        targets = batch_calculate(prices, window_size=300, use_kalman=False)
        assert len(targets) == 500
        for t in targets:
            assert abs(t - 0.0) < 1e-6

    def test_empty_input(self) -> None:
        """Empty input returns empty list."""
        targets = batch_calculate([], use_kalman=True)
        assert targets == []

    def test_single_element(self) -> None:
        """Single element returns 0 (no history)."""
        targets = batch_calculate([42.0], use_kalman=True)
        assert len(targets) == 1
        assert abs(targets[0] - 0.0) < 1e-6

    def test_ramp_signal_kalman(self) -> None:
        """Ramp signal produces small deviations with Kalman (tracks trend)."""
        prices = list(range(1000))
        targets = batch_calculate(prices, use_kalman=True)
        assert len(targets) == 1000
        # After warmup, targets should be small (Kalman tracks trend well)
        later_targets = targets[100:]
        assert abs(np.mean(later_targets)) < 5.0

    def test_ramp_signal_hanning(self) -> None:
        """Ramp signal produces positive deviations with Hanning (has lag)."""
        prices = list(range(1000))
        targets = batch_calculate(prices, window_size=100, use_kalman=False)
        assert len(targets) == 1000
        # After warmup, targets should be positive (Hanning has lag)
        later_targets = targets[200:]
        assert all(t > 0 for t in later_targets)

    def test_kalman_vs_hanning_lag(self) -> None:
        """Kalman has less lag than Hanning for trending prices."""
        prices = list(range(500))  # Strong uptrend

        targets_kalman = batch_calculate(prices, use_kalman=True)
        targets_hanning = batch_calculate(prices, window_size=100, use_kalman=False)

        # Kalman targets should be smaller (less lag = closer to trend)
        kalman_magnitude = np.mean(np.abs(targets_kalman[100:]))
        hanning_magnitude = np.mean(np.abs(targets_hanning[100:]))

        # Kalman tracks trend better (smaller deviation from trend)
        assert kalman_magnitude < hanning_magnitude


class TestBatchCalculateNumpy:
    """Test numpy vectorized calculation."""

    def test_matches_batch_calculate_kalman(self) -> None:
        """Numpy version matches pure Python version (Kalman)."""
        np.random.seed(42)
        prices = np.random.uniform(100, 200, 500).tolist()

        targets_py = batch_calculate(prices, use_kalman=True)
        targets_np = batch_calculate_numpy(prices, use_kalman=True).tolist()

        assert len(targets_py) == len(targets_np)
        for py, np_val in zip(targets_py, targets_np):
            assert abs(py - np_val) < 1e-6, f"Mismatch: {py} vs {np_val}"

    def test_matches_batch_calculate_hanning(self) -> None:
        """Numpy version matches pure Python version (Hanning)."""
        np.random.seed(42)
        prices = np.random.uniform(100, 200, 500).tolist()

        targets_py = batch_calculate(prices, window_size=300, use_kalman=False)
        targets_np = batch_calculate_numpy(prices, window_size=300, use_kalman=False).tolist()

        assert len(targets_py) == len(targets_np)
        for py, np_val in zip(targets_py, targets_np):
            assert abs(py - np_val) < 1e-6, f"Mismatch: {py} vs {np_val}"

    def test_empty_input(self) -> None:
        """Empty input returns empty array."""
        result = batch_calculate_numpy(np.array([]), use_kalman=True)
        assert len(result) == 0

    def test_constant_series_kalman(self) -> None:
        """Constant series returns all zeros (Kalman)."""
        prices = np.full(500, 100.0)
        targets = batch_calculate_numpy(prices, use_kalman=True)
        for t in targets:
            assert abs(t - 0.0) < 0.1

    def test_kalman_vs_hanning_variance(self) -> None:
        """Kalman produces smaller variance for trending prices."""
        np.random.seed(42)
        prices = np.linspace(100, 200, 1000) + np.random.randn(1000) * 2

        targets_kalman = batch_calculate_numpy(prices, use_kalman=True)
        targets_hanning = batch_calculate_numpy(prices, window_size=300, use_kalman=False)

        # After warmup, compare variance
        kalman_var = np.var(targets_kalman[100:])
        hanning_var = np.var(targets_hanning[300:])

        # Kalman should have smaller variance (tracks trend better)
        assert kalman_var < hanning_var
