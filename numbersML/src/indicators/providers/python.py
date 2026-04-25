"""
Python Indicator Provider - Explicit Registration

Loads indicators from explicitly registered Python classes.
No magic discovery - you register what you want to use.

Use Cases:
    - Development (quick testing)
    - Unit tests (controlled environment)
    - Integration tests (specific indicators)

Example:
    >>> from src.indicators.momentum import RSIIndicator
    >>> from src.indicators.trend import SMAIndicator
    >>> 
    >>> provider = PythonIndicatorProvider({
    ...     'rsi_14': RSIIndicator,
    ...     'sma_20': SMAIndicator,
    ... })
    >>> 
    >>> rsi = provider.get_indicator('rsi_14')
    >>> assert rsi is not None
    >>> 
    >>> # With custom parameters
    >>> rsi_custom = provider.get_indicator('rsi_14', period=21)
"""

from typing import Dict, List, Optional, Type, Any
import logging

from typing_extensions import override

from ..base import Indicator
from .provider import IIndicatorProvider

logger = logging.getLogger(__name__)


class PythonIndicatorProvider(IIndicatorProvider):
    """
    Indicator provider with explicit Python class registration.
    
    This provider requires you to explicitly register indicator classes,
    providing full control and testability.
    
    Attributes:
        _indicators: Dict mapping name → Indicator class
    
    Example:
        >>> provider = PythonIndicatorProvider({
        ...     'rsi_14': RSIIndicator,
        ...     'sma_20': SMAIndicator,
        ... })
        >>> 
        >>> # List available indicators
        >>> provider.list_indicators()
        ['rsi_14', 'sma_20']
        >>> 
        >>> # Get indicator instance
        >>> rsi = provider.get_indicator('rsi_14')
        >>> assert rsi.params['period'] == 14
        >>> 
        >>> # Get with custom parameters
        >>> rsi_21 = provider.get_indicator('rsi_14', period=21)
        >>> assert rsi_21.params['period'] == 21
    """
    
    def __init__(
        self,
        indicator_classes: Optional[Dict[str, Type[Indicator]]] = None
    ) -> None:
        """
        Initialize provider with indicator classes.
        
        Args:
            indicator_classes: Dict mapping name → Indicator class
                              If None, starts empty (use register())
        """
        self._indicators: Dict[str, Type[Indicator]] = {}
        
        if indicator_classes:
            for name, cls in indicator_classes.items():
                self.register(name, cls)
    
    def register(self, name: str, indicator_class: Type[Indicator]) -> None:
        """
        Register an indicator class.
        
        Args:
            name: Name to register under (e.g., 'rsi_14')
            indicator_class: Indicator class to register
        
        Example:
            >>> provider = PythonIndicatorProvider()
            >>> provider.register('rsi_14', RSIIndicator)
        """
        self._indicators[name] = indicator_class
        logger.debug(f"Registered indicator: {name} = {indicator_class.__name__}")
    
    def unregister(self, name: str) -> None:
        """
        Unregister an indicator.
        
        Args:
            name: Name to unregister
        """
        if name in self._indicators:
            del self._indicators[name]
            logger.debug(f"Unregistered indicator: {name}")
    
    def get_indicator(
        self,
        name: str,
        **params: Any
    ) -> Optional[Indicator]:
        """
        Get indicator instance by name.
        
        Args:
            name: Indicator name (e.g., 'rsi_14')
            **params: Optional parameters to override defaults
        
        Returns:
            Indicator instance or None if not registered
        
        Example:
            >>> provider = PythonIndicatorProvider({'rsi_14': RSIIndicator})
            >>> 
            >>> # Default parameters
            >>> rsi = provider.get_indicator('rsi_14')
            >>> assert rsi.params['period'] == 14
            >>> 
            >>> # Custom parameters
            >>> rsi = provider.get_indicator('rsi_14', period=21)
            >>> assert rsi.params['period'] == 21
        """
        if name not in self._indicators:
            logger.debug(f"Indicator not registered: {name}")
            return None
        
        indicator_class = self._indicators[name]
        
        try:
            if params:
                # Create with custom parameters
                indicator = indicator_class(**params)
                logger.debug(f"Created {name} with params: {params}")
            else:
                # Create with default parameters
                indicator = indicator_class()
                logger.debug(f"Created {name} with defaults")
            
            return indicator
            
        except Exception as e:
            logger.error(f"Failed to create indicator {name}: {e}")
            return None
    
    def list_indicators(self) -> List[str]:
        """
        List all registered indicator names.
        
        Returns:
            List of indicator names
        
        Example:
            >>> provider = PythonIndicatorProvider({
            ...     'rsi_14': RSIIndicator,
            ...     'sma_20': SMAIndicator,
            ... })
            >>> provider.list_indicators()
            ['rsi_14', 'sma_20']
        """
        return list(self._indicators.keys())
    
    def is_available(self, name: str) -> bool:
        """
        Check if indicator is registered.
        
        Args:
            name: Indicator name to check
        
        Returns:
            True if indicator is registered
        
        Example:
            >>> provider = PythonIndicatorProvider({'rsi_14': RSIIndicator})
            >>> provider.is_available('rsi_14')
            True
            >>> provider.is_available('nonexistent')
            False
        """
        return name in self._indicators
    
    def get_indicator_class(self, name: str) -> Optional[Type[Indicator]]:
        """
        Get indicator class (not instance) by name.
        
        Args:
            name: Indicator name
        
        Returns:
            Indicator class or None if not registered
        
        Example:
            >>> provider = PythonIndicatorProvider({'rsi_14': RSIIndicator})
            >>> cls = provider.get_indicator_class('rsi_14')
            >>> assert cls == RSIIndicator
        """
        return self._indicators.get(name)
    
    def clear(self) -> None:
        """
        Clear all registered indicators.
        
        Example:
            >>> provider = PythonIndicatorProvider({'rsi_14': RSIIndicator})
            >>> provider.clear()
            >>> provider.list_indicators()
            []
        """
        self._indicators.clear()
        logger.debug("Cleared all registered indicators")

    @override
    async def list_indicators_async(self) -> List[str]:
        """Async version of list_indicators."""
        return self.list_indicators()
    
    @override
    async def get_indicator_async(self, name: str, **params: Any) -> Optional[Indicator]:
        """Async version of get_indicator."""
        return self.get_indicator(name, **params)
