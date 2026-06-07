"""
Trend indicators for long-term analysis.

Includes:
- SMA (Simple Moving Average) — 20, 50, 100, 200 periods
- EMA (Exponential Moving Average) — 12, 26, 50, 200 periods
- MACDSMA (SMA-based MACD) — vectorised, no convergence buffer
- ADX (Average Directional Index)
- Aroon Indicator
"""

import logging
from typing import Any, Optional

import numpy as np

from .base import Indicator, IndicatorResult

logger = logging.getLogger(__name__)


def _calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
    """Vectorised SMA via cumulative sum."""
    valid = prices[~np.isnan(prices)]
    if len(valid) < period:
        return np.full(len(prices), np.nan)

    cumsum = np.cumsum(valid)
    sma = np.full(len(prices), np.nan)
    start_idx = len(prices) - len(valid)
    sma[start_idx + period - 1 :] = (
        cumsum[period - 1 :] - np.concatenate([[0], cumsum[:-period]])
    ) / period
    return sma


class SMAIndicator(Indicator):
    """
    Simple Moving Average.

    Long-term trend indicator. Common periods:
    - 20: Short-term trend
    - 50: Medium-term trend
    - 100: Long-term trend
    - 200: Very long-term trend (institutional)
    """

    category = "trend"
    description = "Simple Moving Average - Long-term trend indicator"

    def __init__(self, period: int = 50) -> None:
        """Initialize SMA indicator."""
        super().__init__(period=period)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "maximum": 8000, "default": 50}
            },
            "required": ["period"],
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate SMA values."""
        period = self.params["period"]
        sma = _calculate_sma(prices, period)
        return IndicatorResult(name=self.name, values={"sma": sma}, metadata={"period": period})


class EMAIndicator(Indicator):
    """
    Exponential Moving Average.

    Gives more weight to recent prices, more responsive than SMA.
    """

    category = "trend"
    description = "Exponential Moving Average - Responsive trend indicator"

    def __init__(self, period: int = 20) -> None:
        """Initialize EMA indicator."""
        super().__init__(period=period)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "maximum": 5000, "default": 20}
            },
            "required": ["period"],
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate EMA values."""
        period = self.params["period"]
        ema = self._calculate_ema(prices, period)

        return IndicatorResult(name=self.name, values={"ema": ema}, metadata={"period": period})

    def _calculate_ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA using lfilter (compiled C, ~50x faster than Python loop)."""
        n = len(prices)
        if n < period:
            return np.full(n, np.nan)

        from scipy.signal import lfilter

        ema = np.full(n, np.nan)
        multiplier = 2 / (period + 1)

        # First EMA is SMA
        ema[period - 1] = np.mean(prices[:period])

        # Apply IIR filter for remaining elements
        # EMA: ema[i] = price[i] * multiplier + ema[i-1] * (1 - multiplier)
        b = np.array([multiplier])
        a = np.array([1.0, -(1 - multiplier)])
        ema[period:] = lfilter(b, a, prices[period:], zi=[ema[period - 1]])[0]

        return ema


class MACDSMAIndicator(Indicator):
    """
    MACD using Simple Moving Averages instead of EMAs.

    More computationally efficient than EMA-based MACD for large periods
    (fast vectorised cumsum vs Python for-loop), and requires no
    convergence buffer — SMA is deterministic from any data length >=
    slow_period.
    """

    category = "trend"
    description = "MACD-SMA - Efficient MACD using Simple Moving Averages"

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        """Initialize MACD-SMA indicator."""
        super().__init__(
            fast_period=fast_period, slow_period=slow_period, signal_period=signal_period
        )

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema with large max for 1s data."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "fast_period": {"type": "integer", "minimum": 2, "maximum": 100000, "default": 12},
                "slow_period": {"type": "integer", "minimum": 2, "maximum": 100000, "default": 26},
                "signal_period": {"type": "integer", "minimum": 2, "maximum": 100000, "default": 9},
            },
            "required": ["fast_period", "slow_period", "signal_period"],
        }

    def _calculate_sma(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Vectorised SMA via cumulative sum (delegates to module-level helper)."""
        return _calculate_sma(prices, period)

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate MACD-SMA values."""
        fast_period = self.params["fast_period"]
        slow_period = self.params["slow_period"]
        signal_period = self.params["signal_period"]

        # SMAs
        fast_sma = self._calculate_sma(prices, fast_period)
        slow_sma = self._calculate_sma(prices, slow_period)

        # MACD Line
        macd_line = fast_sma - slow_sma

        # Signal Line (SMA of MACD)
        signal_line = self._calculate_sma(macd_line, signal_period)

        # Histogram
        histogram = macd_line - signal_line

        return IndicatorResult(
            name=self.name,
            values={"macd": macd_line, "signal": signal_line, "histogram": histogram},
            metadata={
                "fast_period": fast_period,
                "slow_period": slow_period,
                "signal_period": signal_period,
            },
        )


class ADXIndicator(Indicator):
    """
    Average Directional Index.

    Measures trend strength (not direction).
    """

    category = "trend"
    description = "ADX - Trend strength indicator"

    def __init__(self, period: int = 14) -> None:
        """Initialize ADX indicator."""
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
        """Calculate ADX values."""
        period = self.params["period"]

        if highs is None:
            highs = prices
        if lows is None:
            lows = prices

        adx, plus_di, minus_di = self._calculate_adx(highs, lows, prices, period)

        return IndicatorResult(
            name=self.name,
            values={"adx": adx, "plus_di": plus_di, "minus_di": minus_di},
            metadata={"period": period},
        )

    def _calculate_adx(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int,
    ) -> tuple:
        """Calculate ADX, +DI, -DI using vectorized operations."""
        n = len(closes)
        adx = np.full(n, np.nan)
        plus_di = np.full(n, np.nan)
        minus_di = np.full(n, np.nan)

        if n < period * 2:
            return adx, plus_di, minus_di

        # Vectorized TR, +DM, -DM calculation
        tr = np.zeros(n)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)

        # True Range (vectorized)
        tr[1:] = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
        )

        # Directional Movement (vectorized)
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]
        plus_dm[1:] = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm[1:] = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        # Smoothed sums (vectorized initial sum)
        tr_smooth = np.zeros(n)
        plus_dm_smooth = np.zeros(n)
        minus_dm_smooth = np.zeros(n)

        tr_smooth[period] = np.sum(tr[1 : period + 1])
        plus_dm_smooth[period] = np.sum(plus_dm[1 : period + 1])
        minus_dm_smooth[period] = np.sum(minus_dm[1 : period + 1])

        # Smoothing loop (inherently sequential)
        for i in range(period + 1, n):
            tr_smooth[i] = tr_smooth[i - 1] - tr_smooth[i - 1] / period + tr[i]
            plus_dm_smooth[i] = plus_dm_smooth[i - 1] - plus_dm_smooth[i - 1] / period + plus_dm[i]
            minus_dm_smooth[i] = (
                minus_dm_smooth[i - 1] - minus_dm_smooth[i - 1] / period + minus_dm[i]
            )

        # Calculate +DI, -DI (vectorized)
        valid = tr_smooth[period:] > 0
        plus_di[period:] = np.where(valid, 100 * plus_dm_smooth[period:] / tr_smooth[period:], 0)
        minus_di[period:] = np.where(valid, 100 * minus_dm_smooth[period:] / tr_smooth[period:], 0)

        # Calculate DX (vectorized)
        di_sum = plus_di[period:] + minus_di[period:]
        dx = np.zeros(n)
        dx[period:] = np.where(di_sum > 0, 100 * np.abs(plus_di[period:] - minus_di[period:]) / di_sum, 0)

        # ADX: first value is SMA of DX
        adx[period * 2 - 1] = np.mean(dx[period : period * 2])

        # ADX smoothing loop (inherently sequential)
        for i in range(period * 2, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return adx, plus_di, minus_di


class AroonIndicator(Indicator):
    """
    Aroon Indicator.

    Identifies trend changes and measures trend strength.
    """

    category = "trend"
    description = "Aroon - Trend change indicator"

    def __init__(self, period: int = 25) -> None:
        """Initialize Aroon indicator."""
        super().__init__(period=period)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "maximum": 5000, "default": 25}
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
        """Calculate Aroon values."""
        period = self.params["period"]

        if highs is None:
            highs = prices
        if lows is None:
            lows = prices

        aroon_up, aroon_down = self._calculate_aroon(highs, lows, period)

        return IndicatorResult(
            name=self.name,
            values={"aroon_up": aroon_up, "aroon_down": aroon_down},
            metadata={"period": period},
        )

    def _calculate_aroon(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        period: int,
    ) -> tuple:
        """Calculate Aroon Up and Down using vectorized sliding window operations."""
        n = len(highs)
        aroon_up = np.full(n, np.nan)
        aroon_down = np.full(n, np.nan)

        if n < period:
            return aroon_up, aroon_down

        # Vectorized sliding window argmax/argmin
        high_windows = np.lib.stride_tricks.sliding_window_view(highs, period)
        low_windows = np.lib.stride_tricks.sliding_window_view(lows, period)

        # argmax/argmin give position within window (0 = oldest, period-1 = newest)
        high_argmax = np.argmax(high_windows, axis=1)
        low_argmin = np.argmin(low_windows, axis=1)

        # Aroon: 100 * (period - 1 - position) / (period - 1)
        # position 0 (oldest) -> aroon = 100, position period-1 (newest) -> aroon = 0
        aroon_up[period - 1 :] = 100 * (period - 1 - high_argmax) / (period - 1)
        aroon_down[period - 1 :] = 100 * (period - 1 - low_argmin) / (period - 1)

        return aroon_up, aroon_down
