"""Example RSI strategy written as a user-defined Python class.

This strategy demonstrates:
- Persistent state between ticks
- Access to indicators from EnrichedTick
- Access to configuration values
- BUY/SELL signal generation
"""

import logging
from decimal import Decimal
from typing import Optional, Any

from src.domain.strategies.base import Strategy, Signal, SignalType, EnrichedTick

logger = logging.getLogger(__name__)


class ExampleRSIStrategy(Strategy):
    """RSI-based strategy with persistent state.
    
    State:
        - tick_count: Number of ticks processed
        - last_rsi: Last RSI value seen
        - position_open: Whether we have an open position
    
    Configuration (accessed via self.get_config):
        - oversold_threshold: RSI value to trigger BUY (default: 30)
        - overbought_threshold: RSI value to trigger SELL (default: 70)
        - rsi_indicator_name: Name of RSI indicator in tick data
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: "TimeFrame | None" = None,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)
        
        # Persistent state between ticks
        self.tick_count: int = 0
        self.last_rsi: float = 0.0
        self.position_open: bool = False
        
        logger.info(f"ExampleRSIStrategy {strategy_id} initialized with state")

    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """Process tick and generate RSI-based signals.
        
        Args:
            tick: Enriched tick data with indicators
            
        Returns:
            Signal if conditions met, None otherwise
        """
        # Update persistent state
        self.tick_count += 1
        
        # Get configuration values
        oversold = self.get_config("oversold_threshold", 30)
        overbought = self.get_config("overbought_threshold", 70)
        rsi_name = self.get_config("rsi_indicator_name", "rsiindicator_period14_rsi")
        
        # Access indicator from tick
        rsi = tick.get_indicator(rsi_name, 50.0)
        self.last_rsi = rsi
        
        # Log every 100 ticks
        if self.tick_count % 100 == 0:
            logger.info(
                f"[{self._strategy_id}] Tick #{self.tick_count}, "
                f"RSI={rsi:.2f}, Price={tick.price}, State: pos_open={self.position_open}"
            )
        
        # Generate BUY signal when RSI crosses below oversold threshold
        if rsi < oversold and not self.position_open:
            self.position_open = True
            logger.info(
                f"[{self._strategy_id}] BUY signal: RSI={rsi:.2f} < {oversold}"
            )
            return Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=1.0 - (rsi / 100.0),  # Higher confidence when RSI is lower
                metadata={
                    "rsi": rsi,
                    "threshold": oversold,
                    "tick_count": self.tick_count,
                },
            )
        
        # Generate SELL signal when RSI crosses above overbought threshold
        if rsi > overbought and self.position_open:
            self.position_open = False
            logger.info(
                f"[{self._strategy_id}] SELL signal: RSI={rsi:.2f} > {overbought}"
            )
            return Signal(
                strategy_id=self._strategy_id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=rsi / 100.0,  # Higher confidence when RSI is higher
                metadata={
                    "rsi": rsi,
                    "threshold": overbought,
                    "tick_count": self.tick_count,
                },
            )
        
        return None

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update({
            "tick_count": self.tick_count,
            "last_rsi": self.last_rsi,
            "position_open": self.position_open,
        })
        return stats
