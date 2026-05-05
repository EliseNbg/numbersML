"""Domain repository port for algorithm lifecycle persistence."""

from abc import abstractmethod
from typing import Any
from uuid import UUID

from ..algorithms.algorithm_config import AlgorithmConfigVersion, AlgorithmDefinition
from .base import Repository


class AlgorithmRepository(Repository[AlgorithmDefinition, UUID]):
    """Repository contract for algorithm definitions and versions."""

    @abstractmethod
    async def get_by_name(self, name: str) -> AlgorithmDefinition | None:
        """Fetch a algorithm definition by unique name."""

    @abstractmethod
    async def list_versions(self, algorithm_id: UUID) -> list[AlgorithmConfigVersion]:
        """Return all known versions for a algorithm."""

    @abstractmethod
    async def create_version(
        self,
        algorithm_id: UUID,
        config: dict[str, Any],
        schema_version: int,
        created_by: str = "system",
    ) -> AlgorithmConfigVersion:
        """Create and return the next algorithm version."""

    @abstractmethod
    async def set_active_version(self, algorithm_id: UUID, version: int) -> bool:
        """Set one algorithm version as active and update definition status."""
