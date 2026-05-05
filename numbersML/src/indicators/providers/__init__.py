"""
Indicator Providers Package

This package provides different indicator loading algorithms:

- provider: IIndicatorProvider interface
- python: PythonIndicatorProvider (explicit registration)
- mock: MockIndicatorProvider (for testing)
- database: DatabaseIndicatorProvider (production, from DB)

Usage:
    from src.indicators.providers import PythonIndicatorProvider
    from src.indicators.momentum import RSIIndicator

    provider = PythonIndicatorProvider({
        'rsi_14': RSIIndicator,
    })

    rsi = provider.get_indicator('rsi_14')
"""

from .database import DatabaseIndicatorProvider
from .mock import MockIndicatorProvider
from .provider import IIndicatorProvider
from .python import PythonIndicatorProvider

__all__ = [
    "IIndicatorProvider",
    "PythonIndicatorProvider",
    "MockIndicatorProvider",
    "DatabaseIndicatorProvider",
]
