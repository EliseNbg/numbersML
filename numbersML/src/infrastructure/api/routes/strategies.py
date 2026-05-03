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
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.application.services.llm_strategy_service import LLMStrategyService
from src.domain.repositories.runtime_event_repository import StrategyRuntimeEventRepository
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition
from src.infrastructure.api.auth import (
    AuthContext,
    check_live_mode_policy,
    require_trader,
)
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.runtime_event_repository_pg import (
    StrategyRuntimeEventRepositoryPG,
)
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG

if TYPE_CHECKING:
    from src.application.services.strategy_lifecycle import StrategyLifecycleService

router = APIRouter(prefix="/api/strategies", tags=["strategies"])
async def get_strategy_repo() -> AsyncGenerator[StrategyRepository, None]:
    """Get StrategyRepository instance with database connection."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield StrategyRepositoryPG(conn)


async def get_event_repo() -> AsyncGenerator[StrategyRuntimeEventRepository, None]:
    """Get StrategyRuntimeEventRepository instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield StrategyRuntimeEventRepositoryPG(conn)


async def get_llm_service() -> AsyncGenerator[LLMStrategyService, None]:
    """Get LLMStrategyService instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG

        repo = StrategyRepositoryPG(conn)
        yield LLMStrategyService(strategy_repository=repo)

async def get_lifecycle_service(
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
    evt_repo: StrategyRuntimeEventRepository = Depends(get_event_repo),  # noqa: B008
) -> "StrategyLifecycleService":
    """Get StrategyLifecycleService with injected dependencies."""
    from src.application.services.strategy_lifecycle import StrategyLifecycleService
    from src.application.services.strategy_runner import StrategyRunner
    from src.domain.strategies.base import StrategyManager

    runner = StrategyRunner(strategy_manager=StrategyManager())
    return StrategyLifecycleService(
        strategy_repository=repo,
        event_repository=evt_repo,
        strategy_manager=runner,
        actor="api",
    )



logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================


class StrategyConfigSchema(BaseModel):
    """Canonical strategy configuration schema."""

    meta: dict[str, Any] = Field(default_factory=dict)
    universe: dict[str, Any] = Field(default_factory=dict)
    signal: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    status: str = Field(default="draft", pattern="^(draft|validated|active|paused|archived)$")

    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        if "meta" in d and "schema_version" not in d["meta"]:
            d["meta"]["schema_version"] = 1
        return d


class StrategyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    config: StrategyConfigSchema
    created_by: str = Field(default="system", max_length=255)


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    mode: str | None = Field(None, pattern="^(paper|live)$")
    config_version: int | None = Field(None, ge=1)


class StrategyVersionCreateRequest(BaseModel):
    config: StrategyConfigSchema
    schema_version: int = Field(default=1, ge=1)
    created_by: str = Field(default="system", max_length=255)


class StrategyActivateRequest(BaseModel):
    version: int | None = Field(None, ge=1)
    metadata: dict[str, Any] | None = None


# Response models
class StrategyResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
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
    config: dict[str, Any]
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
    last_error: str | None = None
    error_count: int = 0
    last_state_change: datetime | None = None


class LifecycleEventResponse(BaseModel):
    strategy_id: UUID
    strategy_name: str
    strategy_version: int
    from_state: str | None
    to_state: str
    trigger: str
    details: dict[str, Any]
    occurred_at: datetime


# ============================================================================
# Strategy Endpoints
# ============================================================================


# ============================================================================
# Strategy Endpoints
# ============================================================================


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    req: StrategyCreateRequest,
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
) -> StrategyResponse:
    try:
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
        raise HTTPException(status_code=500, detail=f"Failed to create strategy: {e}") from None


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    status: str | None = None,
    mode: str | None = None,
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
) -> list[StrategyResponse]:
    strategies = await repo.get_all()
    if status:
        strategies = [s for s in strategies if s.status == status]
    if mode:
        strategies = [s for s in strategies if s.mode == mode]
    return [StrategyResponse.from_domain(s) for s in strategies]


@router.get("/runtime", response_model=list[StrategyRuntimeStateResponse])
async def get_all_runtime_states(
    svc=Depends(get_lifecycle_service),  # noqa: B008
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



@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: UUID,
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
) -> StrategyResponse:
    s = await repo.get_by_id(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return StrategyResponse.from_domain(s)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: UUID,
    req: StrategyUpdateRequest,
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
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
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
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
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Failed to create version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create version: {e}") from None


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionResponse])
async def list_strategy_versions(
    strategy_id: UUID,
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
) -> list[StrategyVersionResponse]:
    try:
        versions = await repo.list_versions(strategy_id)
        return [StrategyVersionResponse.from_domain(v) for v in versions]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Failed to list versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list versions: {e}") from None


@router.post("/{strategy_id}/versions/{version}/activate", response_model=dict[str, Any])
async def activate_strategy_version(
    strategy_id: UUID,
    version: int,
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
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
        raise HTTPException(status_code=500, detail=f"Failed to activate version: {e}") from None


# ============================================================================
# Lifecycle Endpoints
# ============================================================================


# ============================================================================
# Runtime State
# ============================================================================


@router.get("/{strategy_id}/runtime", response_model=StrategyRuntimeStateResponse)
async def get_runtime_state(
    strategy_id: UUID,
    svc=Depends(get_lifecycle_service),  # noqa: B008
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


@router.post("/{strategy_id}/activate", response_model=dict[str, Any])
async def activate_strategy(
    strategy_id: UUID,
    req: StrategyActivateRequest,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        # Get strategy to check mode for policy
        s = await repo.get_by_id(strategy_id)
        if not s:
            raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

        # Policy check: live mode requires admin
        check_live_mode_policy(s.mode, auth)

        ok = await svc.activate_strategy(strategy_id, req.version, req.metadata or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to activate")
        return {"message": f"Strategy {strategy_id} activated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Activation failed: {e}") from None


@router.post("/{strategy_id}/deactivate", response_model=dict[str, Any])
async def deactivate_strategy(
    strategy_id: UUID,
    req: dict[str, Any] | None = None,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        ok = await svc.deactivate_strategy(strategy_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to deactivate")
        return {"message": f"Strategy {strategy_id} deactivated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Deactivation failed: {e}") from None


@router.post("/{strategy_id}/pause", response_model=dict[str, Any])
async def pause_strategy(
    strategy_id: UUID,
    req: dict[str, Any] | None = None,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        ok = await svc.pause_strategy(strategy_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to pause")
        return {"message": f"Strategy {strategy_id} paused"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pause failed: {e}") from None


@router.post("/{strategy_id}/resume", response_model=dict[str, Any])
async def resume_strategy(
    strategy_id: UUID,
    req: dict[str, Any] | None = None,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        ok = await svc.resume_strategy(strategy_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to resume")
        return {"message": f"Strategy {strategy_id} resumed"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}") from None


# ============================================================================
# Events
# ============================================================================


@router.get("/{strategy_id}/events", response_model=list[LifecycleEventResponse])
async def get_lifecycle_events(
    strategy_id: UUID,
    limit: int = 100,
    svc=Depends(get_lifecycle_service),  # noqa: B008
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


class LLMGenerateRequest(BaseModel):
    """Request model for LLM strategy generation."""

    description: str = Field(
        ..., min_length=10, description="Natural language strategy description"
    )
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDC"], description="Trading symbols")
    timeframe: str = Field(default="1M", description="Candle timeframe")
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    created_by: str = Field(default="llm", max_length=255)


class LLMModifyRequest(BaseModel):
    """Request model for LLM strategy modification."""

    change_request: str = Field(..., min_length=5, description="Natural language change request")
    modified_by: str = Field(default="llm", max_length=255)


@router.post("/generate", summary="Generate strategy config via LLM")
async def generate_strategy_config(
    req: LLMGenerateRequest,
    llm_svc=Depends(get_llm_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    """Generate strategy configuration from natural language using LLM."""
    result = await llm_svc.generate_config(
        description=req.description,
        symbols=req.symbols,
        timeframe=req.timeframe,
        mode=req.mode,
        created_by=req.created_by,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": result.error_message,
                "issues": [{"path": i.path, "message": i.message} for i in result.issues],
                "raw_response": result.raw_response,
            },
        )

    # Save as draft strategy
    try:
        strategy = await llm_svc.save_generated_strategy(
            config=result.config,
            created_by=req.created_by,
        )
        return {
            "message": "Strategy generated successfully",
            "strategy_id": str(strategy.id),
            "config": result.config,
            "validation_issues": [{"path": i.path, "message": i.message} for i in result.issues],
        }
    except Exception as e:
        logger.error(f"Failed to save generated strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save strategy: {str(e)}",
        ) from None

@router.post("/{strategy_id}/modify", summary="Modify strategy via LLM")
async def modify_strategy(
    strategy_id: UUID,
    req: LLMModifyRequest,
    llm_svc=Depends(get_llm_service),  # noqa: B008
    repo: StrategyRepository = Depends(get_strategy_repo),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    """Modify existing strategy configuration using LLM."""
    s = await repo.get_by_id(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Get current config version
    versions = await repo.list_versions(strategy_id)
    if not versions:
        raise HTTPException(status_code=404, detail="No config versions found")

    current_version = versions[-1]
    existing_config = current_version.config

    result = await llm_svc.modify_config(
        existing_config=existing_config,
        change_request=req.change_request,
        modified_by=req.modified_by,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": result.error_message,
                "issues": [{"path": i.path, "message": i.message} for i in result.issues],
                "raw_response": result.raw_response,
            },
        )

    # Save as new version (draft)
    try:
        new_version = await repo.create_version(
            strategy_id=strategy_id,
            config=result.config,
            schema_version=current_version.schema_version,
            created_by=req.modified_by,
        )
        return {
            "message": "Strategy modified successfully",
            "strategy_id": str(strategy_id),
            "version": new_version.version,
            "config": result.config,
            "validation_issues": [{"path": i.path, "message": i.message} for i in result.issues],
        }
    except Exception as e:
        logger.error(f"Failed to save modified strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save modified strategy: {str(e)}",
        ) from None
