"""MACD Momentum Strategy.

This strategy generates both BUY and SELL signals based on MACD peak/trough
detection (local extrema of the MACD line). It is the classic momentum variant:

- BUY when MACD reverses from decline to uptrend (local minimum / trough)
- SELL when MACD reverses from uptrend to decline (local maximum / peak)

Buy conditions:
- MACD was declining for `trend_lookback` consecutive ticks
- MACD is now rising (current MACD > previous MACD)
- Current MACD value < bottom_border_macd_to_buy
- Price below SMA / avg filters (if configured)

Sell conditions:
- MACD was rising for `trend_lookback` consecutive ticks
- MACD is now falling (current MACD < previous MACD)
- Current MACD value > top_border_macd_to_sell
- Currently in a position (in_position = True)

Configuration:
    - macd_indicator_name: Name of MACD indicator (default: macd_980_1960_100)
    - fast_period: MACD fast EMA period (default: 980)
    - slow_period: MACD slow EMA period (default: 1960)
    - signal_period: Signal line period (default: 100)
    - min_relative_threshold: Minimum MACD change ratio to trigger signal (default: 0.001)
    - bottom_border_macd_to_buy: Maximum MACD value to allow BUY signals (default: 0.0)
    - top_border_macd_to_sell: Minimum MACD value to allow SELL signals (default: 0.0)
    - grid_quantity_absolute: USDC amount to trade per signal (default: 100.0)
    - grid_profit_pct: Profit target percentage for take-profit (default: 0.85)
    - sma_fast: Name of fast SMA indicator for price filter (optional)
    - sma_slow: Name of slow SMA indicator for price filter (optional)
    - sma_multiplicator: Multiplier applied to SMA values (default: 0.997)
    - trend_lookback: Number of ticks to confirm trend before reversal (default: 3)
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class MACDMomentumStrategy(Strategy):
    """MACD momentum strategy with peak and trough detection for BUY and SELL signals."""

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        self._tick_count: int = 0
        self._initialized: bool = False
        self._macd_history: list[float] = []
        self._signal_cooldown: int = 0
        self.in_position: bool = False

        logger.info(f"MACDMomentumStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate MACD momentum signals.

        Args:
            tick: Enriched tick data with MACD indicators

        Returns:
            BUY or SELL signal if peak/trough detected, None otherwise
        """
        if not self._initialized:
            self._initialize_macd(tick)
            self._initialized = True

        self._tick_count += 1

        macd_value, signal_value, histogram_value = self._get_macd_values(tick)

        if macd_value is None or signal_value is None:
            return None

        assert macd_value is not None and signal_value is not None

        signal = self._detect_momentum(macd_value, signal_value, tick)

        if self._tick_count < 50 or self._tick_count % 500 == 0:
            sma_fast_val = tick.indicators.get(self.sma_fast, 0.0) if self.sma_fast else 0.0
            sma_slow_val = tick.indicators.get(self.sma_slow, 0.0) if self.sma_slow else 0.0
            logger.info(
                f"{tick.time} Tick {self._tick_count}: "
                f"macd={macd_value:.10f}, signal={signal_value:.10f}, "
                f"fast={sma_fast_val:.10f}, slow={sma_slow_val:.10f}, "
                f"in_position={self.in_position}, sig_cnt={self.signal_count}"
            )

        self.prev_macd = self.last_macd
        self.last_macd = macd_value
        self.last_signal = signal_value
        if histogram_value is not None:
            self.last_histogram = histogram_value

        return signal

    def _initialize_macd(self, tick: EnrichedTick) -> None:
        """Initialize MACD momentum strategy configuration.

        Args:
            tick: First tick used to log available indicators
        """
        self.load_common_config()

        macd_keys = sorted(k for k in tick.indicators if k.endswith("_macd"))

        logger.info(
            f"[{self._strategy_id}] >>> MACD indicator: "
            f"configured='{self.macd_indicator_name}', "
            f"available bases: {[k.replace('_macd', '') for k in macd_keys]}"
        )
        logger.info(
            f"[{self._strategy_id}] MACD params: fast={self.fast_period}, "
            f"slow={self.slow_period}, signal={self.signal_period}, "
            f"min_relative_threshold={self.min_relative_threshold}, "
            f"bottom_border={self.bottom_border_macd_to_buy}"
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

    def _get_macd_values(
        self, tick: EnrichedTick
    ) -> tuple[float | None, float | None, float | None]:
        """Extract MACD, signal, and histogram values from tick.

        Args:
            tick: Enriched tick data with indicators

        Returns:
            Tuple of (macd_value, signal_value, histogram_value) or (None, None, None)
        """
        macd_value = tick.indicators.get(f"{self.macd_indicator_name}_macd")
        signal_value = tick.indicators.get(f"{self.macd_indicator_name}_signal")
        histogram_value = tick.indicators.get(f"{self.macd_indicator_name}_histogram")

        if macd_value is not None and signal_value is not None:
            if histogram_value is None:
                histogram_value = macd_value - signal_value
            return macd_value, signal_value, histogram_value

        macd_value = tick.indicators.get("macd")
        signal_value = tick.indicators.get("macd_signal")
        histogram_value = tick.indicators.get("macd_histogram")

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

    def _detect_momentum(
        self,
        macd_value: float,
        signal_value: float,
        tick: EnrichedTick,
    ) -> Signal | None:
        """Detect MACD peak (sell) or trough (buy) and generate signal.

        Args:
            macd_value: Current MACD line value
            signal_value: Current signal line value
            tick: Enriched tick data

        Returns:
            BUY or SELL signal if peak/trough detected, None otherwise
        """
        if not self._check_sma_filter(tick):
            logger.debug(f"[{self._strategy_id}] Reject: SMA filter failed at price={tick.price}")
            return None

        avg_day = self.get_avg_price(tick.symbol, "day")
        avg_week = self.get_avg_price(tick.symbol, "week")

        if not self.in_position:
            if avg_day and float(tick.price) >= float(avg_day) * self.avg_multiplicator_day:
                logger.debug(
                    f"[{self._strategy_id}] Reject BUY: price {tick.price} >= "
                    f"avg_day {avg_day} * {self.avg_multiplicator_day}"
                )
                return None

            if avg_week and float(tick.price) >= float(avg_week) * self.avg_multiplicator_week:
                logger.debug(
                    f"[{self._strategy_id}] Reject BUY: price {tick.price} >= "
                    f"avg_week {avg_week} * {self.avg_multiplicator_week}"
                )
                return None

        self._macd_history.append(macd_value)
        if len(self._macd_history) > self.trend_lookback + 1:
            self._macd_history.pop(0)

        if len(self._macd_history) < self.trend_lookback + 1:
            logger.debug(
                f"[{self._strategy_id}] Reject: building MACD history "
                f"({len(self._macd_history)}/{self.trend_lookback + 1})"
            )
            return None

        if self._signal_cooldown > 0:
            self._signal_cooldown -= 1
            logger.debug(
                f"[{self._strategy_id}] Reject: cooldown {self._signal_cooldown + 1}/"
                f"{self.trend_lookback + 1} ticks remaining"
            )
            return None

        signal_magnitude = abs(signal_value) if abs(signal_value) > 1e-10 else abs(macd_value)

        was_declining = all(
            self._macd_history[i] > self._macd_history[i + 1]
            for i in range(len(self._macd_history) - 2)
        )
        is_turning_up = macd_value > self._macd_history[-2]

        was_rising = all(
            self._macd_history[i] < self._macd_history[i + 1]
            for i in range(len(self._macd_history) - 2)
        )
        is_turning_down = macd_value < self._macd_history[-2]

        macd_change = abs(macd_value - self._macd_history[-2])

        if (
            signal_magnitude > 1e-10
            and (macd_change / signal_magnitude) < self.min_relative_threshold
        ):
            logger.debug(
                f"[{self._strategy_id}] Reject: MACD change {macd_change:.6g} "
                f"below threshold ({macd_change / signal_magnitude:.6g} < "
                f"{self.min_relative_threshold})"
            )
            return None

        if was_declining and is_turning_up and not self.in_position:
            if macd_value > self.bottom_border_macd_to_buy:
                logger.debug(
                    f"[{self._strategy_id}] Reject BUY: MACD {macd_value:.6f} > "
                    f"bottom_border {self.bottom_border_macd_to_buy}"
                )
                return None

            logger.debug(
                f"[{self._strategy_id}] Accept BUY: trough at MACD={macd_value:.6f}, "
                f"price={tick.price}"
            )
            return self._signal_buy(tick, macd_value, signal_value)

        if was_rising and is_turning_down and self.in_position:
            logger.debug(
                f"[{self._strategy_id}] Accept SELL: peak at MACD={macd_value:.6f}, "
                f"price={tick.price}"
            )
            return self._signal_sell(tick, macd_value, signal_value)

        logger.debug(
            f"[{self._strategy_id}] Reject: no momentum (declining={was_declining}, "
            f"turning_up={is_turning_up}, rising={was_rising}, "
            f"turning_down={is_turning_down}, in_position={self.in_position}, "
            f"macd_history={self._macd_history})"
        )
        return None

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
        self.signal_count += 1
        self._signal_cooldown = self.trend_lookback + 1

        expected_profit_price = tick.price * (
            Decimal("1") + Decimal(str(self.grid_profit_pct)) / Decimal("100")
        )

        qty = Decimal(str(self.grid_quantity_absolute)) / tick.price
        logger.info(
            f"[{self._strategy_id}] BUY signal: "
            f"MACD={macd_value:.4f}, Signal={signal_value:.4f}, "
            f"histogram={macd_value - signal_value:.4f}, "
            f"price={tick.price:.8f}, "
            f"qty={qty:.8f}, "
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
                "momentum_type": "trough_buy",
                "signal_count": self.signal_count,
                "expected_profit_price": expected_profit_price,
                "quantity_usdc": self.grid_quantity_absolute,
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
        self.signal_count += 1
        self._signal_cooldown = self.trend_lookback + 1

        logger.info(
            f"[{self._strategy_id}] SELL signal: "
            f"MACD={macd_value:.4f}, Signal={signal_value:.4f}, "
            f"histogram={macd_value - signal_value:.4f}, "
            f"price={tick.price:.8f}"
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
                "momentum_type": "peak_sell",
                "signal_count": self.signal_count,
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
            grid_index: Not used for MACD momentum strategy
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
                "prev_macd": self.prev_macd,
                "in_position": self.in_position,
                "signal_count": self.signal_count,
                "tick_count": self._tick_count,
                "macd_indicator_name": self.macd_indicator_name,
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "signal_period": self.signal_period,
                "min_relative_threshold": self.min_relative_threshold,
                "bottom_border_macd_to_buy": self.bottom_border_macd_to_buy,
                "grid_quantity_absolute": self.grid_quantity_absolute,
                "grid_profit_pct": self.grid_profit_pct,
                "sma_fast": self.sma_fast,
                "sma_slow": self.sma_slow,
                "sma_multiplicator": self.sma_multiplicator,
                "avg_multiplicator_day": self.avg_multiplicator_day,
                "avg_multiplicator_week": self.avg_multiplicator_week,
                "trend_lookback": self.trend_lookback,
                "signal_cooldown": self._signal_cooldown,
            }
        )
        return stats
