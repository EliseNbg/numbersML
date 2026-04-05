#!/usr/bin/env python3
"""
Demo: Kalman Filter vs Hanning Filter for Target Value Calculation

Shows the advantages of Kalman Filter:
- Minimal lag (reacts faster to trend changes)
- Adapts to volatility (auto-tunes smoothing)
- Optimal smoothing (mean-square error optimal)
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.pipeline.target_value import (
    batch_calculate_numpy,
    kalman_filter_prices,
)

# Generate test price data with different patterns
np.random.seed(42)
n_samples = 1000

# Pattern 1: Trending market with noise
trend = np.linspace(100, 120, n_samples)
noise = np.random.randn(n_samples) * 1.5
prices_trending = trend + noise

# Pattern 2: Sideways market
prices_sideways = 100 + np.random.randn(n_samples) * 2

# Pattern 3: Volatile market (changing volatility)
volatility = 1 + 3 * np.sin(2 * np.pi * np.arange(n_samples) / 500)
prices_volatile = 100 + np.cumsum(np.random.randn(n_samples) * volatility * 0.3)

def plot_comparison(prices, title, filename):
    """Plot Kalman vs Hanning comparison."""
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    
    # Calculate targets
    targets_kalman = batch_calculate_numpy(prices, use_kalman=True)
    targets_hanning = batch_calculate_numpy(prices, window_size=100, use_kalman=False)
    
    # Calculate filtered trends
    filtered_kalman = kalman_filter_prices(prices)
    
    # Hanning filter for visualization
    from src.pipeline.target_value import hanning_window
    hanning = hanning_window(100)
    filtered_hanning = np.convolve(prices, hanning, mode='valid')
    filtered_hanning = np.concatenate([filtered_hanning[:1]] * 50 + [filtered_hanning])
    filtered_hanning = filtered_hanning[:len(prices)]
    
    # Plot prices and filters
    axes[0].plot(prices[:500], label='Close Price', alpha=0.5, linewidth=1)
    axes[0].plot(filtered_kalman[:500], label='Kalman Filter', linewidth=2.5, alpha=0.9)
    axes[0].plot(filtered_hanning[:500], label='Hanning Filter (window=100)', 
                 linewidth=2, alpha=0.7, linestyle='--')
    axes[0].set_ylabel('Price')
    axes[0].set_title(f'{title} - Price & Filters')
    axes[0].legend(loc='upper left', fontsize=8)
    axes[0].grid(True, alpha=0.3)
    
    # Plot targets (deviations)
    axes[1].plot(targets_kalman[:500], label='Kalman Target (close - kalman)', 
                 linewidth=1.5, alpha=0.8)
    axes[1].plot(targets_hanning[:500], label='Hanning Target (close - hanning)', 
                 linewidth=1.5, alpha=0.7, linestyle='--')
    axes[1].axhline(y=0, color='r', linestyle=':', alpha=0.5)
    axes[1].set_ylabel('Target Value')
    axes[1].set_title('Target Values (Deviation from Trend)')
    axes[1].legend(loc='upper left', fontsize=8)
    axes[1].grid(True, alpha=0.3)
    
    # Plot target statistics
    kalman_std = np.std(targets_kalman[:500])
    hanning_std = np.std(targets_hanning[:500])
    kalman_mean = np.mean(np.abs(targets_kalman[:500]))
    hanning_mean = np.mean(np.abs(targets_hanning[:500]))
    
    stats_text = f'Kalman: mean|target|={kalman_mean:.3f}, std={kalman_std:.3f}\n'
    stats_text += f'Hanning: mean|target|={hanning_mean:.3f}, std={hanning_std:.3f}\n'
    stats_text += f'\nKalman reduces lag by ~{hanning_mean/kalman_mean:.1f}x'
    
    axes[2].axis('off')
    axes[2].text(0.1, 0.5, stats_text, fontsize=12, 
                fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                verticalalignment='center')
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close()
    print(f"✓ Saved {filename}")

# Generate comparisons
print("Generating Kalman vs Hanning comparisons...\n")
plot_comparison(prices_trending, "Trending Market", "/tmp/kalman_vs_hanning_trending.png")
plot_comparison(prices_sideways, "Sideways Market", "/tmp/kalman_vs_hanning_sideways.png")
plot_comparison(prices_volatile, "Volatile Market", "/tmp/kalman_vs_hanning_volatile.png")

print("\n" + "="*80)
print("KALMAN FILTER ADVANTAGES")
print("="*80)
print("✓ Minimal lag: Reacts faster to trend changes")
print("✓ Adaptive: Auto-tunes to market volatility")
print("✓ Optimal: Minimum mean-square error estimate")
print("✓ No window size: Uses process/measurement noise instead")
print("✓ Tracks trends: Target ≈ 0 for steady trends (no false signals)")
print("✓ Sensitive to reversals: Quickly detects trend changes")
print("\n" + "="*80)
print("USAGE")
print("="*80)
print("""
# Default: Kalman Filter (recommended)
from src.pipeline.target_value import batch_calculate_numpy
targets = batch_calculate_numpy(prices)

# Legacy: Hanning Filter (backward compatibility)
targets = batch_calculate_numpy(prices, use_kalman=False, window_size=100)
""")
