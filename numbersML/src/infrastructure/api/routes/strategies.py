"""
Strategy lifecycle and management API endpoints.

Provides REST API for strategy operations:
- CRUD for strategy definitions
- Version control for strategy configs
- Lifecycle operations (activate, deactivate, pause, resume)
- LLM-assisted strategy generation and modification
- Audit trail (events, runs, backtests)

Architecture: Infrastructure Layer (API)
Dependencies: Application services, Domain models
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.domain.repositories.runtime_event_repository import StrategyRuntimeEventRepository
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.runtime_event_repository_pg import (
    StrategyRuntimeEventRepositoryPG,
)
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================


class StrategyConfigSchema(BaseModel):
    """Canonical strategy configuration schema."""

    meta: Dict[str, Any] = Field(default_factory=dict)
    universe: Dict[str, Any] = Field(default_factory=dict)
    signal: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)
    execution: Dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    status: str = Field(default="draft", pattern="^(draft|validated|active|paused|archived)$")

    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        if "meta" in d and "schema_version" not in d["meta"]:
            d["meta"]["schema_version"] = 1
        return d


class StrategyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    config: StrategyConfigSchema
    created_by: str = Field(default="system", max_length=255)


class StrategyUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    mode: Optional[str] = Field(None, pattern="^(paper|live)$")
    config_version: Optional[int] = Field(None, ge=1)


class StrategyVersionCreateRequest(BaseModel):
    config: StrategyConfigSchema
    schema_version: int = Field(default=1, ge=1)
    created_by: str = Field(default="system", max_length=255)


class StrategyActivateRequest(BaseModel):
    version: Optional[int] = Field(None, ge=1)
    metadata: Optional[Dict[str, Any]] = None


# Response models
class StrategyResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    mode: str
    status: str
    current_version: int
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, s: StrategyDefinition) -> "StrategyResponse":
        return cls(
            id=s.id,
            name=s.name,
            description=s.description,
            mode=s.mode,
            status=s.status,
            current_version=s.current_version,
            created_by=s.created_by,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


class StrategyVersionResponse(BaseModel):
    strategy_id: UUID
    version: int
    schema_version: int
    config: Dict[str, Any]
    is_active: bool
    created_by: str
    created_at: datetime

    @classmethod
    def from_domain(cls, v: StrategyConfigVersion) -> "StrategyVersionResponse":
        return cls(
            strategy_id=v.strategy_id,
            version=v.version,
            schema_version=v.schema_version,
            config=v.config,
            is_active=v.is_active,
            created_by=v.created_by,
            created_at=v.created_at,
        )


class StrategyRuntimeStateResponse(BaseModel):
    strategy_id: UUID
    strategy_name: str
    state: str
    version: int
    last_error: Optional[str] = None
    error_count: int = 0
    last_state_change: Optional[datetime] = None


class LifecycleEventResponse(BaseModel):
    strategy_id: UUID
    strategy_name: str
    strategy_version: int
    from_state: Optional[str]
    to_state: str
    trigger: str
    details: Dict[str, Any]
    occurred_at: datetime


# ============================================================================
# Dependencies
# ============================================================================


async def get_strategy_repo() -> StrategyRepository:
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        return StrategyRepositoryPG(conn)


async def get_event_repo() -> StrategyRuntimeEventRepository:
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        return StrategyRuntimeEventRepositoryPG(conn)


# ============================================================================
# Strategy Endpoints
# ============================================================================


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    req: StrategyCreateRequest,
) -> StrategyResponse:
    try:
        from datetime import timezone

        repo = await get_strategy_repo()
        s = StrategyDefinition(
            name=req.name,
            description=req.description,
            mode=req.mode,
            status="draft",
            created_by=req.created_by,
        )
        saved = await repo.save(s)
        await repo.create_version(
            strategy_id=saved.id,
            config=req.config.dict(),
            schema_version=req.config.dict().get("meta", {}).get("schema_version", 1),
            created_by=req.created_by,
        )
        return StrategyResponse.from_domain(saved)
    except Exception as e:
        logger.error(f"Failed to create strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create strategy: {e}")


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    status: Optional[str] = None,
    mode: Optional[str] = None,
    repo: StrategyRepository = Depends(get_strategy_repo),
) -> list[StrategyResponse]:
    strategies = await repo.get_all()
    if status:
        strategies = [s for s in strategies if s.status == status]
    if mode:
        strategies = [s for s in strategies if s.mode == mode]
    return [StrategyResponse.from_domain(s) for s in strategies]


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: UUID,
    repo: StrategyRepository = Depends(get_strategy_repo),
) -> StrategyResponse:
    s = await repo.get_by_id(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return StrategyResponse.from_domain(s)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: UUID,
    req: StrategyUpdateRequest,
    repo: StrategyRepository = Depends(get_strategy_repo),
) -> StrategyResponse:
    s = await repo.get_by_id(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    updated = False
    if req.name is not None:
        s.name = req.name
        updated = True
    if req.description is not None:
        s.description = req.description
        updated = True
    if req.mode is not None:
        s.mode = req.mode
        updated = True
    if not updated:
        raise HTTPException(status_code=400, detail="No fields to update")
    saved = await repo.save(s)
    return StrategyResponse.from_domain(saved)


# ============================================================================
# Version Endpoints
# ============================================================================


@router.post(
    "/{strategy_id}/versions",
    response_model=StrategyVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy_version(
    strategy_id: UUID,
    req: StrategyVersionCreateRequest,
    repo: StrategyRepository = Depends(get_strategy_repo),
) -> StrategyVersionResponse:
    try:
        v = await repo.create_version(
            strategy_id=strategy_id,
            config=req.config.dict(),
            schema_version=req.schema_version,
            created_by=req.created_by,
        )
        return StrategyVersionResponse.from_domain(v)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create version: {e}")


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionResponse])
async def list_strategy_versions(
    strategy_id: UUID,
    repo: StrategyRepository = Depends(get_strategy_repo),
) -> list[StrategyVersionResponse]:
    try:
        versions = await repo.list_versions(strategy_id)
        return [StrategyVersionResponse.from_domain(v) for v in versions]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list versions: {e}")


@router.post("/{strategy_id}/versions/{version}/activate", response_model=dict[str, Any])
async def activate_strategy_version(
    strategy_id: UUID,
    version: int,
    repo: StrategyRepository = Depends(get_strategy_repo),
) -> dict[str, Any]:
    try:
        ok = await repo.set_active_version(strategy_id, version)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
        return {"message": f"Version {version} activated", "strategy_id": str(strategy_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to activate version: {e}")


# ============================================================================
# Lifecycle Endpoints
# ============================================================================


async def get_lifecycle_service():
    from src.application.services.strategy_lifecycle import StrategyLifecycleService
    from src.application.services.strategy_runner import StrategyRunner
    from src.domain.strategies.base import StrategyManager

    repo = await get_strategy_repo()
    evt_repo = await get_event_repo()
    runner = StrategyRunner(strategy_manager=StrategyManager())
    return StrategyLifecycleService(
        strategy_repository=repo,
        event_repository=evt_repo,
        strategy_manager=runner,
        actor="api",
    )


@router.post("/{strategy_id}/activate", response_model=dict[str, Any])
async def activate_strategy(
    strategy_id: UUID,
    req: StrategyActivateRequest,
    svc=Depends(get_lifecycle_service),
) -> dict[str, Any]:
    try:
        ok = await svc.activate_strategy(strategy_id, req.version, req.metadata or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to activate")
        return {"message": f"Strategy {strategy_id} activated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Activation failed: {e}")


@router.post("/{strategy_id}/deactivate", response_model=dict[str, Any])
async def deactivate_strategy(
    strategy_id: UUID,
    req: Optional[Dict[str, Any]] = None,
    svc=Depends(get_lifecycle_service),
) -> dict[str, Any]:
    try:
        ok = await svc.deactivate_strategy(strategy_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to deactivate")
        return {"message": f"Strategy {strategy_id} deactivated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Deactivation failed: {e}")


@router.post("/{strategy_id}/pause", response_model=dict[str, Any])
async def pause_strategy(
    strategy_id: UUID,
    req: Optional[Dict[str, Any]] = None,
    svc=Depends(get_lifecycle_service),
) -> dict[str, Any]:
    try:
        ok = await svc.pause_strategy(strategy_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to pause")
        return {"message": f"Strategy {strategy_id} paused"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pause failed: {e}")


@router.post("/{strategy_id}/resume", response_model=dict[str, Any])
async def resume_strategy(
    strategy_id: UUID,
    req: Optional[Dict[str, Any]] = None,
    svc=Depends(get_lifecycle_service),
) -> dict[str, Any]:
    try:
        ok = await svc.resume_strategy(strategy_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to resume")
        return {"message": f"Strategy {strategy_id} resumed"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")


# ============================================================================
# Runtime State
# ============================================================================


@router.get("/{strategy_id}/runtime", response_model=StrategyRuntimeStateResponse)
async def get_runtime_state(
    strategy_id: UUID,
    svc=Depends(get_lifecycle_service),
) -> StrategyRuntimeStateResponse:
    st = await svc.get_runtime_state(strategy_id)
    if not st:
        raise HTTPException(status_code=404, detail="Runtime state not found")
    return StrategyRuntimeStateResponse(
        strategy_id=st.strategy_id,
        strategy_name=st.strategy_name,
        state=st.state.value,
        version=st.version,
        last_error=st.last_error,
        error_count=st.error_count,
        last_state_change=st.last_state_change,
    )


@router.get("/runtime", response_model=list[StrategyRuntimeStateResponse])
async def get_all_runtime_states(
    svc=Depends(get_lifecycle_service),
) -> list[StrategyRuntimeStateResponse]:
    states = await svc.get_all_runtime_states()
    return [
        StrategyRuntimeStateResponse(
            strategy_id=s.strategy_id,
            strategy_name=s.strategy_name,
            state=s.state.value,
            version=s.version,
            last_error=s.last_error,
            error_count=s.error_count,
            last_state_change=s.last_state_change,
        )
        for s in states
    ]


# ============================================================================
# Events
# ============================================================================


@router.get("/{strategy_id}/events", response_model=list[LifecycleEventResponse])
async def get_lifecycle_events(
    strategy_id: UUID,
    limit: int = 100,
    svc=Depends(get_lifecycle_service),
) -> list[LifecycleEventResponse]:
    events = await svc.get_lifecycle_events(strategy_id, limit=limit)
    return [
        LifecycleEventResponse(
            strategy_id=e.strategy_id,
            strategy_name=e.strategy_name,
            strategy_version=e.strategy_version,
            from_state=e.from_state.value if e.from_state else None,
            to_state=e.to_state.value,
            trigger=e.trigger,
            details=e.details,
            occurred_at=e.occurred_at,
        )
        for e in events
    ]


# ============================================================================
# LLM Generation
# ============================================================================


@router.post("/generate", summary="Generate strategy config (placeholder)")
async def generate_strategy_config(req: Dict[str, Any]) -> dict[str, Any]:
    return {
        "message": "LLM generation placeholder",
        "note": "Integrate with OpenAI/Anthropic APIs for production use",
        "config": StrategyConfigSchema().dict(),
    }


@router.post("/{strategy_id}/modify", summary="Modify strategy via LLM (placeholder)")
async def modify_strategy(strategy_id: UUID, req: Dict[str, Any]) -> dict[str, Any]:
    repo = await get_strategy_repo()
    s = await repo.get_by_id(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {
        "message": f"Strategy {strategy_id} modification suggestion",
        "note": "Integrate with LLM APIs for production use",
    }
