"""Grid Trading Strategy.

This strategy implements a grid trading approach:
- Places buy orders at regular price intervals below reference price
- Takes profit at price levels above reference price
- Generates BUY signals when price drops TO a grid level from above
- Generates SELL signals when price rises TO a grid level from below

The strategy maintains:
- Grid levels (calculated from reference price)
- Last price seen (for detecting grid level crosses)
- Current position status
- Last traded grid index (to prevent immediate reversal)
"""

import logging
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class GridTradingStrategy(Strategy):
    """Grid trading strategy with persistent state.

    State:
        - reference_price: Center price for grid
        - grid_levels: List of price levels (sorted ascending)
        - last_price: Last tick price
        - grid_size: Number of grid levels above/below
        - grid_spacing_pct: Spacing between levels as percentage
        - current_grid_index: Current position in grid
        - in_position: Whether currently holding a position
        - last_trade_grid_index: Index of last traded grid level (prevents reversal)

    Configuration (accessed via self.get_config):
        - grid_size: Number of grid levels each side (default: 5)
        - grid_spacing_pct: Spacing between levels as % of reference (default: 1.0)
        - reference_price: Center price (default: None, uses first tick)
        - quantity: Position size per grid level (default: 0.01)
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        # Persistent state
        self.reference_price: float | None = None
        self.grid_levels: list[float] = []
        self.last_price: float = 0.0
        self.grid_size: int = 5
        self.grid_spacing_pct: float = 1.0
        self.current_grid_index: int = 0
        self.in_position: bool = False
        # Track the grid level where we bought (to prevent immediate sell at same level)
        self.last_trade_grid_index: int = -1
        # Track tick count for periodic logging
        self._tick_count: int = 0

        logger.info(f"GridTradingStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate grid trading signals.

        Args:
            tick: Enriched tick data

        Returns:
            Signal if grid level crossed, None otherwise
        """
        price = float(tick.price)

        # Initialize grid on first tick
        if self.reference_price is None:
            self.reference_price = price
            self.grid_size = self.get_config("grid_size", 5)
            self.grid_spacing_pct = self.get_config("grid_spacing_pct", 1.0)
            self._calculate_grid_levels()
            logger.info(
                f"[{self._strategy_id}] Grid initialized BEFORE config apply: "
                f"ref_price={self.reference_price}, grid_size={self.grid_size}, "
                f"spacing_pct={self.grid_spacing_pct}"
            )
            logger.info(
                f"[{self._strategy_id}] Grid levels AFTER config apply: {self.grid_levels}"
            )
            self.last_price = price
            return None

        self._tick_count += 1

        # Debug logging for price values (every 500 ticks)
        if self._tick_count % 500 == 0:
            logger.info(
                f"[{self._strategy_id}] Tick {self._tick_count}: price={price:.6f}, "
                f"in_position={self.in_position}, last_trade_grid_index={self.last_trade_grid_index}"
            )

        # Detect grid level crosses
        signal = None

        if self.last_price > 0:
            # Check if price crossed any grid level
            for i, level in enumerate(self.grid_levels):
                # Skip the grid level where we last traded (prevent immediate reversal)
                if i == self.last_trade_grid_index:
                    continue

                # Levels below reference: BUY when price drops TO them from above
                if level < self.reference_price:
                    cross_condition = self.last_price > level and price <= level
                    if cross_condition:
                        logger.info(
                            f"[{self._strategy_id}] BUY check at level {level:.6f}: "
                            f"last_price={self.last_price:.6f}, price={price:.6f}, "
                            f"cross_cond={cross_condition}, in_pos={self.in_position}"
                        )
                    if cross_condition and not self.in_position:
                        signal = Signal(
                            strategy_id=self._strategy_id,
                            symbol=tick.symbol,
                            signal_type=SignalType.BUY,
                            price=tick.price,
                            confidence=0.8,
                            metadata={
                                "grid_level": level,
                                "grid_index": i,
                                "reference_price": self.reference_price,
                                "price_crossed_from": "above",
                            },
                        )
                        self.in_position = True
                        self.current_grid_index = i
                        self.last_trade_grid_index = i
                        logger.info(f"[{self._strategy_id}] BUY signal at grid level {level}")
                        break

                # Levels above reference: SELL when price rises TO them from below
                elif level > self.reference_price:
                    cross_condition = self.last_price < level and price >= level
                    if cross_condition:
                        logger.info(
                            f"[{self._strategy_id}] SELL check at level {level:.6f}: "
                            f"last_price={self.last_price:.6f}, price={price:.6f}, "
                            f"cross_cond={cross_condition}, in_pos={self.in_position}"
                        )
                    if cross_condition and self.in_position:
                        signal = Signal(
                            strategy_id=self._strategy_id,
                            symbol=tick.symbol,
                            signal_type=SignalType.SELL,
                            price=tick.price,
                            confidence=0.8,
                            metadata={
                                "grid_level": level,
                                "grid_index": i,
                                "reference_price": self.reference_price,
                                "price_crossed_from": "below",
                            },
                        )
                        self.in_position = False
                        self.current_grid_index = i
                        self.last_trade_grid_index = i
                        logger.info(f"[{self._strategy_id}] SELL signal at grid level {level}")
                        break

        self.last_price = price
        return signal

    def _calculate_grid_levels(self) -> None:
        """Calculate grid price levels around reference price."""
        if self.reference_price is None:
            return

        spacing = self.reference_price * (self.grid_spacing_pct / 100.0)

        levels = []
        # Grid levels below reference (for buying)
        for i in range(1, self.grid_size + 1):
            levels.append(self.reference_price - (spacing * i))

        # Grid levels above reference (for taking profit)
        for i in range(1, self.grid_size + 1):
            levels.append(self.reference_price + (spacing * i))

        self.grid_levels = sorted(levels)
        logger.info(f"[{self._strategy_id}] Calculated {len(self.grid_levels)} grid levels")
        logger.debug(f"[{self._strategy_id}] Grid spacing: {spacing}, levels: {self.grid_levels}")

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update(
            {
                "reference_price": self.reference_price,
                "grid_levels_count": len(self.grid_levels),
                "current_grid_index": self.current_grid_index,
                "in_position": self.in_position,
                "last_price": self.last_price,
                "last_trade_grid_index": self.last_trade_grid_index,
            }
        )
        return stats
