"""Domain repository port for strategy lifecycle persistence."""

from abc import abstractmethod
from typing import Any
from uuid import UUID

from ..strategies.strategy_config import StrategyConfigVersion, StrategyDefinition
from .base import Repository


class StrategyRepository(Repository[StrategyDefinition, UUID]):
    """Repository contract for strategy definitions and versions."""

    @abstractmethod
    async def get_by_name(self, name: str) -> StrategyDefinition | None:
        """Fetch a strategy definition by unique name."""

    @abstractmethod
    async def list_versions(self, strategy_id: UUID) -> list[StrategyConfigVersion]:
        """Return all known versions for a strategy."""

    @abstractmethod
    async def create_version(
        self,
        strategy_id: UUID,
        config: dict[str, Any],
        schema_version: int,
        created_by: str = "system",
    ) -> StrategyConfigVersion:
        """Create and return the next strategy version."""

    @abstractmethod
    async def set_active_version(self, strategy_id: UUID, version: int) -> bool:
        """Set one strategy version as active and update definition status."""
