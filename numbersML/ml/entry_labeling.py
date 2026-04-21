"""
Entry Point Labeling Logic for Trading ML Model.

This is the MOST IMPORTANT part of the trading system.
Instead of predicting future price, we label ONLY if:
  - Is this point a GOOD ENTRY for a long position?
  - Will this entry hit 0.5% profit before 0.2% stop loss?

This is binary classification, not regression.
This approach eliminates 90% of the reasons why ML trading models fail.
"""

import numpy as np
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)


def label_entry_points(
    prices: np.ndarray,
    profit_target: float = 0.005,  # 0.5% profit target
    stop_loss: float = 0.002,     # 0.2% stop loss
    look_ahead: int = 1800,       # 30 minutes maximum holding time
    min_bars_after: int = 60      # Ignore entries with immediate stop
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Label every candle if it's a valid entry point.

    Algorithm (NO LOOKAHEAD BIAS):
    For each candle i:
        Look only into THE FUTURE from i onwards
        Check if price hits +profit_target before -stop_loss
        If YES → label = 1 (good entry)
        If NO → label = 0 (bad entry)
        If neither hit within look_ahead bars → label = -1 (ignore)

    Args:
        prices: Array of close prices (1 per second)
        profit_target: Relative profit target (0.005 = 0.5%)
        stop_loss: Relative stop loss (0.002 = 0.2%)
        look_ahead: Maximum bars to look into future
        min_bars_after: Require at least N bars after entry

    Returns:
        labels: Array [0, 1, -1] same length as prices
        entry_scores: Array with quality score [0..1]
    """
    n = len(prices)
    labels = np.full(n, -1, dtype=np.int8)
    scores = np.zeros(n, dtype=np.float32)

    logger.info(f"Labeling {n} candles for entry points...")
    logger.info(f"  Profit target: {profit_target*100:.2f}%")
    logger.info(f"  Stop loss:     {stop_loss*100:.2f}%")
    logger.info(f"  Look ahead:    {look_ahead/60:.1f} minutes")

    for i in range(n - look_ahead - min_bars_after):
        entry_price = prices[i]

        upper_target = entry_price * (1 + profit_target)
        lower_target = entry_price * (1 - stop_loss)

        # Look only FUTURE prices from i+1 onwards
        future_prices = prices[i+1 : i+1 + look_ahead]

        # Find first hit
        hit_upper = np.argmax(future_prices >= upper_target)
        hit_lower = np.argmax(future_prices <= lower_target)

        if future_prices[hit_upper] >= upper_target and future_prices[hit_lower] <= lower_target:
            # Both hit: which comes first?
            if hit_upper < hit_lower:
                labels[i] = 1
                scores[i] = 1.0 - (hit_upper / look_ahead)
            else:
                labels[i] = 0
                scores[i] = 0.0

        elif future_prices[hit_upper] >= upper_target:
            # Only profit hit
            labels[i] = 1
            scores[i] = 1.0 - (hit_upper / look_ahead) * 0.5

        elif future_prices[hit_lower] <= lower_target:
            # Only stop loss hit
            labels[i] = 0
            scores[i] = 0.0

        else:
            # Neither hit
            labels[i] = -1
            scores[i] = 0.5

    valid_count = np.sum(labels != -1)
    positive_count = np.sum(labels == 1)
    negative_count = np.sum(labels == 0)

    logger.info(f"Labeling complete:")
    logger.info(f"  Valid entries:    {valid_count} / {n} ({valid_count/n*100:.1f}%)")
    logger.info(f"  Good entries:     {positive_count} ({positive_count/valid_count*100:.1f}%)")
    logger.info(f"  Bad entries:      {negative_count} ({negative_count/valid_count*100:.1f}%)")

    return labels, scores


def filter_entry_samples(
    features: np.ndarray,
    labels: np.ndarray,
    scores: np.ndarray,
    balance_classes: bool = True,
    undersample_ratio: float = 1.2
) -> Tuple[np.ndarray, np.ndarray]:
    """Filter and optionally balance a labelled dataset while preserving temporal order.

    Temporal order MUST be preserved here so that callers can do a clean
    chronological train/val split afterwards.  Previous random-shuffle-based
    undersampling destroyed this order and caused training samples from the
    future to appear in what looked like the "early" portion of the dataset —
    a form of temporal leakage.

    Undersampling (when enabled) uses a uniform stride across the negative
    class so that the negatives are spread evenly in time rather than chosen
    at random.  All indices are sorted before indexing to maintain the
    original chronological sequence.

    Args:
        features: Feature matrix aligned with ``labels``.
        labels: Integer labels: 1 = good entry, 0 = bad entry, -1 = ignore.
        scores: Quality scores aligned with ``labels``.
        balance_classes: Whether to undersample the majority (negative) class.
        undersample_ratio: Target neg/pos ratio after undersampling.

    Returns:
        X: Filtered (and optionally undersampled) feature matrix in
           chronological order.
        y: Corresponding binary labels.
    """
    # Keep only valid labels
    mask = labels != -1

    X = features[mask]
    y = labels[mask]
    w = scores[mask]

    logger.info("Filtering dataset:")
    logger.info(f"  Original samples: {len(features)}")
    logger.info(f"  Valid samples:    {len(X)}")

    if balance_classes:
        pos_idx = np.where(y == 1)[0]
        neg_idx = np.where(y == 0)[0]

        logger.info(f"  Positive: {len(pos_idx)}, Negative: {len(neg_idx)}")

        if len(neg_idx) > len(pos_idx) * undersample_ratio:
            keep_neg = int(len(pos_idx) * undersample_ratio)

            # Stride-based selection: take every k-th negative so the
            # retained negatives are uniformly spread across the timeline.
            stride = max(1, len(neg_idx) // keep_neg)
            neg_idx_kept = neg_idx[::stride][:keep_neg]

            # Sort to restore chronological order before returning.
            keep_idx = np.sort(np.concatenate([pos_idx, neg_idx_kept]))

            X = X[keep_idx]
            y = y[keep_idx]
            w = w[keep_idx]

            logger.info(f"  After balancing: {len(X)} samples")
            logger.info(f"    Positive: {len(pos_idx)}, Negative: {len(neg_idx_kept)}")

    return X, y
