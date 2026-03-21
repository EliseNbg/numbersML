"""Tests for domain base classes."""

from dataclasses import dataclass
from datetime import datetime
from src.domain.models.base import Entity, ValueObject, DomainEvent


class TestEntity:
    """Test Entity base class."""
    
    def test_entity_timestamps_auto_initialized(self) -> None:
        """Test that Entity timestamps are auto-initialized."""
        @dataclass
        class TestEntity(Entity):
            name: str = "test"
        
        entity = TestEntity()
        
        assert entity.created_at is not None
        assert entity.updated_at is not None
        assert isinstance(entity.created_at, datetime)
    
    def test_entity_equality_by_id(self) -> None:
        """Test that entities are equal when IDs match."""
        @dataclass
        class TestEntity(Entity):
            name: str = "test"
        
        # Entities with same ID are equal (even with different names)
        entity1 = TestEntity(id=1, name="test1")
        entity2 = TestEntity(id=1, name="test2")
        
        # Test __eq__ method directly (pytest assert rewriting causes issues)
        result = entity1.__eq__(entity2)
        assert result is True, f"Expected True but got {result}"
        
        # Different IDs should not be equal
        entity3 = TestEntity(id=2, name="test1")
        result = entity1.__eq__(entity3)
        assert result is False
    
    def test_entity_without_id_not_equal(self) -> None:
        """Test that entities without ID are never equal."""
        @dataclass
        class TestEntity(Entity):
            name: str = "test"
        
        entity1 = TestEntity(name="test1")
        entity2 = TestEntity(name="test2")
        
        # Both have None ID, so not equal
        assert entity1 != entity2


class TestValueObject:
    """Test ValueObject base class."""
    
    def test_value_object_equality_by_value(self) -> None:
        """Test that value objects are equal by value."""
        @dataclass(frozen=True)
        class TestValueObject(ValueObject):
            value: int = 0
        
        vo1 = TestValueObject(value=42)
        vo2 = TestValueObject(value=42)
        vo3 = TestValueObject(value=43)
        
        assert vo1 == vo2  # Same value
        assert vo1 != vo3  # Different value


class TestDomainEvent:
    """Test DomainEvent base class."""
    
    def test_domain_event_id_auto_generated(self) -> None:
        """Test that event ID is auto-generated."""
        @dataclass(frozen=True)
        class TestEvent(DomainEvent):
            message: str = "test"
        
        event = TestEvent()
        
        assert event.event_id is not None
    
    def test_domain_event_timestamp_auto_set(self) -> None:
        """Test that event timestamp is auto-set."""
        @dataclass(frozen=True)
        class TestEvent(DomainEvent):
            message: str = "test"
        
        event = TestEvent()
        
        assert event.occurred_at is not None
        assert isinstance(event.occurred_at, datetime)
    
    def test_domain_event_type_from_class_name(self) -> None:
        """Test that event type is derived from class name."""
        @dataclass(frozen=True)
        class TestEvent(DomainEvent):
            message: str = "test"
        
        event = TestEvent()
        
        assert event.event_type == 'TestEvent'
