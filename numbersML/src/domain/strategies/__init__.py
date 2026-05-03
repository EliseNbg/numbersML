"""
Strategies - Trading strategy framework.

Provides base classes and interfaces for implementing
trading strategies that consume enriched tick data.

Sample Strategies:
    - RSIStrategy: RSI oversold/overbought
    - MACDStrategy: MACD crossover
    - SMACrossoverStrategy: SMA golden/death cross
    - BollingerBandsStrategy: BB mean reversion
    - MultiIndicatorStrategy: Composite strategy
"""

from src.domain.strategies.base import (
    EnrichedTick,
    Position,
    Signal,
    SignalType,
    Strategy,
    StrategyManager,
    TimeFrame,
)
from src.domain.strategies.strategies import (
    BollingerBandsStrategy,
    MACDStrategy,
    MultiIndicatorStrategy,
    RSIStrategy,
    SMACrossoverStrategy,
)
from src.domain.strategies.strategy_instance import StrategyInstanceState

__all__ = [
    # Base classes
    "Strategy",
    "StrategyManager",
    "Signal",
    "Position",
    "EnrichedTick",
    "SignalType",
    "TimeFrame",
    "StrategyInstanceState",
    # Sample strategies
    "RSIStrategy",
    "MACDStrategy",
    "SMACrossoverStrategy",
    "BollingerBandsStrategy",
    "MultiIndicatorStrategy",
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
