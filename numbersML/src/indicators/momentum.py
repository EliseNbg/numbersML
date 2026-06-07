"""
Momentum indicators.

Includes:
- RSI (Relative Strength Index)
- Stochastic Oscillator
"""

from typing import Any, Optional

import numpy as np

from .base import Indicator, IndicatorResult


class RSIIndicator(Indicator):
    """
    Relative Strength Index indicator.

    Measures the speed and magnitude of price changes.
    Values range from 0 to 100.

    - Overbought: > 70
    - Oversold: < 30
    """

    category = "momentum"
    description = "Relative Strength Index - Measures price momentum"

    def __init__(self, period: int = 14) -> None:
        """Initialize RSI indicator."""
        super().__init__(period=period)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "maximum": 500, "default": 14}
            },
            "required": ["period"],
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate RSI values."""
        period = self.params["period"]
        rsi = self._calculate_rsi(prices, period)

        return IndicatorResult(name=self.name, values={"rsi": rsi}, metadata={"period": period})

    def _calculate_rsi(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate RSI using vectorized smoothed averages via lfilter."""
        n = len(prices)
        if n < period + 1:
            return np.full(n, np.nan)

        # Calculate price changes
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate smoothed averages using lfilter (compiled C, ~50x faster than Python loop)
        from scipy.signal import lfilter

        avg_gain = np.zeros(n)
        avg_loss = np.zeros(n)

        # Initial average (seed value)
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])

        # Filter input: gains[period:] has length n-1-period
        # Filter output goes to avg_gain[period+1:] (also n-1-period elements)
        b = np.array([1.0 / period])
        a = np.array([1.0, -(period - 1) / period])

        gain_out, _ = lfilter(b, a, gains[period:], zi=[avg_gain[period]])
        loss_out, _ = lfilter(b, a, losses[period:], zi=[avg_loss[period]])
        avg_gain[period + 1 :] = gain_out
        avg_loss[period + 1 :] = loss_out

        # Calculate RS and RSI
        rs = np.zeros(n)
        mask = avg_loss != 0
        rs[mask] = avg_gain[mask] / avg_loss[mask]

        rsi = np.zeros(n)
        rsi[mask] = 100 - (100 / (1 + rs[mask]))
        rsi[~mask] = 100  # No losses = RSI 100

        # Fill initial period with NaN
        rsi[:period] = np.nan

        return rsi


class StochasticIndicator(Indicator):
    """
    Stochastic Oscillator.

    Compares closing price to price range over a period.

    - Overbought: > 80
    - Oversold: < 20
    """

    category = "momentum"
    description = "Stochastic Oscillator - Compares close to price range"

    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
    ) -> None:
        """Initialize Stochastic indicator."""
        super().__init__(k_period=k_period, d_period=d_period)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "k_period": {"type": "integer", "minimum": 2, "maximum": 5000, "default": 14},
                "d_period": {"type": "integer", "minimum": 2, "maximum": 5000, "default": 3},
            },
            "required": ["k_period", "d_period"],
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate Stochastic values."""
        k_period = self.params["k_period"]
        d_period = self.params["d_period"]

        # Use prices as highs/lows if not provided
        if highs is None:
            highs = prices
        if lows is None:
            lows = prices

        slowk, slowd = self._calculate_stochastic(highs, lows, prices, k_period, d_period)

        return IndicatorResult(
            name=self.name,
            values={"stoch_k": slowk, "stoch_d": slowd},
            metadata={"k_period": k_period, "d_period": d_period},
        )

    def _calculate_stochastic(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        k_period: int,
        d_period: int,
    ) -> tuple:
        """Calculate Stochastic using vectorized sliding window operations."""
        n = len(closes)
        slowk = np.full(n, np.nan)

        if n < k_period:
            slowd = np.full(n, np.nan)
            return slowk, slowd

        # Vectorized sliding window max/min using stride_tricks
        high_windows = np.lib.stride_tricks.sliding_window_view(highs, k_period)
        low_windows = np.lib.stride_tricks.sliding_window_view(lows, k_period)

        highest_high = np.max(high_windows, axis=1)
        lowest_low = np.min(low_windows, axis=1)

        # Calculate %K
        range_hl = highest_high - lowest_low
        valid = range_hl != 0
        k_values = np.full(len(highest_high), 50.0)
        k_values[valid] = 100 * (closes[k_period - 1 :][valid] - lowest_low[valid]) / range_hl[valid]
        slowk[k_period - 1 :] = k_values

        # Calculate %D (SMA of %K) using cumsum
        slowd = np.full(n, np.nan)
        if n >= k_period + d_period - 1:
            valid_k = slowk[k_period - 1 :]
            cumsum = np.cumsum(valid_k)
            d_sma = np.full(len(valid_k), np.nan)
            d_sma[d_period - 1 :] = (cumsum[d_period - 1 :] - np.concatenate([[0], cumsum[:-d_period]])) / d_period
            slowd[k_period - 1 :] = d_sma

        return slowk, slowd
