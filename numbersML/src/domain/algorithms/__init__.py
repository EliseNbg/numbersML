"""
Algorithms - Trading algorithm framework.

Provides base classes and interfaces for implementing
trading algorithms that consume enriched tick data.

Sample Algorithms:
    - RSIAlgorithm: RSI oversold/overbought
    - MACDAlgorithm: MACD crossover
    - SMACrossoverAlgorithm: SMA golden/death cross
    - BollingerBandsAlgorithm: BB mean reversion
    - MultiIndicatorAlgorithm: Composite algorithm
"""

from src.domain.algorithms.base import (
    Algorithm,
    EnrichedTick,
    Position,
    Signal,
    SignalType,
    AlgorithmManager,
    TimeFrame,
)
from src.domain.algorithms.runtime import (
    AlgorithmLifecycleEvent,
)
from src.domain.algorithms.algorithms_impl import (
    BollingerBandsAlgorithm,
    MACDAlgorithm,
    MultiIndicatorAlgorithm,
    RSIAlgorithm,
    SMACrossoverAlgorithm,
)
from src.domain.algorithms.algorithm_config import (
    AlgorithmConfigVersion,
    AlgorithmDefinition,
)
from src.domain.algorithms.strategy_instance import (
    VALID_TRANSITIONS,
    StrategyInstanceState,
)

__all__ = [
    # Base classes
    "Algorithm",
    "AlgorithmManager",
    "Signal",
    "Position",
    "EnrichedTick",
    "SignalType",
    "TimeFrame",
    "StrategyInstanceState",
    # Sample algorithms
    "RSIAlgorithm",
    "MACDAlgorithm",
    "SMACrossoverAlgorithm",
    "BollingerBandsAlgorithm",
    "MultiIndicatorAlgorithm",
    # Runtime and lifecycle
    "AlgorithmLifecycleEvent",
    "VALID_TRANSITIONS",
    # Configuration
    "AlgorithmConfigVersion",
    "AlgorithmDefinition",
]
