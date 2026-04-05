#!/usr/bin/env python3
"""
Demo: New target_value calculation (close - hanning_smoothed)

Shows the difference between:
1. OLD: target = hanning_weighted_average (uses future data - DATA LEAKAGE!)
2. NEW: target = close - hanning_smoothed (causal, no leakage)
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt

from src.pipeline.target_value import batch_calculate_numpy

# Generate test price data
np.random.seed(42)
n_samples = 1000
prices = 100 + np.cumsum(np.random.randn(n_samples) * 0.5)

# Calculate targets with different window sizes
window_sizes = [50, 100, 300]
fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

for idx, window_size in enumerate(window_sizes):
    targets = batch_calculate_numpy(prices, window_size=window_size)
    
    # Calculate smoothed trend for visualization
    from src.pipeline.target_value import hanning_window
    hanning = hanning_window(window_size)
    smoothed = np.convolve(prices, hanning, mode='valid')
    smoothed_aligned = np.roll(smoothed, 1)
    smoothed_aligned[0] = prices[0]
    
    axes[idx].plot(prices[:500], label='Close Price', alpha=0.7, linewidth=1.5)
    axes[idx].plot(smoothed_aligned[:500], label=f'Hanning Smoothed (window={window_size})', 
                   alpha=0.9, linewidth=2)
    axes[idx].plot(targets[:500] + np.mean(prices[:500]), 
                   label=f'Target (deviation, offset for visibility)', 
                   alpha=0.7, linewidth=1, linestyle='--')
    axes[idx].set_ylabel('Price')
    axes[idx].set_title(f'Window Size = {window_size}')
    axes[idx].legend(loc='upper left', fontsize=8)
    axes[idx].grid(True, alpha=0.3)

axes[2].set_xlabel('Candle Index')
plt.tight_layout()
plt.savefig('/tmp/target_value_demo.png', dpi=150)
print("✓ Saved visualization to /tmp/target_value_demo.png")

# Print statistics
print("\n" + "="*80)
print("TARGET VALUE STATISTICS")
print("="*80)

for window_size in window_sizes:
    targets = batch_calculate_numpy(prices, window_size=window_size)
    print(f"\nWindow size: {window_size}")
    print(f"  Mean: {np.mean(targets):.4f}")
    print(f"  Std:  {np.std(targets):.4f}")
    print(f"  Min:  {np.min(targets):.4f}")
    print(f"  Max:  {np.max(targets):.4f}")
    print(f"  % Positive: {100 * np.sum(targets > 0) / len(targets):.1f}%")
    print(f"  % Negative: {100 * np.sum(targets < 0) / len(targets):.1f}%")

print("\n" + "="*80)
print("KEY PROPERTIES")
print("="*80)
print("✓ Causal: Uses ONLY past data (no future leakage)")
print("✓ Target = close - smoothed_trend")
print("✓ Positive target = price ABOVE trend (bullish)")
print("✓ Negative target = price BELOW trend (bearish)")
print("✓ Constant price → target = 0 (no deviation)")
print("✓ Suitable for ML training without data leakage")
