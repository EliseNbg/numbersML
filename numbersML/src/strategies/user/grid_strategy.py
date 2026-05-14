"""
Grid Trading Strategy.

This strategy implements a grid trading approach that profits from
sideways/oscillating markets by buying at lower grid levels and selling
at higher grid levels.

Grid Structure:
    - N levels below reference_price (buy zones)
    - N levels above reference_price (take-profit zones)
    - Levels are evenly spaced by grid_spacing_pct of reference_price

Signal Logic:
    - BUY:  price crosses below a buy-zone level (no current position needed)
    - SELL: price crosses above any grid level above the current buy level

Position Management:
    - The backtest engine handles actual position opening/closing and enforces:
      - Only 1 position per symbol at a time (BUY ignored if position exists)
      - Stop-loss and take-profit execution
    - This strategy uses on_position_closed() callback to detect external closures
      so it can properly reset and re-enter the grid after stop-loss events
    - After a stop-loss, the strategy resets and buys at the next appropriate level

Key fixes vs original implementation:
    1. Uses on_position_closed() callback instead of in_position flag for
       position tracking. The old in_position flag desynced from the engine
       which closes positions via stop_loss internally without telling the strategy.
    2. Removed last_trade_grid_index which permanently blocked grid levels
       from being reused in future cycles.
    3. Sell triggers at ANY level above the buy level, not just levels above
       reference_price. This enables smaller, more frequent profits.

Configuration:
    - grid_size: Number of levels on each side of reference (default: 5)
    - grid_spacing_pct: Vertical spacing between levels as % of reference (default: 1.0)
    - risk.max_position_size_pct: Position size as % of balance (default: 10%)
    - risk.stop_loss_pct: Stop loss as % below entry (0 = disabled)
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class GridTradingStrategy(Strategy):
    """Grid trading strategy with proper lifecycle management.

    The strategy buys when price drops to grid levels below the reference price
    and sells when price rises back to the next available grid level. It is
    designed to profit from range-bound/oscillating market conditions.

    State:
        - reference_price: Center price for grid (set on first tick)
        - grid_levels: Sorted list of all grid price levels
                        (buy levels 0..N-1 below ref, sell levels N..2N-1 above ref)
        - last_price: Previous tick price (for cross detection)
        - grid_size: Number of levels each side of reference
        - grid_spacing_pct: Level spacing as percentage of reference
        - _buy_index: Grid index where current position was opened (-1 if flat)
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        # Grid parameters (loaded from config on first tick)
        self.reference_price: float | None = None
        self.grid_levels: list[float] = []
        self.last_price: float = 0.0
        self.grid_size: int = 5
        self.grid_spacing_pct: float = 1.0

        # Position tracking: index of the grid level where we are currently long
        # -1 means flat (no position). Set on BUY, reset to -1 on SELL or
        # when the engine closes the position externally (stop-loss/take-profit).
        self._buy_index: int = -1

        # Tick counter for periodic debug logging
        self._tick_count: int = 0

        logger.info(f"GridTradingStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate grid trading signals.

        BUY  when price crosses down through a buy-zone level.
        SELL when price rises through any grid level above our current buy level.

        Args:
            tick: Enriched tick data

        Returns:
            Signal if a grid level was crossed, None otherwise
        """
        price = float(tick.price)

        # ------------------------------------------------------------------
        # Initialization: set reference price and calculate grid on first tick
        # ------------------------------------------------------------------
        if self.reference_price is None:
            self._initialize_grid(price)
            self.last_price = price
            return None

        self._tick_count += 1
        signal = None

        # ------------------------------------------------------------------
        # Detect grid level crossings
        # ------------------------------------------------------------------
        if self.last_price > 0:
            signal = self._detect_crossing(price, tick)

        # ------------------------------------------------------------------
        # Periodic debugging output
        # ------------------------------------------------------------------
        if self._tick_count % 500 == 0:
            pos = (
                f"grid_idx={self._buy_index} "
                f"level={self.grid_levels[self._buy_index]:.6f}"
                if self._buy_index >= 0
                else "flat"
            )
            logger.info(
                f"[{self._strategy_id}] Tick {self._tick_count}: "
                f"price={price:.8f}, {pos}"
            )

        self.last_price = price
        return signal

    def _initialize_grid(self, first_price: float) -> None:
        """Initialize grid parameters from config and first tick price."""
        self.reference_price = first_price
        self.grid_size = self.get_config("grid_size", 5)
        self.grid_spacing_pct = self.get_config("grid_spacing_pct", 1.0)
        self._calculate_grid_levels()

        logger.info(
            f"[{self._strategy_id}] Grid initialized BEFORE config apply: "
            f"ref_price={self.reference_price}, grid_size={self.grid_size}, "
            f"spacing_pct={self.grid_spacing_pct}"
        )
        logger.info(
            f"[{self._strategy_id}] Grid levels AFTER config apply: "
            f"{[round(l, 6) for l in self.grid_levels]}"
        )

    # ----------------------------------------------------------------------
    # Core signal detection
    # ----------------------------------------------------------------------

    def _detect_crossing(self, price: float, tick: EnrichedTick) -> Signal | None:
        """Scan all grid levels for upward or downward crossings.

        BUY  triggers when price drops BELOW a buy-zone level (below reference)
             and we are currently flat.

        SELL triggers when price rises to ANY grid level above our current buy
             index, confirming we have an active position to close.

        Returns first matched signal to avoid multiple signals per tick.
        """
        last = self.last_price
        is_buy_eligible = self._buy_index == -1  # No active position
        is_sell_eligible = self._buy_index != -1  # Have active position to close

        for i, level in enumerate(self.grid_levels):
            # --------------------------------------------------------------
            # BUY signal: price drops TO a buy-zone level from above
            # --------------------------------------------------------------
            if level < self.reference_price and is_buy_eligible:
                if last > level and price <= level:
                    return self._signal_buy(tick, level, i)

            # --------------------------------------------------------------
            # SELL signal: price rises TO a grid level above where we bought
            #
            # This is the key fix: sell at the NEXT level above our entry,
            # NOT just levels above reference_price. This allows smaller
            # profit targets and enables the grid to actually cycle.
            # --------------------------------------------------------------
            if is_sell_eligible and i > self._buy_index:
                if last < level and price >= level:
                    return self._signal_sell(tick, level, i)

        return None

    def _signal_buy(self, tick: EnrichedTick, level: float, grid_index: int) -> Signal:
        """Generate a BUY signal and update internal state."""
        logger.info(
            f"[{self._strategy_id}] BUY check at level {level:.6f}: "
            f"last={self.last_price:.6f}, price={float(tick.price):.6f}, "
            f"cross_cond=True, flat=True"
        )
        self._buy_index = grid_index
        logger.info(f"[{self._strategy_id}] BUY signal at grid level {level}")

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.BUY,
            price=tick.price,
            confidence=0.8,
            metadata={
                "grid_level": level,
                "grid_index": grid_index,
                "reference_price": self.reference_price,
                "price_crossed_from": "above",
            },
        )

    def _signal_sell(self, tick: EnrichedTick, level: float, grid_index: int) -> Signal:
        """Generate a SELL signal and update internal state."""
        orig_buy_idx = self._buy_index
        self._buy_index = -1
        logger.info(
            f"[{self._strategy_id}] SELL check at level {level:.6f}: "
            f"last={self.last_price:.6f}, price={float(tick.price):.6f}, "
            f"cross_cond=True, in_pos=True"
        )
        logger.info(
            f"[{self._strategy_id}] SELL signal at grid level {level} "
            f"(bought at grid index {orig_buy_idx} = "
            f"{self.grid_levels[orig_buy_idx]:.6f})"
        )

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.SELL,
            price=tick.price,
            confidence=0.8,
            metadata={
                "grid_level": level,
                "grid_index": grid_index,
                "buy_grid_index": orig_buy_idx,
                "reference_price": self.reference_price,
                "price_crossed_from": "below",
            },
        )

    # ----------------------------------------------------------------------
    # External position lifecycle callbacks
    # ----------------------------------------------------------------------

    def on_position_closed(self, symbol: str, price: Decimal, exit_reason: str) -> None:
        """Handle position closure by the backtest engine.

        Called when the engine closes our position externally:
        - stop-loss triggered
        - take-profit triggered
        - end of backtest

        Without this callback, the strategy's _buy_index would remain set
        after a stop-loss, permanently blocking new BUY signals. This was
        the root cause of the grid strategy getting stuck after the first
        stop-loss event.

        Args:
            symbol: Trading pair symbol
            price: Price at which position was closed
            exit_reason: Reason for closure (stop_loss, take_profit, etc.)
        """
        if self._buy_index != -1:
            logger.info(
                f"[{self._strategy_id}] Position externally closed: "
                f"reason={exit_reason}, price={price:.8f}, "
                f"was at grid_index={self._buy_index} "
                f"(level={self.grid_levels[self._buy_index]:.6f})"
            )
            self._buy_index = -1

    # ----------------------------------------------------------------------
    # Grid calculation
    # ----------------------------------------------------------------------

    def _calculate_grid_levels(self) -> None:
        """Calculate evenly-spaced grid levels around the reference price.

        Structure:
            - grid_size levels below reference_price (buy zone, indices 0..N-1)
            - grid_size levels above reference_price (take-profit zone, indices N..2N-1)
        """
        if self.reference_price is None:
            return

        spacing = self.reference_price * (self.grid_spacing_pct / 100.0)

        levels: list[float] = []
        # Buy levels below reference
        for i in range(1, self.grid_size + 1):
            levels.append(self.reference_price - (spacing * i))
        # Take-profit levels above reference
        for i in range(1, self.grid_size + 1):
            levels.append(self.reference_price + (spacing * i))

        self.grid_levels = sorted(levels)

        buy_levels = [l for l in self.grid_levels if l < self.reference_price]
        sell_levels = [l for l in self.grid_levels if l >= self.reference_price]
        logger.info(
            f"[{self._strategy_id}] Calculated {len(self.grid_levels)} grid levels, "
            f"spacing={spacing:.8f}"
        )
        logger.info(
            f"[{self._strategy_id}] Buy levels: {[round(l, 6) for l in buy_levels]}"
        )
        logger.info(
            f"[{self._strategy_id}] Sell levels: {[round(l, 6) for l in sell_levels]}"
        )

    # ----------------------------------------------------------------------
    # Statistics
    # ----------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom grid state in stats."""
        stats = super().get_stats()
        stats.update(
            {
                "reference_price": self.reference_price,
                "grid_levels_count": len(self.grid_levels),
                "in_position": self._buy_index != -1,
                "grid_index": self._buy_index,
                "last_price": self.last_price,
                "tick_count": self._tick_count,
            }
        )
        return stats
