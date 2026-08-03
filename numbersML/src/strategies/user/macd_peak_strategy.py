"""MACD Peak Strategy.

This strategy generates BUY-only signals based on MACD trend reversal detection.
Instead of waiting for MACD/signal line crossovers, it detects when the MACD line
itself reverses from a decline to an uptrend (local minimum / trough detection).

Buy conditions:
- MACD was declining (previous MACD < MACD before previous)
- MACD is now rising (current MACD > previous MACD)
- Current MACD value < bottom_border_macd_to_buy (ensures buying at dips)
- Current close price < sma_fast * sma_multiplicator (if configured)
- Current close price < sma_slow * sma_multiplicator (if configured)
- Current close price < avg_day * avg_multiplicator_day (if configured)
- Current close price < avg_week * avg_multiplicator_week (if configured and > 0)

No SELL signals are generated. The strategy includes expected_profit_price in signal metadata,
which is handled externally by the market or take-profit mechanism.

Configuration:
    - macd_indicator_name: Name of MACD indicator (default: macdsmaindicator)
    - macd_slow_indicator_name: Name of slow MACD indicator for trend filter (optional, default: macd_8590_13800_195)
    - fast_period: MACD fast EMA period (default: 12)
    - slow_period: MACD slow EMA period (default: 26)
    - signal_period: Signal line period (default: 9)
    - min_relative_threshold: Minimum MACD change ratio to trigger signal (default: 0.001)
    - bottom_border_macd_to_buy: Maximum MACD value to allow BUY signals (default: 0.0)
    - grid_quantity_absolute: USDC amount to buy per signal (default: 100.0)
    - grid_profit_pct: Profit target percentage for take-profit (default: 0.85)
    - sma_fast: Name of fast SMA indicator for price filter (optional, e.g., "sma_800")
    - sma_slow: Name of slow SMA indicator for price filter (optional, e.g., "sma_2000")
    - sma_multiplicator: Multiplier applied to SMA values for price comparison (default: 0.997)
    - trend_lookback: Number of ticks to confirm downtrend before reversal (default: 3)

Quantity multiplier:
    Order size is scaled by distance below avg_week (7-day average).
    Formula: multiplier = max(1.0, 1.0 + diff_pct / 2) where diff_pct = (avg_week - price) / avg_week * 100.
    At 2% below avg_week the multiplier is ~2.0. Never goes below 1.0.
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class MACDPeakStrategy(Strategy):
    """MACD trend reversal BUY-only strategy with bottom border constraint."""

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
        self._test_buy_done: bool = False

        logger.info(f"MACDPeakStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate MACD trend reversal BUY signals.

        Args:
            tick: Enriched tick data with MACD indicators

        Returns:
            BUY signal if trend reversal detected below bottom border, None otherwise
        """
        if not self._initialized:
            self._initialize_macd(tick)
            self._initialized = True

        self._tick_count += 1

        # Test buy: buy once for 5 USDC with 0.5% take-profit to verify execution works
        if self._test_buy_enabled and not self._test_buy_done:
            self._test_buy_done = True
            logger.info(
                f"[{self._strategy_id}] TEST BUY triggered on first tick, "
                f"price={tick.price}"
            )
            return self._signal_test_buy(tick)

        macd_value, signal_value, histogram_value = self._get_macd_values(tick)

        if macd_value is None or signal_value is None:
            return None

        signal = self._detect_trend_reversal(macd_value, signal_value, tick)

        avg_day = self.get_avg_price(tick.symbol, "day")
        avg_week = self.get_avg_price(tick.symbol, "week")

        if self._tick_count < 50 or self._tick_count % 500 == 0:
            sma_fast_val = tick.indicators.get(self.sma_fast, 0.0)
            sma_slow_val = tick.indicators.get(self.sma_slow, 0.0)
            logger.info(
                f"{tick.time} Tick {self._tick_count}: "
                f" macd={macd_value:.10f}, fast={sma_fast_val:.10f}, slow={sma_slow_val:.10f},"
                f" avg_day={float(avg_day):.8f}, avg_week={float(avg_week):.8f},"
                f" sig_cnt={self.signal_count}"
            )

        self.prev_macd = self.last_macd
        self.last_macd = macd_value
        self.last_signal = signal_value
        self.last_histogram = histogram_value

        return signal

    def _initialize_macd(self, tick: EnrichedTick) -> None:
        """Initialize MACD strategy configuration.

        Args:
            tick: First tick used to log available indicators
        """
        self.load_common_config()
        self._test_buy_enabled = self.get_config("test_buy_enabled", False)

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
            f"bottom_border={self.bottom_border_macd_to_buy}, "
            f"trend_lookback={self.trend_lookback}"
        )
        logger.info(
            f"[{self._strategy_id}] Trade: quantity={self.grid_quantity_absolute} USDC, "
            f"profit_target={self.grid_profit_pct}%"
        )
        logger.info(
            f"[{self._strategy_id}] Slow MACD filter: indicator='{self.macd_slow_indicator_name}'"
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
        if self.rsi_99_threshold:
            logger.info(f"[{self._strategy_id}] RSI filter: threshold={self.rsi_99_threshold}")

        logger.info(f"[{self._strategy_id}] Config: {self._config}")
        logger.info(f"[{self._strategy_id}] Indicators: {tick.indicators}")

    def _get_macd_values(
        self, tick: EnrichedTick
    ) -> tuple[float | None, float | None, float | None]:
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

    def _detect_trend_reversal(
        self,
        macd_value: float,
        signal_value: float,
        tick: EnrichedTick,
    ) -> Signal | None:
        """Detect MACD trend reversal from decline to uptrend and generate BUY signal.

        Args:
            macd_value: Current MACD line value
            signal_value: Current signal line value
            tick: Enriched tick data

        Returns:
            BUY signal if trend reversal detected below bottom border, None otherwise
        """
        if not self._check_sma_filter(tick):
            logger.debug(f"[{self._strategy_id}] Reject: SMA filter failed at price={tick.price}")
            return None

        slow_macd_value = tick.indicators.get(f"{self.macd_slow_indicator_name}_macd")
        if slow_macd_value is not None:
            if slow_macd_value >= 0:
                logger.debug(
                    f"[{self._strategy_id}] Reject BUY: slow MACD {slow_macd_value:.6f} >= 0"
                )
                return None

        avg_day = self.get_avg_price(tick.symbol, "day")
        if avg_day and float(tick.price) >= float(avg_day) * self.avg_multiplicator_day:
            logger.debug(
                f"[{self._strategy_id}] Reject: price {tick.price} >= "
                f"avg_day {avg_day} * {self.avg_multiplicator_day}"
            )
            return None

        if self.avg_multiplicator_week:
            avg_week = self.get_avg_price(tick.symbol, "week")
            if avg_week and float(tick.price) >= float(avg_week) * self.avg_multiplicator_week:
                logger.debug(
                    f"[{self._strategy_id}] Reject: price {tick.price} >= "
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

        # Cooldown after a signal: wait for old decline values to leave the window
        if self._signal_cooldown > 0:
            self._signal_cooldown -= 1
            logger.debug(
                f"[{self._strategy_id}] Reject: cooldown {self._signal_cooldown + 1}/"
                f"{self.trend_lookback + 1} ticks remaining"
            )
            return None

        was_declining = all(
            self._macd_history[i] > self._macd_history[i + 1]
            for i in range(len(self._macd_history) - 2)
        )
        is_turning_up = macd_value > self._macd_history[-2]

        if not was_declining or not is_turning_up:
            logger.debug(
                f"[{self._strategy_id}] Reject: no reversal (declining={was_declining}, "
                f"turning_up={is_turning_up}, macd_history={self._macd_history})"
            )
            return None

        macd_change = abs(macd_value - self._macd_history[-2])
        signal_magnitude = abs(signal_value) if abs(signal_value) > 1e-10 else abs(macd_value)
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

        if macd_value > self.bottom_border_macd_to_buy:
            logger.debug(
                f"[{self._strategy_id}] Reject: MACD {macd_value:.6f} > "
                f"bottom_border {self.bottom_border_macd_to_buy}"
            )
            return None

        logger.debug(
            f"[{self._strategy_id}] Accept: trend reversal at MACD={macd_value:.6f}, "
            f"price={tick.price}"
        )
        return self._signal_buy(tick, macd_value, signal_value)

    def _calculate_quantity_multiplier(self, symbol: str, price: Decimal) -> float:
        """Calculate quantity multiplier based on distance below avg_week.

        The further the price is below the weekly average, the larger the order.
        At 2% below avg_week the multiplier is ~2.0, at 1% it is ~1.5.
        Never goes below 1.0.

        Args:
            symbol: Trading pair symbol
            price: Current price

        Returns:
            Multiplier >= 1.0
        """
        avg_week = self.get_avg_price(symbol, "week")
        if not avg_week or avg_week <= 0:
            return 1.0

        diff_pct = (float(avg_week) - float(price)) / float(avg_week) * 100.0
        return max(1.0, 1.0 + diff_pct / 2.0)

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
        self.signal_count += 1
        self._signal_cooldown = self.trend_lookback + 1
        expected_profit_price = tick.price * (
            Decimal("1") + Decimal(str(self.grid_profit_pct)) / Decimal("100")
        )

        quantity_multiplier = self._calculate_quantity_multiplier(tick.symbol, tick.price)
        effective_quantity = Decimal(str(self.grid_quantity_absolute)) * Decimal(str(quantity_multiplier))
        qty = effective_quantity / tick.price
        avg_week = self.get_avg_price(tick.symbol, "week")
        logger.info(
            f"[{self._strategy_id}] BUY signal: "
            f"MACD={macd_value:.4f}, Signal={signal_value:.4f}, "
            f"histogram={macd_value - signal_value:.4f}, "
            f"price={tick.price:.8f}, "
            f"qty={qty:.8f}, "
            f"quantity_usdc={effective_quantity:.2f}, "
            f"quantity_multiplier={quantity_multiplier:.2f}, "
            f"avg_week={avg_week}, "
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
                "reversal_type": "decline_to_uptrend",
                "signal_count": self.signal_count,
                "expected_profit_price": expected_profit_price,
                "quantity_usdc": float(effective_quantity),
                "quantity_multiplier": quantity_multiplier,
                "effective_quantity_usdc": float(effective_quantity),
            },
        )

    def _signal_test_buy(self, tick: EnrichedTick) -> Signal:
        """Generate a one-time test BUY signal to verify execution works.

        Buys for 5 USDC and sets a 0.5% take-profit sell limit order.

        Args:
            tick: Enriched tick data

        Returns:
            BUY signal with 5 USDC quantity and 0.5% expected profit price
        """
        test_quantity_usdc = Decimal("7")
        expected_profit_price = tick.price * (Decimal("1") + Decimal("0.005"))
        qty = test_quantity_usdc / tick.price

        logger.info(
            f"[{self._strategy_id}] TEST BUY: "
            f"price={tick.price:.8f}, qty={qty:.8f}, "
            f"quantity_usdc={test_quantity_usdc}, "
            f"expected_profit={expected_profit_price:.8f} (+0.5%)"
        )

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.BUY,
            price=tick.price,
            confidence=1.0,
            metadata={
                "reversal_type": "test_buy",
                "expected_profit_price": expected_profit_price,
                "quantity_usdc": float(test_quantity_usdc),
                "quantity_multiplier": 1.0,
                "effective_quantity_usdc": float(test_quantity_usdc),
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
                "prev_macd": self.prev_macd,
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
                "rsi_99_threshold": self.rsi_99_threshold,
                "trend_lookback": self.trend_lookback,
                "signal_cooldown": self._signal_cooldown,
            }
        )
        return stats
