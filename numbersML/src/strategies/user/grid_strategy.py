"""
Grid Trading Strategy.

Grid Structure:
    - grid_size is total number of levels
    - Even indices (0, 2, 4...): BUY levels below reference
    - Odd indices (1, 3, 5...): TAKE-PROFIT levels ~2*spacing above corresponding buy
    - Buy at level i, sell at level i+1 for ~2*grid_spacing_pct profit (e.g., 1.3%)

Configuration:
    - grid_size: Number of grid levels (default: 10)
    - grid_spacing_pct: Spacing between levels as % (default: 0.65)
    - grid_quantity_absolute: Dollar amount per grid position
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class GridTradingStrategy(Strategy):
    """Grid trading with alternating buy/take-profit levels around reference."""

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

        self._open_positions: dict[int, int] = {}  # buy_index -> tp_index
        self._used_buy_levels: set[int] = set()

        self._tick_count: int = 0

        logger.info(f"GridTradingStrategy {strategy_id} initialized")

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
                f"price={price:.8f}, open_positions={len(self._open_positions)}"
            )

        self.last_price = price
        return signal

    def _initialize_grid(self, first_price: float) -> None:
        self.reference_price = first_price
        self.grid_size = self.get_config("grid_size", 10)
        self.grid_spacing_pct = self.get_config("grid_spacing_pct", 0.65)
        self._calculate_grid_levels()

        logger.info(
            f"[{self._strategy_id}] Grid: ref={self.reference_price}, "
            f"size={self.grid_size}, spacing={self.grid_spacing_pct}%, "
            f"levels={[round(level, 6) for level in self.grid_levels]}"
        )

    def _calculate_grid_levels(self) -> None:
        """Calculate alternating buy (below ref) and TP levels for 2*spacing profit.

        Grid pairs: BUY at ref - n*spacing, TP at ref - (n-2)*spacing for n=1,2,3...
        This gives ~2*grid_spacing_pct profit per complete grid cycle (e.g., 1.3%).
        """
        if self.reference_price is None:
            return

        spacing = self.reference_price * (self.grid_spacing_pct / 100.0)
        levels = []

        pair_index = 0
        for i in range(self.grid_size):
            if i % 2 == 0:  # BUY level (below reference)
                # For pair n (starting at 1): buy at ref - n*spacing
                levels.append(self.reference_price - (pair_index + 1) * spacing)
            else:  # TP level (2*spacing above corresponding buy)
                # For pair n: TP at ref - (n-2)*spacing = BUY + 2*spacing
                levels.append(self.reference_price - (pair_index - 1) * spacing)
                pair_index += 1

        self.grid_levels = levels

    def _detect_crossing(self, price: float, tick: EnrichedTick) -> Signal | None:
        last = self.last_price

        for i, level in enumerate(self.grid_levels):
            if i % 2 == 0:  # BUY level (below reference)
                if i not in self._used_buy_levels and last > level and price <= level:
                    return self._signal_buy(tick, level, i)
            else:  # TAKE-PROFIT level (above reference)
                if i in self._open_positions.values() and last < level and price >= level:
                    return self._signal_sell(tick, level, i)

        return None

    def _signal_buy(self, tick: EnrichedTick, level: float, grid_index: int) -> Signal:
        tp_index = grid_index + 1
        tp_price = self.grid_levels[tp_index]
        self._used_buy_levels.add(grid_index)
        self._open_positions[grid_index] = tp_index

        logger.info(f"[{self._strategy_id}] BUY at lvl {grid_index} ({level:.6f}), TP @ {tp_price:.6f}")

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.BUY,
            price=tick.price,
            confidence=0.8,
            metadata={
                "grid_level": level,
                "grid_index": grid_index,
                "take_profit_price": tp_price,
                "reference_price": self.reference_price,
            },
        )

    def _signal_sell(self, tick: EnrichedTick, level: float, grid_index: int) -> Signal:
        buy_index = grid_index - 1
        self._open_positions.pop(buy_index, None)
        self._used_buy_levels.discard(buy_index)

        logger.info(f"[{self._strategy_id}] SELL at lvl {grid_index} ({level:.6f})")

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.SELL,
            price=tick.price,
            confidence=0.8,
            metadata={
                "grid_level": level,
                "grid_index": grid_index,
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
        logger.info(
            f"[{self._strategy_id}] Position closed: reason={exit_reason}, "
            f"price={price:.8f}, grid_index={grid_index}"
        )
        if grid_index is not None:
            buy_index = grid_index - 1 if grid_index % 2 == 1 else grid_index
            self._open_positions.pop(buy_index, None)
            self._used_buy_levels.discard(buy_index)

    def get_stats(self) -> dict[str, Any]:
        stats = super().get_stats()
        stats.update(
            {
                "reference_price": self.reference_price,
                "grid_levels": self.grid_levels,
                "open_positions_count": len(self._open_positions),
                "used_buy_levels": list(self._used_buy_levels),
                "tick_count": self._tick_count,
            }
        )
        return stats
