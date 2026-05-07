"""
Simple Grid Algorithm - Easy to understand and modify.

Strategy:
    - Places buy orders below current price
    - Places sell orders above current price
    - Profits from price oscillations

State:
    - self._grid_levels: Current grid price levels
    - self._base_price: Base price for grid calculation
    - self._position: Current open position (None if no position)
"""

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.domain.algorithms.base import (
    Algorithm,
    EnrichedTick,
    Signal,
    SignalType,
    TimeFrame,
)

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

    Example:
        >>> from uuid import uuid4
        >>> from src.domain.algorithms.base import TimeFrame
        >>> algo = SimpleGridAlgorithm(
        ...     algorithm_id=uuid4(),
        ...     symbols=["BTC/USDT"],
        ...     time_frame=TimeFrame.TICK,
        ... )
        >>> signal = algo.on_tick(tick)
    """

    def __init__(
        self,
        algorithm_id: UUID,
        symbols: list[str],
        time_frame: TimeFrame = TimeFrame.TICK,
    ) -> None:
        """
        Initialize with grid state.

        Args:
            algorithm_id: Unique algorithm UUID
            symbols: List of symbols to trade
            time_frame: Algorithm time frame
        """
        super().__init__(algorithm_id=algorithm_id, symbols=symbols, time_frame=time_frame)

        # State - persists between ticks
        self._grid_levels: list[Decimal] = []
        self._base_price: Decimal | None = None
        self._position: dict[str, Any] | None = None
        self._config: dict[str, Any] = {}

        logger.info(f"SimpleGridAlgorithm {algorithm_id} initialized for {symbols}")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """
        Process tick - main algorithm logic.

        Args:
            tick: Enriched tick data with indicators

        Returns:
            Signal if conditions met, None otherwise
        """
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
        """
        Create grid levels around base price.

        Args:
            base_price: Current price to center grid around
        """
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
        """
        Check if price is near a buy grid level.

        Args:
            tick: Enriched tick data
            price: Current price

        Returns:
            Buy Signal if condition met, None otherwise
        """
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
        """
        Check if we should sell (take profit or stop loss).

        Args:
            tick: Enriched tick data
            price: Current price

        Returns:
            Sell Signal if conditions met, None otherwise
        """
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
        """
        Get configuration value from ConfigurationSet.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self._config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """
        Set configuration value (runtime override).

        Args:
            key: Configuration key
            value: Value to set
        """
        self._config[key] = value

    def get_grid_levels(self) -> list[Decimal]:
        """
        Get current grid levels.

        Returns:
            List of grid price levels
        """
        return self._grid_levels.copy()

    def get_algorithm_state(self) -> dict[str, Any]:
        """
        Get current algorithm state for monitoring.

        Returns:
            Dictionary with current state
        """
        return {
            "has_position": self._position is not None,
            "position": self._position,
            "grid_levels_count": len(self._grid_levels),
            "base_price": float(self._base_price) if self._base_price else None,
        }
