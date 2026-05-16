"""Example RSI Strategy for testing class-based strategy loading."""

from decimal import Decimal
from typing import Any
import logging

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class ExampleRSIStrategy(Strategy):
    """Example RSI strategy for testing.

    Configuration (accessed via self.get_config):
        - oversold_threshold: RSI oversold level (default: 30)
        - overbought_threshold: RSI overbought level (default: 70)
        - rsi_indicator_name: Name of RSI indicator in tick data

    State:
        - tick_count: Number of ticks processed
        - last_rsi: Last RSI value processed
        - position_open: Whether position is currently open
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)
        # Initialize state attributes
        self.tick_count = 0
        self.last_rsi = None
        self.position_open = False
        logger.info(f"ExampleRSIStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate RSI-based signals.

        Args:
            tick: Enriched tick data with RSI indicator

        Returns:
            Signal if RSI crosses thresholds, None otherwise
        """
        # Update state
        self.tick_count += 1

        oversold = self.get_config("oversold_threshold", 30)
        overbought = self.get_config("overbought_threshold", 70)
        rsi_name = self.get_config("rsi_indicator_name", "rsiindicator_period14_rsi")

        # Get RSI value from indicators
        rsi_value = tick.get_indicator(rsi_name, None)

        if rsi_value is None:
            return None

        # Update last RSI
        self.last_rsi = rsi_value

        signal = None

        # RSI crosses below oversold -> BUY signal
        if rsi_value < oversold and not self.position_open:
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=min(1.0, (oversold - rsi_value) / oversold),
                metadata={
                    "rsi_value": rsi_value,
                    "threshold": oversold,
                    "signal_reason": "rsi_oversold",
                },
            )
            self.position_open = True
            logger.info(
                f"[{self._strategy_id}] BUY signal: RSI={rsi_value:.2f} < {oversold} (oversold)"
            )

        # RSI crosses above overbought -> SELL signal
        elif rsi_value > overbought and self.position_open:
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=min(1.0, (rsi_value - overbought) / (100 - overbought)),
                metadata={
                    "rsi_value": rsi_value,
                    "threshold": overbought,
                    "signal_reason": "rsi_overbought",
                },
            )
            self.position_open = False
            logger.info(
                f"[{self._strategy_id}] SELL signal: RSI={rsi_value:.2f} > {overbought} (overbought)"
            )

        return signal

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update(
            {
                "strategy_type": "example_rsi",
                "tick_count": self.tick_count,
                "last_rsi": self.last_rsi,
                "position_open": self.position_open,
            }
        )
        return stats

    def on_position_closed(
        self,
        symbol: str,
        price: Decimal,
        exit_reason: str,
        grid_index: int | None = None,
    ) -> None:
        """Handle position closure."""
        self.position_open = False
