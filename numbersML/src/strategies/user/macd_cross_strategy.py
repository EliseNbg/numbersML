"""MACD Cross Strategy.

This strategy generates signals based on MACD line crossing the signal line:
- BUY when MACD crosses above signal line (bullish crossover)
- SELL when MACD crosses below signal line (bearish crossover)

The strategy maintains:
- Last MACD and signal values to detect crosses
- State to track position (in position or not)
- Cross count for statistics

Configuration:
    - macd_indicator_name: Name of MACD indicator (default: macdindicator)
    - fast_period: MACD fast EMA period (default: 12)
    - slow_period: MACD slow EMA period (default: 26)
    - signal_period: Signal line period (default: 9)
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class MACDCrossStrategy(Strategy):
    """MACD crossover strategy with persistent state."""

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
        self.macd_indicator_name: str = "macdindicator"
        self.fast_period: int = 12
        self.slow_period: int = 26
        self.signal_period: int = 9

        self._tick_count: int = 0
        self._initialized: bool = False

        logger.info(f"MACDCrossStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate MACD crossover signals.

        Args:
            tick: Enriched tick data with MACD indicators

        Returns:
            Signal if crossover detected, None otherwise
        """
        if not self._initialized:
            self._initialize_macd()
            self._initialized = True

        self._tick_count += 1

        macd_value, signal_value, histogram_value = self._get_macd_values(tick)

        if macd_value is None or signal_value is None:
            return None

        signal = self._detect_crossover(macd_value, signal_value, tick)

        if self._tick_count % 500 == 0:
            logger.info(
                f"{tick.time} Tick {self._tick_count}: "
                f"macd={macd_value:.4f}, signal={signal_value:.4f}, "
                f"histogram={histogram_value:.4f}, "
                f"in_position={self.in_position}, cross_count={self.cross_count}"
            )

        self.last_macd = macd_value
        self.last_signal = signal_value
        self.last_histogram = histogram_value

        return signal

    def _initialize_macd(self) -> None:
        """Initialize MACD strategy configuration."""
        self.macd_indicator_name = self.get_config("macd_indicator_name", "macdindicator")
        self.fast_period = self.get_config("fast_period", 12)
        self.slow_period = self.get_config("slow_period", 26)
        self.signal_period = self.get_config("signal_period", 9)

        logger.info(
            f"[{self._strategy_id}] MACD: name={self.macd_indicator_name}, "
            f"fast={self.fast_period}, slow={self.slow_period}, "
            f"signal={self.signal_period}"
        )

    def _get_macd_values(self, tick: EnrichedTick) -> tuple[float | None, float | None, float | None]:
        """Extract MACD, signal, and histogram values from tick.

        Args:
            tick: Enriched tick data with indicators

        Returns:
            Tuple of (macd_value, signal_value, histogram_value) or (None, None, None) if not available
        """
        macd_value = tick.get_indicator(f"{self.macd_indicator_name}_macd", None)
        signal_value = tick.get_indicator(f"{self.macd_indicator_name}_signal", None)
        histogram_value = tick.get_indicator(f"{self.macd_indicator_name}_histogram", None)

        if macd_value is None or signal_value is None:
            macd_value = tick.get_indicator("macd", None)
            signal_value = tick.get_indicator("macd_signal", None)
            histogram_value = tick.get_indicator("macd_histogram", None)

        if macd_value is None or signal_value is None:
            return None, None, None

        if histogram_value is None:
            histogram_value = macd_value - signal_value

        return macd_value, signal_value, histogram_value

    def _detect_crossover(
        self,
        macd_value: float,
        signal_value: float,
        tick: EnrichedTick,
    ) -> Signal | None:
        """Detect MACD crossover and generate signal.

        Args:
            macd_value: Current MACD line value
            signal_value: Current signal line value
            tick: Enriched tick data

        Returns:
            Signal if crossover detected, None otherwise
        """
        signal = None

        # Bullish crossover: MACD crosses above signal line
        if (
            self.last_macd <= self.last_signal
            and macd_value > signal_value
            and not self.in_position
        ):
            signal = self._signal_buy(tick, macd_value, signal_value)

        # Bearish crossover: MACD crosses below signal line
        elif self.last_macd >= self.last_signal and macd_value < signal_value and self.in_position:
            signal = self._signal_sell(tick, macd_value, signal_value)

        return signal

    def _signal_buy(
        self,
        tick: EnrichedTick,
        macd_value: float,
        signal_value: float,
    ) -> Signal:
        """Generate BUY signal.

        Args:
            tick: Enriched tick data
            macd_value: Current MACD line value
            signal_value: Current signal line value

        Returns:
            BUY signal
        """
        self.in_position = True
        self.cross_count += 1

        logger.info(
            f"[{self._strategy_id}] BUY signal: "
            f"MACD={macd_value:.4f} > Signal={signal_value:.4f}, "
            f"histogram={macd_value - signal_value:.4f}"
        )

        return Signal(
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

    def _signal_sell(
        self,
        tick: EnrichedTick,
        macd_value: float,
        signal_value: float,
    ) -> Signal:
        """Generate SELL signal.

        Args:
            tick: Enriched tick data
            macd_value: Current MACD line value
            signal_value: Current signal line value

        Returns:
            SELL signal
        """
        self.in_position = False
        self.cross_count += 1

        logger.info(
            f"[{self._strategy_id}] SELL signal: "
            f"MACD={macd_value:.4f} < Signal={signal_value:.4f}, "
            f"histogram={macd_value - signal_value:.4f}"
        )

        return Signal(
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

    def on_position_closed(
        self,
        symbol: str,
        price: Decimal,
        exit_reason: str,
        grid_index: int | None = None,
    ) -> None:
        """Called when position is closed externally.

        Args:
            symbol: Trading pair symbol
            price: Price at which position was closed
            exit_reason: Reason for closure
            grid_index: Not used for MACD strategy
        """
        logger.info(
            f"[{self._strategy_id}] Position closed for {symbol}: "
            f"reason={exit_reason}, price={price:.8f}"
        )
        self.in_position = False

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
                "tick_count": self._tick_count,
                "macd_indicator_name": self.macd_indicator_name,
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "signal_period": self.signal_period,
            }
        )
        return stats
