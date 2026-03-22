# Step 006: Indicator Framework - Implementation Guide

**Phase**: 4 - Enrichment  
**Effort**: 6 hours  
**Dependencies**: Step 003 (Domain Models) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements the dynamic indicator framework with:
- Base indicator class (ABC)
- Indicator registry with auto-discovery
- Dynamic indicator definitions
- Parameter validation with JSON Schema
- Code versioning for recalculation triggers
- Comprehensive tests (90%+ coverage)

---

## Implementation Tasks

### Task 1: Indicator Base Class

**File**: `src/indicators/base.py`

```python
"""
Base indicator class.

All indicators must inherit from this base class.
Provides common functionality for parameter validation,
code hashing, and result formatting.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import numpy as np
import hashlib
import inspect


@dataclass
class IndicatorResult:
    """
    Result of indicator calculation.
    
    Attributes:
        name: Indicator name (e.g., 'rsi_14')
        values: Dictionary of calculated values
        metadata: Additional metadata about calculation
    """
    
    name: str
    values: Dict[str, np.ndarray]
    metadata: Dict[str, Any] = field(default_factory=dict)


class Indicator(ABC):
    """
    Base class for all indicators.
    
    Each indicator is a Python class that:
    - Defines its parameters with validation
    - Implements calculation logic
    - Can be serialized/deserialized for versioning
    
    Attributes:
        params: Indicator parameters
        category: Indicator category (trend, momentum, etc.)
        description: Indicator description
        version: Indicator version string
    
    Example:
        >>> class RSIIndicator(Indicator):
        ...     category = 'momentum'
        ...     description = 'Relative Strength Index'
        ...
        >>> indicator = RSIIndicator(period=14)
        >>> result = indicator.calculate(prices, volumes)
    """
    
    # Class-level metadata (override in subclasses)
    category: str = 'custom'
    description: str = ''
    version: str = '1.0.0'
    
    def __init__(self, **params: Any) -> None:
        """
        Initialize indicator with parameters.
        
        Args:
            **params: Indicator parameters (e.g., period=14)
        """
        self.params: Dict[str, Any] = params
        self._validate_params()
    
    @abstractmethod
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        opens: Optional[np.ndarray] = None,
        closes: Optional[np.ndarray] = None,
    ) -> IndicatorResult:
        """
        Calculate indicator values.
        
        Args:
            prices: Array of prices (required)
            volumes: Array of volumes (required)
            highs: Array of highs (optional, for some indicators)
            lows: Array of lows (optional)
            opens: Array of opens (optional)
            closes: Array of closes (optional)
        
        Returns:
            IndicatorResult with calculated values
        
        Example:
            >>> result = indicator.calculate(prices, volumes)
            >>> print(result.values['rsi'])  # numpy array
        """
        pass
    
    def _validate_params(self) -> None:
        """
        Validate parameters against schema.
        
        Raises:
            ValueError: If parameters are invalid
        """
        schema = self.params_schema()
        
        # Check required parameters
        if 'required' in schema:
            for param in schema['required']:
                if param not in self.params:
                    raise ValueError(f"Missing required parameter: {param}")
        
        # Check parameter types and ranges
        if 'properties' in schema:
            for param, spec in schema['properties'].items():
                if param in self.params:
                    value = self.params[param]
                    
                    # Type checking
                    if 'type' in spec:
                        expected_type = spec['type']
                        if expected_type == 'integer' and not isinstance(value, int):
                            raise ValueError(
                                f"Parameter {param} must be integer, got {type(value)}"
                            )
                        elif expected_type == 'number' and not isinstance(value, (int, float)):
                            raise ValueError(
                                f"Parameter {param} must be number, got {type(value)}"
                            )
                    
                    # Range checking
                    if 'minimum' in spec and value < spec['minimum']:
                        raise ValueError(
                            f"Parameter {param} must be >= {spec['minimum']}, got {value}"
                        )
                    if 'maximum' in spec and value > spec['maximum']:
                        raise ValueError(
                            f"Parameter {param} must be <= {spec['maximum']}, got {value}"
                        )
    
    @classmethod
    @abstractmethod
    def params_schema(cls) -> Dict[str, Any]:
        """
        Return JSON Schema for parameter validation.
        
        Returns:
            JSON Schema dictionary
        
        Example:
            {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "period": {
                        "type": "integer",
                        "minimum": 2,
                        "default": 14
                    }
                },
                "required": ["period"]
            }
        """
        pass
    
    def get_code_hash(self) -> str:
        """
        Calculate hash of indicator code.
        
        Used for versioning and detecting code changes.
        
        Returns:
            SHA256 hash of indicator source code
        """
        source = inspect.getsource(self.__class__)
        return hashlib.sha256(source.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize indicator definition to dictionary.
        
        Returns:
            Dictionary with indicator metadata and parameters
        
        Example:
            {
                'name': 'rsi_14',
                'class_name': 'RSIIndicator',
                'module_path': 'indicators.momentum',
                'category': 'momentum',
                'params': {'period': 14},
                'code_hash': 'abc123...',
                'description': 'Relative Strength Index'
            }
        """
        return {
            'name': self.name,
            'class_name': self.__class__.__name__,
            'module_path': self.__module__,
            'category': self.category,
            'params': self.params,
            'params_schema': self.params_schema(),
            'code_hash': self.get_code_hash(),
            'description': self.description,
        }
    
    @property
    def name(self) -> str:
        """
        Generate unique name from class and parameters.
        
        Returns:
            Indicator name (e.g., 'rsi_14', 'macd_12_26_9')
        
        Example:
            >>> RSIIndicator(period=14).name
            'rsiindicator_14'
        """
        params_str = '_'.join(
            f"{k}{v}" for k, v in sorted(self.params.items())
        )
        return f"{self.__class__.__name__.lower()}_{params_str}"

```

### Task 2: Indicator Registry

**File**: `src/indicators/registry.py`

```python
"""
Indicator registry with auto-discovery.

Automatically discovers and registers all indicator classes
from the indicators package.
"""

import importlib
import pkgutil
from typing import Dict, Type, List, Optional
from .base import Indicator


class IndicatorRegistry:
    """
    Registry for all available indicators.
    
    Auto-discovers indicators from modules and provides
    factory methods for creating indicator instances.
    
    Example:
        >>> IndicatorRegistry.discover()
        >>> rsi = IndicatorRegistry.get('rsi_14', period=14)
        >>> all_indicators = IndicatorRegistry.list_indicators()
    """
    
    _indicators: Dict[str, Type[Indicator]] = {}
    
    @classmethod
    def discover(cls) -> None:
        """
        Auto-discover all indicator classes.
        
        Scans all modules in the indicators package and
        registers any classes that inherit from Indicator.
        """
        import indicators
        
        for importer, modname, ispkg in pkgutil.iter_modules(indicators.__path__):
            try:
                module = importlib.import_module(f"indicators.{modname}")
                
                for name in dir(module):
                    obj = getattr(module, name)
                    
                    # Check if it's an indicator class
                    if (isinstance(obj, type) and
                        issubclass(obj, Indicator) and
                        obj is not Indicator):
                        cls.register(obj)
                
            except ImportError as e:
                # Skip modules with missing dependencies (e.g., TA-Lib)
                print(f"Warning: Could not import indicators.{modname}: {e}")
    
    @classmethod
    def register(cls, indicator_class: Type[Indicator]) -> None:
        """
        Register an indicator class.
        
        Args:
            indicator_class: Indicator class to register
        
        Example:
            >>> IndicatorRegistry.register(RSIIndicator)
        """
        # Create instance to get name
        try:
            instance = indicator_class()
            cls._indicators[instance.name] = indicator_class
        except Exception as e:
            print(f"Warning: Could not register {indicator_class.__name__}: {e}")
    
    @classmethod
    def get(
        cls,
        name: str,
        **params: Any,
    ) -> Optional[Indicator]:
        """
        Get indicator instance by name.
        
        Args:
            name: Indicator name (e.g., 'rsi_14')
            **params: Parameters to override defaults
        
        Returns:
            Indicator instance or None if not found
        
        Example:
            >>> rsi = IndicatorRegistry.get('rsi_14', period=14)
            >>> macd = IndicatorRegistry.get('macd', fast=12, slow=26, signal=9)
        """
        if name not in cls._indicators:
            return None
        
        indicator_class = cls._indicators[name]
        
        try:
            return indicator_class(**params)
        except Exception as e:
            print(f"Error creating indicator {name}: {e}")
            return None
    
    @classmethod
    def list_indicators(
        cls,
        category: Optional[str] = None,
    ) -> List[str]:
        """
        List all registered indicators.
        
        Args:
            category: Filter by category (optional)
        
        Returns:
            List of indicator names
        
        Example:
            >>> IndicatorRegistry.list_indicators()
            ['rsi_14', 'macd_12_26_9', 'sma_20', ...]
            
            >>> IndicatorRegistry.list_indicators('momentum')
            ['rsi_14', 'stoch_14_3', ...]
        """
        if category:
            return [
                name for name, indicator_class in cls._indicators.items()
                if indicator_class.category == category
            ]
        return list(cls._indicators.keys())
    
    @classmethod
    def get_indicator_class(cls, name: str) -> Optional[Type[Indicator]]:
        """
        Get indicator class by name.
        
        Args:
            name: Indicator name
        
        Returns:
            Indicator class or None if not found
        """
        return cls._indicators.get(name)
    
    @classmethod
    def get_all_categories(cls) -> List[str]:
        """
        Get all indicator categories.
        
        Returns:
            List of unique categories
        """
        categories = set()
        for indicator_class in cls._indicators.values():
            categories.add(indicator_class.category)
        return sorted(list(categories))

```

### Task 3: Example Indicator Implementations

**File**: `src/indicators/momentum.py`

```python
"""
Momentum indicators.

Includes:
- RSI (Relative Strength Index)
- Stochastic Oscillator
- Williams %R
"""

import numpy as np
from typing import Dict, Any
from .base import Indicator, IndicatorResult

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False


class RSIIndicator(Indicator):
    """
    Relative Strength Index indicator.
    
    Measures the speed and magnitude of price changes.
    Values range from 0 to 100.
    
    - Overbought: > 70
    - Oversold: < 30
    
    Attributes:
        period: Lookback period (default: 14)
    """
    
    category = 'momentum'
    description = 'Relative Strength Index - Measures price momentum'
    
    def __init__(self, period: int = 14) -> None:
        """
        Initialize RSI indicator.
        
        Args:
            period: Lookback period (default: 14)
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
        **kwargs: Any,
    ) -> IndicatorResult:
        """
        Calculate RSI values.
        
        Args:
            prices: Array of prices
            volumes: Array of volumes (not used for RSI)
        
        Returns:
            IndicatorResult with RSI values
        """
        period = self.params['period']
        
        if TALIB_AVAILABLE:
            rsi = talib.RSI(prices, timeperiod=period)
        else:
            # Fallback implementation
            rsi = self._calculate_rsi(prices, period)
        
        return IndicatorResult(
            name=self.name,
            values={'rsi': rsi},
            metadata={'period': period}
        )
    
    def _calculate_rsi(self, prices: np.ndarray, period: int) -> np.ndarray:
        """
        Calculate RSI without TA-Lib.
        
        Args:
            prices: Array of prices
            period: Lookback period
        
        Returns:
            RSI values
        """
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
            avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i-1]) / period
            avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i-1]) / period
        
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
    
    category = 'momentum'
    description = 'Stochastic Oscillator - Compares close to price range'
    
    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
    ) -> None:
        """
        Initialize Stochastic indicator.
        
        Args:
            k_period: %K period (default: 14)
            d_period: %D period (default: 3)
        """
        super().__init__(k_period=k_period, d_period=d_period)
    
    @classmethod
    def params_schema(cls) -> Dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "k_period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 100,
                    "default": 14
                },
                "d_period": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 50,
                    "default": 3
                }
            },
            "required": ["k_period", "d_period"]
        }
    
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: np.ndarray = None,
        lows: np.ndarray = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Calculate Stochastic values."""
        k_period = self.params['k_period']
        d_period = self.params['d_period']
        
        # Use prices as highs/lows if not provided
        if highs is None:
            highs = prices
        if lows is None:
            lows = prices
        
        if TALIB_AVAILABLE:
            slowk, slowd = talib.STOCH(
                highs, lows, prices,
                fastk_period=k_period,
                slowk_period=d_period,
                slowk_mattype=0,
                slowd_period=d_period,
                slowd_mattype=0
            )
        else:
            slowk, slowd = self._calculate_stochastic(highs, lows, prices, k_period, d_period)
        
        return IndicatorResult(
            name=self.name,
            values={
                'stoch_k': slowk,
                'stoch_d': slowd
            },
            metadata={
                'k_period': k_period,
                'd_period': d_period
            }
        )
    
    def _calculate_stochastic(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        k_period: int,
        d_period: int,
    ) -> tuple:
        """Calculate Stochastic without TA-Lib."""
        n = len(closes)
        slowk = np.full(n, np.nan)
        
        for i in range(k_period - 1, n):
            highest_high = np.max(highs[i-k_period+1:i+1])
            lowest_low = np.min(lows[i-k_period+1:i+1])
            
            if highest_high != lowest_low:
                slowk[i] = 100 * (closes[i] - lowest_low) / (highest_high - lowest_low)
            else:
                slowk[i] = 50
        
        # Calculate %D (SMA of %K)
        slowd = np.full(n, np.nan)
        for i in range(d_period - 1, n):
            if not np.isnan(slowk[i-d_period+1:i+1]).all():
                slowd[i] = np.nanmean(slowk[i-d_period+1:i+1])
        
        return slowk, slowd

```

---

## Acceptance Criteria

- [ ] Indicator base class implemented
- [ ] Indicator registry with auto-discovery
- [ ] At least 3 indicator implementations
- [ ] Parameter validation working
- [ ] Code hashing for versioning
- [ ] Unit tests (90%+ coverage)

---

## Next Steps

After completing this step, proceed to **Step 007: Indicator Implementations**
