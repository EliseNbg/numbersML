"""
Volatility and Volume indicators for long-term analysis.

Volatility:
- Bollinger Bands
- ATR (Average True Range)
- Keltner Channel

Volume:
- OBV (On Balance Volume)
- VWAP (Volume Weighted Average Price)
- MFI (Money Flow Index)
"""

from typing import Any, Optional

import numpy as np

from .base import Indicator, IndicatorResult


class BollingerBandsIndicator(Indicator):
    """
    Bollinger Bands.

    Volatility bands around moving average.
    Standard: SMA(20) with ±2 standard deviations

    Signals:
    - Price touches upper band: Overbought
    - Price touches lower band: Oversold
    - Bands squeeze: Low volatility (breakout coming)
    - Bands expand: High volatility
    """

    category = "volatility"
    description = "Bollinger Bands - Volatility bands"

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        """Initialize Bollinger Bands indicator."""
        super().__init__(period=period, std_dev=std_dev)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "maximum": 5000, "default": 20},
                "std_dev": {"type": "number", "minimum": 0.5, "maximum": 5.0, "default": 2.0},
            },
            "required": ["period", "std_dev"],
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate Bollinger Bands."""
        period = self.params["period"]
        std_dev = self.params["std_dev"]

        if len(prices) < period:
            return IndicatorResult(
                name=self.name,
                values={
                    "upper": np.full(len(prices), np.nan),
                    "middle": np.full(len(prices), np.nan),
                    "lower": np.full(len(prices), np.nan),
                },
                metadata={"period": period, "std_dev": std_dev},
            )

        n = len(prices)

        # Vectorized rolling mean and std using sliding_window_view
        windows = np.lib.stride_tricks.sliding_window_view(prices, period)
        rolling_mean = np.mean(windows, axis=1)
        rolling_std = np.std(windows, axis=1)

        # Build full arrays with NaN padding
        middle = np.full(n, np.nan)
        std = np.full(n, np.nan)
        middle[period - 1 :] = rolling_mean
        std[period - 1 :] = rolling_std

        # Upper and lower bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return IndicatorResult(
            name=self.name,
            values={"upper": upper, "middle": middle, "lower": lower, "std": std},
            metadata={"period": period, "std_dev": std_dev},
        )


class ATRIndicator(Indicator):
    """
    Average True Range.

    Measures volatility (not direction).
    Standard period: 14

    Higher ATR = Higher volatility
    Lower ATR = Lower volatility
    """

    category = "volatility"
    description = "Average True Range - Volatility indicator"

    def __init__(self, period: int = 14) -> None:
        """Initialize ATR indicator."""
        super().__init__(period=period)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "maximum": 5000, "default": 14}
            },
            "required": ["period"],
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate ATR."""
        period = self.params["period"]

        if highs is None:
            highs = prices
        if lows is None:
            lows = prices

        atr = self._calculate_atr(highs, lows, prices, period)

        return IndicatorResult(name=self.name, values={"atr": atr}, metadata={"period": period})

    def _calculate_atr(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int,
    ) -> np.ndarray:
        """Calculate ATR using vectorized operations."""
        n = len(closes)
        atr = np.full(n, np.nan)
        tr = np.zeros(n)

        # Vectorized True Range
        tr[1:] = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
        )

        # First ATR is simple average
        if n > period:
            atr[period] = np.mean(tr[1 : period + 1])

            # Smoothed ATR (inherently sequential)
            for i in range(period + 1, n):
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        return atr


class OBVIndicator(Indicator):
    """
    On Balance Volume.

    Volume-based momentum indicator.

    Signals:
    - OBV rising: Buying pressure
    - OBV falling: Selling pressure
    - OBV divergence: Potential reversal
    """

    category = "volume"
    description = "On Balance Volume - Volume momentum indicator"

    def __init__(self) -> None:
        """Initialize OBV indicator (no parameters)."""
        super().__init__()

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {},
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate OBV using vectorized operations."""
        n = len(prices)
        obv = np.zeros(n)

        # Vectorized: compare consecutive prices
        price_diff = np.diff(prices)
        signs = np.zeros(n - 1)
        signs[price_diff > 0] = 1.0
        signs[price_diff < 0] = -1.0
        obv[1:] = np.cumsum(signs * volumes[1:])

        return IndicatorResult(name=self.name, values={"obv": obv}, metadata={})


class VWAPIndicator(Indicator):
    """
    Volume Weighted Average Price.

    Average price weighted by volume.
    Institutional benchmark.

    Signals:
    - Price above VWAP: Bullish
    - Price below VWAP: Bearish
    """

    category = "volume"
    description = "VWAP - Volume weighted average price"

    def __init__(self) -> None:
        """Initialize VWAP indicator (no parameters)."""
        super().__init__()

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {},
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate VWAP."""
        vwap = np.zeros(len(prices))
        cum_volume = 0.0
        cum_pv = 0.0

        for i in range(len(prices)):
            cum_volume += volumes[i]
            cum_pv += prices[i] * volumes[i]

            if cum_volume > 0:
                vwap[i] = cum_pv / cum_volume

        return IndicatorResult(name=self.name, values={"vwap": vwap}, metadata={})


class MFIIndicator(Indicator):
    """
    Money Flow Index.

    Volume-weighted RSI.
    Standard period: 14

    Signals:
    - MFI > 80: Overbought
    - MFI < 20: Oversold
    """

    category = "volume"
    description = "Money Flow Index - Volume-weighted RSI"

    def __init__(self, period: int = 14) -> None:
        """Initialize MFI indicator."""
        super().__init__(period=period)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "maximum": 5000, "default": 14}
            },
            "required": ["period"],
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate MFI."""
        period = self.params["period"]

        if highs is None:
            highs = prices
        if lows is None:
            lows = prices

        mfi = self._calculate_mfi(highs, lows, prices, volumes, period)

        return IndicatorResult(name=self.name, values={"mfi": mfi}, metadata={"period": period})

    def _calculate_mfi(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
        period: int,
    ) -> np.ndarray:
        """Calculate MFI using vectorized operations."""
        n = len(closes)
        mfi = np.full(n, np.nan)

        if n < period + 1:
            return mfi

        # Typical price (vectorized)
        typical_price = (highs + lows + closes) / 3

        # Money flow (vectorized)
        money_flow = typical_price * volumes

        # Positive and negative money flow (vectorized)
        tp_diff = np.diff(typical_price)
        positive_flow = np.zeros(n)
        negative_flow = np.zeros(n)
        positive_flow[1:] = np.where(tp_diff > 0, money_flow[1:], 0)
        negative_flow[1:] = np.where(tp_diff < 0, money_flow[1:], 0)

        # Money ratio and MFI using cumsum for rolling sums
        pos_cumsum = np.cumsum(positive_flow)
        neg_cumsum = np.cumsum(negative_flow)

        for i in range(period, n):
            positive_sum = pos_cumsum[i] - (pos_cumsum[i - period] if i >= period else 0)
            negative_sum = neg_cumsum[i] - (neg_cumsum[i - period] if i >= period else 0)

            if negative_sum > 0:
                money_ratio = positive_sum / negative_sum
                mfi[i] = 100 - (100 / (1 + money_ratio))
            else:
                mfi[i] = 100

        return mfi
