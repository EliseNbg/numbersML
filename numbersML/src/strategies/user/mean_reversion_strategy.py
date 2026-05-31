"""Mean Reversion Strategy using Bollinger Bands and RSI.

This strategy generates BUY and SELL signals based on price touching
Bollinger Bands with RSI confirmation:

BUY conditions:
- Price touches or crosses below the lower Bollinger Band
- RSI is below the oversold threshold (confirming bearish extreme)
- Price is below SMA filters (if configured, ensures trading with trend)
- Price is below daily/weekly average filters (if configured)

SELL conditions:
- Price touches or crosses above the upper Bollinger Band
- RSI is above the overbought threshold (confirming bullish extreme)

No SELL signals are generated for positions — the strategy is BUY-only with
take-profit managed externally via expected_profit_price in signal metadata.
"""

import logging
from decimal import Decimal
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class MeanReversionStrategy(Strategy):
    """Mean reversion strategy using Bollinger Bands and RSI confirmation.

    State:
        - _tick_count: Number of ticks processed
        - _initialized: Whether strategy has been initialized
        - last_bb_lower: Last lower Bollinger Band value
        - last_bb_upper: Last upper Bollinger Band value
        - last_rsi: Last RSI value
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        self._tick_count: int = 0
        self._initialized: bool = False
        self.last_bb_lower: float = 0.0
        self.last_bb_upper: float = 0.0
        self.last_rsi: float = 0.0

        logger.info(f"MeanReversionStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate mean reversion signals.

        Args:
            tick: Enriched tick data with Bollinger Bands and RSI indicators

        Returns:
            BUY signal if conditions are met, None otherwise
        """
        if not self._initialized:
            self._initialize(tick)
            self._initialized = True

        self._tick_count += 1

        bb_lower, bb_upper, bb_middle = self._get_bb_values(tick)
        rsi_value = self._get_rsi_value(tick)

        if bb_lower is None or bb_upper is None:
            return None

        if rsi_value is None:
            rsi_value = 50.0
        rsi_confirmed = self.rsi_indicator_name is None or rsi_value < self.oversold_threshold

        if self._tick_count < 50 or self._tick_count % 500 == 0:
            sma_fast_val = tick.indicators.get(self.sma_fast, 0.0) if self.sma_fast else 0.0
            sma_slow_val = tick.indicators.get(self.sma_slow, 0.0) if self.sma_slow else 0.0
            logger.info(
                f"{tick.time} Tick {self._tick_count}:"
                f" bb_lower={bb_lower:.8f}, bb_middle={bb_middle:.8f},"
                f" bb_upper={bb_upper:.8f}, rsi={rsi_value:.4f},"
                f" fast={sma_fast_val:.8f}, slow={sma_slow_val:.8f},"
                f" price={tick.price:.8f}"
            )

        signal = self._detect_mean_reversion(bb_lower, bb_upper, rsi_value, rsi_confirmed, tick)

        self.last_bb_lower = bb_lower
        self.last_bb_upper = bb_upper
        self.last_rsi = rsi_value

        return signal

    def _initialize(self, tick: EnrichedTick) -> None:
        """Initialize strategy configuration.

        Args:
            tick: First tick used to detect available indicators
        """
        self.load_common_config()

        self.bb_indicator_lower = self.get_config("bb_indicator_lower")
        self.bb_indicator_upper = self.get_config("bb_indicator_upper")
        self.rsi_indicator_name = self.get_config("rsi_indicator_name")

        if not self.bb_indicator_lower or not self.bb_indicator_upper:
            self._autodetect_bb(tick.indicators)

        if not self.rsi_indicator_name:
            self._autodetect_rsi(tick.indicators)

        self.oversold_threshold = self.get_config("oversold_threshold", 31.9)
        self.overbought_threshold = self.get_config("overbought_threshold", 100.0 - 31.9)  # 68.1

        logger.info(
            f"[{self._strategy_id}] BB: lower={self.bb_indicator_lower}, "
            f"upper={self.bb_indicator_upper}"
        )
        logger.info(
            f"[{self._strategy_id}] RSI: indicator={self.rsi_indicator_name}, "
            f"oversold={self.oversold_threshold}, overbought={self.overbought_threshold}"
        )
        logger.info(
            f"[{self._strategy_id}] Trade: quantity={self.grid_quantity_absolute} USDC, "
            f"profit_target={self.grid_profit_pct}%"
        )
        if self.sma_fast or self.sma_slow:
            logger.info(
                f"[{self._strategy_id}] SMA filter: fast={self.sma_fast}, "
                f"slow={self.sma_slow}, multiplicator={self.sma_multiplicator}"
            )
        if self.avg_multiplicator_day or self.avg_multiplicator_week:
            logger.info(
                f"[{self._strategy_id}] AVG filter: "
                f"day_multiplicator={self.avg_multiplicator_day}, "
                f"week_multiplicator={self.avg_multiplicator_week}"
            )

        logger.info(f"[{self._strategy_id}] Config: {self._config}")
        logger.info(f"[{self._strategy_id}] Indicators: {tick.indicators}")

    def _autodetect_bb(self, indicators: dict[str, float]) -> None:
        """Auto-detect Bollinger Bands indicators from available keys.

        Looks for keys matching the pattern bb_{period}_{std_dev}_lower
        and bb_{period}_{std_dev}_upper.

        Args:
            indicators: Dictionary of indicator values from tick
        """
        lower_key = None
        upper_key = None
        middle_key = None

        for key in indicators:
            key_lower = key.lower()
            if not key_lower.startswith("bb_"):
                continue

            if key_lower.endswith("_lower"):
                lower_key = key
                middle_key = key_lower.replace("_lower", "_middle")
                upper_key = key_lower.replace("_lower", "_upper")
            elif key_lower.endswith("_upper"):
                if upper_key is None:
                    upper_key = key

        if lower_key and upper_key:
            self.bb_indicator_lower = lower_key
            self.bb_indicator_upper = upper_key
            if middle_key and middle_key in indicators:
                self.bb_indicator_middle = middle_key
            logger.info(
                f"[{self._strategy_id}] Auto-detected BB indicators: "
                f"lower={lower_key}, upper={upper_key}"
            )

    def _autodetect_rsi(self, indicators: dict[str, float]) -> None:
        """Auto-detect RSI indicator from available keys.

        Args:
            indicators: Dictionary of indicator values from tick
        """
        for key in indicators:
            key_lower = key.lower()
            if key_lower.startswith("rsi_"):
                self.rsi_indicator_name = key
                logger.info(f"[{self._strategy_id}] Auto-detected RSI indicator: {key}")
                return

    def _get_bb_values(self, tick: EnrichedTick) -> tuple[float | None, float | None, float | None]:
        """Extract Bollinger Bands values from tick.

        Args:
            tick: Enriched tick data with indicators

        Returns:
            Tuple of (lower_band, upper_band, middle_band) or (None, None, None)
        """
        lower = tick.indicators.get(self.bb_indicator_lower) if self.bb_indicator_lower else None
        upper = tick.indicators.get(self.bb_indicator_upper) if self.bb_indicator_upper else None

        if lower is None or upper is None:
            return None, None, None

        if hasattr(self, "bb_indicator_middle") and self.bb_indicator_middle:
            middle = tick.indicators.get(self.bb_indicator_middle)
        else:
            middle = (lower + upper) / 2.0

        return lower, upper, middle

    def _get_rsi_value(self, tick: EnrichedTick) -> float | None:
        """Extract RSI value from tick.

        Args:
            tick: Enriched tick data with indicators

        Returns:
            RSI value or None if not available
        """
        if self.rsi_indicator_name:
            return tick.indicators.get(self.rsi_indicator_name)
        return None

    def _detect_mean_reversion(
        self,
        bb_lower: float,
        bb_upper: float,
        rsi_value: float,
        rsi_confirmed: bool,
        tick: EnrichedTick,
    ) -> Signal | None:
        """Detect mean reversion entry signal.

        Buy when price touches/breaks the lower band with RSI confirming
        oversold conditions (or RSI not configured), and SMA/AVG filters allow.

        Args:
            bb_lower: Current lower Bollinger Band value
            bb_upper: Current upper Bollinger Band value
            rsi_value: Current RSI value
            rsi_confirmed: Whether RSI confirms oversold (or RSI not configured)
            tick: Enriched tick data

        Returns:
            BUY signal if all conditions met, None otherwise
        """
        price = float(tick.price)

        # Check SMA filter (price below SMAs)
        if not self._check_sma_filter(tick):
            return None

        # Check AVG price filters
        avg_day = self.get_avg_price(tick.symbol, "day")
        if avg_day and price >= float(avg_day) * self.avg_multiplicator_day:
            return None

        avg_week = self.get_avg_price(tick.symbol, "week")
        if avg_week and price >= float(avg_week) * self.avg_multiplicator_week:
            return None

        # BUY signal: price at or below lower band + RSI oversold (or RSI not configured)
        if price <= bb_lower and rsi_confirmed:
            return self._signal_buy(tick, bb_lower, bb_upper, rsi_value)

        return None

    def _signal_buy(
        self,
        tick: EnrichedTick,
        bb_lower: float,
        bb_upper: float,
        rsi_value: float,
    ) -> Signal:
        """Generate BUY signal with metadata.

        Args:
            tick: Enriched tick data
            bb_lower: Current lower Bollinger Band value
            bb_upper: Current upper Bollinger Band value
            rsi_value: Current RSI value

        Returns:
            BUY signal with take-profit price in metadata
        """
        self.signal_count += 1
        expected_profit_price = tick.price * (
            Decimal("1") + Decimal(str(self.grid_profit_pct)) / Decimal("100")
        )

        logger.info(
            f"[{self._strategy_id}] BUY signal: "
            f"price={tick.price:.8f}, bb_lower={bb_lower:.8f}, "
            f"rsi={rsi_value:.4f}, "
            f"expected_profit={expected_profit_price:.8f}"
        )

        return Signal(
            strategy_id=self._strategy_id,
            symbol=tick.symbol,
            signal_type=SignalType.BUY,
            price=tick.price,
            confidence=min(1.0, (bb_upper - float(tick.price)) / (bb_upper - bb_lower)),
            metadata={
                "bb_lower": bb_lower,
                "bb_upper": bb_upper,
                "rsi": rsi_value,
                "signal_count": self.signal_count,
                "expected_profit_price": expected_profit_price,
                "quantity_usdc": self.grid_quantity_absolute,
                "signal_reason": "mean_reversion_lower_band",
            },
        )

    def on_position_closed(
        self,
        symbol: str,
        price: Decimal,
        exit_reason: str,
        grid_index: int | None = None,
    ) -> None:
        """Handle position closure.

        Args:
            symbol: Trading pair symbol
            price: Price at which position was closed
            exit_reason: Reason for closure
            grid_index: Not used for mean reversion strategy
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
                "last_bb_lower": self.last_bb_lower,
                "last_bb_upper": self.last_bb_upper,
                "last_rsi": self.last_rsi,
                "signal_count": self.signal_count,
                "tick_count": self._tick_count,
                "bb_indicator_lower": self.bb_indicator_lower,
                "bb_indicator_upper": self.bb_indicator_upper,
                "rsi_indicator_name": self.rsi_indicator_name,
                "oversold_threshold": self.oversold_threshold,
                "overbought_threshold": self.overbought_threshold,
                "grid_quantity_absolute": self.grid_quantity_absolute,
                "grid_profit_pct": self.grid_profit_pct,
                "sma_fast": self.sma_fast,
                "sma_slow": self.sma_slow,
                "sma_multiplicator": self.sma_multiplicator,
                "avg_multiplicator_day": self.avg_multiplicator_day,
                "avg_multiplicator_week": self.avg_multiplicator_week,
            }
        )
        return stats
