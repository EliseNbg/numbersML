"""MACD Cross Strategy.

This strategy generates signals based on MACD line crossing the signal line:
- BUY when MACD crosses above signal line (bullish crossover)
- SELL when MACD crosses below signal line (bearish crossover)

The strategy maintains:
- Last MACD and signal values to detect crosses
- State to track position (in position or not)
"""

import logging
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class MACDCrossStrategy(Strategy):
    """MACD crossover strategy with persistent state.

    State:
        - last_macd: Last MACD line value
        - last_signal: Last signal line value
        - last_histogram: Last MACD histogram value
        - in_position: Whether we have an open position
        - cross_count: Number of crosses detected

    Configuration (accessed via self.get_config):
        - macd_indicator_name: Name of MACD indicator (default: macdindicator)
        - fast_period: MACD fast EMA period (default: 12)
        - slow_period: MACD slow EMA period (default: 26)
        - signal_period: Signal line period (default: 9)
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        # Persistent state
        self.last_macd: float = 0.0
        self.last_signal: float = 0.0
        self.last_histogram: float = 0.0
        self.in_position: bool = False
        self.cross_count: int = 0

        logger.info(f"MACDCrossStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate MACD crossover signals.

        Args:
            tick: Enriched tick data with MACD indicators

        Returns:
            Signal if crossover detected, None otherwise
        """
        # Get MACD indicator values from tick
        macd_name = self.get_config("macd_indicator_name", "macdindicator")

        # Try to get MACD values from indicators
        # Assuming indicator names like: macdindicator_macd, macdindicator_signal, macdindicator_histogram
        macd_value = tick.get_indicator(f"{macd_name}_macd", None)
        signal_value = tick.get_indicator(f"{macd_name}_signal", None)

        if macd_value is None or signal_value is None:
            # Try alternative naming
            macd_value = tick.get_indicator("macd", self.last_macd)
            signal_value = tick.get_indicator("macd_signal", self.last_signal)

        if macd_value is None or signal_value is None:
            return None

        # Detect crossover
        signal = None

        # Bullish crossover: MACD crosses above signal line
        if (
            self.last_macd <= self.last_signal
            and macd_value > signal_value
            and not self.in_position
        ):
            self.in_position = True
            self.cross_count += 1
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=min(1.0, abs(macd_value - signal_value) / 10.0),
                metadata={
                    "macd": macd_value,
                    "signal": signal_value,
                    "histogram": macd_value - signal_value,
                    "crossover_type": "bullish",
                    "cross_count": self.cross_count,
                },
            )
            logger.info(
                f"[{self._strategy_id}] BUY signal: "
                f"MACD={macd_value:.4f} > Signal={signal_value:.4f}"
            )

        # Bearish crossover: MACD crosses below signal line
        elif self.last_macd >= self.last_signal and macd_value < signal_value and self.in_position:
            self.in_position = False
            self.cross_count += 1
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=min(1.0, abs(macd_value - signal_value) / 10.0),
                metadata={
                    "macd": macd_value,
                    "signal": signal_value,
                    "histogram": macd_value - signal_value,
                    "crossover_type": "bearish",
                    "cross_count": self.cross_count,
                },
            )
            logger.info(
                f"[{self._strategy_id}] SELL signal: "
                f"MACD={macd_value:.4f} < Signal={signal_value:.4f}"
            )

        # Update state
        self.last_macd = macd_value
        self.last_signal = signal_value
        self.last_histogram = macd_value - signal_value

        return signal

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update(
            {
                "last_macd": self.last_macd,
                "last_signal": self.last_signal,
                "last_histogram": self.last_histogram,
                "in_position": self.in_position,
                "cross_count": self.cross_count,
            }
        )
        return stats
