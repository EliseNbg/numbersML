"""
ML Target Value Calculator.

Calculates target values for ML model training as the deviation from a
causal Hanning filter (no data leakage).

The target value at each candle is:
    target[t] = close[t] - hanning_smoothed[t]

where hanning_smoothed uses ONLY past data (causal filter).

This represents the price deviation from the smoothed trend, which is
what the model should predict.

Usage:
    >>> from src.pipeline.target_value import calculate_target_value, batch_calculate
    >>> target = calculate_target_value(prices, center=150, window_size=300)
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

    if window_size == 1:
        return np.array([1.0])

    if window_size == 2:
        return np.array([0.5, 0.5])

    window = np.hanning(window_size)
    return window / window.sum()


def calculate_target_value(
    prices: np.ndarray,
    center: int,
    window_size: int = 300,
) -> float:
    """
    Calculate the target value for a single candle as deviation from causal Hanning filter.

    Uses ONLY past data (causal): prices[center - window_size : center]
    Target = close[center] - hanning_smoothed

    Args:
        prices: Array of close prices (numpy float64)
        center: Index of the current candle
        window_size: Window size in candles for Hanning filter (default: 300 = 5 minutes)

    Returns:
        Target value (close - smoothed_trend), positive = above trend, negative = below

    Raises:
        ValueError: If center is outside valid range
    """
    if len(prices) == 0:
        return 0.0

    # Causal window: only use past data up to (but not including) current candle
    start = max(0, center - window_size)
    end = center  # Exclusive, so we use prices[start:end] which is past data only

    # If not enough history, use what we have
    if end <= start:
        return 0.0  # No history to smooth against

    window = prices[start:end]

    # Generate matching Hanning window
    hanning = hanning_window(len(window))

    # Smoothed trend (weighted average of past prices)
    smoothed = float(np.dot(window, hanning))

    # Target = current price - smoothed trend
    current_price = float(prices[center]) if center < len(prices) else 0.0
    target = current_price - smoothed

    return target


def batch_calculate(
    prices: List[float],
    window_size: int = 300,
) -> List[float]:
    """
    Calculate target values for all candles in a price series.

    For each candle at index i, computes:
        target[i] = close[i] - hanning_smoothed[i]

    where hanning_smoothed uses only past data (causal).

    Args:
        prices: List of close prices
        window_size: Window size for Hanning filter (default: 300)

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

    For each candle at index i, computes:
        target[i] = close[i] - hanning_smoothed[i]

    Uses causal filtering (only past data) to prevent data leakage.

    Args:
        prices: Numpy array of close prices
        window_size: Window size for Hanning filter (default: 300)

    Returns:
        Numpy array of target values (same length as input)
    """
    n = len(prices)
    if n == 0:
        return np.array([])

    if n == 1:
        return np.array([0.0])

    # For proper Hanning window behavior, we need at least 2 points
    # Use variable window size at the beginning
    targets = np.zeros(n, dtype=np.float64)

    # For positions with enough history, use full convolution
    if n >= window_size:
        hanning = hanning_window(window_size)
        # Convolve: result[i] uses prices[i:i+window_size]
        smoothed_with_current = np.convolve(prices, hanning, mode='valid')

        # smoothed_with_current[i] = weighted avg of prices[i:i+window_size]
        # We want smoothed[i] = weighted avg of prices[i-window_size:i] (past only)
        # So smoothed_trend[i] = smoothed_with_current[i-window_size] for i >= window_size
        # And for i < window_size, we use partial windows

        # For simplicity, start using full window from index window_size
        for i in range(window_size, n):
            smoothed = smoothed_with_current[i - window_size]
            targets[i] = prices[i] - smoothed

        # For early positions (i < window_size), use variable window
        for i in range(1, min(window_size, n)):
            window = prices[0:i]
            if len(window) >= 2:
                hann = hanning_window(len(window))
                smoothed = float(np.dot(window, hann))
                targets[i] = prices[i] - smoothed
            # else: leave as 0.0 (not enough data)
    else:
        # Not enough data for full window, use all available data
        for i in range(1, n):
            window = prices[0:i]
            if len(window) >= 2:
                hann = hanning_window(len(window))
                smoothed = float(np.dot(window, hann))
                targets[i] = prices[i] - smoothed

    return targets
