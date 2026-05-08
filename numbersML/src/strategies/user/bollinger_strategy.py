"""Bollinger Bands Strategy.

This strategy generates signals based on price touching Bollinger Bands:
- BUY when price touches or crosses below lower band (oversold)
- SELL when price touches or crosses above upper band (overbought)

The strategy maintains:
- Last price and band values
- Position state
"""

import logging
from typing import Any

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy

logger = logging.getLogger(__name__)


class BollingerBandsStrategy(Strategy):
    """Bollinger Bands mean reversion strategy with persistent state.

    State:
        - last_price: Last tick price
        - last_upper: Last upper band value
        - last_lower: Last lower band value
        - last_middle: Last middle band (SMA) value
        - in_position: Whether we have an open position
        - band_touch_count: Number of band touches

    Configuration (accessed via self.get_config):
        - bb_indicator_name: Name of Bollinger Bands indicator (default: bollingerindicator)
        - period: Bollinger Bands period (default: 20)
        - std_dev: Standard deviation multiplier (default: 2.0)
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: Any = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)

        # Persistent state
        self.last_price: float = 0.0
        self.last_upper: float = 0.0
        self.last_lower: float = 0.0
        self.last_middle: float = 0.0
        self.in_position: bool = False
        self.band_touch_count: int = 0

        logger.info(f"BollingerBandsStrategy {strategy_id} initialized")

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Process tick and generate Bollinger Bands signals.

        Args:
            tick: Enriched tick data with Bollinger Bands indicators

        Returns:
            Signal if price touches bands, None otherwise
        """
        bb_name = self.get_config("bb_indicator_name", "bollingerindicator")

        # Get Bollinger Bands values from indicators
        upper = tick.get_indicator(f"{bb_name}_upper", None)
        lower = tick.get_indicator(f"{bb_name}_lower", None)
        middle = tick.get_indicator(f"{bb_name}_middle", None)

        if upper is None or lower is None:
            # Try alternative naming
            upper = tick.get_indicator("bb_upper", self.last_upper)
            lower = tick.get_indicator("bb_lower", self.last_lower)
            middle = tick.get_indicator("bb_middle", self.last_middle)

        if upper is None or lower is None:
            return None

        price = float(tick.price)
        signal = None

        # Price touches or crosses below lower band (oversold) -> BUY
        if price <= lower and not self.in_position:
            self.in_position = True
            self.band_touch_count += 1
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=min(1.0, (lower - price) / lower + 1.0),
                metadata={
                    "price": price,
                    "upper_band": upper,
                    "lower_band": lower,
                    "middle_band": middle,
                    "bandwidth": upper - lower,
                    "touch_type": "lower_band",
                    "touch_count": self.band_touch_count,
                },
            )
            logger.info(
                f"[{self._strategy_id}] BUY signal: " f"Price={price:.2f} <= Lower={lower:.2f}"
            )

        # Price touches or crosses above upper band (overbought) -> SELL
        elif price >= upper and self.in_position:
            self.in_position = False
            self.band_touch_count += 1
            signal = Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=min(1.0, (price - upper) / upper + 1.0),
                metadata={
                    "price": price,
                    "upper_band": upper,
                    "lower_band": lower,
                    "middle_band": middle,
                    "bandwidth": upper - lower,
                    "touch_type": "upper_band",
                    "touch_count": self.band_touch_count,
                },
            )
            logger.info(
                f"[{self._strategy_id}] SELL signal: " f"Price={price:.2f} >= Upper={upper:.2f}"
            )

        # Update state
        self.last_price = price
        self.last_upper = upper
        self.last_lower = lower
        self.last_middle = middle if middle else (upper + lower) / 2.0

        return signal

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update(
            {
                "last_price": self.last_price,
                "last_upper": self.last_upper,
                "last_lower": self.last_lower,
                "last_middle": self.last_middle,
                "in_position": self.in_position,
                "band_touch_count": self.band_touch_count,
            }
        )
        return stats
