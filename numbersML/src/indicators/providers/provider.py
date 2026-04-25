"""
Indicator Provider Pattern - Clean Architecture for Indicators

This module provides a clean abstraction for indicator loading and management,
replacing the fragile pkgutil-based discovery with explicit provider pattern.

Architecture:
    IIndicatorProvider (interface)
    ├─ DatabaseIndicatorProvider (production - loads from DB)
    ├─ PythonIndicatorProvider (dev/tests - explicit registration)
    └─ MockIndicatorProvider (tests - mock indicators)

Benefits:
    - Test-friendly (easy to mock)
    - No magic (no pkgutil discovery)
    - Single source of truth (database)
    - Loose coupling (dependency injection)

Usage:
    # Production
    provider = DatabaseIndicatorProvider(db_pool)
    rsi = provider.get_indicator('rsi_14')
    result = rsi.calculate(prices, volumes)
    
    # Tests
    provider = PythonIndicatorProvider({'rsi_14': RSIIndicator})
    rsi = provider.get_indicator('rsi_14')
    
    # Mock tests
    provider = MockIndicatorProvider()
    rsi = provider.get_indicator('rsi_14')
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type, Any
import logging

from ..base import Indicator
from ..base import IndicatorResult

logger = logging.getLogger(__name__)


class IIndicatorProvider(ABC):
    """
    Interface for indicator providers.
    
    This abstraction allows different loading strategies:
    - Database loading (production)
    - Python class loading (development/tests)
    - Mock loading (unit tests)
    
    Example:
        >>> provider = DatabaseIndicatorProvider(db_pool)
        >>> rsi = provider.get_indicator('rsi_14')
        >>> result = rsi.calculate(prices, volumes)
    """
    
    @abstractmethod
    def get_indicator(self, name: str, **params: Any) -> Optional[Indicator]:
        """
        Get indicator instance by name.
        
        Args:
            name: Indicator name (e.g., 'rsi_14')
            **params: Optional parameters to override defaults
        
        Returns:
            Indicator instance or None if not available
        """
        pass
    
    @abstractmethod
    def list_indicators(self) -> List[str]:
        """
        List all available indicator names.
        
        Returns:
            List of indicator names
        """
        pass
    
    @abstractmethod
    def is_available(self, name: str) -> bool:
        """
        Check if indicator is available.
        
        Args:
            name: Indicator name to check
        
        Returns:
            True if indicator is available
        """
        pass
    
    @abstractmethod
    def get_indicator_class(self, name: str) -> Optional[Type[Indicator]]:
        """
        Get indicator class (not instance) by name.
        
        Args:
            name: Indicator name
        
        Returns:
            Indicator class or None if not available
        """
        pass
    
    @abstractmethod
    async def list_indicators_async(self) -> List[str]:
        """
        Async version to list all available indicator names.
        
        Returns:
            List of indicator names
        """
        pass
    
    @abstractmethod
    async def get_indicator_async(self, name: str, **params: Any) -> Optional[Indicator]:
        """
        Async version to get indicator instance by name.
        
        Args:
            name: Indicator name (e.g., 'rsi_14')
            **params: Optional parameters to override defaults
        
        Returns:
            Indicator instance or None if not available
        """
        pass
