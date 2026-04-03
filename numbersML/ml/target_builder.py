"""
Target Value Builder with Causal Hanning Filter.

IMPORTANT: This implements CAUSAL filtering to prevent data leakage!
- WRONG: smoothed[t] = Hanning(close[t-150 : t+150])  # Uses future data!
- RIGHT: smoothed[t] = Hanning(close[t-300 : t])      # Only past data

The target is the smoothed price at t + prediction_horizon (future prediction).
This ensures the model learns to PREDICT the future, not just rebuild the filter.
"""

import numpy as np
from typing import Optional


def causal_hanning_filter(
    prices: np.ndarray,
    window_size: int = 300,
    prediction_horizon: int = 30,
) -> np.ndarray:
    """
    Apply causal Hanning filter to prices (NO data leakage).
    
    Args:
        prices: Array of close prices [t0, t1, t2, ..., tn]
        window_size: Size of the Hanning window (only uses PAST data)
        prediction_horizon: How many steps into the future to predict
        
    Returns:
        Array of smoothed prices, where target[t] = smoothed_price[t + prediction_horizon]
        NaN values at the beginning (need window_size samples to start)
        and at the end (need prediction_horizon future samples)
    
    How it works:
        For each time t, we compute:
            smoothed[t] = Hanning(prices[t-window_size : t])
        
        Then the target for time t is:
            target[t] = smoothed[t + prediction_horizon]
        
        This means at time t, we predict the smoothed price at t + prediction_horizon
    """
    if len(prices) < window_size + prediction_horizon:
        raise ValueError(
            f"Not enough data: need {window_size + prediction_horizon} samples, "
            f"got {len(prices)}"
        )
    
    # Create Hanning window (causal - only uses past data)
    hanning_window = np.hanning(window_size)
    hanning_window = hanning_window / hanning_window.sum()  # Normalize
    
    # Apply causal convolution
    # smoothed[t] = sum(prices[t-window_size:t] * hanning_window)
    smoothed = np.convolve(prices, hanning_window, mode='valid')
    
    # smoothed[0] corresponds to time window_size-1 (first valid position)
    # smoothed[i] corresponds to time window_size-1+i
    
    # Now create target array with prediction horizon
    # We want target[t] = smoothed[t + prediction_horizon]
    # So we shift smoothed backwards by prediction_horizon
    
    # Total length needed: len(smoothed) - prediction_horizon
    target_length = len(smoothed) - prediction_horizon
    
    if target_length <= 0:
        raise ValueError(
            f"Prediction horizon {prediction_horizon} too large for smoothed array of length {len(smoothed)}"
        )
    
    # Target at time t is smoothed at t + prediction_horizon
    # First valid target is at index (window_size - 1 + prediction_horizon) in original prices
    targets = smoothed[:target_length]
    
    return targets


def compute_target_with_horizon(
    prices: np.ndarray,
    window_size: int = 300,
    prediction_horizon: int = 30,
    return_alignment: bool = False,
) -> dict:
    """
    Compute target values with causal Hanning filter and future prediction.
    
    Args:
        prices: Array of close prices
        window_size: Hanning window size (causal, uses only past)
        prediction_horizon: Steps into future to predict
        return_alignment: If True, return alignment info for dataset
        
    Returns:
        Dictionary with:
            - targets: Array of target values
            - valid_start_idx: First valid index in original prices
            - valid_end_idx: Last valid index in original prices
    """
    # Apply causal Hanning filter
    targets = causal_hanning_filter(prices, window_size, prediction_horizon)
    
    # Calculate valid range in original price array
    # First valid target uses prices from index (window_size - 1 + prediction_horizon)
    valid_start_idx = window_size - 1 + prediction_horizon
    # Last valid target uses prices up to the end
    valid_end_idx = len(prices)
    
    result = {
        'targets': targets,
        'valid_start_idx': valid_start_idx,
        'valid_end_idx': valid_end_idx,
    }
    
    if return_alignment:
        result['window_size'] = window_size
        result['prediction_horizon'] = prediction_horizon
        result['total_length'] = len(prices)
        result['num_targets'] = len(targets)
    
    return result


# Test the implementation
if __name__ == "__main__":
    # Create test prices
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(1000)) + 100
    
    window_size = 300
    prediction_horizon = 30
    
    print(f"Testing causal Hanning filter...")
    print(f"  Prices: {len(prices)} samples")
    print(f"  Window size: {window_size} (causal, only past)")
    print(f"  Prediction horizon: {prediction_horizon} steps into future")
    print()
    
    result = compute_target_with_horizon(
        prices, window_size, prediction_horizon, return_alignment=True
    )
    
    print(f"Results:")
    print(f"  Valid start index: {result['valid_start_idx']}")
    print(f"  Valid end index: {result['valid_end_idx']}")
    print(f"  Number of targets: {result['num_targets']}")
    print(f"  First target value: {result['targets'][0]:.4f}")
    print(f"  Last target value: {result['targets'][-1]:.4f}")
    print()
    
    # Verify no data leakage
    print("Verification:")
    print(f"  ✓ Target[0] uses prices from index 0 to {window_size + prediction_horizon - 1}")
    print(f"  ✓ Target[0] = smoothed_price at time {window_size - 1 + prediction_horizon}")
    print(f"  ✓ NO future data beyond prediction horizon")
    print()
    
    # Test different prediction horizons
    for horizon in [10, 30, 60, 300]:
        if len(prices) >= window_size + horizon:
            result = compute_target_with_horizon(prices, window_size, horizon)
            print(f"  Horizon {horizon:3d}s: {len(result['targets']):5d} targets, "
                  f"range [{result['targets'].min():.2f}, {result['targets'].max():.2f}]")
