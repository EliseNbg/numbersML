"""
External data provider for wide vector.

Implement get_features() to add custom features to the wide vector.
Called once per second during wide vector generation.

Example:
    >>> from src.external.data_provider import get_features
    >>> features = get_features(candles={"BTC_USDC": {"close": 67000, "volume": 1.5}}, candle_time=now)
    >>> features
    {"fear_greed_index": 72.5, "btc_dominance": 55.3}
"""

from datetime import datetime
from typing import Dict


def get_features(
    candles: Dict[str, Dict[str, float]],
    candle_time: datetime,
) -> Dict[str, float]:
    """
    Compute external features for the wide vector.

    Args:
        candles: Per-symbol candle data with normalized keys (BTC_USDC, ETH_USDC, ...):
            {
                "BTC_USDC": {"close": 67000.0, "volume": 1.5},
                "ETH_USDC": {"close": 3500.0, "volume": 10.0},
                ...
            }
        candle_time: Current candle timestamp (second-aligned)

    Returns:
        Feature dict to append to wide vector:
            {"fear_greed_index": 72.5, "btc_dominance": 55.3}

    Notes:
        - Must be synchronous (no await)
        - Must not raise exceptions (catch and return empty dict)
        - Column names should be unique (not colliding with {symbol}_{field} format)
        - Values must be floats (no None, no strings)
    """
    try:
        # === YOUR CODE HERE ===
        # Example: fetch from external API, compute cross-symbol metrics, etc.
        #
        # btc_close = candles.get("BTC_USDC", {}).get("close", 0)
        # eth_close = candles.get("ETH_USDC", {}).get("close", 0)
        # ratio = btc_close / eth_close if eth_close > 0 else 0
        #
        # return {"btc_eth_ratio": ratio}

        return {}

    except Exception:
        # Never raise - return empty dict on error
        return {}
