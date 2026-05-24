"""RSI Peak Strategy.

This strategy generates BUY-only signals based on RSI_99 trend reversal detection.
Instead of waiting for RSI threshold crossovers, it detects when the RSI_99 value
reverses from a decline to an uptrend (local minimum / trough detection).

Buy conditions:
- RSI_99 was declining (previous RSI < RSI before previous)
- RSI_99 is now rising (current RSI > previous RSI)
- Current RSI_99 value < rsi_99_threshold (ensures buying at oversold levels)
- Current close price < sma_fast * sma_multiplicator (if configured)
- Current close price < sma_slow * sma_multiplicator (if configured)
- Current close price < avg_day * avg_multiplicator_day (if configured)
- Current close price < avg_week * avg_multiplicator_week (if configured)

No SELL signals are generated. The strategy includes expected_profit_price in signal metadata,
which is handled externally by the market or take-profit mechanism.

Configuration:
    - rsi_99_indicator_name: Name of RSI_99 indicator (default: "rsiindicator_period99_rsi")
    - rsi_99_threshold: Maximum RSI_99 value to allow BUY signals (default: 32.0)
    - min_relative_threshold: Minimum absolute RSI change to trigger signal (default: 0.001)
    - grid_quantity_absolute: USDC amount to buy per signal (default: 100.0)
    - grid_profit_pct: Profit target percentage for take-profit (default: 0.85)
    - sma_fast: Name of fast SMA indicator for price filter (optional, e.g., "sma_800")
    - sma_slow: Name of slow SMA indicator for price filter (optional, e.g., "sma_2000")
    - sma_multiplicator: Multiplier applied to SMA values for price comparison (default: 0.997)
    - trend_lookback: Number of ticks to confirm downtrend before reversal (default: 3)
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class RSIPeakStrategy(Strategy):
    """RSI_99 trend reversal BUY-only strategy with threshold constraint."""

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        self._tick_count: int = 0
        self._initialized: bool = False
        self._rsi_history: list[float] = []

        logger.info(f"RSIPeakStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate RSI_99 trend reversal BUY signals.

        Args:
            tick: Enriched tick data with RSI_99 indicators

        Returns:
            BUY signal if trend reversal detected below threshold, None otherwise
        """
        if not self._initialized:
            self._initialize(tick)
            self._initialized = True

        self._tick_count += 1

        rsi_value = self._get_rsi_value(tick)

        if rsi_value is None:
            return None

        signal = self._detect_trend_reversal(rsi_value, tick)

        if self._tick_count % 500 == 0:
            logger.info(
                f"{tick.time} Tick {self._tick_count}: "
                f"avg_day={self.get_avg_price(tick.symbol, "day"):.8f}, "
                f"avg_week={self.get_avg_price(tick.symbol, "week"):.8f}, "
                f"rsi_99={rsi_value:.4f}, signal_count={self.signal_count}"
            )

        self._rsi_history.append(rsi_value)
        if len(self._rsi_history) > self.trend_lookback + 1:
            self._rsi_history.pop(0)

        return signal

    def _initialize(self, tick: EnrichedTick) -> None:
        """Initialize RSI peak strategy configuration.

        Args:
            tick: First tick used to log available indicators
        """
        self.load_common_config()

        logger.info(
            f"[{self._strategy_id}] RSI_99: threshold={self.rsi_99_threshold}, "
            f"min_change={self.min_relative_threshold}, "
            f"trend_lookback={self.trend_lookback}"
        )
        logger.info(
            f"[{self._strategy_id}] Trade: quantity={self.grid_quantity_absolute} USDC, "
            f"profit_target={self.grid_profit_pct}%"
        )
        if self.sma_fast or self.sma_slow:
            logger.info(
                f"[{self._strategy_id}] SMA filter: fast={self.sma_fast}, slow={self.sma_slow}, "
                f"multiplicator={self.sma_multiplicator}"
            )
        if self.avg_multiplicator_day or self.avg_multiplicator_week:
            logger.info(
                f"[{self._strategy_id}] AVG filter: "
                f"day_multiplicator={self.avg_multiplicator_day}, "
                f"week_multiplicator={self.avg_multiplicator_week}"
            )

        logger.info(f"[{self._strategy_id}] Config: {self._config}")
        logger.info(f"[{self._strategy_id}] Indicators: {tick.indicators}")

    def _get_rsi_value(self, tick: EnrichedTick) -> float | None:
        """Extract RSI_99 value from tick.

        Args:
            tick: Enriched tick data with indicators

        Returns:
            RSI_99 value or None if not available
        """
        indicator_name = self.get_config(
            "rsi_99_indicator_name", "rsiindicator_period99_rsi"
        )
        rsi_value = tick.get_indicator(indicator_name, None)
        if rsi_value is not None:
            return rsi_value

        rsi_value = tick.get_indicator("rsi_99", None)
        if rsi_value is not None:
            return rsi_value

        return tick.get_indicator("rsi", None)

    def _check_sma_filter(self, tick: EnrichedTick) -> bool:
        """Check if current price is below configured SMA indicators.

        Args:
            tick: Enriched tick data with indicators

        Returns:
            True if price is below all configured SMAs, or if no SMA filter is configured
        """
        if not self.sma_fast and not self.sma_slow:
            return True

        price = float(tick.price)

        if self.sma_fast:
            if self.sma_fast in tick.indicators:
                sma_fast_value = tick.indicators[self.sma_fast] * self.sma_multiplicator
                if price >= sma_fast_value:
                    return False

        if self.sma_slow:
            if self.sma_slow in tick.indicators:
                sma_slow_value = tick.indicators[self.sma_slow] * self.sma_multiplicator
                if price >= sma_slow_value:
                    return False

        return True

    def _detect_trend_reversal(
        self,
        rsi_value: float,
        tick: EnrichedTick,
    ) -> Signal | None:
        """Detect RSI_99 trend reversal from decline to uptrend and generate BUY signal.

        Args:
            rsi_value: Current RSI_99 value
            tick: Enriched tick data

        Returns:
            BUY signal if trend reversal detected below threshold, None otherwise
        """
        if not self._check_sma_filter(tick):
            return None

        avg_day = self.get_avg_price(tick.symbol, "day")
        if avg_day and float(tick.price) >= float(avg_day) * self.avg_multiplicator_day:
            return None

        avg_week = self.get_avg_price(tick.symbol, "week")
        if avg_week and float(tick.price) >= float(avg_week) * self.avg_multiplicator_week:
            return None

        if len(self._rsi_history) < self.trend_lookback:
            return None

        lookback_values = self._rsi_history[-(self.trend_lookback):]

        was_declining = all(
            lookback_values[i] > lookback_values[i + 1]
            for i in range(len(lookback_values) - 1)
        )
        is_turning_up = rsi_value > lookback_values[-1]

        if not was_declining or not is_turning_up:
            return None

        rsi_change = abs(rsi_value - lookback_values[-1])
        if rsi_change < self.min_relative_threshold:
            return None

        if rsi_value >= self.rsi_99_threshold:
            return None

        return self._signal_buy(tick, rsi_value)

    def _signal_buy(
        self,
        tick: EnrichedTick,
        rsi_value: float,
    ) -> Signal:
        """Generate BUY signal with take-profit price.

        Args:
            tick: Enriched tick data
            rsi_value: Current RSI_99 value

        Returns:
            BUY signal with expected profit price in metadata
        """
        self.signal_count += 1
        expected_profit_price = float(tick.price) * (1 + self.grid_profit_pct / 100.0)
        
        logger.info(
            f"[{self._strategy_id}] BUY signal: "
            f"RSI_99={rsi_value:.4f}, "
            f"price={tick.price:.8f}, "
            f"expected_profit={expected_profit_price:.8f}"
        )

        quantity_multiplicator = 1
        if(rsi_value < 25):
            quantity_multiplicator = 1.5
        if(rsi_value < 20):
            quantity_multiplicator = 2.0
        if(rsi_value < 15):
            quantity_multiplicator = 2.5
        

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.BUY,
            price=tick.price,
            confidence=min(1.0, (self.rsi_99_threshold - rsi_value) / self.rsi_99_threshold),
            metadata={
                "rsi_99": rsi_value,
                "rsi_99_threshold": self.rsi_99_threshold,
                "reversal_type": "decline_to_uptrend",
                "signal_count": self.signal_count,
                "expected_profit_price": expected_profit_price,
                "quantity_usdc": self.grid_quantity_absolute * quantity_multiplicator,
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
            grid_index: Not used for RSI strategy
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
                "last_rsi": self._rsi_history[-1] if self._rsi_history else None,
                "signal_count": self.signal_count,
                "tick_count": self._tick_count,
                "rsi_99_threshold": self.rsi_99_threshold,
                "min_relative_threshold": self.min_relative_threshold,
                "grid_quantity_absolute": self.grid_quantity_absolute,
                "grid_profit_pct": self.grid_profit_pct,
                "sma_fast": self.sma_fast,
                "sma_slow": self.sma_slow,
                "sma_multiplicator": self.sma_multiplicator,
                "avg_multiplicator_day": self.avg_multiplicator_day,
                "avg_multiplicator_week": self.avg_multiplicator_week,
                "trend_lookback": self.trend_lookback,
            }
        )
        return stats
