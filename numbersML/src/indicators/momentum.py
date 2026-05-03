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
                "period": {"type": "integer", "minimum": 2, "maximum": 100, "default": 14}
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
        """Calculate RSI."""
        if len(prices) < period + 1:
            return np.full(len(prices), np.nan)

        # Calculate price changes
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gains and losses
        avg_gain = np.zeros(len(prices))
        avg_loss = np.zeros(len(prices))

        # Initial average
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])

        # Smoothed averages
        for i in range(period + 1, len(prices)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

        # Calculate RS and RSI
        rs = np.zeros(len(prices))
        mask = avg_loss != 0
        rs[mask] = avg_gain[mask] / avg_loss[mask]

        rsi = np.zeros(len(prices))
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
        """Calculate Stochastic."""
        n = len(closes)
        slowk = np.full(n, np.nan)

        for i in range(k_period - 1, n):
            highest_high = np.max(highs[i - k_period + 1 : i + 1])
            lowest_low = np.min(lows[i - k_period + 1 : i + 1])

            if highest_high != lowest_low:
                slowk[i] = 100 * (closes[i] - lowest_low) / (highest_high - lowest_low)
            else:
                slowk[i] = 50

        # Calculate %D (SMA of %K)
        slowd = np.full(n, np.nan)
        for i in range(d_period - 1, n):
            if not np.isnan(slowk[i - d_period + 1 : i + 1]).all():
                slowd[i] = np.nanmean(slowk[i - d_period + 1 : i + 1])

        return slowk, slowd
