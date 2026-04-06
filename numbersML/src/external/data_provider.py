"""
External Data Provider for Wide Vector Generation.

This module allows you to inject external data (like BTC Dominance, 
Macro Index, Weather, etc.) into the Wide Vector.

The function `get_features` is called once per wide vector generation.
The returned features are prepended to the wide vector.

Usage:
    1. Edit this function to fetch your data.
    2. Return a dictionary {"feature_name": value_float}.
    3. The wide vector generator will automatically include these.
"""

from typing import Dict, Any, Optional
from datetime import datetime


def get_features(
    candles: Dict[str, Dict[str, float]],
    indicators: Dict[str, Dict[str, float]],
    candle_time: datetime,
) -> Dict[str, float]:
    """
    Calculate external features to be added to the wide vector.

    Args:
        candles: Dict mapping symbol (e.g. 'BTC/USDC') to OHLCV data.
                 Example: {'BTC/USDC': {'close': 50000.0, 'volume': 100.0}, ...}
        indicators: Dict mapping symbol to its indicator values.
                    Example: {'BTC/USDC': {'rsi_14': 60.0, 'macd': ...}, ...}
        candle_time: The timestamp of the current candle being processed.

    Returns:
        Dictionary of feature names to float values.
        Example: {'btc_dominance': 52.5, 'market_cap': 1.2e12}
    """
    features = {}

    # --- YOUR CODE HERE ---
    # Example: Access candles data
    # if 'BTC_USDC' in candles:
    #     btc_close = candles['BTC_USDC']['close']
    #     features['btc_price_normalized'] = btc_close / 100000.0

    return features
