# Step 5: StrategyInstance Repository & API

## Objective
Create repository and API endpoints for StrategyInstance management, enabling CRUD operations and hot-plug functionality.

## Context
- Step 4 complete: `StrategyInstance` domain entity with state machine exists
- Step 2-3 complete: ConfigurationSet repository and API patterns established
- Need to persist StrategyInstance and expose via REST API
- Hot-plug: start/stop without pipeline restart

## DDD Architecture Decision (ADR)

**Decision**: StrategyInstance follows same pattern as ConfigurationSet
- **Domain layer**: `StrategyInstanceRepository` abstract base class
- **Infrastructure layer**: `StrategyInstanceRepositoryPG` asyncpg implementation
- **API layer**: `strategy_instances.py` with FastAPI endpoints

**Database Schema**:
```sql
CREATE TABLE strategy_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id),
    config_set_id UUID NOT NULL REFERENCES configuration_sets(id),
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (status IN (...)),
    runtime_stats JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy_id, config_set_id)
);
```

## TDD Approach

1. **Red**: Write failing repository and API tests
2. **Green**: Implement to pass tests
3. **Refactor**: Add error handling, logging, validation

## Implementation Files

### 1. `migrations/004_strategy_instances.sql`

```sql
--
-- Migration: Create strategy_instances table
-- Phase 4 Step 5
--

CREATE TABLE strategy_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    config_set_id UUID NOT NULL REFERENCES configuration_sets(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (
        status IN ('stopped', 'running', 'paused', 'error')
    ),
    runtime_stats JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_strategy_config UNIQUE(strategy_id, config_set_id),
    CONSTRAINT chk_runtime_stats_json CHECK (jsonb_typeof(runtime_stats) = 'object')
);

CREATE INDEX idx_strategy_instances_status ON strategy_instances(status);
CREATE INDEX idx_strategy_instances_strategy ON strategy_instances(strategy_id);
CREATE INDEX idx_strategy_instances_config ON strategy_instances(config_set_id);

CREATE OR REPLACE FUNCTION update_strategy_instance_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_strategy_instances_updated_at
    BEFORE UPDATE ON strategy_instances
    FOR EACH ROW
    EXECUTE FUNCTION update_strategy_instance_updated_at();

COMMENT ON TABLE strategy_instances IS 'Links Strategy with ConfigurationSet for deployment';
COMMENT ON COLUMN strategy_instances.runtime_stats IS 'JSONB with PnL, trades, uptime, etc.';
```

### 2. `src/domain/repositories/strategy_instance_repository.py`

```python
"""
StrategyInstance repository interface (Domain Layer).

Defines contract for StrategyInstance persistence.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from src.domain.strategies.strategy_instance import StrategyInstance


class StrategyInstanceRepository(ABC):
    """
    Abstract base class for StrategyInstance repository.
    
    Example:
        >>> from src.infrastructure.repositories.strategy_instance_repository_pg import StrategyInstanceRepositoryPG
        >>> repo = StrategyInstanceRepositoryPG(connection)
        >>> instance = await repo.save(instance)
    """
    
    @abstractmethod
    async def save(self, instance: StrategyInstance) -> StrategyInstance:
        """Save (insert or update) a StrategyInstance."""
        pass
    
    @abstractmethod
    async def get_by_id(self, instance_id: UUID) -> Optional[StrategyInstance]:
        """Get StrategyInstance by ID."""
        pass
    
    @abstractmethod
    async def get_by_strategy_and_config(
        self, strategy_id: UUID, config_set_id: UUID
    ) -> Optional[StrategyInstance]:
        """Get instance by strategy + config_set combination."""
        pass
    
    @abstractmethod
    async def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[StrategyInstance]:
        """List instances with optional status filter."""
        pass
    
    @abstractmethod
    async def list_by_strategy(self, strategy_id: UUID) -> List[StrategyInstance]:
        """List all instances for a specific strategy."""
        pass
    
    @abstractmethod
    async def delete(self, instance_id: UUID) -> bool:
        """Delete a StrategyInstance (hard delete)."""
        pass
    
    @abstractmethod
    async def update_status(
        self, instance_id: UUID, status: str, runtime_stats: Optional[dict] = None
    ) -> Optional[StrategyInstance]:
        """Update instance status and optionally runtime stats."""
        pass
```

### 3. `src/infrastructure/repositories/strategy_instance_repository_pg.py`

```python
"""
StrategyInstance repository PostgreSQL implementation.

Uses asyncpg for async database access.
"""

import logging
from typing import List, Optional
from uuid import UUID

import asyncpg

from src.domain.repositories.strategy_instance_repository import StrategyInstanceRepository
from src.domain.strategies.strategy_instance import StrategyInstance, StrategyInstanceState

logger = logging.getLogger(__name__)


class StrategyInstanceRepositoryPG(StrategyInstanceRepository):
    """PostgreSQL implementation of StrategyInstanceRepository."""
    
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn
    
    async def save(self, instance: StrategyInstance) -> StrategyInstance:
        """Save (insert or update) a StrategyInstance."""
        try:
            existing = await self._conn.fetchrow(
                "SELECT id FROM strategy_instances WHERE id = $1", instance.id
            )
            
            if existing:
                await self._conn.execute(
                    """
                    UPDATE strategy_instances
                    SET status = $2, runtime_stats = $3,
                        started_at = $4, stopped_at = $5, updated_at = NOW()
                    WHERE id = $1
                    """,
                    instance.id,
                    instance.status.value,
                    instance.runtime_stats.to_dict(),
                    instance.started_at,
                    instance.stopped_at,
                )
            else:
                await self._conn.execute(
                    """
                    INSERT INTO strategy_instances
                        (id, strategy_id, config_set_id, status, runtime_stats,
                         started_at, stopped_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    instance.id,
                    instance.strategy_id,
                    instance.config_set_id,
                    instance.status.value,
                    instance.runtime_stats.to_dict(),
                    instance.started_at,
                    instance.stopped_at,
                )
            
            return await self.get_by_id(instance.id)
            
        except Exception as e:
            logger.error(f"Failed to save StrategyInstance: {e}")
            raise
    
    async def get_by_id(self, instance_id: UUID) -> Optional[StrategyInstance]:
        """Get StrategyInstance by ID."""
        row = await self._conn.fetchrow(
            """
            SELECT id, strategy_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM strategy_instances
            WHERE id = $1
            """,
            instance_id,
        )
        return self._row_to_entity(row) if row else None
    
    async def get_by_strategy_and_config(
        self, strategy_id: UUID, config_set_id: UUID
    ) -> Optional[StrategyInstance]:
        """Get instance by strategy + config_set combination."""
        row = await self._conn.fetchrow(
            """
            SELECT id, strategy_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM strategy_instances
            WHERE strategy_id = $1 AND config_set_id = $2
            """,
            strategy_id,
            config_set_id,
        )
        return self._row_to_entity(row) if row else None
    
    async def list_all(
        self, status: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[StrategyInstance]:
        """List instances with optional status filter."""
        if status:
            rows = await self._conn.fetch(
                """
                SELECT id, strategy_id, config_set_id, status, runtime_stats,
                       started_at, stopped_at, created_at, updated_at
                FROM strategy_instances
                WHERE status = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status,
                limit,
                offset,
            )
        else:
            rows = await self._conn.fetch(
                """
                SELECT id, strategy_id, config_set_id, status, runtime_stats,
                       started_at, stopped_at, created_at, updated_at
                FROM strategy_instances
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [self._row_to_entity(row) for row in rows]
    
    async def list_by_strategy(self, strategy_id: UUID) -> List[StrategyInstance]:
        """List all instances for a specific strategy."""
        rows = await self._conn.fetch(
            """
            SELECT id, strategy_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM strategy_instances
            WHERE strategy_id = $1
            ORDER BY created_at DESC
            """,
            strategy_id,
        )
        return [self._row_to_entity(row) for row in rows]
    
    async def delete(self, instance_id: UUID) -> bool:
        """Delete a StrategyInstance."""
        result = await self._conn.execute(
            "DELETE FROM strategy_instances WHERE id = $1", instance_id
        )
        return "DELETE 1" in result
    
    async def update_status(
        self, instance_id: UUID, status: str, runtime_stats: Optional[dict] = None
    ) -> Optional[StrategyInstance]:
        """Update instance status and optionally runtime stats."""
        if runtime_stats:
            result = await self._conn.execute(
                """
                UPDATE strategy_instances
                SET status = $2, runtime_stats = $3, updated_at = NOW()
                WHERE id = $1
                """,
                instance_id,
                status,
                runtime_stats,
            )
        else:
            result = await self._conn.execute(
                """
                UPDATE strategy_instances
                SET status = $2, updated_at = NOW()
                WHERE id = $1
                """,
                instance_id,
                status,
            )
        
        if "UPDATE 1" not in result:
            return None
        return await self.get_by_id(instance_id)
    
    def _row_to_entity(self, row: asyncpg.Record) -> StrategyInstance:
        """Convert database row to StrategyInstance entity."""
        from src.domain.strategies.strategy_instance import RuntimeStats
        
        runtime_stats = RuntimeStats(**row["runtime_stats"]) if row["runtime_stats"] else RuntimeStats()
        
        instance = StrategyInstance(
            strategy_id=row["strategy_id"],
            config_set_id=row["config_set_id"],
            id=row["id"],
            status=StrategyInstanceState(row["status"]),
            runtime_stats=runtime_stats,
            started_at=row["started_at"],
            stopped_at=row["stopped_at"],
        )
        return instance
```

### 4. `src/infrastructure/api/routes/strategy_instances.py`

```python
"""
StrategyInstance API endpoints.

Provides REST API for StrategyInstance management:
- CRUD operations
- Start/stop/pause/resume (hot-plug)
- Runtime statistics
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.domain.repositories.strategy_instance_repository import StrategyInstanceRepository
from src.domain.strategies.strategy_instance import (
    StrategyInstance,
    StrategyInstanceState,
)
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.strategy_instance_repository_pg import (
    StrategyInstanceRepositoryPG,
)

router = APIRouter(prefix="/api/strategy-instances", tags=["strategy-instances"])
logger = logging.getLogger(__name__)


# Pydantic Models
class StrategyInstanceCreateRequest(BaseModel):
    strategy_id: str = Field(..., description="UUID of the Strategy")
    config_set_id: str = Field(..., description="UUID of the ConfigurationSet")


class StrategyInstanceResponse(BaseModel):
    id: str
    strategy_id: str
    config_set_id: str
    status: str
    runtime_stats: Dict[str, Any]
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_domain(cls, instance: StrategyInstance) -> "StrategyInstanceResponse":
        return cls(
            id=str(instance.id),
            strategy_id=str(instance.strategy_id),
            config_set_id=str(instance.config_set_id),
            status=instance.status.value,
            runtime_stats=instance.runtime_stats.to_dict(),
            started_at=instance.started_at,
            stopped_at=instance.stopped_at,
            created_at=instance.created_at,
            updated_at=instance.updated_at,
        )


# Dependencies
async def get_instance_repository() -> StrategyInstanceRepository:
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        return StrategyInstanceRepositoryPG(conn)


# Endpoints
@router.get("", response_model=List[StrategyInstanceResponse])
async def list_instances(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> List[StrategyInstanceResponse]:
    """List StrategyInstances with optional status filter."""
    instances = await repo.list_all(status=status, limit=limit, offset=offset)
    return [StrategyInstanceResponse.from_domain(i) for i in instances]


@router.post("", response_model=StrategyInstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_instance(
    req: StrategyInstanceCreateRequest,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> StrategyInstanceResponse:
    """Create a new StrategyInstance (link Strategy + ConfigurationSet)."""
    try:
        from uuid import UUID
        strategy_id = UUID(req.strategy_id)
        config_set_id = UUID(req.config_set_id)
        
        # Check if already exists
        existing = await repo.get_by_strategy_and_config(strategy_id, config_set_id)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Instance with this strategy and config set already exists",
            )
        
        instance = StrategyInstance(
            strategy_id=strategy_id,
            config_set_id=config_set_id,
        )
        saved = await repo.save(instance)
        return StrategyInstanceResponse.from_domain(saved)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create instance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create instance")


@router.get("/{instance_id}", response_model=StrategyInstanceResponse)
async def get_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> StrategyInstanceResponse:
    """Get StrategyInstance by ID."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    return StrategyInstanceResponse.from_domain(instance)


@router.post("/{instance_id}/start", status_code=status.HTTP_200_OK)
async def start_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> Dict[str, Any]:
    """Start a StrategyInstance (hot-plug into pipeline)."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    try:
        instance.start()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} started", "status": "running"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{instance_id}/stop", status_code=status.HTTP_200_OK)
async def stop_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> Dict[str, Any]:
    """Stop a StrategyInstance (unplug from pipeline)."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    try:
        instance.stop()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} stopped", "status": "stopped"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{instance_id}/pause", status_code=status.HTTP_200_OK)
async def pause_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> Dict[str, Any]:
    """Pause a running StrategyInstance."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    try:
        instance.pause()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} paused", "status": "paused"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{instance_id}/resume", status_code=status.HTTP_200_OK)
async def resume_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> Dict[str, Any]:
    """Resume a paused StrategyInstance."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    try:
        instance.resume()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} resumed", "status": "running"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
) -> None:
    """Delete a StrategyInstance."""
    success = await repo.delete(instance_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
```

## LLM Implementation Prompt

```text
You are implementing Step 5 of Phase 4: StrategyInstance Repository & API.

## Your Task

Create repository and API endpoints for StrategyInstance management with hot-plug functionality.

## Context

- Step 4 complete: StrategyInstance domain entity in src/domain/strategies/strategy_instance.py
- Step 2-3 complete: ConfigurationSet repository/API patterns established
- Follow DDD: Interface in domain, implementation in infrastructure
- Use FastAPI with pydantic v2 for API

## Requirements

1. Create `migrations/004_strategy_instances.sql` with:
   - CREATE TABLE strategy_instances with all columns
   - Foreign keys to strategies and configuration_sets
   - UNIQUE constraint on (strategy_id, config_set_id)
   - CHECK constraint on status values
   - Indexes on status, strategy_id, config_set_id
   - Trigger for updated_at auto-update

2. Create `src/domain/repositories/strategy_instance_repository.py` with:
   - Abstract base class StrategyInstanceRepository(ABC)
   - Methods: save, get_by_id, get_by_strategy_and_config, list_all, list_by_strategy, delete, update_status
   - Full type annotations

3. Create `src/infrastructure/repositories/strategy_instance_repository_pg.py` with:
   - StrategyInstanceRepositoryPG implementing interface
   - save(): upsert (INSERT ON CONFLICT)
   - get_by_id(), get_by_strategy_and_config()
   - list_all() with status filter, pagination
   - update_status(): update status and optionally runtime_stats
   - _row_to_entity(): Convert Record to StrategyInstance

4. Create `src/infrastructure/api/routes/strategy_instances.py` with:
   - Pydantic models: StrategyInstanceCreateRequest, StrategyInstanceResponse
   - GET /api/strategy-instances (list with status filter)
   - POST /api/strategy-instances (create)
   - GET /api/strategy-instances/{id} (get by ID)
   - POST /api/strategy-instances/{id}/start (hot-plug)
   - POST /api/strategy-instances/{id}/stop (unplug)
   - POST /api/strategy-instances/{id}/pause
   - POST /api/strategy-instances/{id}/resume
   - DELETE /api/strategy-instances/{id} (delete)

5. Create tests following TDD:
   - tests/unit/infrastructure/repositories/test_strategy_instance_repository_pg.py
   - tests/unit/infrastructure/api/test_strategy_instances_api.py
   - Mock asyncpg.Connection with AsyncMock
   - Test all state transitions

## Constraints

- Follow AGENTS.md coding standards
- Use type hints on all public methods (mypy strict)
- Use Google-style docstrings
- Line length max 100 characters
- Log errors with logger.error(f"message: {e}")
- Use asyncpg (not psycopg2)
- All repository methods must be async

## Acceptance Criteria

1. Migration 004 creates table with correct schema
2. StrategyInstanceRepository interface defines all methods
3. StrategyInstanceRepositoryPG implements all methods
4. All CRUD endpoints working
5. Hot-plug endpoints (start/stop/pause/resume) working
6. State machine validation in API (cannot start from running, etc.)
7. All tests pass
8. mypy passes with no errors
9. ruff check passes with no errors
10. black formatting applied

## Commands to Run

```bash
# Format and lint
black src/domain/repositories/strategy_instance_repository.py src/infrastructure/repositories/strategy_instance_repository_pg.py src/infrastructure/api/routes/strategy_instances.py
ruff check src/domain/repositories/strategy_instance_repository.py src/infrastructure/repositories/strategy_instance_repository_pg.py src/infrastructure/api/routes/strategy_instances.py
mypy src/domain/repositories/strategy_instance_repository.py src/infrastructure/repositories/strategy_instance_repository_pg.py

# Run tests
.venv/bin/python -m pytest tests/unit/infrastructure/repositories/test_strategy_instance_repository_pg.py tests/unit/infrastructure/api/test_strategy_instances_api.py -v
```

## Output

1. List of files created/modified
2. Test results (passed/failed count)
3. mypy/ruff output (no errors)
4. Any issues encountered and how resolved
```

## Success Criteria

- [ ] StrategyInstance repository created with all CRUD operations
- [ ] API endpoints for all operations including hot-plug
- [ ] State machine enforced in API (can_start(), can_stop(), etc.)
- [ ] UNIQUE constraint prevents duplicate strategy+config pairs
- [ ] All tests pass (mocked asyncpg)
- [ ] mypy strict mode passes
- [ ] ruff check passes
- [ ] black formatting applied
