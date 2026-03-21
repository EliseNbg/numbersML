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

import numpy as np
from typing import Dict, Any, Optional
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
    
    category = 'volatility'
    description = 'Bollinger Bands - Volatility bands'
    
    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        """Initialize Bollinger Bands indicator."""
        super().__init__(period=period, std_dev=std_dev)
    
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
                    "maximum": 200,
                    "default": 20
                },
                "std_dev": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 5.0,
                    "default": 2.0
                }
            },
            "required": ["period", "std_dev"]
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate Bollinger Bands."""
        period = self.params['period']
        std_dev = self.params['std_dev']
        
        if len(prices) < period:
            return IndicatorResult(
                name=self.name,
                values={
                    'upper': np.full(len(prices), np.nan),
                    'middle': np.full(len(prices), np.nan),
                    'lower': np.full(len(prices), np.nan)
                },
                metadata={'period': period, 'std_dev': std_dev}
            )
        
        # Middle band (SMA)
        middle = np.full(len(prices), np.nan)
        for i in range(period - 1, len(prices)):
            middle[i] = np.mean(prices[i-period+1:i+1])
        
        # Standard deviation
        std = np.full(len(prices), np.nan)
        for i in range(period - 1, len(prices)):
            std[i] = np.std(prices[i-period+1:i+1])
        
        # Upper and lower bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return IndicatorResult(
            name=self.name,
            values={
                'upper': upper,
                'middle': middle,
                'lower': lower,
                'std': std
            },
            metadata={'period': period, 'std_dev': std_dev}
        )


class ATRIndicator(Indicator):
    """
    Average True Range.
    
    Measures volatility (not direction).
    Standard period: 14
    
    Higher ATR = Higher volatility
    Lower ATR = Lower volatility
    """
    
    category = 'volatility'
    description = 'Average True Range - Volatility indicator'
    
    def __init__(self, period: int = 14) -> None:
        """Initialize ATR indicator."""
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
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate ATR."""
        period = self.params['period']
        
        if highs is None:
            highs = prices
        if lows is None:
            lows = prices
        
        atr = self._calculate_atr(highs, lows, prices, period)
        
        return IndicatorResult(
            name=self.name,
            values={'atr': atr},
            metadata={'period': period}
        )
    
    def _calculate_atr(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int,
    ) -> np.ndarray:
        """Calculate ATR."""
        n = len(closes)
        atr = np.full(n, np.nan)
        tr = np.zeros(n)
        
        # Calculate True Range
        for i in range(1, n):
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
        
        # First ATR is simple average
        if n > period:
            atr[period] = np.mean(tr[1:period+1])
            
            # Smoothed ATR
            for i in range(period + 1, n):
                atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        
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
    
    category = 'volume'
    description = 'On Balance Volume - Volume momentum indicator'
    
    def __init__(self) -> None:
        """Initialize OBV indicator (no parameters)."""
        super().__init__()
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {}
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate OBV."""
        obv = np.zeros(len(prices))
        
        for i in range(1, len(prices)):
            if prices[i] > prices[i-1]:
                obv[i] = obv[i-1] + volumes[i]
            elif prices[i] < prices[i-1]:
                obv[i] = obv[i-1] - volumes[i]
            else:
                obv[i] = obv[i-1]
        
        return IndicatorResult(
            name=self.name,
            values={'obv': obv},
            metadata={}
        )


class VWAPIndicator(Indicator):
    """
    Volume Weighted Average Price.
    
    Average price weighted by volume.
    Institutional benchmark.
    
    Signals:
    - Price above VWAP: Bullish
    - Price below VWAP: Bearish
    """
    
    category = 'volume'
    description = 'VWAP - Volume weighted average price'
    
    def __init__(self) -> None:
        """Initialize VWAP indicator (no parameters)."""
        super().__init__()
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {}
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
        
        return IndicatorResult(
            name=self.name,
            values={'vwap': vwap},
            metadata={}
        )


class MFIIndicator(Indicator):
    """
    Money Flow Index.
    
    Volume-weighted RSI.
    Standard period: 14
    
    Signals:
    - MFI > 80: Overbought
    - MFI < 20: Oversold
    """
    
    category = 'volume'
    description = 'Money Flow Index - Volume-weighted RSI'
    
    def __init__(self, period: int = 14) -> None:
        """Initialize MFI indicator."""
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
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate MFI."""
        period = self.params['period']
        
        if highs is None:
            highs = prices
        if lows is None:
            lows = prices
        
        mfi = self._calculate_mfi(highs, lows, prices, volumes, period)
        
        return IndicatorResult(
            name=self.name,
            values={'mfi': mfi},
            metadata={'period': period}
        )
    
    def _calculate_mfi(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
        period: int,
    ) -> np.ndarray:
        """Calculate MFI."""
        n = len(closes)
        mfi = np.full(n, np.nan)
        
        if n < period + 1:
            return mfi
        
        # Typical price
        typical_price = (highs + lows + closes) / 3
        
        # Money flow
        money_flow = typical_price * volumes
        
        # Positive and negative money flow
        positive_flow = np.zeros(n)
        negative_flow = np.zeros(n)
        
        for i in range(1, n):
            if typical_price[i] > typical_price[i-1]:
                positive_flow[i] = money_flow[i]
            elif typical_price[i] < typical_price[i-1]:
                negative_flow[i] = money_flow[i]
        
        # Money ratio and MFI
        for i in range(period, n):
            positive_sum = np.sum(positive_flow[i-period+1:i+1])
            negative_sum = np.sum(negative_flow[i-period+1:i+1])
            
            if negative_sum > 0:
                money_ratio = positive_sum / negative_sum
                mfi[i] = 100 - (100 / (1 + money_ratio))
            else:
                mfi[i] = 100
        
        return mfi
