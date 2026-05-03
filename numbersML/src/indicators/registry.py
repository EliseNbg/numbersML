"""
Indicator registry with auto-discovery.

Automatically discovers and registers all indicator classes
from the indicators package.
"""

import importlib
import pkgutil
from typing import Any, Optional

from .base import Indicator


class IndicatorRegistry:
    """
    Registry for all available indicators.

    Auto-discovers indicators from modules and provides
    factory methods for creating indicator instances.
    """

    _indicators: dict[str, type[Indicator]] = {}

    @classmethod
    def discover(cls) -> None:
        """Auto-discover all indicator classes."""
        try:
            import indicators

            for importer, modname, ispkg in pkgutil.iter_modules(indicators.__path__):
                try:
                    module = importlib.import_module(f"indicators.{modname}")

                    for name in dir(module):
                        obj = getattr(module, name)

                        # Check if it's an indicator class
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, Indicator)
                            and obj is not Indicator
                        ):
                            cls.register(obj)

                except ImportError as e:
                    # Skip modules with missing dependencies (e.g., TA-Lib)
                    print(f"Warning: Could not import indicators.{modname}: {e}")

        except ImportError:
            print("Warning: indicators package not found")

    @classmethod
    def register(cls, indicator_class: type[Indicator]) -> None:
        """Register an indicator class."""
        try:
            instance = indicator_class()
            cls._indicators[instance.name] = indicator_class
        except Exception as e:
            print(f"Warning: Could not register {indicator_class.__name__}: {e}")

    @classmethod
    def get(
        cls,
        name: str,
        **params: Any,
    ) -> Optional[Indicator]:
        """
        Get indicator instance by name.

        Args:
            name: Indicator name (e.g., 'rsi_14')
            **params: Parameters to override defaults

        Returns:
            Indicator instance or None if not found
        """
        if name not in cls._indicators:
            return None

        indicator_class = cls._indicators[name]

        try:
            return indicator_class(**params)
        except Exception as e:
            print(f"Error creating indicator {name}: {e}")
            return None

    @classmethod
    def list_indicators(
        cls,
        category: Optional[str] = None,
    ) -> list[str]:
        """
        List all registered indicators.

        Args:
            category: Filter by category (optional)

        Returns:
            List of indicator names
        """
        if category:
            return [
                name
                for name, indicator_class in cls._indicators.items()
                if indicator_class.category == category
            ]
        return list(cls._indicators.keys())

    @classmethod
    def get_indicator_class(cls, name: str) -> Optional[type[Indicator]]:
        """Get indicator class by name."""
        return cls._indicators.get(name)

    @classmethod
    def get_all_categories(cls) -> list[str]:
        """Get all indicator categories."""
        categories = set()
        for indicator_class in cls._indicators.values():
            categories.add(indicator_class.category)
        return sorted(list(categories))
