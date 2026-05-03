"""
Strategies - Trading strategy framework.

Provides base classes and interfaces for implementing
trading algorithms that consume enriched tick data.

Sample Strategies:
    - RSIAlgorithm: RSI oversold/overbought
    - MACDAlgorithm: MACD crossover
    - SMACrossoverAlgorithm: SMA golden/death cross
    - BollingerBandsAlgorithm: BB mean reversion
    - MultiIndicatorAlgorithm: Composite strategy
"""

from src.domain.strategies.base import (
    Algorithm,
    EnrichedTick,
    Position,
    Signal,
    SignalType,
    StrategyManager,
    TimeFrame,
)
from src.domain.strategies.strategies import (
    BollingerBandsAlgorithm,
    MACDAlgorithm,
    MultiIndicatorAlgorithm,
    RSIAlgorithm,
    SMACrossoverAlgorithm,
)
from src.domain.strategies.strategy_instance import StrategyInstanceState

__all__ = [
    # Base classes
    "Algorithm",
    "StrategyManager",
    "Signal",
    "Position",
    "EnrichedTick",
    "SignalType",
    "TimeFrame",
    "StrategyInstanceState",
    # Sample strategies
    "RSIAlgorithm",
    "MACDAlgorithm",
    "SMACrossoverAlgorithm",
    "BollingerBandsAlgorithm",
    "MultiIndicatorAlgorithm",
]


__all__.extend(
    [
        "StrategyRuntimeState",
        "StrategyLifecycleEvent",
        "VALID_TRANSITIONS",
        "StrategyConfigVersion",
        "StrategyDefinition",
    ]
)
