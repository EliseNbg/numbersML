"""
Infinity Grid Trading Strategy.

Grid Structure:
    - grid_size is total number of BUY levels
    - All indices (0, 1, 2...): BUY levels below reference
    - Buy at level i, sell at expected profit price (current buy price + grid_profit_pct%)
    - Market (or user) is responsible for selling the asset at expected profit price.

Configuration:
    - grid_size: Number of grid levels (BUY levels only)
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

        # Track per symbol: which buy levels have been used and open position grid index
        self._symbol_used_buy_levels: dict[str, set[int]] = {}
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
                f"[{self._strategy_id}] Tick {self._tick_count}: "
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
            self._symbol_used_buy_levels[symbol] = set()
            self._symbol_open_positions[symbol] = None

        logger.info(
            f"[{self._strategy_id}] Grid: ref={self.reference_price}, "
            f"size={self.grid_size}, spacing={self.grid_spacing_pct}%, "
            f"profit_pct={self.grid_profit_pct}%, "
            f"levels={[round(level, 6) for level in self.grid_levels]}"
        )

    def _calculate_grid_levels(self) -> None:
        """Calculate BUY levels only (below reference price)."""
        if self.reference_price is None:
            return

        spacing = self.reference_price * (self.grid_spacing_pct / 100.0)
        levels = []

        for i in range(self.grid_size):
            # BUY level: reference_price - (i+1)*spacing
            levels.append(self.reference_price - (i + 1) * spacing)

        self.grid_levels = levels

    def _detect_crossing(self, price: float, tick: EnrichedTick) -> Signal | None:
        last = self.last_price
        symbol = tick.symbol

        for i, level in enumerate(self.grid_levels):
            # Check if this BUY level is available for this symbol
            if i not in self._symbol_used_buy_levels[symbol] and last > level and price <= level:
                return self._signal_buy(tick, level, i, symbol)

        return None

    def _signal_buy(self, tick: EnrichedTick, level: float, grid_index: int, symbol: str) -> Signal:
        # Calculate expected profit price: buy_price * (1 + grid_profit_pct/100)
        expected_profit_price = level * (1 + self.grid_profit_pct / 100.0)

        # Mark level as used for this symbol
        self._symbol_used_buy_levels[symbol].add(grid_index)
        # Mark that we have an open position at this grid index for this symbol
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
