"""Domain models for versioned strategy configuration."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class StrategyConfigVersion:
    """Immutable strategy config version payload."""

    strategy_id: UUID
    version: int
    schema_version: int
    config: dict[str, Any]
    is_active: bool = False
    created_by: str = "system"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: UUID | None = None


@dataclass
class StrategyDefinition:
    """Mutable strategy aggregate root used in lifecycle management."""

    name: str
    description: str | None
    mode: str = "paper"
    status: str = "draft"
    strategy_type: str = "config"  # 'config' or 'class'
    class_path: str | None = None  # e.g., "src.strategies.user.grid1.Grid1Strategy"
    current_version: int = 1
    config: dict[str, Any] = field(default_factory=dict)
    created_by: str = "system"
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_class_based(self) -> bool:
        """Check if this is a class-based strategy."""
        return self.strategy_type == "class"

    def is_config_based(self) -> bool:
        """Check if this is a config-based strategy."""
        return self.strategy_type == "config"
