"""
StrategyInstance repository interface (Domain Layer).

Defines contract for StrategyInstance persistence.
Follows DDD Repository pattern - interface in domain, implementation in infrastructure.
"""

from abc import abstractmethod
from typing import Any
from uuid import UUID

from src.domain.repositories.base import Repository
from src.domain.algorithms.strategy_instance import StrategyInstance


class StrategyInstanceRepository(Repository[StrategyInstance, UUID]):
    """
    Abstract base class for StrategyInstance repository.

    Defines the contract for persisting StrategyInstance entities.
    Implementation is in infrastructure layer (asyncpg, etc.).

    Example:
        >>> from src.infrastructure.repositories.strategy_instance_repository_pg import StrategyInstanceRepositoryPG
        >>> repo = StrategyInstanceRepositoryPG(connection)
        >>> instance = await repo.save(instance)
    """

    @abstractmethod
    async def get_by_algorithm_and_config(
        self, algorithm_id: UUID, config_set_id: UUID
    ) -> StrategyInstance | None:
        """
        Get instance by algorithm + config_set combination.

        Args:
            algorithm_id: UUID of the algorithm
            config_set_id: UUID of the configuration set

        Returns:
            StrategyInstance if found, None otherwise
        """

    @abstractmethod
    async def list_all(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StrategyInstance]:
        """
        List instances with optional status filter.

        Args:
            status: Optional status filter (stopped, running, paused, error)
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of StrategyInstance entities
        """

    @abstractmethod
    async def list_by_algorithm(self, algorithm_id: UUID) -> list[StrategyInstance]:
        """
        List all instances for a specific algorithm.

        Args:
            algorithm_id: UUID of the algorithm

        Returns:
            List of StrategyInstance entities for the algorithm
        """

    @abstractmethod
    async def update_status(
        self, instance_id: UUID, status: str, runtime_stats: dict[str, Any] | None = None
    ) -> StrategyInstance | None:
        """
        Update instance status and optionally runtime stats.

        Args:
            instance_id: UUID of the instance
            status: New status value
            runtime_stats: Optional runtime stats dict to update

        Returns:
            Updated StrategyInstance if found, None otherwise
        """
