"""
Grid Trading Algorithm Implementation.

Places buy orders at regular intervals below current price,
sell orders above current price.
Profits from price oscillations in a range-bound market.

Follows Phase 3 Algorithm base class pattern.
"""

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.domain.strategies.base import (
    Algorithm,
    EnrichedTick,
    Signal,
    SignalType,
    TimeFrame,
)

logger = logging.getLogger(__name__)


class GridAlgorithm(Algorithm):
    """
    Grid trading strategy.

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
        >>> from uuid import uuid4
        >>> from src.domain.strategies.base import TimeFrame
        >>> strategy = GridAlgorithm(
        ...     strategy_id=uuid4(),
        ...     symbols=["TEST/USDT"],
        ...     time_frame=TimeFrame.TICK,
        ... )
        >>> signal = strategy.on_tick(tick)
    """

    def __init__(
        self,
        strategy_id: UUID,
        symbols: list[str],
        time_frame: TimeFrame = TimeFrame.TICK,
    ) -> None:
        """
        Initialize GridAlgorithm.

        Args:
            strategy_id: Unique strategy UUID
            symbols: List of symbols to trade
            time_frame: Time frame (not used for grid)
        """
        super().__init__(strategy_id=strategy_id, symbols=symbols, time_frame=time_frame)

        # Grid state
        self._grid_levels: list[Decimal] = []
        self._grid_orders: dict[str, dict[str, Any]] = {}  # order_id → order info
        self._base_price: Decimal | None = None
        self._highest_price: Decimal | None = None
        self._lowest_price: Decimal | None = None
        self._positions: dict[str, dict[str, Any]] = {}
        self._config: dict[str, Any] = {}

        logger.info(f"GridAlgorithm {strategy_id} initialized for {symbols}")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
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
        if self._highest_price is None or current_price > self._highest_price:
            self._highest_price = current_price
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

    def _check_buy_signal(self, current_price: Decimal, tick: EnrichedTick) -> Signal | None:
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
                strategy_id=str(self._strategy_id),
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=current_price,
                timestamp=tick.time,
                confidence=0.8,
                metadata={
                    "grid_level": float(nearest_buy),
                    "distance_pct": float(distance_pct),
                    "reason": "price_near_buy_grid",
                    "quantity": float(quantity),
                },
            )

        return None

    def _check_sell_signal(self, current_price: Decimal, tick: EnrichedTick) -> Signal | None:
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
        profit_pct = (current_price - position["entry_price"]) / position["entry_price"] * 100

        # Get grid spacing as take profit target
        take_profit_pct = Decimal(str(self.get_config("take_profit_pct", 0.5)))

        # Sell if we hit take profit target
        if profit_pct >= take_profit_pct:
            return Signal(
                strategy_id=str(self._strategy_id),
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                timestamp=tick.time,
                confidence=0.9,
                metadata={
                    "entry_price": float(position["entry_price"]),
                    "profit_pct": float(profit_pct),
                    "reason": "take_profit",
                },
            )

        # Check stop loss
        stop_loss_pct = Decimal(str(self.get_config("stop_loss_pct", 2.0)))

        if profit_pct <= -stop_loss_pct:
            return Signal(
                strategy_id=str(self._strategy_id),
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                timestamp=tick.time,
                confidence=1.0,
                metadata={
                    "entry_price": float(position["entry_price"]),
                    "loss_pct": float(profit_pct),
                    "reason": "stop_loss",
                },
            )

        return None

    def get_grid_levels(self) -> list[Decimal]:
        """Get current grid levels."""
        return self._grid_levels.copy()

    def get_grid_stats(self) -> dict[str, Any]:
        """Get grid statistics."""
        return {
            "base_price": float(self._base_price) if self._base_price else None,
            "grid_levels": [float(lvl) for lvl in self._grid_levels],
            "num_levels": len(self._grid_levels),
            "highest_price": float(self._highest_price) if self._highest_price else None,
            "lowest_price": float(self._lowest_price) if self._lowest_price else None,
            "open_positions": len(self._positions),
        }

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self._config[key] = value

    def open_position(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """Open a position (internal state tracking)."""
        self._positions[symbol] = {
            "side": side,
            "quantity": quantity,
            "entry_price": price,
        }

    def close_position(self, symbol: str) -> None:
        """Close a position (internal state tracking)."""
        self._positions.pop(symbol, None)
