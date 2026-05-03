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

from src.domain.strategies.strategy_instance import StrategyInstanceState

from src.domain.strategies.base import (
    Strategy,
    StrategyManager,
    Signal,
    Position,
    EnrichedTick,
    SignalType,
    TimeFrame,
)

from src.domain.strategies.strategies import (
    RSIStrategy,
    MACDStrategy,
    SMACrossoverStrategy,
    BollingerBandsStrategy,
    MultiIndicatorStrategy,
)

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

from src.domain.strategies.runtime import (
    StrategyRuntimeState,
    StrategyLifecycleEvent,
    VALID_TRANSITIONS,
)
from src.domain.strategies.strategy_config import (
    StrategyConfigVersion,
    StrategyDefinition,
)

__all__.extend(
    [
        "StrategyRuntimeState",
        "StrategyLifecycleEvent",
        "VALID_TRANSITIONS",
        "StrategyConfigVersion",
        "StrategyDefinition",
    ]
)
