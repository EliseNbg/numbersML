# Step 007: Long-Term Indicator Implementations

**Phase**: 4 - Enrichment  
**Effort**: 8 hours  
**Dependencies**: Step 006 (Indicator Framework) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements **long-term trend indicators** for strategic trading:
- **Trend Indicators**: SMA, EMA, MACD, ADX, Aroon
- **Volatility Indicators**: Bollinger Bands, ATR, Keltner Channel
- **Volume Indicators**: OBV, VWAP, MFI
- **Long-term Specific**: SMA 50/200 (Golden/Death Cross)

---

## Implementation Tasks

### Task 1: Trend Indicators

**File**: `src/indicators/trend.py`

```python
"""
Trend indicators for long-term analysis.

Includes:
- SMA (Simple Moving Average) - 20, 50, 100, 200 periods
- EMA (Exponential Moving Average) - 12, 26, 50, 200 periods
- MACD (Moving Average Convergence Divergence)
- ADX (Average Directional Index)
- Aroon Indicator
"""

import numpy as np
from typing import Dict, Any
from .base import Indicator, IndicatorResult


class SMAIndicator(Indicator):
    """
    Simple Moving Average.
    
    Long-term trend indicator. Common periods:
    - 20: Short-term trend
    - 50: Medium-term trend
    - 100: Long-term trend
    - 200: Very long-term trend (institutional)
    
    Signals:
    - Price above SMA: Bullish
    - Price below SMA: Bearish
    - SMA 50 crosses above SMA 200: Golden Cross (bullish)
    - SMA 50 crosses below SMA 200: Death Cross (bearish)
    """
    
    category = 'trend'
    description = 'Simple Moving Average - Long-term trend indicator'
    
    def __init__(self, period: int = 50) -> None:
        """
        Initialize SMA indicator.
        
        Args:
            period: SMA period (default: 50 for medium-term)
        """
        super().__init__(period=period)
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 500,
                    "default": 50
                }
            },
            "required": ["period"]
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate SMA values."""
        period = self.params['period']
        
        if len(prices) < period:
            return IndicatorResult(
                name=self.name,
                values={'sma': np.full(len(prices), np.nan)},
                metadata={'period': period}
            )
        
        # Calculate SMA
        sma = np.full(len(prices), np.nan)
        for i in range(period - 1, len(prices)):
            sma[i] = np.mean(prices[i-period+1:i+1])
        
        return IndicatorResult(
            name=self.name,
            values={'sma': sma},
            metadata={'period': period}
        )


class EMAIndicator(Indicator):
    """
    Exponential Moving Average.
    
    Gives more weight to recent prices, more responsive than SMA.
    Common periods: 12, 26, 50, 200
    
    Signals:
    - Price above EMA: Bullish
    - Price below EMA: Bearish
    - EMA 12 crosses above EMA 26: Bullish (MACD signal)
    """
    
    category = 'trend'
    description = 'Exponential Moving Average - Responsive trend indicator'
    
    def __init__(self, period: int = 20) -> None:
        """Initialize EMA indicator."""
        super().__init__(period=period)
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 500,
                    "default": 20
                }
            },
            "required": ["period"]
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate EMA values."""
        period = self.params['period']
        ema = self._calculate_ema(prices, period)
        
        return IndicatorResult(
            name=self.name,
            values={'ema': ema},
            metadata={'period': period}
        )
    
    def _calculate_ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA."""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        
        ema = np.full(len(prices), np.nan)
        multiplier = 2 / (period + 1)
        
        # First EMA is SMA
        ema[period-1] = np.mean(prices[:period])
        
        # Calculate rest
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema


class MACDIndicator(Indicator):
    """
    Moving Average Convergence Divergence.
    
    Long-term momentum and trend indicator.
    Default parameters: 12, 26, 9
    
    Components:
    - MACD Line: EMA(12) - EMA(26)
    - Signal Line: EMA(9) of MACD Line
    - Histogram: MACD Line - Signal Line
    
    Signals:
    - MACD crosses above Signal: Bullish
    - MACD crosses below Signal: Bearish
    - MACD > 0: Bullish momentum
    - MACD < 0: Bearish momentum
    """
    
    category = 'trend'
    description = 'MACD - Long-term momentum and trend indicator'
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        """Initialize MACD indicator."""
        super().__init__(
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period
        )
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "fast_period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 100,
                    "default": 12
                },
                "slow_period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 200,
                    "default": 26
                },
                "signal_period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 100,
                    "default": 9
                }
            },
            "required": ["fast_period", "slow_period", "signal_period"]
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate MACD values."""
        fast_period = self.params['fast_period']
        slow_period = self.params['slow_period']
        signal_period = self.params['signal_period']
        
        # Calculate EMAs
        fast_ema = self._calculate_ema(prices, fast_period)
        slow_ema = self._calculate_ema(prices, slow_period)
        
        # MACD Line
        macd_line = fast_ema - slow_ema
        
        # Signal Line (EMA of MACD)
        signal_line = self._calculate_ema(macd_line[~np.isnan(macd_line)], signal_period)
        
        # Pad signal line to match length
        if len(signal_line) < len(macd_line):
            signal_line = np.pad(
                signal_line,
                (len(macd_line) - len(signal_line), 0),
                mode='constant',
                constant_values=np.nan
            )
        
        # Histogram
        histogram = macd_line - signal_line
        
        return IndicatorResult(
            name=self.name,
            values={
                'macd': macd_line,
                'signal': signal_line,
                'histogram': histogram
            },
            metadata={
                'fast_period': fast_period,
                'slow_period': slow_period,
                'signal_period': signal_period
            }
        )
    
    def _calculate_ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA."""
        valid_prices = prices[~np.isnan(prices)]
        
        if len(valid_prices) < period:
            return np.full(len(prices), np.nan)
        
        ema = np.full(len(prices), np.nan)
        multiplier = 2 / (period + 1)
        
        # First EMA is SMA
        start_idx = len(prices) - len(valid_prices)
        ema[start_idx + period - 1] = np.mean(valid_prices[:period])
        
        # Calculate rest
        for i in range(start_idx + period, len(prices)):
            if not np.isnan(prices[i]):
                ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema


class ADXIndicator(Indicator):
    """
    Average Directional Index.
    
    Measures trend strength (not direction).
    Period: 14 (standard)
    
    Interpretation:
    - ADX < 20: Weak trend / Ranging
    - ADX 20-40: Moderate trend
    - ADX > 40: Strong trend
    - ADX > 50: Very strong trend
    
    Also provides:
    - +DI: Positive Directional Indicator
    - -DI: Negative Directional Indicator
    """
    
    category = 'trend'
    description = 'ADX - Trend strength indicator'
    
    def __init__(self, period: int = 14) -> None:
        """Initialize ADX indicator."""
        super().__init__(period=period)
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 100,
                    "default": 14
                }
            },
            "required": ["period"]
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: np.ndarray = None,
        lows: np.ndarray = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate ADX values."""
        period = self.params['period']
        
        # Use prices as highs/lows if not provided
        if highs is None:
            highs = prices
        if lows is None:
            lows = prices
        
        adx, plus_di, minus_di = self._calculate_adx(highs, lows, prices, period)
        
        return IndicatorResult(
            name=self.name,
            values={
                'adx': adx,
                'plus_di': plus_di,
                'minus_di': minus_di
            },
            metadata={'period': period}
        )
    
    def _calculate_adx(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int,
    ) -> tuple:
        """Calculate ADX, +DI, -DI."""
        n = len(closes)
        adx = np.full(n, np.nan)
        plus_di = np.full(n, np.nan)
        minus_di = np.full(n, np.nan)
        
        if n < period * 2:
            return adx, plus_di, minus_di
        
        # Calculate TR, +DM, -DM
        tr = np.zeros(n)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        
        for i in range(1, n):
            # True Range
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            
            # +DM and -DM
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            else:
                plus_dm[i] = 0
            
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
            else:
                minus_dm[i] = 0
        
        # Smooth TR, +DM, -DM
        tr_smooth = np.zeros(n)
        plus_dm_smooth = np.zeros(n)
        minus_dm_smooth = np.zeros(n)
        
        # Initial values (first period sum)
        tr_smooth[period] = np.sum(tr[1:period+1])
        plus_dm_smooth[period] = np.sum(plus_dm[1:period+1])
        minus_dm_smooth[period] = np.sum(minus_dm[1:period+1])
        
        # Smoothed values
        for i in range(period + 1, n):
            tr_smooth[i] = tr_smooth[i-1] - tr_smooth[i-1]/period + tr[i]
            plus_dm_smooth[i] = plus_dm_smooth[i-1] - plus_dm_smooth[i-1]/period + plus_dm[i]
            minus_dm_smooth[i] = minus_dm_smooth[i-1] - minus_dm_smooth[i-1]/period + minus_dm[i]
        
        # Calculate +DI, -DI
        for i in range(period, n):
            if tr_smooth[i] > 0:
                plus_di[i] = 100 * plus_dm_smooth[i] / tr_smooth[i]
                minus_di[i] = 100 * minus_dm_smooth[i] / tr_smooth[i]
        
        # Calculate DX and ADX
        dx = np.zeros(n)
        for i in range(period, n):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum
        
        # ADX (smoothed DX)
        adx[period*2-1] = np.mean(dx[period:period*2])
        for i in range(period*2, n):
            adx[i] = (adx[i-1] * (period-1) + dx[i]) / period
        
        return adx, plus_di, minus_di


class AroonIndicator(Indicator):
    """
    Aroon Indicator.
    
    Identifies trend changes and measures trend strength.
    Period: 25 (standard for long-term)
    
    Components:
    - Aroon Up: Days since highest high
    - Aroon Down: Days since lowest low
    
    Signals:
    - Aroon Up > 70: Strong uptrend
    - Aroon Down > 70: Strong downtrend
    - Aroon Up crosses above Aroon Down: Bullish
    - Aroon Up crosses below Aroon Down: Bearish
    """
    
    category = 'trend'
    description = 'Aroon - Trend change indicator'
    
    def __init__(self, period: int = 25) -> None:
        """Initialize Aroon indicator."""
        super().__init__(period=period)
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 100,
                    "default": 25
                }
            },
            "required": ["period"]
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: np.ndarray = None,
        lows: np.ndarray = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate Aroon values."""
        period = self.params['period']
        
        if highs is None:
            highs = prices
        if lows is None:
            lows = prices
        
        aroon_up, aroon_down = self._calculate_aroon(highs, lows, period)
        
        return IndicatorResult(
            name=self.name,
            values={
                'aroon_up': aroon_up,
                'aroon_down': aroon_down
            },
            metadata={'period': period}
        )
    
    def _calculate_aroon(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        period: int,
    ) -> tuple:
        """Calculate Aroon Up and Down."""
        n = len(highs)
        aroon_up = np.full(n, np.nan)
        aroon_down = np.full(n, np.nan)
        
        for i in range(period - 1, n):
            # Highest high in lookback period
            highest = np.max(highs[i-period+1:i+1])
            highest_day = np.argmax(highs[i-period+1:i+1])
            
            # Lowest low in lookback period
            lowest = np.min(lows[i-period+1:i+1])
            lowest_day = np.argmin(lows[i-period+1:i+1])
            
            # Calculate Aroon
            aroon_up[i] = 100 * (period - 1 - highest_day) / (period - 1)
            aroon_down[i] = 100 * (period - 1 - lowest_day) / (period - 1)
        
        return aroon_up, aroon_down

```

---

## Acceptance Criteria

- [ ] SMA indicator (20, 50, 100, 200 periods)
- [ ] EMA indicator (12, 26, 50, 200 periods)
- [ ] MACD indicator
- [ ] ADX indicator
- [ ] Aroon indicator
- [ ] Unit tests (90%+ coverage)
- [ ] Integration with registry

---

## Next Steps

After completing this step, proceed to **Step 008: Enrichment Service**
