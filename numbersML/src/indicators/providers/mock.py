"""
Mock Indicator Provider - For Unit Testing

Provides mock indicators that return predictable values for testing.
No actual calculations - just returns pre-defined values.

Use Cases:
    - Unit tests (isolate from indicator logic)
    - Performance tests (fast, no calculations)
    - Integration tests (controlled outputs)

Example:
    >>> provider = MockIndicatorProvider()
    >>> rsi = provider.get_indicator('rsi_14')
    >>> result = rsi.calculate(prices, volumes)
    >>> assert result.values['rsi'] == [55.0]  # Pre-defined value
"""

import logging
from typing import Any, Optional

import numpy as np
from typing_extensions import override

from ..base import Indicator, IndicatorResult
from .provider import IIndicatorProvider

logger = logging.getLogger(__name__)


class MockIndicator(Indicator):
    """
    Mock indicator for testing.

    Returns pre-defined values instead of calculating.
    Useful for isolating tests from indicator logic.

    Example:
        >>> mock_rsi = MockIndicator(
        ...     name='rsi_14',
        ...     output_name='rsi',
        ...     value=55.0
        ... )
        >>> result = mock_rsi.calculate(prices, volumes)
        >>> assert result.values['rsi'] == [55.0]
    """

    category = "mock"
    description = "Mock indicator for testing"
    version = "1.0.0"

    def __init__(
        self,
        name: str = "mock_indicator",
        output_name: str = "mock",
        value: float = 50.0,
        **params: Any,
    ) -> None:
        """
        Initialize mock indicator.

        Args:
            name: Indicator name
            output_name: Output key name
            value: Pre-defined value to return
            **params: Additional parameters (ignored)
        """
        super().__init__(**params)
        self._name = name
        self._output_name = output_name
        self._value = value

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Return parameter schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {},
        }

    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        opens: Optional[np.ndarray] = None,
    ) -> IndicatorResult:
        """
        Return pre-defined mock values.

        Returns array of same length as input, filled with mock value.
        """
        length = len(prices)
        mock_values = np.full(length, self._value)

        return IndicatorResult(
            name=self._name,
            values={self._output_name: mock_values},
            metadata={
                "mock": True,
                "value": self._value,
            },
        )


class MockIndicatorProvider(IIndicatorProvider):
    """
    Provider of mock indicators for testing.

    Automatically provides any requested indicator as a mock.
    No registration needed - just request and receive.

    Example:
        >>> provider = MockIndicatorProvider()
        >>>
        >>> # Any indicator name works
        >>> rsi = provider.get_indicator('rsi_14')
        >>> macd = provider.get_indicator('macd')
        >>>
        >>> # All return mock indicators
        >>> assert rsi is not None
        >>> assert macd is not None
        >>>
        >>> # Calculate returns mock values
        >>> result = rsi.calculate(prices, volumes)
        >>> assert result.metadata['mock'] is True
    """

    def __init__(
        self, default_value: float = 50.0, custom_indicators: Optional[dict[str, float]] = None
    ) -> None:
        """
        Initialize mock provider.

        Args:
            default_value: Default mock value for all indicators
            custom_indicators: Dict mapping name → custom value
        """
        self._default_value = default_value
        self._custom_values: dict[str, float] = custom_indicators or {}

    def get_indicator(self, name: str, **params: Any) -> Optional[Indicator]:
        """
        Get mock indicator by name.

        Always returns a MockIndicator, regardless of name.

        Args:
            name: Indicator name (any string works)
            **params: Parameters (ignored, but accepted for compatibility)

        Returns:
            MockIndicator instance

        Example:
            >>> provider = MockIndicatorProvider(default_value=55.0)
            >>> rsi = provider.get_indicator('rsi_14')
            >>> result = rsi.calculate(prices, volumes)
            >>> assert all(v == 55.0 for v in result.values['mock'])
        """
        # Get custom value or use default
        value = self._custom_values.get(name, self._default_value)

        # Create mock indicator
        indicator = MockIndicator(name=name, output_name="mock", value=value, **params)

        logger.debug(f"Created mock indicator: {name} (value={value})")
        return indicator

    def list_indicators(self) -> list[str]:
        """
        List available mock indicators.

        Returns empty list (mocks are created on-demand).

        Returns:
            Empty list
        """
        return []

    def is_available(self, name: str) -> bool:
        """
        Check if mock indicator is available.

        Always returns True (mocks are created on-demand).

        Args:
            name: Indicator name

        Returns:
            True (always)
        """
        return True

    def get_indicator_class(self, name: str) -> Optional[type[Indicator]]:
        """
        Get mock indicator class.

        Returns:
            MockIndicator class
        """
        return MockIndicator

    def set_value(self, name: str, value: float) -> None:
        """
        Set custom mock value for specific indicator.

        Args:
            name: Indicator name
            value: Mock value to return

        Example:
            >>> provider = MockIndicatorProvider()
            >>> provider.set_value('rsi_14', 75.0)  # Overbought
            >>> rsi = provider.get_indicator('rsi_14')
            >>> result = rsi.calculate(prices, volumes)
            >>> assert all(v == 75.0 for v in result.values['mock'])
        """
        self._custom_values[name] = value
        logger.debug(f"Set mock value for {name}: {value}")

    @override
    async def list_indicators_async(self) -> list[str]:
        """Async version of list_indicators."""
        return self.list_indicators()

    @override
    async def get_indicator_async(self, name: str, **params: Any) -> Optional[Indicator]:
        """Async version of get_indicator."""
        return self.get_indicator(name, **params)
