# Step 004: Data Collection Service - Implementation Guide

**Phase**: 2 - Data Collection  
**Effort**: 8 hours  
**Dependencies**: Step 003 (Domain Models) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements the Binance WebSocket data collection service with:
- Real-time tick collection from Binance WebSocket
- Data quality validation (7 rules)
- Batch inserts to PostgreSQL
- Automatic reconnection with backoff
- Active symbol filtering (EU compliance)
- Comprehensive tests (80%+ coverage)

---

## Implementation Tasks

### Task 1: Repository Interfaces

**File**: `src/domain/repositories/base.py`

```python
"""
Base repository interface.

Defines the repository pattern for data access.
Repositories are ports in the hexagonal architecture.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List
from src.domain.models.base import Entity

T = TypeVar('T', bound=Entity)


class Repository(ABC, Generic[T]):
    """
    Base repository interface.
    
    Repositories provide a collection-like interface for
    accessing domain entities from storage.
    """
    
    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[T]:
        """Get entity by ID."""
        pass
    
    @abstractmethod
    async def get_all(self) -> List[T]:
        """Get all entities."""
        pass
    
    @abstractmethod
    async def save(self, entity: T) -> T:
        """Save entity."""
        pass
    
    @abstractmethod
    async def delete(self, id: int) -> bool:
        """Delete entity by ID."""
        pass
