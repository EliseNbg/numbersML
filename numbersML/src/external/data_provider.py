"""External Data Provider for Wide Vector Generation.

This module allows you to inject external data (like BTC Dominance,
Macro Index, Weather, etc.) into the Wide Vector.

The function `get_features` is called once per wide vector generation.
The returned features are prepended to the wide vector.

Usage:
    1. Edit this function to fetch your data.
    2. Return a dictionary {"feature_name": value_float}.
    3. The wide vector generator will automatically include these.
"""

import calendar
import math
from datetime import datetime, timedelta


def datetime_to_sinus_float(in_time: datetime, period: str = "day") -> float:
    """Convert datetime to a float [0.0, 1.0] using sinusoidal mapping.

    The transition at period boundaries is mathematically C1-continuous
    (both value and derivative match), so there are no kinks or jumps.

    Args:
        in_time: The datetime to convert.
        period: 'day' (24h), 'week' (7 days), or 'month' (current calendar month).

    Returns:
        Float value between 0.0 and 1.0.

    Raises:
        ValueError: If period is not 'day', 'week', or 'month'.
    """
    if period == "day":
        start = in_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

    elif period == "week":
        # Week starts on Monday (ISO 8601)
        start = (in_time - timedelta(days=in_time.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=7)

    elif period == "month":
        start = in_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _, days_in_month = calendar.monthrange(in_time.year, in_time.month)
        end = start + timedelta(days=days_in_month)

    else:
        raise ValueError("period must be 'day', 'week', or 'month'.")

    total_seconds = (end - start).total_seconds()
    elapsed_seconds = (in_time - start).total_seconds()
    fraction = elapsed_seconds / total_seconds  # Value between 0.0 and 1.0

    # Scale cosine curve to [0, 1]: Start=0, Middle=1, End=0
    return 0.5 * (1 - math.cos(2 * math.pi * fraction))


def get_features(
    candles: dict[str, dict[str, float]],
    indicators: dict[str, dict[str, float]],
    candle_time: datetime,
) -> dict[str, float]:
    """Calculate external features to be added to the wide vector.

    Args:
        candles: Dict mapping symbol (e.g. 'BTC/USDC') to OHLCV data.
        indicators: Dict mapping symbol to its indicator values.
        candle_time: The timestamp of the current candle being processed.

    Returns:
        Dictionary of feature names to float values.
    """
    day_osc = datetime_to_sinus_float(candle_time, "day")
    week_osc = datetime_to_sinus_float(candle_time, "week")
    month_osc = datetime_to_sinus_float(candle_time, "month")

    features = {
        "day_osc": day_osc,
        "week_osc": week_osc,
        "month_osc": month_osc,
    }

    # --- YOUR CODE HERE ---
    # Example: Access candles data
    # if 'BTC_USDC' in candles:
    #     btc_close = candles['BTC_USDC']['close']
    #     features['btc_price_normalized'] = btc_close / 100000.0

    return features
