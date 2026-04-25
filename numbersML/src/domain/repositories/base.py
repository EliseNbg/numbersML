"""Base repository ports for domain entities."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")
ID = TypeVar("ID")


class Repository(ABC, Generic[T, ID]):
    """Generic repository interface used by domain ports."""

    @abstractmethod
    async def get_by_id(self, entity_id: ID) -> T | None:
        """Return an entity by its identifier."""

    @abstractmethod
    async def get_all(self) -> list[T]:
        """Return all entities."""

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Persist and return an entity."""

    @abstractmethod
    async def delete(self, entity_id: ID) -> bool:
        """Delete entity and return True when row existed."""
