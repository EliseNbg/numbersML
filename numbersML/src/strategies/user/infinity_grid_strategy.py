"""
Infinity Grid Trading Strategy.

Grid Structure:
    - grid_size is total number of grid levels (both above and below reference price)
    - All indices (0, 1, 2...): grid levels
    - Buy at level i when price crosses from above to below the level
    - After a buy signal, lock buying until price crosses either level i-1 or i+1
    - Sell at expected profit price (current buy price + grid_profit_pct%)
    - Market (or user) is responsible for selling the asset at expected profit price.

Configuration:
    - grid_size: Number of grid levels
    - grid_spacing_pct: Spacing between levels as % (default: 0.65)
    - grid_profit_pct: Profit percentage for each BUY (default: 0.85)
    - grid_quantity_absolute: Dollar amount per grid position
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class InfinityGridStrategy(Strategy):
    """Infinity grid trading with BUY levels only and expected profit price in metadata."""

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        self.reference_price: float | None = None
        self.grid_levels: list[float] = []
        self.last_price: float = 0.0
        self.grid_spacing_pct: float = 1.0
        self.grid_profit_pct: float = 0.85

        # Track per symbol: which level is locked after a signal (None means not locked)
        self._symbol_locked_level: dict[str, int | None] = {}
        # Track per symbol: which buy levels have been used (for statistics)
        self._symbol_used_buy_levels: dict[str, set[int]] = {}
        # Track per symbol: the grid index of open position (None if no position)
        self._symbol_open_positions: dict[str, int | None] = {}

        self._tick_count: int = 0

        logger.info(f"InfinityGridStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        price = float(tick.price)

        if self.reference_price is None:
            self._initialize_grid(price)
            self.last_price = price
            return None

        self._tick_count += 1
        signal = self._detect_crossing(price, tick) if self.last_price > 0 else None

        if self._tick_count % 500 == 0:
            logger.info(
                f"{tick.time} Tick {self._tick_count}: "
                f"price={price:.8f}, open_positions={sum(1 for v in self._symbol_open_positions.values() if v is not None)}"
            )

        self.last_price = price
        return signal

    def _initialize_grid(self, first_price: float) -> None:
        self.reference_price = first_price
        self.grid_size = self.get_config("grid_size", 8)
        self.grid_spacing_pct = self.get_config("grid_spacing_pct", 0.65)
        self.grid_profit_pct = self.get_config("grid_profit_pct", 0.85)
        self._calculate_grid_levels()

        # Initialize per-symbol tracking
        for symbol in self.symbols:
            self._symbol_locked_level[symbol] = None
            self._symbol_used_buy_levels[symbol] = set()
            self._symbol_open_positions[symbol] = None

        logger.info(
            f"[{self._strategy_id}] Grid: ref={self.reference_price}, "
            f"size={self.grid_size}, spacing={self.grid_spacing_pct}%, "
            f"profit_pct={self.grid_profit_pct}%, "
            f"levels={[round(level, 6) for level in self.grid_levels]}"
        )

    def _calculate_grid_levels(self) -> None:
        """Calculate grid levels both above and below reference price with uniform spacing.
        The reference price is not included in the levels array.
        Half of the levels are below reference, half are above (for even grid_size).
        Only levels below reference price are used for BUY signals.
        """
        if self.reference_price is None:
            return

        spacing = self.reference_price * (self.grid_spacing_pct / 100.0)
        levels = []
        half_size = self.grid_size // 2
        
        # Calculate levels below reference: ref - half_size*spacing, ref - (half_size-1)*spacing, ..., ref - 1*spacing
        for i in range(half_size, 0, -1):
            levels.append(self.reference_price - i * spacing)
            
        # Calculate levels above reference: ref + 1*spacing, ref + 2*spacing, ..., ref + half_size*spacing
        for i in range(1, half_size + 1):
            levels.append(self.reference_price + i * spacing)

        self.grid_levels = levels

    def _detect_crossing(self, price: float, tick: EnrichedTick) -> Signal | None:
        last = self.last_price
        symbol = tick.symbol

        # Track the level that caused unlock (to prevent immediate buy at that level)
        unlocked_at_level = None

        # Check if we crossed any level (either direction)
        crossed_any_level = False
        crossed_level_index = None

        for i, level in enumerate(self.grid_levels):
            # Check if we crossed this level (either direction)
            if (last > level and price <= level) or (last < level and price >= level):
                crossed_any_level = True
                crossed_level_index = i
                break

        # If we crossed a level, check if it's the adjacent level to unlock the locked level
        if crossed_any_level and crossed_level_index is not None:
            locked_level = self._symbol_locked_level.get(symbol)
            if locked_level is not None:
                # Check if crossed level is adjacent to locked level (N-1 or N+1)
                if abs(crossed_level_index - locked_level) == 1:
                    # Unlock the level and track which level caused unlock
                    self._symbol_locked_level[symbol] = None
                    unlocked_at_level = crossed_level_index
                    logger.info(
                        f"[{self._strategy_id}] Unlocked buying after crossing adjacent level "
                        f"(was locked at {locked_level}, crossed at {crossed_level_index}) for {symbol}"
                    )

        # Check for BUY signals (price crossing from above to below)
        for i, level in enumerate(self.grid_levels):
            # Skip BUY at the level that just unlocked us (prevents buy storm)
            if i == unlocked_at_level:
                continue
            if self._symbol_locked_level.get(symbol) is None and last > level and price <= level:
                return self._signal_buy(tick, level, i, symbol)

        return None

    def _detect_crossing_old(self, price: float, tick: EnrichedTick) -> Signal | None:
        last = self.last_price
        symbol = tick.symbol

        # Check if we crossed any level (either direction)
        crossed_any_level = False
        crossed_level_index = None
        
        for i, level in enumerate(self.grid_levels):
            # Check if we crossed this level (either direction)
            if (last > level and price <= level) or (last < level and price >= level):
                crossed_any_level = True
                crossed_level_index = i
                break

        # If we crossed a level, check if it's the adjacent level to unlock the locked level
        if crossed_any_level and crossed_level_index is not None:
            # If we have a locked level for this symbol, check if the crossed level is adjacent
            locked_level = self._symbol_locked_level.get(symbol)
            if locked_level is not None:
                # Check if crossed level is adjacent to locked level (N-1 or N+1)
                if abs(crossed_level_index - locked_level) == 1:
                    # Unlock the level
                    self._symbol_locked_level[symbol] = None
                    logger.info(
                        f"[{self._strategy_id}] Unlocked buying after crossing adjacent level "
                        f"(was locked at {locked_level}, crossed at {crossed_level_index}) for {symbol}"
                    )

        # Check for BUY signals (price crossing from above to below)
        for i, level in enumerate(self.grid_levels):
            # Check if buying is not locked for this symbol and price crossed from above to below
            if self._symbol_locked_level.get(symbol) is None and last > level and price <= level:
                return self._signal_buy(tick, level, i, symbol)

        return None

    def _signal_buy(self, tick: EnrichedTick, level: float, grid_index: int, symbol: str) -> Signal:
        # Calculate expected profit price: buy_price * (1 + grid_profit_pct/100)
        expected_profit_price = level * (1 + self.grid_profit_pct / 100.0)

        # Lock this level for this symbol (prevent another signal at same level until adjacent level crossed)
        self._symbol_locked_level[symbol] = grid_index
        # Mark this level as used and set as open position for statistics
        self._symbol_used_buy_levels[symbol].add(grid_index)
        self._symbol_open_positions[symbol] = grid_index

        logger.info(
            f"[{self._strategy_id}] BUY at lvl {grid_index} ({level:.6f}) for {symbol}, "
            f"expected profit @ {expected_profit_price:.6f}"
        )

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.BUY,
            price=tick.price,
            confidence=0.8,
            metadata={
                "grid_level": level,
                "grid_index": grid_index,
                "expected_profit_price": expected_profit_price,
                "reference_price": self.reference_price,
            },
        )

    def on_position_closed(
        self,
        symbol: str,
        price: Decimal,
        exit_reason: str,
        grid_index: int | None = None,
    ) -> None:
        """Called when position is closed externally (by market or user)."""
        logger.info(
            f"[{self._strategy_id}] Position closed for {symbol}: reason={exit_reason}, "
            f"price={price:.8f}, grid_index={grid_index}"
        )
        # If we have a grid_index from the callback, use it to clean up
        # Otherwise, try to get the open position grid index for this symbol
        if grid_index is None and symbol in self._symbol_open_positions:
            grid_index = self._symbol_open_positions[symbol]

        if grid_index is not None and grid_index in self._symbol_used_buy_levels[symbol]:
            # Unlock the level for reuse
            self._symbol_used_buy_levels[symbol].discard(grid_index)
            # Clear the open position for this symbol
            self._symbol_open_positions[symbol] = None
            logger.info(
                f"[{self._strategy_id}] Unlocked grid level {grid_index} for {symbol}"
            )

    def get_stats(self) -> dict[str, Any]:
        stats = super().get_stats()
        stats.update(
            {
                "reference_price": self.reference_price,
                "grid_levels": self.grid_levels,
                "open_positions_count": sum(1 for v in self._symbol_open_positions.values() if v is not None),
                "used_buy_levels": {sym: list(levels) for sym, levels in self._symbol_used_buy_levels.items()},
                "tick_count": self._tick_count,
            }
        )
        return stats
