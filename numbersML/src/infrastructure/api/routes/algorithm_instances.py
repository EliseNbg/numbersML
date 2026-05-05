"""
AlgorithmInstance API endpoints.

Provides REST API for AlgorithmInstance management:
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

from src.domain.repositories.algorithm_instance_repository import AlgorithmInstanceRepository
from src.domain.algorithms.algorithm_instance import (
    AlgorithmInstance,
)
from src.infrastructure.api.auth import require_read, require_trader
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.algorithm_instance_repository_pg import (
    AlgorithmInstanceRepositoryPG,
)

router = APIRouter(prefix="/api/algorithm-instances", tags=["algorithm-instances"])
logger = logging.getLogger(__name__)


# Pydantic Models
class AlgorithmInstanceCreateRequest(BaseModel):
    """Request model for creating AlgorithmInstance."""

    algorithm_id: str = Field(..., description="UUID of the Algorithm")
    config_set_id: str = Field(..., description="UUID of the ConfigurationSet")


class AlgorithmInstanceResponse(BaseModel):
    """Response model for AlgorithmInstance."""

    id: str
    algorithm_id: str
    config_set_id: str
    status: str
    runtime_stats: dict[str, Any]
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, instance: AlgorithmInstance) -> "AlgorithmInstanceResponse":
        """Convert domain entity to response model."""
        return cls(
            id=str(instance.id),
            algorithm_id=str(instance.algorithm_id),
            config_set_id=str(instance.config_set_id),
            status=instance.status.value,
            runtime_stats=instance.runtime_stats.to_dict(),
            started_at=instance.started_at,
            stopped_at=instance.stopped_at,
            created_at=instance.created_at,
            updated_at=instance.updated_at,
        )


# Dependencies
async def get_instance_repository() -> AsyncGenerator[AlgorithmInstanceRepository, None]:
    """Get AlgorithmInstanceRepository instance with database connection."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield AlgorithmInstanceRepositoryPG(conn)


# Endpoints
@router.get("", response_model=list[AlgorithmInstanceResponse])
async def list_instances(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_read),
) -> list[AlgorithmInstanceResponse]:
    """List AlgorithmInstances with optional status filter."""
    instances = await repo.list_all(status=status, limit=limit, offset=offset)
    return [AlgorithmInstanceResponse.from_domain(i) for i in instances]


@router.post(
    "",
    response_model=AlgorithmInstanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_instance(
    req: AlgorithmInstanceCreateRequest,
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> AlgorithmInstanceResponse:
    """Create a new AlgorithmInstance (link Algorithm + ConfigurationSet)."""
    try:
        algorithm_id = UUID(req.algorithm_id)
        config_set_id = UUID(req.config_set_id)

        # Check if already exists
        existing = await repo.get_by_algorithm_and_config(algorithm_id, config_set_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instance with this algorithm and config set already exists",
            )

        instance = AlgorithmInstance(
            algorithm_id=algorithm_id,
            config_set_id=config_set_id,
        )
        saved = await repo.save(instance)
        return AlgorithmInstanceResponse.from_domain(saved)

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


@router.get("/{instance_id}", response_model=AlgorithmInstanceResponse)
async def get_instance(
    instance_id: UUID,
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_read),
) -> AlgorithmInstanceResponse:
    """Get AlgorithmInstance by ID."""
    instance = await repo.get_by_id(instance_id)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )
    return AlgorithmInstanceResponse.from_domain(instance)


@router.post("/{instance_id}/start", status_code=status.HTTP_200_OK)
async def start_instance(
    instance_id: UUID,
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Start a AlgorithmInstance (hot-plug into pipeline)."""
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
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Stop a AlgorithmInstance (unplug from pipeline)."""
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
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Pause a running AlgorithmInstance."""
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
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> dict[str, Any]:
    """Resume a paused AlgorithmInstance."""
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
    repo: AlgorithmInstanceRepository = Depends(get_instance_repository),
    _auth: None = Depends(require_trader),
) -> None:
    """Delete a AlgorithmInstance."""
    success = await repo.delete(instance_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found",
        )
