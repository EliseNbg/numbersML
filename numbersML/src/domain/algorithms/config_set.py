"""
ConfigurationSet domain entity.

Represents a reusable set of configuration parameters that can be
linked to multiple algorithms. Follows DDD Entity pattern.

Architecture: Domain Layer (pure Python, no external dependencies)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from src.domain.models.base import Entity


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """
    Immutable snapshot of configuration at a point in time.

    Used for audit trail and backtesting reproducibility.

    Attributes:
        config: Configuration dictionary at time of snapshot
        captured_at: Timestamp when snapshot was taken
        captured_by: User or system that made the change

    Example:
        >>> snapshot = ConfigurationSnapshot(
        ...     config={"symbols": ["BTC/USDT"]},
        ...     captured_by="admin"
        ... )
    """

    config: dict[str, Any]
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    captured_by: str = "system"


class ConfigurationSet(Entity):
    """
    Domain entity for algorithm configuration sets.

    Encapsulates all runtime parameters needed by a algorithm:
    - Trading symbols
    - Indicator thresholds
    - Risk parameters
    - Execution parameters

    Lifecycle:
        Created → Active → (optionally) Archived

    Example:
        >>> config_set = ConfigurationSet(
        ...     name="Conservative BTC",
        ...     config={"symbols": ["BTC/USDT"], "risk": {"max_position_size_pct": 5}}
        ... )
        >>> config_set.is_active
        True
    """

    def __init__(
        self,
        name: str,
        config: dict[str, Any],
        description: str | None = None,
        id: UUID | None = None,
        is_active: bool = True,
        created_by: str = "system",
    ) -> None:
        """
        Initialize ConfigurationSet.

        Args:
            name: Human-readable name
            config: Configuration dictionary (validated on set)
            description: Optional description
            id: UUID (auto-generated if None)
            is_active: Whether this config set is available for use
            created_by: User or system identifier

        Raises:
            ValueError: If name is empty or config is invalid
        """
        super().__init__(id or uuid4())

        if not name or not name.strip():
            raise ValueError("ConfigurationSet name cannot be empty")
        if not config:
            raise ValueError("ConfigurationSet config cannot be empty")

        self._name = name
        self._description = description
        self._config = config
        self._is_active = is_active
        self._created_by = created_by
        self.created_at = datetime.now(UTC)
        self.updated_at = self.created_at
        self._version = 1
        self._snapshots: list[ConfigurationSnapshot] = []

    @property
    def name(self) -> str:
        """Get configuration set name."""
        return self._name

    @property
    def description(self) -> str | None:
        """Get description."""
        return self._description

    @property
    def config(self) -> dict[str, Any]:
        """Get configuration (defensive copy)."""
        return self._config.copy()

    @property
    def is_active(self) -> bool:
        """Check if configuration set is active."""
        return self._is_active

    @property
    def created_by(self) -> str:
        """Get creator identifier."""
        return self._created_by

    @property
    def version(self) -> int:
        """Get config version (increments on update)."""
        return self._version

    def update_config(self, new_config: dict[str, Any], updated_by: str = "system") -> None:
        """
        Update configuration, creating a snapshot for audit trail.

        Args:
            new_config: New configuration dictionary
            updated_by: User making the change

        Raises:
            ValueError: If new_config is empty or invalid
        """
        if not new_config:
            raise ValueError("New configuration cannot be empty")

        snapshot = ConfigurationSnapshot(
            config=self._config.copy(),
            captured_by=updated_by,
        )
        self._snapshots.append(snapshot)

        self._config = new_config
        self.updated_at = datetime.now(UTC)
        self._version += 1

    def get_symbols(self) -> list[str]:
        """
        Get list of trading symbols from config.

        Returns:
            List of symbol strings, empty list if not configured
        """
        symbols = self._config.get("symbols", [])
        if isinstance(symbols, list):
            return symbols
        return []

    def get_risk_param(self, key: str, default: Any = None) -> Any:
        """
        Get risk parameter by key.

        Args:
            key: Parameter key
            default: Default value if not found

        Returns:
            Parameter value or default
        """
        risk_config = self._config.get("risk", {})
        return risk_config.get(key, default)

    def get_threshold(self, indicator: str, default: Any = None) -> Any:
        """
        Get indicator threshold by indicator name.

        Args:
            indicator: Indicator name (e.g., 'rsi_oversold')
            default: Default value if not found

        Returns:
            Threshold value or default
        """
        thresholds = self._config.get("thresholds", {})
        return thresholds.get(indicator, default)

    def deactivate(self) -> None:
        """Deactivate this configuration set (soft delete)."""
        self._is_active = False
        self.updated_at = datetime.now(UTC)

    def activate(self) -> None:
        """Activate this configuration set."""
        self._is_active = True
        self.updated_at = datetime.now(UTC)

    def get_snapshots(self) -> list[ConfigurationSnapshot]:
        """Get audit trail of configuration changes."""
        return self._snapshots.copy()

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "id": str(self.id),
            "name": self._name,
            "description": self._description,
            "config": self._config.copy(),
            "is_active": self._is_active,
            "created_by": self._created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self._version,
        }
