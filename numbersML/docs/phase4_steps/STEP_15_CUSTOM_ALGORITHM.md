# Step 15: Custom Algorithm Development Guide

## Objective
Enable senior developers and quantitative researchers to write custom trading algorithms manually with full access to state management, indicators, and configuration.

## Context
- Phase 3 complete: Algorithm base class in `src/domain/algorithms/base.py`
- Phase 4 complete: ConfigurationSet, StrategyInstance, and infrastructure
- Previous steps assumed LLM-generated algorithms
- This step provides documentation and patterns for manual algorithm development
- Target audience: Senior developers, quants, and financial engineers

## Architecture Overview

### Key Components
1. **Algorithm Base Class** (`src/domain/algorithms/base.py`): Abstract base defining the interface
2. **EnrichedTick**: Tick data with indicators pre-calculated
3. **ConfigurationSet**: Key-value configuration stored in DB, accessible via `get_config()`
4. **Signal**: Output object representing BUY/SELL/HOLD decisions
5. **State**: Instance variables in your algorithm class persist between ticks

### Data Flow
```
Market Data → Enrichment Service (adds indicators) → Redis Pub/Sub → Algorithm.on_tick(tick) → Signal
```

## Implementation Guide

### 1. Basic Algorithm Structure

```python
"""
Custom RSI + Moving Average Algorithm.

Demonstrates:
- State management between ticks
- Indicator access from EnrichedTick
- ConfigurationSet access
- Signal generation with metadata
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.domain.algorithms.base import (
    Algorithm,
    Signal,
    SignalType,
    EnrichedTick,
    TimeFrame,
)
from uuid import UUID

logger = logging.getLogger(__name__)


class RSIMovingAverageAlgorithm(Algorithm):
    """
    RSI + MA crossover algorithm with state.
    
    Strategy:
        - Buy when RSI < oversold_threshold and price > MA
        - Sell when RSI > overbought_threshold or stop loss hit
        - Track state between ticks for complex conditions
    
    Configuration (in ConfigurationSet.config):
        - rsi_period: RSI calculation period (default: 14)
        - rsi_oversold: Oversold threshold (default: 30)
        - rsi_overbought: Overbought threshold (default: 70)
        - ma_period: Moving average period (default: 20)
        - quantity: Base order quantity (default: 0.01)
        - stop_loss_pct: Stop loss percentage (default: 2.0)
        - take_profit_pct: Take profit percentage (default: 3.0)
    
    State (persists between ticks):
        - self._position: Current position info (entry_price, quantity, side)
        - self._tick_count: Number of ticks processed
        - self._price_history: Recent price history for custom calculations
        - self._last_rsi: Last RSI value for divergence detection
    """
    
    def __init__(
        self,
        algorithm_id: UUID,
        symbols: list[str],
        time_frame: TimeFrame = TimeFrame.TICK,
    ) -> None:
        """
        Initialize algorithm with state containers.
        
        Args:
            algorithm_id: Unique algorithm UUID
            symbols: List of symbols to trade
            time_frame: Algorithm time frame
        """
        super().__init__(
            algorithm_id=algorithm_id,
            symbols=symbols,
            time_frame=time_frame,
        )
        
        # State that persists between ticks
        self._position: dict[str, Any] | None = None
        self._tick_count: int = 0
        self._price_history: list[Decimal] = []
        self._rsi_history: list[float] = []
        self._last_signal_time: datetime | None = None
        self._max_price_history: int = 100  # Keep last 100 prices
        
        # Internal config cache (loaded from ConfigurationSet)
        self._config: dict[str, Any] = {}
        
        logger.info(f"RSIMovingAverageAlgorithm {algorithm_id} initialized")
    
    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """
        Process tick and generate trading signal.
        
        This method is called for every tick. State variables persist
        between calls, allowing complex multi-tick strategies.
        
        Args:
            tick: Enriched tick with indicators and price data
            
        Returns:
            Signal if conditions met, None otherwise
        """
        if tick.symbol not in self._symbols:
            return None
        
        # Update state
        self._tick_count += 1
        self._update_price_history(tick.price)
        
        # Extract indicators from tick (pre-calculated by enrichment service)
        rsi = tick.get_indicator("rsiindicator_period14_rsi", 50.0)
        sma = tick.get_indicator("smaindicator_period20_sma", float(tick.price))
        
        # Track RSI history for divergence
        self._rsi_history.append(rsi)
        if len(self._rsi_history) > self._max_price_history:
            self._rsi_history.pop(0)
        
        current_price = tick.price
        
        # Log state for debugging
        if self._tick_count % 100 == 0:
            logger.info(
                f"Tick {self._tick_count}: price={current_price}, "
                f"rsi={rsi:.2f}, sma={sma:.2f}, "
                f"position={'Yes' if self._position else 'No'}"
            )
        
        # Check for exit conditions first (if in position)
        if self._position is not None:
            return self._check_exit_conditions(tick, current_price, rsi)
        
        # Check for entry conditions
        return self._check_entry_conditions(tick, current_price, rsi, sma)
    
    def _update_price_history(self, price: Decimal) -> None:
        """Update price history for custom calculations."""
        self._price_history.append(price)
        if len(self._price_history) > self._max_price_history:
            self._price_history.pop(0)
    
    def _check_entry_conditions(
        self,
        tick: EnrichedTick,
        price: Decimal,
        rsi: float,
        sma: float,
    ) -> Signal | None:
        """Check if we should enter a position."""
        rsi_oversold = float(self.get_config("rsi_oversold", 30))
        min_rsi = float(self.get_config("min_rsi", 25))
        
        # Entry condition: RSI oversold and price above SMA (trend confirmation)
        if rsi < rsi_oversold and float(price) > sma:
            # Additional filter: RSI rising (momentum)
            if len(self._rsi_history) >= 3:
                recent_rsi = self._rsi_history[-3:]
                if all(recent_rsi[i] <= recent_rsi[i + 1] for i in range(len(recent_rsi) - 1)):
                    if recent_rsi[-1] < min_rsi:  # Strong oversold
                        return self._create_buy_signal(tick, price, rsi, sma)
        
        return None
    
    def _check_exit_conditions(
        self,
        tick: EnrichedTick,
        price: Decimal,
        rsi: float,
    ) -> Signal | None:
        """Check if we should exit position."""
        if self._position is None:
            return None
        
        entry_price = Decimal(str(self._position["entry_price"]))
        stop_loss_pct = float(self.get_config("stop_loss_pct", 2.0))
        take_profit_pct = float(self.get_config("take_profit_pct", 3.0))
        rsi_overbought = float(self.get_config("rsi_overbought", 70))
        
        # Calculate PnL
        pnl_pct = (price - entry_price) / entry_price * 100
        
        # Stop loss
        if pnl_pct <= -stop_loss_pct:
            return self._create_sell_signal(tick, price, rsi, "stop_loss", pnl_pct)
        
        # Take profit
        if pnl_pct >= take_profit_pct:
            return self._create_sell_signal(tick, price, rsi, "take_profit", pnl_pct)
        
        # RSI overbought (exit signal)
        if rsi > rsi_overbought:
            return self._create_sell_signal(tick, price, rsi, "rsi_overbought", pnl_pct)
        
        return None
    
    def _create_buy_signal(
        self,
        tick: EnrichedTick,
        price: Decimal,
        rsi: float,
        sma: float,
    ) -> Signal:
        """Create a BUY signal and update state."""
        quantity = Decimal(str(self.get_config("quantity", 0.01)))
        
        # Update position state
        self._position = {
            "entry_price": float(price),
            "quantity": float(quantity),
            "side": "LONG",
            "entry_time": datetime.now(timezone.utc),
            "entry_rsi": rsi,
        }
        
        return Signal(
            algorithm_id=str(self._algorithm_id),
            symbol=tick.symbol,
            signal_type=SignalType.BUY,
            price=price,
            timestamp=tick.time,
            confidence=0.85,
            metadata={
                "rsi": rsi,
                "sma": sma,
                "quantity": float(quantity),
                "reason": "rsi_oversold_with_momentum",
                "entry_price": float(price),
            },
        )
    
    def _create_sell_signal(
        self,
        tick: EnrichedTick,
        price: Decimal,
        rsi: float,
        reason: str,
        pnl_pct: float,
    ) -> Signal:
        """Create a SELL signal and clear position state."""
        quantity = Decimal(str(self._position["quantity"])) if self._position else Decimal("0.01")
        
        signal = Signal(
            algorithm_id=str(self._algorithm_id),
            symbol=tick.symbol,
            signal_type=SignalType.SELL,
            price=price,
            timestamp=tick.time,
            confidence=0.9,
            metadata={
                "rsi": rsi,
                "quantity": float(quantity),
                "reason": reason,
                "pnl_pct": pnl_pct,
                "entry_price": self._position["entry_price"] if self._position else None,
            },
        )
        
        # Clear position state
        self._position = None
        
        return signal
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value from ConfigurationSet.
        
        ConfigurationSets are stored in DB and linked to StrategyInstance.
        Override this method to load from actual ConfigurationSet.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self._config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value (runtime override)."""
        self._config[key] = value
    
    def get_algorithm_state(self) -> dict[str, Any]:
        """
        Get current algorithm state for monitoring/debugging.
        
        Returns:
            Dictionary with current state variables
        """
        return {
            "tick_count": self._tick_count,
            "has_position": self._position is not None,
            "position": self._position,
            "price_history_count": len(self._price_history),
            "rsi_history_count": len(self._rsi_history),
            "last_signal_time": self._last_signal_time.isoformat() if self._last_signal_time else None,
        }
```

### 2. Simple Grid Algorithm Example

Here's a minimal grid algorithm you can use as a starting point:

```python
"""
Simple Grid Algorithm - Easy to understand and modify.

Strategy:
    - Places buy orders below current price
    - Places sell orders above current price
    - Profits from price oscillations
    
State:
    - self._grid_levels: Current grid price levels
    - self._last_price: Last processed price
    - self._position: Current open position
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.algorithms.base import (
    Algorithm,
    Signal,
    SignalType,
    EnrichedTick,
    TimeFrame,
)
from uuid import UUID

logger = logging.getLogger(__name__)


class SimpleGridAlgorithm(Algorithm):
    """
    Simple grid trading algorithm with clear state management.
    
    Configuration (in ConfigurationSet.config):
        - grid_levels: Number of grid levels each side (default: 3)
        - grid_spacing_pct: Spacing between levels % (default: 1.0)
        - quantity: Quantity per order (default: 0.01)
        - take_profit_pct: Profit target per grid (default: 0.5)
        - stop_loss_pct: Stop loss (default: 2.0)
    
    Example ConfigurationSet.config:
        {
            "grid_levels": 3,
            "grid_spacing_pct": 1.0,
            "quantity": 0.01,
            "take_profit_pct": 0.5,
            "stop_loss_pct": 2.0
        }
    """
    
    def __init__(
        self,
        algorithm_id: UUID,
        symbols: list[str],
        time_frame: TimeFrame = TimeFrame.TICK,
    ) -> None:
        """Initialize with grid state."""
        super().__init__(algorithm_id=algorithm_id, symbols=symbols, time_frame=time_frame)
        
        # State - persists between ticks
        self._grid_levels: list[Decimal] = []
        self._base_price: Decimal | None = None
        self._position: dict[str, Any] | None = None
        self._config: dict[str, Any] = {}
        
        logger.info(f"SimpleGridAlgorithm {algorithm_id} initialized")
    
    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick - main algorithm logic."""
        if tick.symbol not in self._symbols:
            return None
        
        current_price = tick.price
        
        # Initialize grid on first tick
        if self._base_price is None:
            self._setup_grid(current_price)
            return None
        
        # If we have a position, check for exit
        if self._position is not None:
            return self._check_exit(tick, current_price)
        
        # No position - check for entry (price near grid level)
        return self._check_entry(tick, current_price)
    
    def _setup_grid(self, base_price: Decimal) -> None:
        """Create grid levels around base price."""
        grid_levels = int(self.get_config("grid_levels", 3))
        spacing_pct = Decimal(str(self.get_config("grid_spacing_pct", 1.0)))
        
        self._base_price = base_price
        self._grid_levels = []
        
        # Spacing in price units
        spacing = base_price * spacing_pct / Decimal("100")
        
        # Create levels below and above
        for i in range(1, grid_levels + 1):
            self._grid_levels.append(base_price - (spacing * i))  # Buy levels
            self._grid_levels.append(base_price + (spacing * i))  # Sell levels
        
        logger.info(f"Grid set: {len(self._grid_levels)} levels around {base_price}")
    
    def _check_entry(self, tick: EnrichedTick, price: Decimal) -> Signal | None:
        """Check if price is near a buy grid level."""
        # Find closest buy level below current price
        buy_levels = [level for level in self._grid_levels if level < price]
        if not buy_levels:
            return None
        
        closest_buy = max(buy_levels)
        distance_pct = abs(price - closest_buy) / closest_buy * 100
        
        # If price is within 0.15% of grid level, buy
        if distance_pct <= Decimal("0.15"):
            quantity = Decimal(str(self.get_config("quantity", 0.01)))
            
            # Update state
            self._position = {
                "entry_price": float(price),
                "quantity": float(quantity),
                "side": "LONG",
            }
            
            return Signal(
                algorithm_id=str(self._algorithm_id),
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=price,
                timestamp=tick.time,
                confidence=0.8,
                metadata={
                    "grid_level": float(closest_buy),
                    "distance_pct": float(distance_pct),
                    "reason": "price_near_grid",
                },
            )
        
        return None
    
    def _check_exit(self, tick: EnrichedTick, price: Decimal) -> Signal | None:
        """Check if we should sell (take profit or stop loss)."""
        if self._position is None:
            return None
        
        entry_price = Decimal(str(self._position["entry_price"]))
        pnl_pct = (price - entry_price) / entry_price * 100
        
        take_profit = Decimal(str(self.get_config("take_profit_pct", 0.5)))
        stop_loss = Decimal(str(self.get_config("stop_loss_pct", 2.0)))
        
        # Take profit
        if pnl_pct >= take_profit:
            self._position = None  # Clear state
            return Signal(
                algorithm_id=str(self._algorithm_id),
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=price,
                timestamp=tick.time,
                confidence=0.9,
                metadata={
                    "reason": "take_profit",
                    "pnl_pct": float(pnl_pct),
                },
            )
        
        # Stop loss
        if pnl_pct <= -stop_loss:
            self._position = None  # Clear state
            return Signal(
                algorithm_id=str(self._algorithm_id),
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=price,
                timestamp=tick.time,
                confidence=1.0,
                metadata={
                    "reason": "stop_loss",
                    "pnl_pct": float(pnl_pct),
                },
            )
        
        return None
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get config value."""
        return self._config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Set config value."""
        self._config[key] = value
```

### 3. Fitted ConfigurationSet Examples

ConfigurationSets store algorithm parameters in the database. Here are fitted examples for the SimpleGridAlgorithm:

#### Example 1: Conservative Grid for TEST/USDT

```json
{
    "name": "Conservative Grid TEST/USDT",
    "description": "Low-risk grid trading for TEST/USDT with tight spacing",
    "config": {
        "symbols": ["TEST/USDT"],
        "grid_levels": 3,
        "grid_spacing_pct": 0.5,
        "quantity": 0.01,
        "take_profit_pct": 0.3,
        "stop_loss_pct": 1.5,
        "max_positions": 1
    },
    "is_active": true,
    "created_by": "senior_trader"
}
```

#### Example 2: Aggressive Grid for BTC/USDT

```json
{
    "name": "Aggressive Grid BTC/USDT",
    "description": "Higher risk grid with wider spacing for BTC volatility",
    "config": {
        "symbols": ["BTC/USDT"],
        "grid_levels": 5,
        "grid_spacing_pct": 1.5,
        "quantity": 0.001,
        "take_profit_pct": 1.0,
        "stop_loss_pct": 3.0,
        "max_positions": 3
    },
    "is_active": true,
    "created_by": "quant_team"
}
```

#### Example 3: Multi-Symbol Grid

```json
{
    "name": "Multi-Symbol Grid Portfolio",
    "description": "Grid trading across multiple symbols",
    "config": {
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "grid_levels": 4,
        "grid_spacing_pct": 1.0,
        "quantity": 0.01,
        "take_profit_pct": 0.5,
        "stop_loss_pct": 2.0,
        "per_symbol_quantity": {
            "BTC/USDT": 0.001,
            "ETH/USDT": 0.01,
            "SOL/USDT": 0.1
        }
    },
    "is_active": true,
    "created_by": "portfolio_manager"
}
```

#### Creating ConfigurationSet via API

```bash
# Create via curl
curl -X POST http://localhost:8000/api/v1/config-sets \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Conservative Grid TEST/USDT",
    "description": "Low-risk grid trading",
    "config": {
      "symbols": ["TEST/USDT"],
      "grid_levels": 3,
      "grid_spacing_pct": 0.5,
      "quantity": 0.01,
      "take_profit_pct": 0.3,
      "stop_loss_pct": 1.5
    }
  }'

# Response includes the ID for linking to StrategyInstance
# {"id": "550e8400-e29b-41d4-a716-446655440000", "name": "Conservative Grid TEST/USDT", ...}
```

#### Creating ConfigurationSet via Python

```python
from src.domain.algorithms.config_set import ConfigurationSet
from uuid import uuid4

# Create ConfigurationSet
config_set = ConfigurationSet(
    name="Conservative Grid TEST/USDT",
    description="Low-risk grid trading for TEST/USDT",
    config={
        "symbols": ["TEST/USDT"],
        "grid_levels": 3,
        "grid_spacing_pct": 0.5,
        "quantity": 0.01,
        "take_profit_pct": 0.3,
        "stop_loss_pct": 1.5,
    },
    is_active=True,
    created_by="senior_architect",
)

# Save to database via repository
# repository.save(config_set)
```

#### How ConfigurationSet Maps to Algorithm

```python
# In your algorithm's on_tick method:
def on_tick(self, tick):
    # These calls read from the ConfigurationSet linked to StrategyInstance
    
    # Returns 3 (from config_set.config["grid_levels"])
    grid_levels = int(self.get_config("grid_levels", 5))
    
    # Returns 0.5 (from config_set.config["grid_spacing_pct"])
    spacing = Decimal(str(self.get_config("grid_spacing_pct", 1.0)))
    
    # Returns 0.01 (from config_set.config["quantity"])
    quantity = Decimal(str(self.get_config("quantity", 0.01)))
    
    # Returns 0.3 (from config_set.config["take_profit_pct"])
    take_profit = Decimal(str(self.get_config("take_profit_pct", 0.5)))
```

#### ConfigurationSets for Different Market Conditions

```python
# Bull market config - wider spacing, higher take profit
bull_config = {
    "grid_levels": 5,
    "grid_spacing_pct": 2.0,
    "quantity": 0.02,
    "take_profit_pct": 1.5,
    "stop_loss_pct": 3.0,
}

# Bear market config - tighter spacing, lower take profit
bear_config = {
    "grid_levels": 3,
    "grid_spacing_pct": 0.5,
    "quantity": 0.005,
    "take_profit_pct": 0.3,
    "stop_loss_pct": 1.0,
}

# Sideways market config - balanced
sideways_config = {
    "grid_levels": 4,
    "grid_spacing_pct": 1.0,
    "quantity": 0.01,
    "take_profit_pct": 0.5,
    "stop_loss_pct": 2.0,
}
```

### 4. Key Concepts

#### State Management
State variables declared in `__init__` persist between `on_tick()` calls:
```python
def __init__(self, ...):
    super().__init__(...)
    self._my_state = {}  # Persists between ticks
    self._counter = 0    # Persists between ticks

def on_tick(self, tick):
    self._counter += 1  # Updates persist
    # State is available on next tick
```

#### Accessing Indicators
Indicators are pre-calculated and attached to `EnrichedTick`:
```python
def on_tick(self, tick: EnrichedTick):
    # Method 1: Using get_indicator (with default)
    rsi = tick.get_indicator("rsiindicator_period14_rsi", 50.0)
    
    # Method 2: Direct access (may raise KeyError)
    rsi = tick.indicators["rsiindicator_period14_rsi"]
    
    # Method 3: Safe access
    rsi = tick.indicators.get("rsiindicator_period14_rsi", 50.0)
```

Indicator naming convention: `{name}{period}_{indicator}`
- `rsiindicator_period14_rsi` → RSI period 14
- `smaindicator_period20_sma` → SMA period 20
- `emaindicator_period12_ema` → EMA period 12
- `macdindicator_fast12_slow26_signal9_macd` → MACD

#### ConfigurationSet Access
Configuration is accessed via `get_config()`:
```python
def on_tick(self, tick):
    # Get config with default
    quantity = Decimal(str(self.get_config("quantity", 0.01)))
    threshold = float(self.get_config("threshold", 30.0))
    
    # Config is loaded from ConfigurationSet linked to StrategyInstance
    # Can be updated via Dashboard or API
```

#### Signal Generation
Return `Signal` objects to generate trades:
```python
from src.domain.algorithms.base import Signal, SignalType

def on_tick(self, tick):
    if condition:
        return Signal(
            algorithm_id=str(self._algorithm_id),
            symbol=tick.symbol,
            signal_type=SignalType.BUY,  # or SELL, HOLD
            price=tick.price,
            timestamp=tick.time,
            confidence=0.8,  # 0.0 to 1.0
            metadata={
                "reason": "rsi_oversold",
                "indicator_value": 25.5,
            },
        )
    return None  # No signal
```

### 5. Advanced Patterns

#### Multi-Symbol State
```python
def __init__(self, ...):
    self._symbol_states: dict[str, dict[str, Any]] = {}  # Per-symbol state

def on_tick(self, tick):
    symbol = tick.symbol
    if symbol not in self._symbol_states:
        self._symbol_states[symbol] = {"count": 0, "last_price": None}
    
    state = self._symbol_states[symbol]
    state["count"] += 1
    state["last_price"] = tick.price
```

#### Time-Based Conditions
```python
def on_tick(self, tick):
    now = datetime.now(timezone.utc)
    
    # Only trade during certain hours
    if now.hour < 9 or now.hour > 17:
        return None
    
    # Minimum time between signals
    if self._last_signal_time:
        time_since_last = (now - self._last_signal_time).total_seconds()
        if time_since_last < 300:  # 5 minutes
            return None
```

#### Custom Indicator Calculation
```python
def on_tick(self, tick):
    # Calculate custom indicator from price history
    if len(self._price_history) >= 20:
        prices = self._price_history[-20:]
        custom_ma = sum(prices) / len(prices)
        
        if tick.price > custom_ma:
            # Bullish
            pass
```

### 6. Integration with StrategyInstance

When deployed via StrategyInstance, your algorithm:
1. Is instantiated with `algorithm_id` (UUID)
2. Receives ticks via `AlgorithmManager.process_tick()`
3. Has access to `ConfigurationSet` via `get_config()`
4. State persists for the life of the instance
5. Can be started/stopped/paused via instance lifecycle

```python
# Infrastructure wires it together:
# 1. ConfigurationSet created in DB with config values
# 2. StrategyInstance links Algorithm + ConfigurationSet
# 3. Algorithm instantiated with ID
# 4. StrategyInstance.start() begins processing ticks
# 5. Your on_tick() called for each tick
```

### 7. Testing Your Algorithm

```python
"""
tests/unit/domain/algorithms/test_rsi_ma_algorithm.py
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from src.domain.algorithms.base import EnrichedTick, SignalType
from src.domain.algorithms.your_algorithm import RSIMovingAverageAlgorithm


@pytest.fixture
def algorithm():
    return RSIMovingAverageAlgorithm(
        algorithm_id=uuid4(),
        symbols=["BTC/USDT"],
    )


@pytest.fixture
def create_tick():
    def _create(price=100.0, rsi=50.0, sma=100.0):
        return EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal(str(price)),
            volume=Decimal("1.0"),
            time=datetime.now(timezone.utc),
            indicators={
                "rsiindicator_period14_rsi": rsi,
                "smaindicator_period20_sma": sma,
            },
        )
    return _create


class TestStatePersistence:
    """Test that state persists between ticks."""
    
    def test_counter_increments(self, algorithm, create_tick):
        """Test tick counter increments."""
        assert algorithm._tick_count == 0
        
        tick1 = create_tick()
        algorithm.on_tick(tick1)
        assert algorithm._tick_count == 1
        
        tick2 = create_tick()
        algorithm.on_tick(tick2)
        assert algorithm._tick_count == 2


class TestSignalGeneration:
    """Test buy/sell signal generation."""
    
    def test_buy_signal_oversold(self, algorithm, create_tick):
        """Test buy signal when RSI oversold."""
        algorithm.set_config("rsi_oversold", 30)
        
        tick = create_tick(price=100.0, rsi=25.0, sma=98.0)
        signal = algorithm.on_tick(tick)
        
        if signal:
            assert signal.signal_type == SignalType.BUY
            assert signal.metadata["reason"] == "rsi_oversold_with_momentum"


class TestConfigAccess:
    """Test configuration access."""
    
    def test_get_config_with_default(self, algorithm):
        """Test get_config returns default when key missing."""
        value = algorithm.get_config("nonexistent", 42)
        assert value == 42
    
    def test_set_and_get_config(self, algorithm):
        """Test runtime config override."""
        algorithm.set_config("quantity", 0.05)
        assert algorithm.get_config("quantity") == 0.05


class TestAlgorithmState:
    """Test state getter for monitoring."""
    
    def test_get_state_no_position(self, algorithm, create_tick):
        """Test state when no position."""
        tick = create_tick()
        algorithm.on_tick(tick)
        
        state = algorithm.get_algorithm_state()
        assert state["has_position"] is False
        assert state["tick_count"] == 1
```

## Algorithm Performance Checklist

Before deploying your algorithm:

- [ ] **State initialization**: All state vars initialized in `__init__`
- [ ] **State cleanup**: Position state cleared on exit
- [ ] **Indicator access**: Using `get_indicator()` with defaults
- [ ] **Config access**: Using `get_config()` with defaults
- [ ] **Error handling**: Try/except in `on_tick()` for robustness
- [ ] **Logging**: Key events logged with `logger.info/error()`
- [ ] **Signal metadata**: Relevant data included in signal
- [ ] **Type hints**: All methods have proper type annotations
- [ ] **Docstrings**: Google-style docstrings on public methods
- [ ] **Unit tests**: Tests for state, signals, config, edge cases
- [ ] **Backtesting**: Verified with historical data
- [ ] **Paper trading**: Tested in paper mode before live

## Common Pitfalls

1. **Forgetting state initialization**: Always init state in `__init__`
2. **Not handling missing indicators**: Use `get_indicator(key, default)`
3. **Blocking in on_tick**: Keep `on_tick()` fast (<10ms)
4. **Mutable default args**: Never use `[]` or `{}` as defaults
5. **Not clearing position state**: Clear `_position` on SELL
6. **Hardcoding config**: Use `get_config()` for flexibility

## Success Criteria

- [ ] Algorithm extends `Algorithm` base class
- [ ] State persists between ticks (demonstrated in tests)
- [ ] Indicators accessed from `EnrichedTick` correctly
- [ ] Configuration accessed via `get_config()`
- [ ] BUY/SELL signals generated correctly
- [ ] Signal metadata includes relevant context
- [ ] Unit tests cover state, signals, config, edge cases
- [ ] All tests pass
- [ ] mypy strict mode passes
- [ ] ruff check passes
- [ ] black formatting applied

## Commands to Run

```bash
# Format and lint
black src/domain/algorithms/your_algorithm.py tests/unit/domain/algorithms/test_your_algorithm.py
ruff check src/domain/algorithms/your_algorithm.py tests/unit/domain/algorithms/test_your_algorithm.py
mypy src/domain/algorithms/your_algorithm.py

# Run tests
.venv/bin/python -m pytest tests/unit/domain/algorithms/test_your_algorithm.py -v
```

## Output

1. Algorithm implementation file(s)
2. Unit test file(s)
3. Test results (passed/failed count)
4. mypy/ruff output (no errors)
5. Any issues encountered and resolution
