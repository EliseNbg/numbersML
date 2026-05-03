"""
ConfigurationSet repository interface (Domain Layer).

Defines the contract for ConfigurationSet persistence.
Follows DDD Repository pattern - interface in domain, implementation in infrastructure.
"""

from abc import abstractmethod
from typing import Any
from uuid import UUID

from src.domain.strategies.config_set import ConfigurationSet

from .base import Repository


class ConfigSetRepository(Repository[ConfigurationSet, UUID]):
    """
    Abstract base class for ConfigurationSet repository.

    Defines the contract for persisting ConfigurationSet entities.
    Implementation is in infrastructure layer (asyncpg, etc.).

    Example:
        >>> from src.infrastructure.repositories.config_set_repository_pg import ConfigSetRepositoryPG
        >>> repo = ConfigSetRepositoryPG(connection)
        >>> config_set = await repo.save(config_set)
    """

    @abstractmethod
    async def get_by_name(self, name: str) -> ConfigurationSet | None:
        """
        Get ConfigurationSet by name.

        Args:
            name: Unique name of the configuration set

        Returns:
            ConfigurationSet if found, None otherwise
        """
        ...

    @abstractmethod
    async def list_all(
        self,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConfigurationSet]:
        """
        List ConfigurationSets with optional filtering.

        Args:
            active_only: If True, return only active config sets
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of ConfigurationSet entities
        """
        ...

    @abstractmethod
    async def update_config(
        self,
        config_set_id: UUID,
        new_config: dict[str, Any],
        updated_by: str = "system",
    ) -> ConfigurationSet | None:
        """
        Update configuration and increment version.

        Args:
            config_set_id: UUID of the configuration set
            new_config: New configuration dictionary
            updated_by: User making the change

        Returns:
            Updated ConfigurationSet if found, None otherwise
        """
        ...
