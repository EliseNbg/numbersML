"""Domain repositories - Ports for data access."""

from .base import Repository
from .algorithm_repository import AlgorithmRepository

__all__ = ["Repository", "AlgorithmRepository"]
