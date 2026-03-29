"""
Tests for target value calculator.

Tests:
    - Hanning window generation
    - Single target value calculation
    - Batch calculation
    - Edge cases (empty, single element, partial window)
    - Numpy vectorized calculation
"""

import pytest
import numpy as np

from src.pipeline.target_value import (
    hanning_window,
    calculate_target_value,
    batch_calculate,
    batch_calculate_numpy,
)


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

    def test_constant_prices(self) -> None:
        """Constant prices return same value."""
        prices = np.array([100.0] * 100, dtype=np.float64)
        target = calculate_target_value(prices, center=50, window_size=20)
        assert abs(target - 100.0) < 1e-6

    def test_increasing_prices(self) -> None:
        """Increasing prices return weighted average near center."""
        prices = np.arange(0.0, 100.0, dtype=np.float64)
        target = calculate_target_value(prices, center=50, window_size=20)
        # Target should be close to 50 (center of range)
        assert 40 < target < 60

    def test_single_price(self) -> None:
        """Single price returns that price."""
        prices = np.array([42.0], dtype=np.float64)
        target = calculate_target_value(prices, center=0, window_size=300)
        assert abs(target - 42.0) < 1e-6

    def test_empty_prices(self) -> None:
        """Empty prices returns 0."""
        prices = np.array([], dtype=np.float64)
        target = calculate_target_value(prices, center=0, window_size=300)
        assert target == 0.0

    def test_edge_center(self) -> None:
        """Center at edge uses partial window."""
        prices = np.array([100.0, 200.0, 300.0], dtype=np.float64)
        target = calculate_target_value(prices, center=0, window_size=10)
        assert 100 <= target <= 200


class TestBatchCalculate:
    """Test batch target value calculation."""

    def test_constant_series(self) -> None:
        """Constant series returns all same values."""
        prices = [50.0] * 500
        targets = batch_calculate(prices, window_size=300)
        assert len(targets) == 500
        for t in targets:
            assert abs(t - 50.0) < 1e-6

    def test_empty_input(self) -> None:
        """Empty input returns empty list."""
        targets = batch_calculate([], window_size=300)
        assert targets == []

    def test_single_element(self) -> None:
        """Single element returns single value."""
        targets = batch_calculate([42.0], window_size=300)
        assert len(targets) == 1
        assert abs(targets[0] - 42.0) < 1e-6

    def test_ramp_signal(self) -> None:
        """Ramp signal produces smooth output."""
        prices = list(range(1000))
        targets = batch_calculate(prices, window_size=100)
        assert len(targets) == 1000
        # Targets should be monotonically increasing
        for i in range(1, len(targets)):
            assert targets[i] >= targets[i - 1] - 1e-6

    def test_window_size_1(self) -> None:
        """Window size 1 returns raw prices."""
        prices = [10.0, 20.0, 30.0]
        targets = batch_calculate(prices, window_size=1)
        for p, t in zip(prices, targets):
            assert abs(p - t) < 1e-6


class TestBatchCalculateNumpy:
    """Test numpy vectorized calculation."""

    def test_matches_batch_calculate(self) -> None:
        """Numpy version matches pure Python version."""
        np.random.seed(42)
        prices = np.random.uniform(100, 200, 500).tolist()

        targets_py = batch_calculate(prices, window_size=300)
        targets_np = batch_calculate_numpy(prices, window_size=300).tolist()

        assert len(targets_py) == len(targets_np)
        for py, np_val in zip(targets_py, targets_np):
            assert abs(py - np_val) < 1e-6, f"Mismatch: {py} vs {np_val}"

    def test_empty_input(self) -> None:
        """Empty input returns empty array."""
        result = batch_calculate_numpy(np.array([]), window_size=300)
        assert len(result) == 0

    def test_constant_series(self) -> None:
        """Constant series returns all same values."""
        prices = np.full(500, 100.0)
        targets = batch_calculate_numpy(prices, window_size=300)
        for t in targets:
            assert abs(t - 100.0) < 1e-6
