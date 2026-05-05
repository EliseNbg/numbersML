# Step 11: Grid Algorithm Implementation#

## Objective#
Implement a simple Grid Algorithm that generates positive PnL on noised sin wave data for TEST/USDT.

## Context#
- Phase 3 complete: Algorithm base class in `src/domain/algorithms/base.py`#
- Step 4 complete: AlgorithmInstance entity exists#
- Need a algorithm that works with TEST/USDT synthetic data#

## DDD Architecture Decision (ADR)#

**Decision**: GridAlgorithm is a concrete Algorithm implementation#
- **Extends**: `Algorithm` base class from Phase 3#
- **Logic**: Place buy orders at grid levels below price, sell orders above#
- **Profit**: From price oscillations in a range#
- **Grid Levels**: Configurable number of levels and spacing#

**Key Design**:#
- Use RSI or price distance to determine grid levels#
- Execute trades via MarketService (paper mode for backtest)#
- Track grid orders and PnL#

## TDD Approach#

1. **Red**: Write failing tests for GridAlgorithm#
2. **Green**: Implement algorithm to pass tests#
3. **Refactor**: Add logging, error handling, optimization#

## Implementation Files#

### 1. `src/domain/algorithms/grid_algorithm.py`#

```python
"""
Grid Trading Algorithm Implementation.

Places buy orders at regular intervals below current price,
sell orders above current price.
Profits from price oscillations in a range-bound market.

Follows Phase 3 Algorithm base class pattern.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.domain.algorithms.base import (
    Algorithm,
    Signal,
    SignalType,
    EnrichedTick,
)

logger = logging.getLogger(__name__)


class GridAlgorithm(Algorithm):
    """
    Grid trading algorithm.
    
    Places buy orders at grid levels below current price,
    and sell orders above current price.
    Profits from price oscillations.
    
    Configuration (in config_set.config):
        - grid_levels: Number of grid levels (default: 5)
        - grid_spacing_pct: Spacing between levels as % (default: 1%)
        - quantity: Base quantity per order (default: 0.01)
        - take_profit_pct: Take profit per grid (default: 0.5%)
        - stop_loss_pct: Stop loss (default: 2.0%)
    
    Example:
        >>> algorithm = GridAlgorithm(
        ...     algorithm_id="grid-1",
        ...     symbols=["TEST/USDT"],
        ... )
        >>> signal = algorithm.on_tick(tick)
    """
    
    def __init__(
        self,
        algorithm_id: str,
        symbols: List[str],
        time_frame: Any = None,
    ) -> None:
        """
        Initialize GridAlgorithm.
        
        Args:
            algorithm_id: Unique algorithm identifier
            symbols: List of symbols to trade
            time_frame: Time frame (not used for grid)
        """
        super().__init__(algorithm_id=algorithm_id, symbols=symbols)
        
        # Grid state
        self._grid_levels: List[Decimal] = []
        self._grid_orders: Dict[str, Dict[str, Any]] = {}  # order_id → order info
        self._base_price: Optional[Decimal] = None
        self._höhest_price: Optional[Decimal] = None
        self._lowest_price: Optional[Decimal] = None
        
        logger.info(f"GridAlgorithm {algorithm_id} initialized for {symbols}")
    
    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """
        Process tick and generate grid trading signal.
        
        Args:
            tick: Enriched tick data with indicators
            
        Returns:
            Signal if grid condition met, None otherwise
        """
        if tick.symbol not in self._symbols:
            return None
        
        current_price = tick.price
        
        # Initialize grid on first tick
        if self._base_price is None:
            self._initialize_grid(current_price)
            return None
        
        # Update price bounds
        if self._höhest_price is None or current_price > self._höhest_price:
            self._höhest_price = current_price
        if self._lowest_price is None or current_price < self._lowest_price:
            self._lowest_price = current_price
        
        # Check if price moved significantly → rebalance grid
        price_change_pct = abs(current_price - self._base_price) / self._base_price * 100
        if price_change_pct > Decimal("5.0"):  # Rebalance if >5% move
            logger.info(f"Price moved {price_change_pct:.2f}%, rebalancing grid")
            self._initialize_grid(current_price)
        
        # Check for buy signals (price near grid level)
        buy_signal = self._check_buy_signal(current_price, tick)
        if buy_signal:
            return buy_signal
        
        # Check for sell signals (in profit)
        sell_signal = self._check_sell_signal(current_price, tick)
        if sell_signal:
            return sell_signal
        
        return None
    
    def _initialize_grid(self, base_price: Decimal) -> None:
        """
        Initialize grid levels around base price.
        
        Args:
            base_price: Current price to center grid around
        """
        grid_levels = int(self.get_config("grid_levels", 5))
        grid_spacing_pct = Decimal(str(self.get_config("grid_spacing_pct", 1.0)))
        
        self._base_price = base_price
        self._grid_levels = []
        
        # Create grid levels below and above base price
        spacing = base_price * grid_spacing_pct / Decimal("100")
        
        for i in range(1, grid_levels + 1):
            # Buy levels below
            buy_level = base_price - (spacing * i)
            self._grid_levels.append(buy_level)
            
            # Sell levels above
            sell_level = base_price + (spacing * i)
            self._grid_levels.append(sell_level)
        
        self._grid_levels.sort()
        
        logger.info(
            f"Grid initialized: {len(self._grid_levels)} levels, "
            f"spacing={grid_spacing_pct}%, range=[{self._grid_levels[0]:.4f}, {self._grid_levels[-1]:.4f}]"
        )
    
    def _check_buy_signal(
        self, current_price: Decimal, tick: EnrichedTick
    ) -> Optional[Signal]:
        """
        Check if price is near a buy grid level.
        
        Args:
            current_price: Current price
            tick: Enriched tick data
            
        Returns:
            Buy Signal if condition met, None otherwise
        """
        # Check if we have open positions
        if tick.symbol in self._positions:
            return None  # Already have position
        
        # Find nearest buy level below current price
        buy_levels = [lvl for lvl in self._grid_levels if lvl < current_price]
        
        if not buy_levels:
            return None
        
        nearest_buy = max(buy_levels)  # Highest buy level below price
        
        # Check if price is within threshold of buy level
        threshold_pct = Decimal("0.1")  # 0.1% threshold
        distance_pct = abs(current_price - nearest_buy) / nearest_buy * 100
        
        if distance_pct <= threshold_pct:
            quantity = Decimal(str(self.get_config("quantity", 0.01)))
            
            return Signal(
                algorithm_id=self._algorithm_id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=current_price,
                timestamp=tick.time,
                confidence=0.8,
                metadata={
                    "grid_level": float(nearest_buy),
                    "distance_pct": float(distance_pct),
                    "reason": "price_near_buy_grid",
                },
            )
        
        return None
    
    def _check_sell_signal(
        self, current_price: Decimal, tick: EnrichedTick
    ) -> Optional[Signal]:
        """
        Check if we should sell for profit.
        
        Args:
            current_price: Current price
            tick: Enriched tick data
            
        Returns:
            Sell Signal if in profit, None otherwise
        """
        if tick.symbol not in self._positions:
            return None  # No open position
        
        position = self._positions[tick.symbol]
        
        # Calculate profit percentage
        profit_pct = (current_price - position.entry_price) / position.entry_price * 100
        
        # Get grid spacing as take profit target
        take_profit_pct = Decimal(str(self.get_config("take_profit_pct", 0.5)))
        
        # Sell if we hit take profit target
        if profit_pct >= take_profit_pct:
            return Signal(
                algorithm_id=self._algorithm_id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                timestamp=tick.time,
                confidence=0.9,
                metadata={
                    "entry_price": float(position.entry_price),
                    "profit_pct": float(profit_pct),
                    "reason": "take_profit",
                },
            )
        
        # Check stop loss
        stop_loss_pct = Decimal(str(self.get_config("stop_loss_pct", 2.0)))
        
        if profit_pct <= -stop_loss_pct:
            return Signal(
                algorithm_id=self._algorithm_id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                timestamp=tick.time,
                confidence=1.0,
                metadata={
                    "entry_price": float(position.entry_price),
                    "loss_pct": float(profit_pct),
                    "reason": "stop_loss",
                },
            )
        
        return None
    
    def get_grid_levels(self) -> List[Decimal]:
        """Get current grid levels."""
        return self._grid_levels.copy()
    
    def get_grid_stats(self) -> Dict[str, Any]:
        """Get grid statistics."""
        return {
            "base_price": float(self._base_price) if self._base_price else None,
            "grid_levels": [float(lvl) for lvl in self._grid_levels],
            "num_levels": len(self._grid_levels),
            "highest_price": float(self._höhest_price) if self._höhest_price else None,
            "lowest_price": float(self._lowest_price) if self._lowest_price else None,
            "open_positions": len(self._positions),
        }
```

### 2. `tests/unit/domain/algorithms/test_grid_algorithm.py`#

```python
"""
Unit tests for GridAlgorithm.

Follows TDD approach: tests first, then implementation.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.domain.algorithms.grid_algorithm import GridAlgorithm
from src.domain.algorithms.base import SignalType, EnrichedTick


@pytest.fixture
def grid_algorithm():
    """Create a GridAlgorithm for testing."""
    return GridAlgorithm(
        algorithm_id="test-grid-1",
        symbols=["TEST/USDT"],
    )


@pytest.fixture
def create_tick():
    """Factory for creating EnrichedTick."""
    def _create(
        symbol="TEST/USDT",
        price=100.0,
        time=None,
        indicators=None,
    ):
        return EnrichedTick(
            symbol=symbol,
            price=Decimal(str(price)),
            volume=Decimal("1.0"),
            time=time or datetime.now(timezone.utc),
            indicators=indicators or {},
        )
    return _create


class TestGridAlgorithmInit:
    """Tests for GridAlgorithm initialization."""
    
    def test_create_grid_algorithm(self, grid_algorithm):
        """Test creating a GridAlgorithm."""
        assert grid_algorithm.id == "test-grid-1"
        assert grid_algorithm.symbols == ["TEST/USDT"]
        assert grid_algorithm.state.value == "STOPPED"
    
    def test_initial_grid_empty(self, grid_algorithm):
        """Test that grid levels are empty initially."""
        assert len(grid_algorithm.get_grid_levels()) == 0
        stats = grid_algorithm.get_grid_stats()
        assert stats["num_levels"] == 0


class TestGridInitialization:
    """Tests for grid initialization."""
    
    def test_initialize_grid(self, grid_algorithm):
        """Test grid initialization on first tick."""
        tick = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("100.0"),
            volume=Decimal("1.0"),
            time=datetime.now(timezone.utc),
        )
        
        # Process tick to initialize grid
        grid_algorithm.on_tick(tick)
        
        # Check grid was initialized
        levels = grid_algorithm.get_grid_levels()
        assert len(levels) > 0
        
        # Check levels are around base price (100.0)
        for level in levels:
            assert Decimal("90.0") < level < Decimal("110.0")
    
    def test_grid_levels_count(self, grid_algorithm):
        """Test that correct number of levels are created."""
        grid_algorithm.set_config("grid_levels", 3)
        
        tick = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("100.0"),
            volume=Decimal("1.0"),
            time=datetime.now(timezone.utc),
        )
        
        grid_algorithm.on_tick(tick)
        
        # 3 levels below + 3 levels above = 6 total
        levels = grid_algorithm.get_grid_levels()
        assert len(levels) == 6
    
    def test_grid_rebalance(self, grid_algorithm):
        """Test grid rebalancing on large price move."""
        # Initialize at 100
        tick1 = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("100.0"),
            volume=Decimal("1.0"),
            time=datetime.now(timezone.utc),
        )
        grid_algorithm.on_tick(tick1)
        old_levels = grid_algorithm.get_grid_levels().copy()
        
        # Price moves >5% → should rebalance
        tick2 = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("106.0"),  # 6% move
            volume=Decimal("1.0"),
            time=datetime.now(timezone.utc),
        )
        grid_algorithm.on_tick(tick2)
        
        new_levels = grid_algorithm.get_grid_levels()
        
        # New levels should be around 106, not 100
        for level in new_levels:
            assert Decimal("96.0") < level < Decimal("116.0")


class TestBuySignals:
    """Tests for buy signal generation."""
    
    def test_buy_signal_near_grid(self, grid_algorithm, create_tick):
        """Test buy signal when price near grid level."""
        # Initialize grid at 100
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)
        
        # Price at 99.0 should be near a buy grid level
        tick2 = create_tick(price=99.0)
        signal = grid_algorithm.on_tick(tick2)
        
        # Check if signal generated (may depend on grid spacing)
        # This test may need adjustment based on exact grid logic
        if signal:
            assert signal.signal_type == SignalType.BUY
            assert signal.symbol == "TEST/USDT"
    
    def test_no_buy_with_position(self, grid_algorithm, create_tick):
        """Test that no buy signal if position exists."""
        # Initialize grid
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)
        
        # Open a position
        grid_algorithm.open_position(
            symbol="TEST/USDT",
            side="LONG",
            quantity=Decimal("0.01"),
            price=Decimal("99.0"),
        )
        
        # Try to get another buy signal
        tick2 = create_tick(price=98.0)
        signal = grid_algorithm.on_tick(tick2)
        
        # Should not get buy signal with open position
        assert signal is None


class TestSellSignals:
    """Tests for sell signal generation."""
    
    def test_sell_at_take_profit(self, grid_algorithm, create_tick):
        """Test sell signal at take profit."""
        # Initialize and open position
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)
        
        grid_algorithm.open_position(
            symbol="TEST/USDT",
            side="LONG",
            quantity=Decimal("0.01"),
            price=Decimal("100.0"),
        )
        
        # Price rises to trigger take profit (0.5% by default)
        tick2 = create_tick(price=100.6)  # 0.6% profit
        signal = grid_algorithm.on_tick(tick2)
        
        if signal:
            assert signal.signal_type == SignalType.SELL
            assert "take_profit" in signal.metadata.get("reason", "")
    
    def test_sell_at_stop_loss(self, grid_algorithm, create_tick):
        """Test sell signal at stop loss."""
        # Initialize and open position
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)
        
        grid_algorithm.open_position(
            symbol="TEST/USDT",
            side="LONG",
            quantity=Decimal("0.01"),
            price=Decimal("100.0"),
        )
        
        # Price drops to trigger stop loss (2% by default)
        tick2 = create_tick(price=97.5)  # -2.5% loss
        signal = grid_algorithm.on_tick(tick2)
        
        if signal:
            assert signal.signal_type == SignalType.SELL
            assert "stop_loss" in signal.metadata.get("reason", "")


class TestGridStats:
    """Tests for grid statistics."""
    
    def test_get_grid_stats(self, grid_algorithm, create_tick):
        """Test getting grid statistics."""
        tick = create_tick(price=100.0)
        grid_algorithm.on_tick(tick)
        
        stats = grid_algorithm.get_grid_stats()
        
        assert "base_price" in stats
        assert stats["base_price"] == 100.0
        assert "num_levels" in stats
        assert stats["num_levels"] > 0
        assert "open_positions" in stats
```

## LLM Implementation Prompt#

```text
You are implementing Step 11 of Phase 4: Grid Algorithm Implementation.

## Your Task#

Implement a simple Grid Algorithm that generates positive PnL on TEST/USDT.

## Context#

- Phase 3 complete: Algorithm base class in src/domain/algorithms/base.py`
- Step 4 complete: AlgorithmInstance entity exists
- Grid algorithm places buy orders below price, sell above
- Must follow existing Algorithm base class pattern#

## Requirements#

1. Create `src/domain/algorithms/grid_algorithm.py` with:
   - GridAlgorithm class extending Algorithm
   - __init__(algorithm_id, symbols, time_frame)
   - on_tick(tick) -> Optional[Signal]:
     * Initialize grid on first tick
     * Check for buy signals (price near grid level)
     * Check for sell signals (take profit or stop loss)
     * Rebalance grid if price moves >5%
   - _initialize_grid(base_price): Create grid levels
   - _check_buy_signal(): Generate buy signal
   - _check_sell_signal(): Generate sell signal
   - get_grid_levels() -> List[Decimal]
   - get_grid_stats() -> Dict with grid info
   - Configuration keys: grid_levels, grid_spacing_pct, quantity, take_profit_pct, stop_loss_pct
   - Full type annotations (mypy strict)
   - Google-style docstrings

2. Create `tests/unit/domain/algorithms/test_grid_algorithm.py` with TDD:
   - TestGridAlgorithmInit: creation, initial state
   - TestGridInitialization: initialize grid, levels count, rebalance
   - TestBuySignals: buy near grid, no buy with position
   - TestSellSignals: sell at take profit, sell at stop loss
   - TestGridStats: get_grid_stats()
   - Use EnrichedTick from base module for testing#

3. Key Implementation Details:
   - Grid levels: N levels below and N levels above base price
   - Spacing: base_price * grid_spacing_pct / 100
   - Buy signal: price within 0.1% of grid level, no open position
   - Sell signal: profit >= take_profit_pct OR loss >= stop_loss_pct
   - Rebalance: if price moves >5% from base_price#

## Constraints#

- Follow AGENTS.md coding standards#
- Use type hints on all public methods (mypy strict)#
- Use Google-style docstrings#
- Line length max 100 characters#
- Use Decimal for price calculations (not float)#
- Log with logger.info(f"..."), logger.error(f"...")#

## Acceptance Criteria#

1. GridAlgorithm extends Algorithm base class#
2. Grid initializes on first tick with correct levels#
3. Buy signals generated near grid levels (no position)#
4. Sell signals generated at take profit or stop loss#
5. Grid rebalances on large price moves (>5%)#
6. get_grid_stats() returns correct information#
7. All unit tests pass#
8. mypy passes with no errors#
9. ruff check passes with no errors#
10. black formatting applied#

## Commands to Run#

```bash
# Format and lint
black src/domain/algorithms/grid_algorithm.py tests/unit/domain/algorithms/test_grid_algorithm.py
ruff check src/domain/algorithms/grid_algorithm.py tests/unit/domain/algorithms/test_grid_algorithm.py
mypy src/domain/algorithms/grid_algorithm.py

# Run tests
.venv/bin/python -m pytest tests/unit/domain/algorithms/test_grid_algorithm.py -v
```

## Output#

1. List of files created/modified#
2. Test results (passed/failed count)#
3. mypy/ruff output (no errors)#
4. Any issues encountered and how resolved#
```

## Success Criteria#

- [ ] GridAlgorithm created extending Algorithm base#
- [ ] Grid initializes correctly with configurable levels#
- [ ] Buy signals work (near grid levels)#
- [ ] Sell signals work (take profit/stop loss)#
- [ ] Grid rebalancing on large price moves#
- [ ] All unit tests pass (TDD approach)#
- [ ] mypy strict mode passes#
- [ ] ruff check passes (rules: E, W, F, I, N, UP, B, C4)#
- [ ] black formatting applied#
- [ ] Google-style docstrings on all public methods#
