"""
StrategyInstance API endpoints.

Provides REST API for StrategyInstance management:
- CRUD operations
- Start/stop/pause/resume (hot-plug)
- Runtime statistics

Architecture: Infrastructure Layer (API)
Dependencies: Domain repositories, Pydantic models, Auth
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.domain.repositories.strategy_instance_repository import StrategyInstanceRepository
from src.domain.strategies.strategy_instance import (
    StrategyInstance,
)
from src.infrastructure.api.auth import require_read, require_trader
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.strategy_instance_repository_pg import (
    StrategyInstanceRepositoryPG,
)

router = APIRouter(prefix="/api/strategy-instances", tags=["strategy-instances"])
logger = logging.getLogger(__name__)


# Pydantic Models
class StrategyInstanceCreateRequest(BaseModel):
    """Request model for creating StrategyInstance."""

    strategy_id: str = Field(..., description="UUID of the Algorithm")
    config_set_id: str = Field(..., description="UUID of the ConfigurationSet")


class StrategyInstanceResponse(BaseModel):
    """Response model for StrategyInstance."""

    id: str
    strategy_id: str
    config_set_id: str
    status: str
    runtime_stats: dict[str, Any]
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, instance: StrategyInstance) -> "StrategyInstanceResponse":
        """Convert domain entity to response model."""
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
async def get_instance_repository() -> AsyncGenerator[StrategyInstanceRepository, None]:
    """Get StrategyInstanceRepository instance with database connection."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield StrategyInstanceRepositoryPG(conn)


# Endpoints
@router.get("", response_model=list[StrategyInstanceResponse])
async def list_instances(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_read),
) -> list[StrategyInstanceResponse]:
    """List StrategyInstances with optional status filter."""
    instances = await repo.list_all(status=status, limit=limit, offset=offset)
    return [StrategyInstanceResponse.from_domain(i) for i in instances]


@router.post(
    "",
    response_model=StrategyInstanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_instance(
    req: StrategyInstanceCreateRequest,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> StrategyInstanceResponse:
    """Create a new StrategyInstance (link Algorithm + ConfigurationSet)."""
    try:
        strategy_id = UUID(req.strategy_id)
        config_set_id = UUID(req.config_set_id)

        # Check if already exists
        existing = await repo.get_by_strategy_and_config(strategy_id, config_set_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instance with this strategy and config set already exists",
            )

        instance = StrategyInstance(
            strategy_id=strategy_id,
            config_set_id=config_set_id,
        )
        saved = await repo.save(instance)
        return StrategyInstanceResponse.from_domain(saved)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create instance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create instance",
        ) from None


@router.get("/{instance_id}", response_model=StrategyInstanceResponse)
async def get_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_read),
) -> StrategyInstanceResponse:
    """Get StrategyInstance by ID."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )
    return StrategyInstanceResponse.from_domain(instance)


@router.post("/{instance_id}/start", status_code=status.HTTP_200_OK)
async def start_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Start a StrategyInstance (hot-plug into pipeline)."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    try:
        instance.start()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} started", "status": "running"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/{instance_id}/stop", status_code=status.HTTP_200_OK)
async def stop_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Stop a StrategyInstance (unplug from pipeline)."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    try:
        instance.stop()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} stopped", "status": "stopped"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/{instance_id}/pause", status_code=status.HTTP_200_OK)
async def pause_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Pause a running StrategyInstance."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    try:
        instance.pause()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} paused", "status": "paused"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/{instance_id}/resume", status_code=status.HTTP_200_OK)
async def resume_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Resume a paused StrategyInstance."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )

    try:
        instance.resume()
        await repo.save(instance)
        return {"message": f"Instance {instance_id} resumed", "status": "running"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: UUID,
    repo: StrategyInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> None:
    """Delete a StrategyInstance."""
    success = await repo.delete(instance_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )
