"""SMA Cross Strategy (Golden Cross / Death Cross).

This strategy generates signals based on two Simple Moving Averages crossing:
- BUY when fast SMA crosses above slow SMA (Golden Cross)
- SELL when fast SMA crosses below slow SMA (Death Cross)

The strategy maintains:
- Last fast and slow SMA values
- Position state
"""

import logging
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class SMACrossStrategy(Strategy):
    """SMA crossover strategy with persistent state.

    State:
        - last_fast_sma: Last fast SMA value
        - last_slow_sma: Last slow SMA value
        - in_position: Whether we have an open position
        - cross_count: Number of crosses detected

    Configuration (accessed via self.get_config):
        - fast_period: Fast SMA period (default: 20)
        - slow_period: Slow SMA period (default: 50)
        - sma_indicator_prefix: Prefix for SMA indicator names (default: smaindicator)
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        # Persistent state
        self.last_fast_sma: float = 0.0
        self.last_slow_sma: float = 0.0
        self.in_position: bool = False
        self.cross_count: int = 0

        logger.info(f"SMACrossStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate SMA crossover signals.

        Args:
            tick: Enriched tick data with SMA indicators

        Returns:
            Signal if crossover detected, None otherwise
        """
        fast_period = self.get_config("fast_period", 20)
        slow_period = self.get_config("slow_period", 50)
        prefix = self.get_config("sma_indicator_prefix", "smaindicator")

        # Get SMA values from indicators
        # Assuming names like smaindicator_period20_sma
        fast_sma = tick.get_indicator(f"{prefix}_period{fast_period}_sma", None)
        slow_sma = tick.get_indicator(f"{prefix}_period{slow_period}_sma", None)

        if fast_sma is None or slow_sma is None:
            # Try alternative naming
            fast_sma = tick.get_indicator("sma_fast", self.last_fast_sma)
            slow_sma = tick.get_indicator("sma_slow", self.last_slow_sma)

        if fast_sma is None or slow_sma is None:
            return None

        # Detect crossover
        signal = None

        # Golden Cross: Fast SMA crosses above Slow SMA
        if (
            self.last_fast_sma <= self.last_slow_sma
            and fast_sma > slow_sma
            and not self.in_position
        ):
            self.in_position = True
            self.cross_count += 1
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=min(1.0, (fast_sma - slow_sma) / slow_sma),
                metadata={
                    "fast_sma": fast_sma,
                    "slow_sma": slow_sma,
                    "spread": fast_sma - slow_sma,
                    "crossover_type": "golden_cross",
                    "cross_count": self.cross_count,
                    "fast_period": fast_period,
                    "slow_period": slow_period,
                },
            )
            logger.info(
                f"[{self._strategy_id}] BUY signal: "
                f"Fast SMA={fast_sma:.2f} > Slow SMA={slow_sma:.2f} (Golden Cross)"
            )

        # Death Cross: Fast SMA crosses below Slow SMA
        elif self.last_fast_sma >= self.last_slow_sma and fast_sma < slow_sma and self.in_position:
            self.in_position = False
            self.cross_count += 1
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=min(1.0, (slow_sma - fast_sma) / slow_sma),
                metadata={
                    "fast_sma": fast_sma,
                    "slow_sma": slow_sma,
                    "spread": fast_sma - slow_sma,
                    "crossover_type": "death_cross",
                    "cross_count": self.cross_count,
                    "fast_period": fast_period,
                    "slow_period": slow_period,
                },
            )
            logger.info(
                f"[{self._strategy_id}] SELL signal: "
                f"Fast SMA={fast_sma:.2f} < Slow SMA={slow_sma:.2f} (Death Cross)"
            )

        # Update state
        self.last_fast_sma = fast_sma
        self.last_slow_sma = slow_sma

        return signal

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update(
            {
                "last_fast_sma": self.last_fast_sma,
                "last_slow_sma": self.last_slow_sma,
                "in_position": self.in_position,
                "cross_count": self.cross_count,
            }
        )
        return stats
