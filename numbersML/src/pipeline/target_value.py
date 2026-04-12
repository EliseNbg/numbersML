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
from scipy.signal import savgol_filter, find_peaks


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


def savgol_filter_prices(
    prices: np.ndarray,
    window_length: int = 200,
    polyorder: int = 3,
    causal: bool = True,
) -> np.ndarray:
    """
    Apply Savitzky-Golay filter to price series.

    Savitzky-Golay fits a polynomial to a sliding window of data,
    producing very smooth output that preserves the shape of trends.

    Args:
        prices: Array of close prices
        window_length: Window size for polynomial fitting (default: 200)
                      Larger = smoother, but more lag
        polyorder: Polynomial order (default: 3 = cubic)
                  Higher = more flexible, lower = smoother
        causal: If True, uses only past data (t-window : t)
               If False, uses centered window (t-window/2 : t+window/2)
                      For ML training only - NOT for live indicators!

    Returns:
        Array of filtered price estimates
    """
    n = len(prices)
    if n == 0:
        return np.array([])

    if n == 1:
        return prices.copy()

    # Adjust window length if we don't have enough data
    actual_window = min(window_length, n)

    # Ensure window_length is odd (required by savgol_filter)
    if actual_window % 2 == 0:
        actual_window -= 1

    # Ensure polyorder < window_length
    actual_polyorder = min(polyorder, actual_window - 1)

    # Need at least polyorder + 1 points
    if actual_window <= actual_polyorder:
        return prices.copy()

    try:
        # Apply savgol_filter
        # Use mode='nearest' to handle edges properly
        filtered = savgol_filter(
            prices,
            window_length=actual_window,
            polyorder=actual_polyorder,
            mode='nearest',
        )

        if causal:
            # Causal: shift by half window to avoid future leakage
            # This makes smoothed[t] depend on prices[t-window : t]
            shift = actual_window // 2
            filtered = np.roll(filtered, shift)

            # Handle the first 'shift' points with partial windows
            for i in range(1, min(shift + 1, n)):
                window = prices[0:i+1]
                if len(window) > actual_polyorder:
                    try:
                        win_len = len(window) if len(window) % 2 == 1 else len(window) - 1
                        win_len = max(win_len, actual_polyorder + 1)
                        win_poly = min(actual_polyorder, win_len - 1)
                        filtered[i] = savgol_filter(
                            window,
                            window_length=win_len,
                            polyorder=win_poly,
                            mode='nearest',
                        )[-1]
                    except:
                        pass  # Keep the rolled value
        # else: non-causal (centered window) - no shift needed
        # savgol_filter already uses centered window by default

    except Exception:
        # Fallback: use simple moving average if savgol fails
        filtered = np.zeros(n)
        for i in range(n):
            if causal:
                start = max(0, i - actual_window + 1)
            else:
                half = actual_window // 2
                start = max(0, i - half)
                end = min(n, i + half + 1)
            filtered[i] = np.mean(prices[start:i+1])

    return filtered


def batch_calculate_target_data(
    prices: List[float],
    response_time: float = 2000.0,
    method: str = 'hanning',
    use_future: bool = True,  # For ML training only!
    use_kalman: bool = True,  # Deprecated, kept for backward compatibility
) -> List[Optional[Dict[str, Any]]]:
    """
    Calculate market state for all candles in a price series.

    Returns list of dicts with filtered_value, close, diff, trend, velocity,
    and normalized_value (local [0..1] range for ML target prediction).

    Args:
        prices: List of close prices
        response_time: Window size for smoothing (default: 600)
        method: Smoothing method: 'kalman', 'savgol', 'hanning'
        use_future: If True, Savitzky-Golay uses centered window (ML training ONLY!)
        use_kalman: Deprecated - use method='kalman' instead

    Returns:
        List of dicts with market state (same length as prices)
    """
    if not prices:
        return []

    prices_arr = np.array(prices, dtype=np.float64)

    # Handle deprecated use_kalman parameter
    if method == 'kalman' or (use_kalman and method not in ['savgol', 'hanning']):
        if not use_kalman:
            method = 'hanning'
        else:
            method = 'savgol' if method not in ['kalman', 'savgol', 'hanning'] else method

    # Calculate filtered values based on method
    if method == 'kalman':
        filtered = kalman_filter_prices(prices_arr, response_time=response_time)
    elif method == 'savgol':
        causal = not use_future  # If use_future=True, causal=False
        filtered = savgol_filter_prices(prices_arr, window_length=int(response_time), causal=causal)
    elif method == 'hanning':
        # Hanning Filter
        # Uses a sliding window of data with Hanning weights
        window_length = int(response_time)
        if window_length < 2 or len(prices_arr) < window_length:
            filtered = prices_arr.copy()
        else:
            # Create and normalize Hanning window
            hann = np.hanning(window_length)
            hann = hann / hann.sum()

            # Convolve prices with Hanning window
            valid_conv = np.convolve(prices_arr, hann, mode='valid')

            filtered = np.empty_like(prices_arr)
            shift = window_length // 2

            if not use_future:
                # Causal: Align result with the END of the window (uses past data only)
                # valid_conv[i] corresponds to window ending at i + window_length - 1
                filtered[:window_length-1] = prices_arr[:window_length-1]
                filtered[window_length-1:] = valid_conv
            else:
                # Centered: Align result with the CENTER of the window (uses future data)
                # valid_conv[i] corresponds to window centered at i + shift
                filtered[:shift] = prices_arr[:shift]
                filtered[shift:shift+len(valid_conv)] = valid_conv
                filtered[shift+len(valid_conv):] = prices_arr[shift+len(valid_conv):]
    else:  # legacy fallback
        filtered = prices_arr  # Simplified

    # Calculate velocity (rate of change of filtered trend, used for trend direction)
    velocity = np.zeros(len(filtered))
    for i in range(1, len(filtered)):
        velocity[i] = float(filtered[i]) - float(filtered[i-1])

    # Compute std of price returns for ML target scaling
    # Use 30s return std as reference scale
    if len(filtered) > 31:
        ret_30s = (filtered[30:] - filtered[:-30]) / np.abs(filtered[:-30] + 1e-10)
        std_return = float(np.std(ret_30s))
    else:
        std_return = 1e-6
    if std_return < 1e-10:
        std_return = 1e-6

    # Calculate normalized value: map filtered_value to [0..1] using local min/max
    n = len(filtered)
    normalized = np.zeros(n)  # Will hold [0..1] values
    norm_min = np.zeros(n)
    norm_max = np.zeros(n)

    if n > 10:
        try:
            # Find peaks (maxima) and valleys (minima)
            peaks, _ = find_peaks(filtered, distance=10)
            valleys, _ = find_peaks(-filtered, distance=10)

            # Merge and sort all extrema points
            all_extrema = np.sort(np.concatenate([peaks, valleys]))

            # Add boundaries
            if len(all_extrema) == 0 or all_extrema[0] > 0:
                all_extrema = np.concatenate([[0], all_extrema])
            if all_extrema[-1] < n - 1:
                all_extrema = np.concatenate([all_extrema, [n - 1]])

            # For each segment between extrema, compute min/max and normalize
            for seg_idx in range(len(all_extrema) - 1):
                start_idx = int(all_extrema[seg_idx])
                end_idx = int(all_extrema[seg_idx + 1])

                segment_min = float(filtered[start_idx:end_idx+1].min())
                segment_max = float(filtered[start_idx:end_idx+1].max())

                norm_min[start_idx:end_idx+1] = segment_min
                norm_max[start_idx:end_idx+1] = segment_max

                # Normalize to [0..1]
                seg_range = segment_max - segment_min
                if seg_range > 0:
                    normalized[start_idx:end_idx+1] = (filtered[start_idx:end_idx+1] - segment_min) / seg_range
                else:
                    normalized[start_idx:end_idx+1] = 0.5  # Flat segment -> middle
        except Exception:
            # Fallback: use running window min/max
            window = 60
            for i in range(n):
                start = max(0, i - window)
                end = min(n, i + 1)
                w_min = filtered[start:end].min()
                w_max = filtered[start:end].max()
                norm_min[i] = w_min
                norm_max[i] = w_max
                w_range = w_max - w_min
                if w_range > 0:
                    normalized[i] = (filtered[i] - w_min) / w_range
                else:
                    normalized[i] = 0.5
    else:
        # Not enough data, use flat values
        f_min = filtered.min() if n > 0 else 0.0
        f_max = filtered.max() if n > 0 else 0.0
        norm_min.fill(f_min)
        norm_max.fill(f_max)
        f_range = f_max - f_min
        if f_range > 0:
            normalized = (filtered - f_min) / f_range
        else:
            normalized.fill(0.5)

    results = []
    for i in range(len(prices_arr)):
        current_price = float(prices_arr[i])
        filtered_value = float(filtered[i])
        diff = current_price - filtered_value
        norm_val = float(normalized[i])
        n_min = float(norm_min[i])
        n_max = float(norm_max[i])

        # Velocity (rate of change)
        if i > 0:
            vel = filtered_value - float(filtered[i-1])
        else:
            vel = 0.0

        # Scaled return targets for ML training (stored for visualization)
        # target = sigmoid(return / std * 2), range [0..1]
        # >0.5 = bullish, <0.5 = bearish
        def scaled_return(horizon_secs):
            j = i + horizon_secs  # future index
            if j < len(prices_arr):
                ret = (float(prices_arr[j]) - current_price) / current_price
                return round(1.0 / (1.0 + np.exp(-ret / (std_return + 1e-10) * 2.0)), 8)
            return None

        ml_target_30 = scaled_return(30)
        ml_target_120 = scaled_return(120)

        # Trend direction
        if vel > 0.01:
            trend = 'up'
        elif vel < -0.01:
            trend = 'down'
        else:
            trend = 'flat'

        results.append({
            'filtered_value': round(filtered_value, 8),
            'close': current_price,
            'diff': round(diff, 8),
            'trend': trend,
            'velocity': round(vel, 8),
            'normalized_value': round(norm_val, 8),
            'norm_min': round(n_min, 8),
            'norm_max': round(n_max, 8),
            'ml_target_30': ml_target_30,
            'ml_target_120': ml_target_120,
            'method': method,
            'use_future': use_future if method == 'savgol' else False,
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
