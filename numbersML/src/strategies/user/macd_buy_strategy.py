"""MACD Buy Strategy.

This strategy generates BUY-only signals based on MACD line crossing above the signal line,
with an additional constraint that the MACD value must be below a configured bottom border.

Buy conditions:
- MACD crosses above signal line (bullish crossover)
- Current MACD value < bottom_border_macd_to_buy (ensures buying at dips)

No SELL signals are generated. The strategy includes expected_profit_price in signal metadata,
which is handled externally by the market or take-profit mechanism.

Configuration:
    - macd_indicator_name: Name of MACD indicator (default: macdindicator)
    - fast_period: MACD fast EMA period (default: 12)
    - slow_period: MACD slow EMA period (default: 26)
    - signal_period: Signal line period (default: 9)
    - min_relative_threshold: Minimum histogram/price ratio to trigger signal (default: 0.001)
    - bottom_border_macd_to_buy: Maximum MACD value to allow BUY signals (default: 0.0)
    - grid_quantity_absolute: USDC amount to buy per signal (default: 100.0)
    - grid_profit_pct: Profit target percentage for take-profit (default: 0.85)
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class MACDBuyStrategy(Strategy):
    """MACD crossover BUY-only strategy with bottom border constraint."""

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        self.last_macd: float = 0.0
        self.last_signal: float = 0.0
        self.last_histogram: float = 0.0
        self.cross_count: int = 0
        self.macd_indicator_name: str = "macdindicator"
        self.fast_period: int = 12
        self.slow_period: int = 26
        self.signal_period: int = 9
        self.min_relative_threshold: float = 0.001
        self.bottom_border_macd_to_buy: float = 0.0
        self.grid_quantity_absolute: float = 100.0
        self.grid_profit_pct: float = 0.85

        self._tick_count: int = 0
        self._initialized: bool = False

        logger.info(f"MACDBuyStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate MACD crossover BUY signals.

        Args:
            tick: Enriched tick data with MACD indicators

        Returns:
            BUY signal if crossover detected below bottom border, None otherwise
        """
        if not self._initialized:
            self._initialize_macd(tick)
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
                f"histogram={histogram_value:.4f}, cross_count={self.cross_count}"
            )

        self.last_macd = macd_value
        self.last_signal = signal_value
        self.last_histogram = histogram_value

        return signal

    def _initialize_macd(self, tick: EnrichedTick) -> None:
        """Initialize MACD strategy configuration.

        Args:
            tick: First tick used to log available indicators
        """
        self.macd_indicator_name = self.get_config("macd_indicator_name", "macdindicator")
        self.fast_period = self.get_config("fast_period", 12)
        self.slow_period = self.get_config("slow_period", 26)
        self.signal_period = self.get_config("signal_period", 9)
        self.min_relative_threshold = self.get_config("min_relative_threshold", 0.001)
        self.bottom_border_macd_to_buy = self.get_config("bottom_border_macd_to_buy", 0.0)
        self.grid_quantity_absolute = self.get_config("grid_quantity_absolute", 100.0)
        self.grid_profit_pct = self.get_config("grid_profit_pct", 0.85)

        logger.info(
            f"[{self._strategy_id}] MACD: name={self.macd_indicator_name}, "
            f"fast={self.fast_period}, slow={self.slow_period}, "
            f"signal={self.signal_period}, min_relative_threshold={self.min_relative_threshold}, "
            f"bottom_border={self.bottom_border_macd_to_buy}"
        )
        logger.info(
            f"[{self._strategy_id}] Trade: quantity={self.grid_quantity_absolute} USDC, "
            f"profit_target={self.grid_profit_pct}%"
        )

        logger.info(f"[{self._strategy_id}] Config: {self._config}")
        logger.info(f"[{self._strategy_id}] Indicators: {tick.indicators}")

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

        if macd_value is not None and signal_value is not None:
            if histogram_value is None:
                histogram_value = macd_value - signal_value
            return macd_value, signal_value, histogram_value

        macd_value = tick.get_indicator("macd", None)
        signal_value = tick.get_indicator("macd_signal", None)
        histogram_value = tick.get_indicator("macd_histogram", None)

        if macd_value is not None and signal_value is not None:
            if histogram_value is None:
                histogram_value = macd_value - signal_value
            return macd_value, signal_value, histogram_value

        macd_value, signal_value, histogram_value = self._autodetect_macd(tick.indicators)

        return macd_value, signal_value, histogram_value

    def _autodetect_macd(
        self, indicators: dict[str, float]
    ) -> tuple[float | None, float | None, float | None]:
        """Auto-detect MACD indicators from available keys.

        Looks for keys ending with _macd, _signal, _histogram that contain
        'macd' in the base name.
        """
        macd_key = None
        signal_key = None
        histogram_key = None

        for key in indicators:
            key_lower = key.lower()
            if "macd" not in key_lower:
                continue

            if key_lower.endswith("_macd"):
                macd_key = key
            elif key_lower.endswith("_signal"):
                signal_key = key
            elif key_lower.endswith("_histogram"):
                histogram_key = key

        macd_value = indicators.get(macd_key) if macd_key else None
        signal_value = indicators.get(signal_key) if signal_key else None
        histogram_value = indicators.get(histogram_key) if histogram_key else None

        if macd_value is not None and signal_value is not None:
            if histogram_value is None:
                histogram_value = macd_value - signal_value
            return macd_value, signal_value, histogram_value

        return None, None, None

    def _detect_crossover(
        self,
        macd_value: float,
        signal_value: float,
        tick: EnrichedTick,
    ) -> Signal | None:
        """Detect MACD bullish crossover and generate BUY signal.

        Args:
            macd_value: Current MACD line value
            signal_value: Current signal line value
            tick: Enriched tick data

        Returns:
            BUY signal if crossover detected below bottom border, None otherwise
        """
        histogram = abs(macd_value - signal_value)
        price = float(tick.price)

        if price > 0 and (histogram / price) < self.min_relative_threshold:
            return None

        if macd_value > self.bottom_border_macd_to_buy:
            return None

        if self.last_macd <= self.last_signal and macd_value > signal_value:
            return self._signal_buy(tick, macd_value, signal_value)

        return None

    def _signal_buy(
        self,
        tick: EnrichedTick,
        macd_value: float,
        signal_value: float,
    ) -> Signal:
        """Generate BUY signal with take-profit price.

        Args:
            tick: Enriched tick data
            macd_value: Current MACD line value
            signal_value: Current signal line value

        Returns:
            BUY signal with expected profit price in metadata
        """
        self.cross_count += 1
        expected_profit_price = float(tick.price) * (1 + self.grid_profit_pct / 100.0)

        logger.info(
            f"[{self._strategy_id}] BUY signal: "
            f"MACD={macd_value:.4f} > Signal={signal_value:.4f}, "
            f"histogram={macd_value - signal_value:.4f}, "
            f"price={tick.price:.8f}, "
            f"expected_profit={expected_profit_price:.8f}"
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
                "expected_profit_price": expected_profit_price,
                "quantity_usdc": self.grid_quantity_absolute,
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

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update(
            {
                "last_macd": self.last_macd,
                "last_signal": self.last_signal,
                "last_histogram": self.last_histogram,
                "cross_count": self.cross_count,
                "tick_count": self._tick_count,
                "macd_indicator_name": self.macd_indicator_name,
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "signal_period": self.signal_period,
                "min_relative_threshold": self.min_relative_threshold,
                "bottom_border_macd_to_buy": self.bottom_border_macd_to_buy,
                "grid_quantity_absolute": self.grid_quantity_absolute,
                "grid_profit_pct": self.grid_profit_pct,
            }
        )
        return stats
