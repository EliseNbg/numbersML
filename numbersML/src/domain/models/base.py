"""
Base classes for domain entities.

Provides foundational classes for Domain-Driven Design:
- Entity: Base class for objects with identity
- ValueObject: Base class for immutable objects  
- DomainEvent: Base class for domain events
"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(eq=False)
class Entity(ABC):
    """
    Base class for all domain entities.
    
    Entities have a distinct identity that runs through time.
    They track creation and update timestamps automatically.
    Equality is based on ID only, not all attributes.
    """
    
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __eq__(self, other: Any) -> bool:
        """Compare entities by ID only."""
        if not isinstance(other, Entity):
            return False
        if self.id is None or other.id is None:
            return False
        return self.id == other.id
    
    def __hash__(self) -> int:
        """Hash entity by ID."""
        return hash(self.id) if self.id else id(self)


@dataclass(frozen=True)
class ValueObject(ABC):
    """
    Base class for all value objects.
    
    Value Objects are immutable and compared by value, not identity.
    """
    
    def __eq__(self, other: Any) -> bool:
        """Compare value objects by attributes."""
        if not isinstance(other, ValueObject):
            return False
        return self.__dict__ == other.__dict__
    
    def __hash__(self) -> int:
        """Hash value object by attributes."""
        return hash(tuple(sorted(self.__dict__.values())))


@dataclass(frozen=True)
class DomainEvent:
    """
    Base class for domain events.
    
    Domain Events represent significant occurrences in the domain.
    They are immutable and contain all relevant event data.
    """
    
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def event_type(self) -> str:
        """Get event type from class name."""
        return self.__class__.__name__
