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
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.domain.repositories.config_set_repository import ConfigSetRepository
from src.domain.algorithms.config_set import ConfigurationSet
from src.infrastructure.api.auth import require_admin, require_read, require_trader
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
    description: str | None = Field(None, max_length=2000, description="Optional description")
    config: dict[str, Any] = Field(..., description="Configuration dictionary")
    created_by: str = Field(default="system", max_length=255, description="Creator identifier")


class ConfigurationSetUpdateRequest(BaseModel):
    """Request model for updating ConfigurationSet."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    config: dict[str, Any] | None = None


class ConfigurationSetResponse(BaseModel):
    """Response model for ConfigurationSet."""

    id: str
    name: str
    description: str | None = None
    config: dict[str, Any]
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


async def get_config_set_repository() -> AsyncGenerator[ConfigSetRepository, None]:
    """Get ConfigSetRepository instance with database connection."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield ConfigSetRepositoryPG(conn)


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=list[ConfigurationSetResponse])
async def list_config_sets(
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    repo: ConfigSetRepository = Depends(get_config_set_repository),  # noqa: B008
    _auth: None = Depends(require_read),  # noqa: B008
) -> list[ConfigurationSetResponse]:
    """List ConfigurationSets with optional filtering.

    Args:
        active_only: If True, return only active config sets
        limit: Maximum number of results
        offset: Pagination offset
        repo: ConfigSet repository instance
        _auth: Authentication check

    Returns:
        List of ConfigurationSetResponse

    Raises:
        401: If not authenticated
        403: If insufficient permissions
    """
    config_sets = await repo.list_all(active_only=active_only, limit=limit, offset=offset)
    return [ConfigurationSetResponse.from_domain(cs) for cs in config_sets]


@router.post(
    "",
    response_model=ConfigurationSetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_config_set(
    req: ConfigurationSetCreateRequest,
    repo: ConfigSetRepository = Depends(get_config_set_repository),  # noqa: B008
    _auth: None = Depends(require_trader),  # noqa: B008
) -> ConfigurationSetResponse:
    """Create a new ConfigurationSet.

    Args:
        req: Create request with name, config, etc.
        repo: ConfigSet repository instance
        _auth: Authentication check (requires trader or admin)

    Returns:
        Created ConfigurationSetResponse

    Raises:
        400: If name already exists or config invalid
        401: If not authenticated
        403: If insufficient permissions
        500: If creation fails
    """
    try:
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

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Failed to create ConfigurationSet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ConfigurationSet",
        ) from None


@router.get("/{config_set_id}", response_model=ConfigurationSetResponse)
async def get_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),  # noqa: B008
    _auth: None = Depends(require_read),  # noqa: B008
) -> ConfigurationSetResponse:
    """Get ConfigurationSet by ID.

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance
        _auth: Authentication check (requires read access)

    Returns:
        ConfigurationSetResponse

    Raises:
        401: If not authenticated
        403: If insufficient permissions
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
    repo: ConfigSetRepository = Depends(get_config_set_repository),  # noqa: B008
    _auth: None = Depends(require_trader),  # noqa: B008
) -> ConfigurationSetResponse:
    """Update ConfigurationSet (partial update).

    Args:
        config_set_id: UUID of the ConfigurationSet
        req: Update request with fields to update
        repo: ConfigSet repository instance
        _auth: Authentication check (requires trader or admin)

    Returns:
        Updated ConfigurationSetResponse

    Raises:
        401: If not authenticated
        403: If insufficient permissions
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

        if req.name is not None and req.name != config_set.name:
            existing = await repo.get_by_name(req.name)
            if existing and existing.id != config_set_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"ConfigurationSet with name '{req.name}' already exists",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name update not yet implemented",
            )

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Failed to update ConfigurationSet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ConfigurationSet",
        ) from None


@router.delete("/{config_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),  # noqa: B008
    _auth: None = Depends(require_admin),  # noqa: B008
) -> None:
    """Soft delete ConfigurationSet (deactivate).

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance
        _auth: Authentication check (requires admin)

    Raises:
        401: If not authenticated
        403: If insufficient permissions
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
        ) from None


@router.post("/{config_set_id}/activate", status_code=status.HTTP_200_OK)
async def activate_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),  # noqa: B008
    _auth: None = Depends(require_admin),  # noqa: B008
) -> dict[str, Any]:
    """Activate a ConfigurationSet.

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance
        _auth: Authentication check (requires admin)

    Returns:
        Success message

    Raises:
        401: If not authenticated
        403: If insufficient permissions
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
        ) from None


@router.post("/{config_set_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_config_set(
    config_set_id: UUID,
    repo: ConfigSetRepository = Depends(get_config_set_repository),  # noqa: B008
    _auth: None = Depends(require_admin),  # noqa: B008
) -> dict[str, Any]:
    """Deactivate a ConfigurationSet.

    Args:
        config_set_id: UUID of the ConfigurationSet
        repo: ConfigSet repository instance
        _auth: Authentication check (requires admin)

    Returns:
        Success message

    Raises:
        401: If not authenticated
        403: If insufficient permissions
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
        ) from None
