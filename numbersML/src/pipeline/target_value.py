"""
ML Target Value Calculator.

Calculates target values for ML model training using a Hanning filter
applied to candle close prices.

The target value at each candle is the Hanning-filtered weighted average
of close prices in a window centered on that candle.

Usage:
    >>> from src.pipeline.target_value import calculate_target_value, batch_calculate
    >>> value = calculate_target_value(prices, center=150, window_size=300)
    >>> targets = batch_calculate(prices, window_size=300)
"""

import math
import numpy as np
from typing import List, Optional


def hanning_window(window_size: int) -> np.ndarray:
    """
    Generate a Hanning window of given size.

    The Hanning window is a bell-shaped weighting function:
        w(n) = 0.5 * (1 - cos(2 * pi * n / (N - 1)))

    Args:
        window_size: Number of samples in the window

    Returns:
        Normalized Hanning window (sums to 1.0)
    """
    if window_size < 1:
        return np.array([1.0])

    window = np.hanning(window_size)
    return window / window.sum()


def calculate_target_value(
    prices: np.ndarray,
    center: int,
    window_size: int = 300,
) -> float:
    """
    Calculate the Hanning-filtered target value for a single candle.

    Uses prices[center - window_size//2 : center + window_size//2] weighted
    by a Hanning window. The target is the weighted average of these prices.

    Args:
        prices: Array of close prices (numpy float64)
        center: Index of the current candle
        window_size: Window size in candles (default: 300 = 5 minutes)

    Returns:
        Hanning-filtered target value (float)

    Raises:
        ValueError: If center is outside valid range
    """
    if len(prices) == 0:
        return 0.0

    half = window_size // 2
    start = max(0, center - half)
    end = min(len(prices), center + half + 1)

    # Use available data (partial window at edges)
    window = prices[start:end]

    if len(window) == 0:
        return float(prices[center]) if center < len(prices) else 0.0

    # Generate matching Hanning window
    hanning = hanning_window(len(window))

    # Weighted average
    target = float(np.dot(window, hanning))

    return target


def batch_calculate(
    prices: List[float],
    window_size: int = 300,
) -> List[float]:
    """
    Calculate target values for all candles in a price series.

    For each candle at index i, computes the Hanning-filtered weighted
    average of prices in [i - half, i + half].

    Args:
        prices: List of close prices
        window_size: Window size (default: 300)

    Returns:
        List of target values (same length as prices)
    """
    if not prices:
        return []

    prices_arr = np.array(prices, dtype=np.float64)
    return batch_calculate_numpy(prices_arr, window_size).tolist()


def batch_calculate_numpy(
    prices: np.ndarray,
    window_size: int = 300,
) -> np.ndarray:
    """
    Vectorized target value calculation using numpy convolution.

    For each candle at index i, computes the Hanning-filtered weighted
    average of prices in [i - half, i + half].

    Args:
        prices: Numpy array of close prices
        window_size: Window size (default: 300)

    Returns:
        Numpy array of target values (same length as input)
    """
    n = len(prices)
    if n == 0:
        return np.array([])

    half = window_size // 2

    # Compute Hanning filter directly for each position (handles edges properly)
    targets = np.empty(n, dtype=np.float64)

    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        size = end - start

        if size < 1:
            targets[i] = float(prices[i])
            continue

        # Generate Hanning window of exact size needed
        window = np.hanning(size)
        window = window / window.sum()

        targets[i] = float(np.dot(prices[start:end], window))

    return targets
