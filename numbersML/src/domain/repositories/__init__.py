"""Domain repositories - Ports for data access."""

from .base import Repository
from .strategy_repository import StrategyRepository

__all__ = ["Repository", "StrategyRepository"]
