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


@dataclass
class StrategyDefinition:
    """Mutable strategy aggregate root used in lifecycle management."""

    name: str
    description: str | None
    mode: str = "paper"
    status: str = "draft"
    current_version: int = 1
    created_by: str = "system"
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
