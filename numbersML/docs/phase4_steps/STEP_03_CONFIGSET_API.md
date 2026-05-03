# Step 3: ConfigurationSet API Endpoints

## Objective
Create FastAPI endpoints for ConfigurationSet CRUD operations following REST principles and DDD architecture.

## Context
- Step 1 complete: `ConfigurationSet` domain entity exists
- Step 2 complete: Repository interface and PostgreSQL implementation exist
- Existing API pattern: `src/infrastructure/api/routes/strategies.py`
- FastAPI with pydantic v2 for request/response models
- Dependency injection via `Depends()`

## DDD Architecture Decision (ADR)

**Decision**: API layer is in Infrastructure, not Domain or Application
- Routes in `src/infrastructure/api/routes/`
- Pydantic models for request/response validation
- Dependency injection for repository access
- Error handling with HTTPException

**API Design**:
```
GET    /api/config-sets           → List all (with active_only filter)
POST   /api/config-sets           → Create new
GET    /api/config-sets/{id}      → Get by ID
PUT    /api/config-sets/{id}      → Update (full or partial)
DELETE /api/config-sets/{id}      → Soft delete (deactivate)
POST   /api/config-sets/{id}/activate   → Activate config set
POST   /api/config-sets/{id}/deactivate → Deactivate config set
```

## TDD Approach

1. **Red**: Write failing API tests first (using FastAPI's TestClient)
2. **Green**: Implement endpoints to pass tests
3. **Refactor**: Add error handling, validation, logging

## Implementation Files

### 1. `src/infrastructure/api/routes/config_sets.py`

```python
"""
ConfigurationSet API endpoints.

Provides REST API for ConfigurationSet management:
- CRUD operations
- Activation/deactivation
- Listing with filters

Architecture: Infrastructure Layer (API)
Dependencies: Domain repositories, Pydantic models
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.domain.repositories.config_set_repository import ConfigSetRepository
from src.domain.strategies.config_set import ConfigurationSet
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.config_set_repository_pg import (
    ConfigSetRepositoryPG,
)

router = APIRouter(prefix="/api/config-sets", tags=["config-sets"])

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================


class ConfigurationSetCreateRequest(BaseModel):
    """Request model for creating ConfigurationSet."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique name")
    description: Optional[str] = Field(None, max_length=2000, description="Optional description")
    config: Dict[str, Any] = Field(..., description="Configuration dictionary")
    created_by: str = Field(default="system", max_length=255, description="Creator identifier")


class ConfigurationSetUpdateRequest(BaseModel):
    """Request model for updating ConfigurationSet."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    config: Optional[Dict[str, Any]] = None


class ConfigurationSetResponse(BaseModel):
    """Response model for ConfigurationSet."""

    id: str
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    is_active: bool = True
    created_by: str
    created_at: datetime
    updated_at: datetime
    version: int = 1

    @classmethod
    def from_domain(cls, cs: ConfigurationSet) -> "ConfigurationSetResponse":
        """Convert domain entity to response model."""
        return cls(
            id=str(cs.id),
            name=cs.name,
            description=cs.description,
            config=cs.config,
            is_active=cs.is_active,
            created_by=cs.created_by,
            created_at=cs.created_at,
            updated_at=cs.updated_at,
            version=cs.version,
        )


# ============================================================================
# Dependencies
# ============================================================================


async def get_config_set_repository() -> ConfigSetRepository:
    """Get ConfigSetRepository instance with database connection."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        return ConfigSetRepositoryPG(conn)


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=List[ConfigurationSetResponse])
async def list_config_sets(
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    repo: ConfigSetRepository = Depends(get_config_set_repository),
) -> List[ConfigurationSetResponse]:
    """
    List ConfigurationSets with optional filtering.

    Args:
        active_only: If True, return only active config sets
        limit: Maximum number of results
        offset: Pagination offset
        repo: ConfigSet repository instance

    Returns:
        List of ConfigurationSetResponse
    """
    config_sets = await repo.list_all(
        active_only=active_only, limit=limit, offset=offset
    )
    return [ConfigurationSetResponse.from_domain(cs) for cs in config_sets]


@router.post(
    "",
    response_model=ConfigurationSetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_config_set(
    req: ConfigurationSetCreateRequest,
    repo: ConfigSetRepository = Depends(get_config_set_repository),
) -> ConfigurationSetResponse:
    """
    Create a new ConfigurationSet.

    Args:
        req: Create request with name, config, etc.
        repo: ConfigSet repository instance

    Returns:
        Created ConfigurationSetResponse

    Raises:
        400: If name already exists or config invalid
        500: If creation fails
    """
    try:
        # Check if name already exists
        existing = await repo.get_by_name(req.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ConfigurationSet with name '{req.name}' already exists",
            )

        config_set = ConfigurationSet(
            name=req.name,
            config=req.config,
            description=req.description,
            created_by=req.created_by,
        )

        saved = await repo.save(config_set)
        return ConfigurationSetResponse.from_domain(saved)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create ConfigurationSet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ConfigurationSet",
        )


@router.get("/{config_set_id}", response_model=ConfigurationSetResponse)
async def get_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),
) -> ConfigurationSetResponse:
    """
    Get ConfigurationSet by ID.

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance

    Returns:
        ConfigurationSetResponse

    Raises:
        404: If ConfigurationSet not found
    """
    config_set = await repo.get_by_id(config_set_id)
    if not config_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ConfigurationSet {config_set_id} not found",
        )
    return ConfigurationSetResponse.from_domain(config_set)


@router.put("/{config_set_id}", response_model=ConfigurationSetResponse)
async def update_config_set(
    config_set_id: UUID,
    req: ConfigurationSetUpdateRequest,
    repo: ConfigSetRepository = Depends(get_config_set_repository),
) -> ConfigurationSetResponse:
    """
    Update ConfigurationSet (partial update).

    Args:
        config_set_id: UUID of the ConfigurationSet
        req: Update request with fields to update
        repo: ConfigSet repository instance

    Returns:
        Updated ConfigurationSetResponse

    Raises:
        404: If ConfigurationSet not found
        400: If no fields to update or name conflict
        500: If update fails
    """
    try:
        config_set = await repo.get_by_id(config_set_id)
        if not config_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ConfigurationSet {config_set_id} not found",
            )

        updated = False

        # Update name if provided
        if req.name is not None and req.name != config_set.name:
            # Check if new name conflicts
            existing = await repo.get_by_name(req.name)
            if existing and existing.id != config_set_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"ConfigurationSet with name '{req.name}' already exists",
                )
            # Note: ConfigurationSet doesn't have set_name() method
            # Would need to create new entity or add method
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name update not yet implemented",
            )

        # Update config if provided
        if req.config is not None:
            config_set.update_config(req.config, updated_by="api")
            updated = True

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        saved = await repo.save(config_set)
        return ConfigurationSetResponse.from_domain(saved)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update ConfigurationSet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ConfigurationSet",
        )


@router.delete("/{config_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),
) -> None:
    """
    Soft delete ConfigurationSet (deactivate).

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance

    Raises:
        404: If ConfigurationSet not found
        500: If deletion fails
    """
    try:
        success = await repo.delete(config_set_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ConfigurationSet {config_set_id} not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete ConfigurationSet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete ConfigurationSet",
        )


@router.post("/{config_set_id}/activate", status_code=status.HTTP_200_OK)
async def activate_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),
) -> Dict[str, Any]:
    """
    Activate a ConfigurationSet.

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance

    Returns:
        Success message

    Raises:
        404: If ConfigurationSet not found
        500: If activation fails
    """
    try:
        config_set = await repo.get_by_id(config_set_id)
        if not config_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ConfigurationSet {config_set_id} not found",
            )

        config_set.activate()
        await repo.save(config_set)

        return {"message": f"ConfigurationSet {config_set_id} activated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate ConfigurationSet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate ConfigurationSet",
        )


@router.post("/{config_set_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),
) -> Dict[str, Any]:
    """
    Deactivate a ConfigurationSet.

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance

    Returns:
        Success message

    Raises:
        404: If ConfigurationSet not found
        500: If deactivation fails
    """
    try:
        config_set = await repo.get_by_id(config_set_id)
        if not config_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ConfigurationSet {config_set_id} not found",
            )

        config_set.deactivate()
        await repo.save(config_set)

        return {"message": f"ConfigurationSet {config_set_id} deactivated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate ConfigurationSet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate ConfigurationSet",
        )
```

### 2. `tests/unit/infrastructure/api/test_config_sets_api.py`

```python
"""
Tests for ConfigurationSet API endpoints.

Uses FastAPI's TestClient for endpoint testing.
Follows TDD: tests first, then implementation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

from fastapi.testclient import TestClient

from src.infrastructure.api.app import app


@pytest.fixture
def client():
    """Create TestClient for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_repository():
    """Create a mock ConfigSetRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def sample_config_set_data():
    """Sample data for creating ConfigurationSet."""
    return {
        "name": "Test Config",
        "description": "Test description",
        "config": {"symbols": ["BTC/USDT"], "risk": {"max_position_size_pct": 10}},
        "created_by": "test",
    }


class TestListConfigSets:
    """Tests for GET /api/config-sets"""

    def test_list_empty(self, client, mock_repository):
        """Test listing when no config sets exist."""
        # Mock the dependency
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        mock_repository.list_all.return_value = []
        
        response = client.get("/api/config-sets")
        
        assert response.status_code == 200
        assert response.json() == []
        
        # Clean up
        app.dependency_overrides.clear()

    def test_list_with_data(self, client, mock_repository):
        """Test listing config sets."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        # Create mock config set
        cs = ConfigurationSet(
            name="Test",
            config={"key": "value"},
        )
        
        mock_repository.list_all.return_value = [cs]
        
        response = client.get("/api/config-sets")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test"
        
        app.dependency_overrides.clear()

    def test_list_active_only(self, client, mock_repository):
        """Test listing with active_only filter."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        mock_repository.list_all.return_value = []
        
        response = client.get("/api/config-sets?active_only=true")
        
        assert response.status_code == 200
        # Verify active_only=True was passed
        call_args = mock_repository.list_all.call_args
        assert call_args[1]["active_only"] is True
        
        app.dependency_overrides.clear()


class TestCreateConfigSet:
    """Tests for POST /api/config-sets"""

    def test_create_success(self, client, mock_repository, sample_config_set_data):
        """Test creating a ConfigurationSet successfully."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        # Mock get_by_name to return None (no conflict)
        mock_repository.get_by_name.return_value = None
        
        # Mock save to return config set
        cs = ConfigurationSet(**sample_config_set_data)
        mock_repository.save.return_value = cs
        
        response = client.post("/api/config-sets", json=sample_config_set_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_config_set_data["name"]
        assert data["config"] == sample_config_set_data["config"]
        
        app.dependency_overrides.clear()

    def test_create_duplicate_name(self, client, mock_repository, sample_config_set_data):
        """Test creating with duplicate name returns 400."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        # Mock get_by_name to return existing config set
        existing = ConfigurationSet(**sample_config_set_data)
        mock_repository.get_by_name.return_value = existing
        
        response = client.post("/api/config-sets", json=sample_config_set_data)
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]
        
        app.dependency_overrides.clear()

    def test_create_invalid_data(self, client, mock_repository):
        """Test creating with invalid data returns 422."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        # Missing required field 'config'
        invalid_data = {"name": "Test"}
        
        response = client.post("/api/config-sets", json=invalid_data)
        
        assert response.status_code == 422  # Unprocessable Entity
        
        app.dependency_overrides.clear()


class TestGetConfigSet:
    """Tests for GET /api/config-sets/{id}"""

    def test_get_existing(self, client, mock_repository):
        """Test getting an existing ConfigurationSet."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        cs = ConfigurationSet(name="Test", config={"key": "value"})
        mock_repository.get_by_id.return_value = cs
        
        response = client.get(f"/api/config-sets/{cs.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test"
        assert data["id"] == str(cs.id)
        
        app.dependency_overrides.clear()

    def test_get_nonexistent(self, client, mock_repository):
        """Test getting non-existent ConfigurationSet returns 404."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        mock_repository.get_by_id.return_value = None
        
        response = client.get(f"/api/config-sets/{uuid4()}")
        
        assert response.status_code == 404
        
        app.dependency_overrides.clear()


class TestUpdateConfigSet:
    """Tests for PUT /api/config-sets/{id}"""

    def test_update_config(self, client, mock_repository):
        """Test updating ConfigurationSet config."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        cs = ConfigurationSet(name="Test", config={"old": "value"})
        mock_repository.get_by_id.return_value = cs
        mock_repository.save.return_value = cs
        
        response = client.put(
            f"/api/config-sets/{cs.id}",
            json={"config": {"new": "value"}},
        )
        
        assert response.status_code == 200
        
        app.dependency_overrides.clear()

    def test_update_nonexistent(self, client, mock_repository):
        """Test updating non-existent returns 404."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        mock_repository.get_by_id.return_value = None
        
        response = client.put(
            f"/api/config-sets/{uuid4()}",
            json={"config": {"new": "value"}},
        )
        
        assert response.status_code == 404
        
        app.dependency_overrides.clear()

    def test_update_no_fields(self, client, mock_repository):
        """Test updating with no fields returns 400."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        cs = ConfigurationSet(name="Test", config={"key": "value"})
        mock_repository.get_by_id.return_value = cs
        
        response = client.put(
            f"/api/config-sets/{cs.id}",
            json={},  # No fields to update
        )
        
        assert response.status_code == 400
        
        app.dependency_overrides.clear()


class TestDeleteConfigSet:
    """Tests for DELETE /api/config-sets/{id}"""

    def test_delete_existing(self, client, mock_repository):
        """Test deleting an existing ConfigurationSet."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        mock_repository.delete.return_value = True
        
        response = client.delete(f"/api/config-sets/{uuid4()}")
        
        assert response.status_code == 204
        
        app.dependency_overrides.clear()

    def test_delete_nonexistent(self, client, mock_repository):
        """Test deleting non-existent returns 404."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        mock_repository.delete.return_value = False
        
        response = client.delete(f"/api/config-sets/{uuid4()}")
        
        assert response.status_code == 404
        
        app.dependency_overrides.clear()


class TestActivateDeactivateConfigSet:
    """Tests for activate/deactivate endpoints."""

    def test_activate(self, client, mock_repository):
        """Test activating a ConfigurationSet."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        cs = ConfigurationSet(name="Test", config={})
        mock_repository.get_by_id.return_value = cs
        mock_repository.save.return_value = cs
        
        response = client.post(f"/api/config-sets/{cs.id}/activate")
        
        assert response.status_code == 200
        assert "activated" in response.json()["message"]
        
        app.dependency_overrides.clear()

    def test_deactivate(self, client, mock_repository):
        """Test deactivating a ConfigurationSet."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository
        
        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository
        
        cs = ConfigurationSet(name="Test", config={})
        mock_repository.get_by_id.return_value = cs
        mock_repository.save.return_value = cs
        
        response = client.post(f"/api/config-sets/{cs.id}/deactivate")
        
        assert response.status_code == 200
        assert "deactivated" in response.json()["message"]
        
        app.dependency_overrides.clear()
```

## LLM Implementation Prompt

```text
You are implementing Step 3 of Phase 4: ConfigurationSet API Endpoints.

## Your Task

Create FastAPI endpoints for ConfigurationSet CRUD operations.

## Context

- Step 1 complete: ConfigurationSet domain entity in src/domain/strategies/config_set.py
- Step 2 complete: Repository in src/infrastructure/repositories/config_set_repository_pg.py
- Follow existing API pattern in src/infrastructure/api/routes/strategies.py
- Use FastAPI with pydantic v2 for request/response models
- Use TestClient from fastapi.testclient for testing

## Requirements

1. Create `src/infrastructure/api/routes/config_sets.py` with:
   - Pydantic models: ConfigurationSetCreateRequest, ConfigurationSetUpdateRequest, ConfigurationSetResponse
   - GET /api/config-sets (list with active_only, limit, offset filters)
   - POST /api/config-sets (create, check name uniqueness)
   - GET /api/config-sets/{id} (get by ID)
   - PUT /api/config-sets/{id} (update, partial)
   - DELETE /api/config-sets/{id} (soft delete → deactivate)
   - POST /api/config-sets/{id}/activate (activate config set)
   - POST /api/config-sets/{id}/deactivate (deactivate config set)
   - Dependency injection for repository (get_config_set_repository)
   - Error handling: 404 for not found, 400 for conflicts/invalid, 500 for server errors
   - Google-style docstrings on all endpoints

2. Create `tests/unit/infrastructure/api/test_config_sets_api.py` with TDD:
   - TestListConfigSets: empty list, with data, active_only filter
   - TestCreateConfigSet: success, duplicate name, invalid data
   - TestGetConfigSet: existing, non-existent
   - TestUpdateConfigSet: update config, non-existent, no fields
   - TestDeleteConfigSet: existing, non-existent
   - TestActivateDeactivateConfigSet: activate, deactivate
   - Use FastAPI TestClient
   - Mock repository with AsyncMock
   - Override app.dependency_overrides for testing

## Constraints

- Follow AGENTS.md coding standards
- Use type hints on all public methods (mypy strict)
- Use Google-style docstrings
- Use relative imports within package
- Line length max 100 characters
- Log errors with logger.error(f"message: {e}")
- Return appropriate HTTP status codes (200, 201, 204, 400, 404, 500)
- Soft delete: set is_active=False (not hard DELETE)

## Acceptance Criteria

1. All CRUD endpoints implemented and working
2. Activation/deactivation endpoints toggle is_active
3. Duplicate name check on create/update
4. Proper error responses (404, 400, 500)
5. All API tests pass
6. mypy passes with no errors
7. ruff check passes with no errors
8. black formatting applied

## Commands to Run

```bash
# Format and lint
black src/infrastructure/api/routes/config_sets.py tests/unit/infrastructure/api/test_config_sets_api.py
ruff check src/infrastructure/api/routes/config_sets.py tests/unit/infrastructure/api/test_config_sets_api.py
mypy src/infrastructure/api/routes/config_sets.py

# Run tests
.venv/bin/python -m pytest tests/unit/infrastructure/api/test_config_sets_api.py -v
```

## Output

1. List of files created/modified
2. Test results (passed/failed count)
3. mypy/ruff output (no errors)
4. Any issues encountered and how resolved
```

## Success Criteria

- [ ] All ConfigurationSet CRUD endpoints created
- [ ] Pydantic request/response models with validation
- [ ] Dependency injection for repository
- [ ] Proper error handling (404, 400, 500)
- [ ] Activation/deactivation endpoints
- [ ] All API tests pass (TestClient)
- [ ] mypy strict mode passes
- [ ] ruff check passes (rules: E, W, F, I, N, UP, B, C4)
- [ ] black formatting applied
- [ ] Google-style docstrings on all endpoints
