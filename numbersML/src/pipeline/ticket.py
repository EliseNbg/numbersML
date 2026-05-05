"""
Pipeline Ticket for controlling which steps execute per candle.

Each candle emission creates a PipelineTicket that specifies which steps
to run. This decouples step execution from data production and allows
the same pipeline to be reused for different scenarios.

Scenarios:
    LIVE     = {1, 2, 3}  — live data collection (candles + indicators + vectors)
    BACKFILL = {1, 2, 3}  — historical gap filling (same steps, different data source)
    BACKTEST = {4, 6}     — algorithm evaluation on historical data
    PREDICT  = {3, 4}     — ML inference only (on existing data)

Step dependencies (order matters):
    1 (candle) → 2 (indicators need candle) → 3 (vector needs indicators)
                                                 → 4 (ML needs vector) → 5 (trade needs ML)
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.pipeline.aggregator import TradeAggregation


class PipelineStep(IntEnum):
    """Pipeline execution steps, ordered by dependency."""

    CANDLE = 1  # Write 1s OHLCV candle to database
    INDICATOR = 2  # Calculate and store technical indicators
    WIDE_VECTOR = 3  # Build and store ML-ready vector (all symbols)
    ML_PREDICT = 4  # Run ML model inference (future)
    TRADE_EXEC = 5  # Execute trading signal via Binance (future)
    PAPER_TRADE = 6  # Paper trading for backtesting (future)


# Preset step combinations for common scenarios
LIVE_STEPS = frozenset({PipelineStep.CANDLE, PipelineStep.INDICATOR, PipelineStep.WIDE_VECTOR})
BACKFILL_STEPS = frozenset({PipelineStep.CANDLE, PipelineStep.INDICATOR, PipelineStep.WIDE_VECTOR})
BACKTEST_STEPS = frozenset({PipelineStep.ML_PREDICT, PipelineStep.PAPER_TRADE})


@dataclass(frozen=True)
class PipelineTicket:
    """
    Controls which pipeline steps execute for a candle.

    Attributes:
        steps: Set of step IDs to execute
        symbol: Trading pair (e.g., 'BTC/USDC')
        candle_time: Time of the candle being processed
        candle: The candle data (None for cross-symbol steps)
    """

    steps: frozenset[int]
    symbol: str
    candle_time: object  # datetime, avoids import
    candle: Optional["TradeAggregation"] = None

    def has(self, step: PipelineStep) -> bool:
        """Check if a step should be executed."""
        return step in self.steps
