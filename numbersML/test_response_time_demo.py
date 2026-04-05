#!/usr/bin/env python3
"""
Demo: Kalman Filter response_time parameter

Shows how response_time controls the Kalman Filter behavior:
- Small values (10-20): Fast response, tracks price closely
- Medium values (30-100): Balanced smoothing (default: 50)
- Large values (100+): Slow response, very smooth trend
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.pipeline.target_value import (
    batch_calculate_numpy,
    kalman_filter_prices,
)

# Generate test price data
np.random.seed(42)
n_samples = 500

# Create price with trend changes
prices = np.zeros(n_samples)
prices[:100] = 100 + np.cumsum(np.random.randn(100) * 0.5)  # Sideways
prices[100:250] = prices[99] + np.linspace(0, 15, 150) + np.random.randn(150) * 0.5  # Uptrend
prices[250:350] = prices[249] - np.linspace(0, 10, 100) + np.random.randn(100) * 0.5  # Downtrend
prices[350:] = prices[349] + np.linspace(0, 5, 150) + np.random.randn(150) * 0.5  # Recovery

# Test different response times
response_times = [10, 30, 50, 100, 200]

fig, axes = plt.subplots(len(response_times) + 1, 1, figsize=(14, 12), sharex=True)

# Plot raw prices
axes[0].plot(prices, linewidth=1.5, alpha=0.7, label='Close Price', color='black')
axes[0].set_ylabel('Price')
axes[0].set_title('Raw Price Data')
axes[0].legend(loc='upper left', fontsize=8)
axes[0].grid(True, alpha=0.3)
axes[0].axvline(x=100, color='g', linestyle='--', alpha=0.5, label='Trend Change')
axes[0].axvline(x=250, color='r', linestyle='--', alpha=0.5)
axes[0].axvline(x=350, color='b', linestyle='--', alpha=0.5)

# Plot filtered trends and targets for each response_time
for idx, rt in enumerate(response_times):
    filtered = kalman_filter_prices(prices, response_time=rt)
    targets = batch_calculate_numpy(prices, response_time=rt)
    
    # Plot filtered trend
    axes[idx + 1].plot(prices, linewidth=1, alpha=0.4, color='gray', label='Price')
    axes[idx + 1].plot(filtered, linewidth=2.5, label=f'Kalman (response_time={rt})', alpha=0.9)
    axes[idx + 1].set_ylabel('Price')
    axes[idx + 1].set_title(f'response_time = {rt} samples')
    axes[idx + 1].legend(loc='upper left', fontsize=8)
    axes[idx + 1].grid(True, alpha=0.3)
    
    # Add lag indicator
    # Find where filtered reaches 50% of price change
    price_change_start = prices[100]
    price_change_end = prices[250]
    target_level = price_change_start + 0.5 * (price_change_end - price_change_start)
    
    # Find when filtered crosses target
    cross_idx = np.argmax(filtered[100:] > target_level) + 100
    price_cross_idx = np.argmax(prices[100:] > target_level) + 100
    lag = cross_idx - price_cross_idx
    
    axes[idx + 1].text(0.98, 0.02, 
                      f'Lag: ~{lag} samples\n'
                      f'Target std: {np.std(targets[100:]):.2f}',
                      transform=axes[idx + 1].transAxes,
                      fontsize=8,
                      verticalalignment='bottom',
                      horizontalalignment='right',
                      bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

plt.tight_layout()
plt.savefig('/tmp/kalman_response_time_demo.png', dpi=150)
print("✓ Saved /tmp/kalman_response_time_demo.png")

print("\n" + "="*80)
print("RESPONSE TIME PARAMETER GUIDE")
print("="*80)
print("\nHanning Filter:")
print("  - Uses window_size (e.g., 100, 300, 900)")
print("  - Larger window = more smoothing, more lag")
print("  - Fixed weights, doesn't adapt to volatility")
print("\nKalman Filter:")
print("  - Uses response_time (in samples)")
print("  - Equivalent concept: how long to react to changes")
print("  - Auto-adapts to price volatility")
print("\nConversion guide (approximate):")
print("  Hanning window=100  →  Kalman response_time=50")
print("  Hanning window=300  →  Kalman response_time=100")
print("  Hanning window=900  →  Kalman response_time=200")
print("\nRecommended values:")
print("  response_time=10-20:  Fast trading (scalping, high frequency)")
print("  response_time=30-50:  Day trading (balanced)")
print("  response_time=50-100: Swing trading (smooth trends)")
print("  response_time=100+:   Position trading (very smooth)")

print("\n" + "="*80)
print("USAGE")
print("="*80)
print("""
# Fast response (tracks price closely)
targets = batch_calculate_numpy(prices, response_time=20)

# Balanced (default)
targets = batch_calculate_numpy(prices, response_time=50)

# Smooth (like Hanning window=300)
targets = batch_calculate_numpy(prices, response_time=100)

# Legacy Hanning (backward compatible)
targets = batch_calculate_numpy(prices, use_kalman=False, window_size=300)
""")
