"""
Configuration entities.

This module contains domain models for configuration management.
These are pure Python classes with no external dependencies (DDD Domain Layer).

Entities:
    - ConfigEntry: Single configuration entry
    - SymbolConfig: Symbol configuration
    - IndicatorConfig: Indicator configuration
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ConfigEntry:
    """
    Single configuration entry from system_config table.

    Attributes:
        id: Unique identifier
        key: Configuration key
        value: Configuration value (JSON)
        description: Human-readable description
        is_sensitive: Whether value contains sensitive data
        is_editable: Whether value can be modified
        version: Version number for optimistic locking
        updated_at: Last update timestamp
        updated_by: User who last updated

    Example:
        >>> entry = ConfigEntry(
        ...     id=1,
        ...     key='collector.batch_size',
        ...     value={'size': 500},
        ...     description='Batch size for collector',
        ...     is_editable=True,
        ... )
    """

    id: int
    key: str
    value: dict[str, Any]
    description: Optional[str] = None
    is_sensitive: bool = False
    is_editable: bool = True
    version: int = 1
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


@dataclass
class SymbolConfig:
    """
    Symbol configuration from symbols table.

    Attributes:
        symbol_id: Unique identifier
        symbol: Symbol string (e.g., 'BTC/USDT')
        base_asset: Base asset (e.g., 'BTC')
        quote_asset: Quote asset (e.g., 'USDT')
        is_active: Whether symbol is being collected
        is_allowed: Whether symbol is allowed (EU compliance)
        tick_size: Price precision
        step_size: Quantity precision
        min_notional: Minimum notional value

    Example:
        >>> symbol = SymbolConfig(
        ...     symbol_id=1,
        ...     symbol='BTC/USDT',
        ...     base_asset='BTC',
        ...     quote_asset='USDT',
        ...     is_active=True,
        ...     is_allowed=True,
        ... )
        >>> symbol.is_collectable
        True
    """

    symbol_id: int
    symbol: str
    base_asset: str
    quote_asset: str
    is_active: bool = True
    is_allowed: bool = True
    tick_size: float = 0.01
    step_size: float = 0.00001
    min_notional: float = 10.0

    @property
    def is_collectable(self) -> bool:
        """
        Check if symbol can be collected.

        Returns:
            True if active and allowed
        """
        return self.is_active and self.is_allowed

    @property
    def display_name(self) -> str:
        """
        Get human-readable symbol name.

        Returns:
            Symbol string (e.g., 'BTC/USDT')
        """
        return self.symbol


@dataclass
class IndicatorConfig:
    """
    Indicator configuration from indicator_definitions table.

    Attributes:
        name: Unique indicator name (e.g., 'rsi_14')
        class_name: Python class name (e.g., 'RSIIndicator')
        module_path: Python module path (e.g., 'src.indicators.momentum')
        category: Indicator category (momentum, trend, volatility, volume)
        params: Indicator parameters (JSON)
        is_active: Whether indicator is being calculated
        created_at: Creation timestamp
        updated_at: Last update timestamp

    Example:
        >>> indicator = IndicatorConfig(
        ...     name='rsi_14',
        ...     class_name='RSIIndicator',
        ...     module_path='src.indicators.momentum',
        ...     category='momentum',
        ...     params={'period': 14},
        ...     is_active=True,
        ... )
        >>> indicator.full_class_path
        'src.indicators.momentum.RSIIndicator'
    """

    name: str
    class_name: str
    module_path: str
    category: str
    params: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def full_class_path(self) -> str:
        """
        Get full Python class path for import.

        Returns:
            Full path (e.g., 'src.indicators.momentum.RSIIndicator')
        """
        return f"{self.module_path}.{self.class_name}"

    @property
    def display_name(self) -> str:
        """
        Get human-readable indicator name.

        Returns:
            Formatted name (e.g., 'RSI (14)')
        """
        # Convert name to readable format
        # e.g., 'rsi_14' → 'RSI (14)'
        parts = self.name.split("_")
        if len(parts) >= 2:
            name = parts[0].upper()
            params = "_".join(parts[1:])
            return f"{name} ({params})"
        return self.name.upper()

    @property
    def category_icon(self) -> str:
        """
        Get icon for indicator category.

        Returns:
            Bootstrap icon class
        """
        icons = {
            "momentum": "bi-speedometer2",
            "trend": "bi-graph-up",
            "volatility": "bi-activity",
            "volume": "bi-bar-chart",
        }
        return icons.get(self.category, "bi-gear")
