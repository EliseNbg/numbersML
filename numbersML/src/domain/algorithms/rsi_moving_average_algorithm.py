"""
RSI + Moving Average Algorithm.

Demonstrates:
- State management between ticks
- Indicator access from EnrichedTick
- ConfigurationSet access
- Signal generation with metadata
"""

import logging
from datetime import UTC, datetime
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

        # Extract indicators from tick (pre-calculated by enrichment service)
        rsi = tick.get_indicator("rsiindicator_period14_rsi", 50.0)
        sma = tick.get_indicator("smaindicator_period20_sma", float(tick.price))

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
            result = self._check_exit_conditions(tick, current_price, rsi)
            # Update price history and RSI history after check
            self._update_price_history(current_price)
            self._rsi_history.append(rsi)
            if len(self._rsi_history) > self._max_price_history:
                self._rsi_history.pop(0)
            return result

        # Update history before entry check
        self._update_price_history(current_price)
        self._rsi_history.append(rsi)
        if len(self._rsi_history) > self._max_price_history:
            self._rsi_history.pop(0)

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
            # Additional filter: RSI rising (momentum) - check last 3 before current
            if len(self._rsi_history) >= 4:
                # Get the 3 RSI values before current tick
                prev_rsi_values = self._rsi_history[-4:-1]  # Exclude current (last)
                if len(prev_rsi_values) >= 3:
                    # Check if RSI was rising
                    if all(
                        prev_rsi_values[i] <= prev_rsi_values[i + 1]
                        for i in range(len(prev_rsi_values) - 1)
                    ):
                        # Current RSI is still very low (strong oversold)
                        if rsi < min_rsi:
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
        pnl_pct: float = float((price - entry_price) / entry_price * 100)

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
            "entry_time": datetime.now(UTC),
            "entry_rsi": rsi,
        }

        self._last_signal_time = datetime.now(UTC)

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

        self._last_signal_time = datetime.now(UTC)

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
                "entry_price": (self._position["entry_price"] if self._position else None),
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
        """
        Set configuration value (runtime override).

        Args:
            key: Configuration key
            value: Value to set
        """
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
            "last_signal_time": (
                self._last_signal_time.isoformat() if self._last_signal_time else None
            ),
        }
