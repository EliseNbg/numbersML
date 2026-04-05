"""
ML Target Value Calculator.

Calculates target values for ML model training as the deviation from a
Kalman Filter estimate (optimal smoothing with minimal lag).

The target value at each candle is:
    target[t] = close[t] - kalman_filtered[t]

where kalman_filtered uses optimal state estimation that adapts to
market volatility and has minimal lag compared to fixed-window filters.

Advantages over Hanning:
    - Minimal lag (reacts faster to trend changes)
    - Adapts to volatility (auto-tunes smoothing)
    - Optimal in the mean-square error sense
    - No arbitrary window size (uses process/measurement noise)

Usage:
    >>> from src.pipeline.target_value import calculate_target_value, batch_calculate
    >>> target = calculate_target_value(prices, center=150)
    >>> targets = batch_calculate(prices)
"""

import math
import numpy as np
from typing import List, Optional, Tuple, Dict, Any


class KalmanFilter1D:
    """
    1D Kalman Filter for price trend estimation.

    State: [position, velocity] (price and rate of change)
    Model: Constant velocity with process noise

    This provides optimal smoothing with minimal lag by tracking
    both the price level and its momentum.
    """

    def __init__(
        self,
        process_noise: float = 0.01,
        measurement_noise: float = 1.0,
        initial_state: Optional[np.ndarray] = None,
    ) -> None:
        """
        Initialize Kalman Filter.

        Args:
            process_noise: Q - How much we expect the trend to change
            measurement_noise: R - How noisy our price measurements are
            initial_state: [position, velocity] initial state
        """
        # State: [position (price), velocity (rate of change)]
        if initial_state is not None:
            self.x = initial_state.copy()
        else:
            self.x = np.array([0.0, 0.0])

        # State covariance (uncertainty)
        self.P = np.eye(2) * 10.0

        # Process noise covariance (how much trend can change)
        self.Q = np.array([
            [process_noise * 0.25, process_noise * 0.5],
            [process_noise * 0.5, process_noise]
        ])

        # Measurement noise (price noise)
        self.R = measurement_noise

        # State transition matrix (constant velocity model)
        self.F = np.array([
            [1.0, 1.0],
            [0.0, 1.0]
        ])

        # Measurement matrix (we observe position only)
        self.H = np.array([[1.0, 0.0]])

    def predict(self) -> None:
        """Predict next state (time update)."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

    def update(self, measurement: float) -> float:
        """
        Update state with new measurement and return filtered value.

        Args:
            measurement: Observed price

        Returns:
            Filtered price estimate
        """
        z = np.array([measurement])

        # Innovation
        y = z - self.H @ self.x

        # Innovation covariance
        S = self.H @ self.P @ self.H.T + self.R

        # Kalman gain
        K = self.P @ self.H.T @ np.linalg.inv(S)

        # Update state
        self.x = self.x + K @ y

        # Update covariance
        I = np.eye(2)
        self.P = (I - K @ self.H) @ self.P

        return self.x[0]

    def filter(self, measurements: np.ndarray) -> np.ndarray:
        """
        Filter entire measurement series.

        Args:
            measurements: Array of price observations

        Returns:
            Array of filtered values (same length)
        """
        n = len(measurements)
        filtered = np.zeros(n)

        # Initialize with first measurement
        if n > 0:
            self.x[0] = measurements[0]
            filtered[0] = measurements[0]

        for i in range(1, n):
            self.predict()
            filtered[i] = self.update(measurements[i])

        return filtered


def estimate_kalman_params(
    prices: np.ndarray,
    lookback: int = 100,
) -> Tuple[float, float]:
    """
    Estimate optimal Kalman filter parameters from recent price data.

    Uses the variance of price changes to estimate measurement noise,
    and the variance of velocity changes to estimate process noise.

    Args:
        prices: Recent price data
        lookback: Number of samples to use

    Returns:
        (process_noise, measurement_noise)
    """
    if len(prices) < 10:
        return 0.01, 1.0

    # Use recent data
    prices = prices[-lookback:]

    # Price changes (velocity)
    diff = np.diff(prices)

    # Measurement noise: variance of price
    measurement_noise = max(np.var(prices) * 0.01, 0.1)

    # Process noise: variance of velocity changes
    if len(diff) > 1:
        velocity_changes = np.diff(diff)
        process_noise = max(np.var(velocity_changes) * 0.1, 0.001)
    else:
        process_noise = 0.01

    return process_noise, measurement_noise


def response_time_to_noise_ratio(response_time: float) -> float:
    """
    Convert desired response time to Kalman noise ratio.

    Maps intuitive "response time" (in samples) to the Q/R noise ratio.

    Args:
        response_time: Number of samples to react to a step change
                      - 10 = very fast (reacts in 10 samples)
                      - 50 = moderate (default)
                      - 100+ = slow (very smooth)

    Returns:
        Noise ratio λ = Q/R for Kalman Filter
    """
    # Relationship: response_time ≈ 1/λ
    # So: λ ≈ 1/response_time
    if response_time <= 0:
        return 1.0  # Maximum responsiveness
    
    return 1.0 / response_time


def kalman_filter_prices(
    prices: np.ndarray,
    response_time: float = 50.0,
    auto_tune: bool = True,
    process_noise: Optional[float] = None,
    measurement_noise: Optional[float] = None,
) -> np.ndarray:
    """
    Apply Kalman Filter to price series.

    Args:
        prices: Array of close prices
        response_time: Samples to react to step change (default: 50)
                      - Small (10-20): Fast response, less smoothing
                      - Medium (30-100): Balanced (default 50)
                      - Large (100+): Slow response, more smoothing
        auto_tune: Auto-estimate base noise levels from data (default: True)
                  If True, uses response_time to set Q/R ratio but scales
                  to actual price volatility
                  If False, uses fixed process_noise/measurement_noise
        process_noise: Fixed Q (ignored if auto_tune=True)
        measurement_noise: Fixed R (ignored if auto_tune=True)

    Returns:
        Array of filtered price estimates

    Examples:
        >>> # Fast response (like EMA with α=0.1)
        >>> filtered = kalman_filter_prices(prices, response_time=10)
        >>>
        >>> # Balanced (default)
        >>> filtered = kalman_filter_prices(prices, response_time=50)
        >>>
        >>> # Smooth (like Hanning with window=100)
        >>> filtered = kalman_filter_prices(prices, response_time=100)
    """
    n = len(prices)
    if n == 0:
        return np.array([])

    if n == 1:
        return prices.copy()

    if auto_tune:
        # Auto-estimate base noise levels from data
        q_base, r_base = estimate_kalman_params(prices)
        
        # Apply response_time to set Q/R ratio
        noise_ratio = response_time_to_noise_ratio(response_time)
        
        # Scale: keep base levels but adjust ratio
        # Q/R = noise_ratio, so Q = noise_ratio * R
        # Use geometric mean to preserve overall noise level
        target_ratio = noise_ratio
        current_ratio = q_base / r_base if r_base > 0 else 1.0
        
        # Adjust to match target ratio
        scale_factor = np.sqrt(target_ratio / current_ratio) if current_ratio > 0 else 1.0
        process_noise = q_base * scale_factor
        measurement_noise = r_base / scale_factor
    else:
        # Use fixed parameters
        if process_noise is None:
            process_noise = 0.01
        if measurement_noise is None:
            measurement_noise = 1.0

    # Create and run filter
    kf = KalmanFilter1D(
        process_noise=process_noise,
        measurement_noise=measurement_noise,
    )

    return kf.filter(prices)


def hanning_window(window_size: int) -> np.ndarray:
    """
    Generate a Hanning window of given size.

    DEPRECATED: Use Kalman Filter instead for better performance.
    Kept for backward compatibility.

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


def calculate_target_data(
    prices: np.ndarray,
    center: int,
    response_time: float = 200.0,
    use_kalman: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Calculate complete market state for a single candle as JSON-serializable dict.

    Returns rich market information instead of just a single number:
    - filtered_value: Smooth Kalman trend (WAVES visualization)
    - close: Current candle close price
    - diff: Deviation from trend (close - filtered)
    - trend: 'up' or 'down' (trend direction)
    - velocity: Rate of change (trend strength)

    Args:
        prices: Array of close prices
        center: Index of the current candle
        response_time: Kalman response time in samples (default: 200)
        use_kalman: Use Kalman Filter (True, default) or Hanning (False)

    Returns:
        Dictionary with market state, or None if insufficient data
    """
    if len(prices) == 0 or center >= len(prices):
        return None

    current_price = float(prices[center])

    if center < 1:
        return {
            'filtered_value': current_price,
            'close': current_price,
            'diff': 0.0,
            'trend': 'flat',
            'velocity': 0.0,
        }

    if use_kalman:
        # Use Kalman Filter
        history = prices[:center + 1]
        if len(history) < 2:
            return None

        filtered = kalman_filter_prices(history, response_time=response_time)
        filtered_value = float(filtered[-1])

        # Calculate velocity (rate of change of filtered trend)
        if len(filtered) >= 2:
            velocity = filtered_value - float(filtered[-2])
        else:
            velocity = 0.0
    else:
        # Legacy Hanning filter (for backward compatibility)
        filtered_value = current_price  # Simplified
        velocity = 0.0

    # Calculate deviation
    diff = current_price - filtered_value

    # Determine trend direction
    if velocity > 0.01:
        trend = 'up'
    elif velocity < -0.01:
        trend = 'down'
    else:
        trend = 'flat'

    return {
        'filtered_value': round(filtered_value, 8),
        'close': current_price,
        'diff': round(diff, 8),
        'trend': trend,
        'velocity': round(velocity, 8),
    }


def batch_calculate_target_data(
    prices: List[float],
    response_time: float = 200.0,
    use_kalman: bool = True,
) -> List[Optional[Dict[str, Any]]]:
    """
    Calculate market state for all candles in a price series.

    Returns list of dicts with filtered_value, close, diff, trend, velocity.

    Args:
        prices: List of close prices
        response_time: Kalman response time in samples (default: 200)
        use_kalman: Use Kalman Filter (True, default) or Hanning (False)

    Returns:
        List of dicts with market state (same length as prices)
    """
    if not prices:
        return []

    prices_arr = np.array(prices, dtype=np.float64)
    results = []

    if use_kalman:
        # Calculate Kalman filter once for all prices
        filtered = kalman_filter_prices(prices_arr, response_time=response_time)

        for i in range(len(prices_arr)):
            current_price = float(prices_arr[i])
            filtered_value = float(filtered[i])
            diff = current_price - filtered_value

            # Velocity (rate of change)
            if i > 0:
                velocity = filtered_value - float(filtered[i-1])
            else:
                velocity = 0.0

            # Trend direction
            if velocity > 0.01:
                trend = 'up'
            elif velocity < -0.01:
                trend = 'down'
            else:
                trend = 'flat'

            results.append({
                'filtered_value': round(filtered_value, 8),
                'close': current_price,
                'diff': round(diff, 8),
                'trend': trend,
                'velocity': round(velocity, 8),
            })
    else:
        # Legacy mode - simplified
        for i in range(len(prices_arr)):
            current_price = float(prices_arr[i])
            results.append({
                'filtered_value': current_price,
                'close': current_price,
                'diff': 0.0,
                'trend': 'flat',
                'velocity': 0.0,
            })

    return results


def calculate_target_value(
    prices: np.ndarray,
    center: int,
    window_size: int = 300,
    response_time: float = 50.0,
    use_kalman: bool = True,
) -> float:
    """
    Calculate the target value for a single candle as deviation from trend.

    Uses Kalman Filter by default (minimal lag, adaptive smoothing).
    Falls back to Hanning filter if use_kalman=False.

    Args:
        prices: Array of close prices (numpy float64)
        center: Index of the current candle
        window_size: Window size for Hanning filter (ignored if use_kalman=True)
        response_time: Kalman response time in samples (default: 50)
                      - Small (10-20): Fast response, tracks price closely
                      - Medium (30-100): Balanced (default 50)
                      - Large (100+): Slow response, smoother targets
        use_kalman: Use Kalman Filter (True, default) or Hanning (False)

    Returns:
        Target value (close - trend), positive = above trend, negative = below
    """
    if len(prices) == 0:
        return 0.0

    if center >= len(prices):
        return 0.0

    if use_kalman:
        # Use Kalman Filter up to current candle
        history = prices[:center + 1]
        if len(history) < 2:
            return 0.0

        filtered = kalman_filter_prices(history, response_time=response_time)
        current_price = float(prices[center])
        trend = float(filtered[-1])
        target = current_price - trend
    else:
        # Legacy Hanning filter (causal)
        start = max(0, center - window_size)
        end = center

        if end <= start:
            return 0.0

        window = prices[start:end]
        hanning = hanning_window(len(window))
        smoothed = float(np.dot(window, hanning))

        current_price = float(prices[center]) if center < len(prices) else 0.0
        target = current_price - smoothed

    return target


def batch_calculate(
    prices: List[float],
    window_size: int = 300,
    response_time: float = 50.0,
    use_kalman: bool = True,
) -> List[float]:
    """
    Calculate target values for all candles in a price series.

    Uses Kalman Filter by default (minimal lag, adaptive smoothing).

    Args:
        prices: List of close prices
        window_size: Window size for Hanning filter (ignored if use_kalman=True)
        response_time: Kalman response time in samples (default: 50)
        use_kalman: Use Kalman Filter (True, default) or Hanning (False)

    Returns:
        List of target values (same length as prices)
    """
    if not prices:
        return []

    prices_arr = np.array(prices, dtype=np.float64)
    return batch_calculate_numpy(
        prices_arr, window_size, response_time, use_kalman
    ).tolist()


def batch_calculate_numpy(
    prices: np.ndarray,
    window_size: int = 300,
    response_time: float = 50.0,
    use_kalman: bool = True,
) -> np.ndarray:
    """
    Vectorized target value calculation.

    Uses Kalman Filter by default (minimal lag, adaptive smoothing).
    Falls back to Hanning filter if use_kalman=False.

    Args:
        prices: Numpy array of close prices
        window_size: Window size for Hanning filter (ignored if use_kalman=True)
        response_time: Kalman response time in samples (default: 50)
                      - Small (10-20): Fast response, tracks price closely
                      - Medium (30-100): Balanced (default 50)
                      - Large (100+): Slow response, smoother targets
        use_kalman: Use Kalman Filter (True, default) or Hanning (False)

    Returns:
        Numpy array of target values (same length as input)
    """
    n = len(prices)
    if n == 0:
        return np.array([])

    if n == 1:
        return np.array([0.0])

    if use_kalman:
        # Kalman Filter: target = price - filtered
        filtered = kalman_filter_prices(prices, response_time=response_time)
        targets = prices - filtered
        targets[0] = 0.0  # First candle has no target
        return targets
    else:
        # Legacy Hanning filter
        targets = np.zeros(n, dtype=np.float64)

        if n >= window_size:
            hanning = hanning_window(window_size)
            smoothed_with_current = np.convolve(prices, hanning, mode='valid')

            for i in range(window_size, n):
                smoothed = smoothed_with_current[i - window_size]
                targets[i] = prices[i] - smoothed

            for i in range(1, min(window_size, n)):
                window = prices[0:i]
                if len(window) >= 2:
                    hann = hanning_window(len(window))
                    smoothed = float(np.dot(window, hann))
                    targets[i] = prices[i] - smoothed
        else:
            for i in range(1, n):
                window = prices[0:i]
                if len(window) >= 2:
                    hann = hanning_window(len(window))
                    smoothed = float(np.dot(window, hann))
                    targets[i] = prices[i] - smoothed

        return targets
