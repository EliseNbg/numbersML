"""
Algorithm lifecycle and management API endpoints.

Provides REST API for algorithm operations:
- CRUD for algorithm definitions
- Version control for algorithm configs
- Lifecycle operations (activate, deactivate, pause, resume)
- LLM-assisted algorithm generation and modification
- Audit trail (events, runs, backtests)

Architecture: Infrastructure Layer (API)
Dependencies: Application services, Domain models
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.application.services.llm_algorithm_service import LLMAlgorithmService
from src.domain.algorithms.algorithm_config import AlgorithmConfigVersion, AlgorithmDefinition
from src.domain.repositories.algorithm_repository import AlgorithmRepository
from src.domain.repositories.runtime_event_repository import AlgorithmRuntimeEventRepository
from src.infrastructure.api.auth import (
    AuthContext,
    check_live_mode_policy,
    require_trader,
)
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.algorithm_repository_pg import AlgorithmRepositoryPG
from src.infrastructure.repositories.runtime_event_repository_pg import (
    AlgorithmRuntimeEventRepositoryPG,
)

if TYPE_CHECKING:
    from src.application.services.algorithm_lifecycle import AlgorithmLifecycleService

router = APIRouter(prefix="/api/algorithms", tags=["algorithms"])


async def get_algorithm_repo() -> AsyncGenerator[AlgorithmRepository, None]:
    """Get AlgorithmRepository instance with database connection."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield AlgorithmRepositoryPG(conn)


async def get_event_repo() -> AsyncGenerator[AlgorithmRuntimeEventRepository, None]:
    """Get AlgorithmRuntimeEventRepository instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield AlgorithmRuntimeEventRepositoryPG(conn)


async def get_llm_service() -> AsyncGenerator[LLMAlgorithmService, None]:
    """Get LLMAlgorithmService instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        from src.infrastructure.repositories.algorithm_repository_pg import AlgorithmRepositoryPG

        repo = AlgorithmRepositoryPG(conn)
        yield LLMAlgorithmService(algorithm_repository=repo)


async def get_lifecycle_service(
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
    evt_repo: AlgorithmRuntimeEventRepository = Depends(get_event_repo),  # noqa: B008
) -> "AlgorithmLifecycleService":
    """Get AlgorithmLifecycleService with injected dependencies."""
    from src.application.services.algorithm_lifecycle import AlgorithmLifecycleService
    from src.application.services.algorithm_runner import AlgorithmRunner
    from src.domain.algorithms.base import AlgorithmManager

    runner = AlgorithmRunner(algorithm_manager=AlgorithmManager())
    return AlgorithmLifecycleService(
        algorithm_repository=repo,
        event_repository=evt_repo,
        algorithm_manager=runner,
        actor="api",
    )


logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================


class AlgorithmConfigSchema(BaseModel):
    """Canonical algorithm configuration schema."""

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


class AlgorithmCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    config: AlgorithmConfigSchema
    created_by: str = Field(default="system", max_length=255)


class AlgorithmUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    mode: str | None = Field(None, pattern="^(paper|live)$")
    config_version: int | None = Field(None, ge=1)


class AlgorithmVersionCreateRequest(BaseModel):
    config: AlgorithmConfigSchema
    schema_version: int = Field(default=1, ge=1)
    created_by: str = Field(default="system", max_length=255)


class AlgorithmActivateRequest(BaseModel):
    version: int | None = Field(None, ge=1)
    metadata: dict[str, Any] | None = None


# Response models
class AlgorithmResponse(BaseModel):
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
    def from_domain(cls, s: AlgorithmDefinition) -> "AlgorithmResponse":
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


class AlgorithmVersionResponse(BaseModel):
    algorithm_id: UUID
    version: int
    schema_version: int
    config: dict[str, Any]
    is_active: bool
    created_by: str
    created_at: datetime

    @classmethod
    def from_domain(cls, v: AlgorithmConfigVersion) -> "AlgorithmVersionResponse":
        return cls(
            algorithm_id=v.algorithm_id,
            version=v.version,
            schema_version=v.schema_version,
            config=v.config,
            is_active=v.is_active,
            created_by=v.created_by,
            created_at=v.created_at,
        )


class AlgorithmRuntimeStateResponse(BaseModel):
    algorithm_id: UUID
    algorithm_name: str
    state: str
    version: int
    last_error: str | None = None
    error_count: int = 0
    last_state_change: datetime | None = None


class LifecycleEventResponse(BaseModel):
    algorithm_id: UUID
    algorithm_name: str
    algorithm_version: int
    from_state: str | None
    to_state: str
    trigger: str
    details: dict[str, Any]
    occurred_at: datetime


# ============================================================================
# Algorithm Endpoints
# ============================================================================


# ============================================================================
# Algorithm Endpoints
# ============================================================================


@router.post("", response_model=AlgorithmResponse, status_code=status.HTTP_201_CREATED)
async def create_algorithm(
    req: AlgorithmCreateRequest,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> AlgorithmResponse:
    try:
        s = AlgorithmDefinition(
            name=req.name,
            description=req.description,
            mode=req.mode,
            status="draft",
            created_by=req.created_by,
        )
        saved = await repo.save(s)
        await repo.create_version(
            algorithm_id=saved.id,
            config=req.config.dict(),
            schema_version=req.config.dict().get("meta", {}).get("schema_version", 1),
            created_by=req.created_by,
        )
        return AlgorithmResponse.from_domain(saved)
    except Exception as e:
        logger.error(f"Failed to create algorithm: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create algorithm: {e}") from None


@router.get("", response_model=list[AlgorithmResponse])
async def list_algorithms(
    status: str | None = None,
    mode: str | None = None,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> list[AlgorithmResponse]:
    algorithms = await repo.get_all()
    if status:
        algorithms = [s for s in algorithms if s.status == status]
    if mode:
        algorithms = [s for s in algorithms if s.mode == mode]
    return [AlgorithmResponse.from_domain(s) for s in algorithms]


@router.get("/runtime", response_model=list[AlgorithmRuntimeStateResponse])
async def get_all_runtime_states(
    svc=Depends(get_lifecycle_service),  # noqa: B008
) -> list[AlgorithmRuntimeStateResponse]:
    states = await svc.get_all_runtime_states()
    return [
        AlgorithmRuntimeStateResponse(
            algorithm_id=s.algorithm_id,
            algorithm_name=s.algorithm_name,
            state=s.state.value,
            version=s.version,
            last_error=s.last_error,
            error_count=s.error_count,
            last_state_change=s.last_state_change,
        )
        for s in states
    ]


@router.get("/{algorithm_id}", response_model=AlgorithmResponse)
async def get_algorithm(
    algorithm_id: UUID,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> AlgorithmResponse:
    s = await repo.get_by_id(algorithm_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Algorithm {algorithm_id} not found")
    return AlgorithmResponse.from_domain(s)


@router.get("/{algorithm_id}/source")
async def get_algorithm_source(
    algorithm_id: UUID,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> dict[str, Any]:
    """Get the Python source code for an algorithm.

    Tries to determine the source file from the algorithm config,
    then reads and returns the source code.
    """
    s = await repo.get_by_id(algorithm_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Algorithm {algorithm_id} not found")

    # Try to get versions to find the config
    versions = await repo.list_versions(algorithm_id)
    if not versions:
        raise HTTPException(status_code=404, detail="No config versions found")

    # Get active version or latest
    config = versions[-1].config

    # Map signal type to source file
    signal_type = config.get("signal", {}).get("type", "")
    source_module = config.get("meta", {}).get("source_module", "")

    # If source_module is specified in config, use it
    if source_module:
        file_path = Path(f"{source_module.replace('.', '/')}.py")
    else:
        # Try to infer from signal type
        type_to_file = {
            "rsi": Path("src/domain/algorithms/algorithms_impl.py"),
            "macd": Path("src/domain/algorithms/algorithms_impl.py"),
            "sma": Path("src/domain/algorithms/algorithms_impl.py"),
            "bollinger": Path("src/domain/algorithms/algorithms_impl.py"),
            "multi": Path("src/domain/algorithms/algorithms_impl.py"),
            "simple_grid": Path("src/domain/algorithms/simple_grid_algorithm.py"),
            "rsi_ma": Path("src/domain/algorithms/rsi_moving_average_algorithm.py"),
        }
        file_path = type_to_file.get(signal_type)

    if not file_path or not file_path.exists():
        return {
            "source": None,
            "file_path": None,
            "message": f"Source file not found for algorithm type '{signal_type}'. "
            f"Specify 'meta.source_module' in config to map to source file.",
        }

    try:
        with open(file_path) as f:
            source = f.read()
        return {
            "source": source,
            "file_path": str(file_path),
            "message": "Source code retrieved successfully",
        }
    except Exception as e:
        logger.error(f"Failed to read source file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read source: {e}") from None


@router.put("/{algorithm_id}/source")
async def update_algorithm_source(
    algorithm_id: UUID,
    body: dict[str, Any],
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> dict[str, Any]:
    """Update the Python source code for an algorithm.

    Creates a backup of the original file, then writes the new source.
    """
    s = await repo.get_by_id(algorithm_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Algorithm {algorithm_id} not found")

    source = body.get("source")
    if not source:
        raise HTTPException(status_code=400, detail="Missing 'source' in request body")

    # Get file path (same logic as GET)
    versions = await repo.list_versions(algorithm_id)
    if not versions:
        raise HTTPException(status_code=404, detail="No config versions found")

    config = versions[-1].config
    signal_type = config.get("signal", {}).get("type", "")
    source_module = config.get("meta", {}).get("source_module", "")

    if source_module:
        file_path = Path(f"{source_module.replace('.', '/')}.py")
    else:
        type_to_file = {
            "rsi": Path("src/domain/algorithms/algorithms_impl.py"),
            "macd": Path("src/domain/algorithms/algorithms_impl.py"),
            "sma": Path("src/domain/algorithms/algorithms_impl.py"),
            "bollinger": Path("src/domain/algorithms/algorithms_impl.py"),
            "multi": Path("src/domain/algorithms/algorithms_impl.py"),
            "simple_grid": Path("src/domain/algorithms/simple_grid_algorithm.py"),
            "rsi_ma": Path("src/domain/algorithms/rsi_moving_average_algorithm.py"),
        }
        file_path = type_to_file.get(signal_type)

    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Source file not found for algorithm type '{signal_type}'",
        )

    try:
        # Create backup
        backup_path = file_path.with_suffix(
            f".py.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(file_path, backup_path)

        # Write new source
        with open(file_path, "w") as f:
            f.write(source)

        logger.info(f"Updated source file: {file_path}, backup: {backup_path}")
        return {
            "message": f"Source code saved successfully. Backup created at {backup_path}",
            "file_path": str(file_path),
            "backup_path": str(backup_path),
        }
    except Exception as e:
        logger.error(f"Failed to write source file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save source: {e}") from None


@router.put("/{algorithm_id}", response_model=AlgorithmResponse)
async def update_algorithm(
    algorithm_id: UUID,
    req: AlgorithmUpdateRequest,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> AlgorithmResponse:
    s = await repo.get_by_id(algorithm_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Algorithm {algorithm_id} not found")
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
    return AlgorithmResponse.from_domain(saved)


@router.delete("/{algorithm_id}", response_model=dict[str, Any])
async def delete_algorithm(
    algorithm_id: UUID,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> dict[str, Any]:
    """Delete an algorithm (sets status to archived)."""
    try:
        # Get algorithm first to check if it exists
        s = await repo.get_by_id(algorithm_id)
        if not s:
            raise HTTPException(status_code=404, detail=f"Algorithm {algorithm_id} not found")

        # Use archive instead of hard delete for safety
        s.status = "archived"
        await repo.save(s)
        return {"message": f"Algorithm {algorithm_id} archived"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete algorithm: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}") from None


# ============================================================================
# Version Endpoints
# ============================================================================


@router.post(
    "/{algorithm_id}/versions",
    response_model=AlgorithmVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_algorithm_version(
    algorithm_id: UUID,
    req: AlgorithmVersionCreateRequest,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> AlgorithmVersionResponse:
    try:
        v = await repo.create_version(
            algorithm_id=algorithm_id,
            config=req.config.dict(),
            schema_version=req.schema_version,
            created_by=req.created_by,
        )
        return AlgorithmVersionResponse.from_domain(v)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Failed to create version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create version: {e}") from None


@router.get("/{algorithm_id}/versions", response_model=list[AlgorithmVersionResponse])
async def list_algorithm_versions(
    algorithm_id: UUID,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> list[AlgorithmVersionResponse]:
    try:
        versions = await repo.list_versions(algorithm_id)
        return [AlgorithmVersionResponse.from_domain(v) for v in versions]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Failed to list versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list versions: {e}") from None


@router.post("/{algorithm_id}/versions/{version}/activate", response_model=dict[str, Any])
async def activate_algorithm_version(
    algorithm_id: UUID,
    version: int,
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
) -> dict[str, Any]:
    try:
        ok = await repo.set_active_version(algorithm_id, version)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
        return {"message": f"Version {version} activated", "algorithm_id": str(algorithm_id)}
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


@router.get("/{algorithm_id}/runtime", response_model=AlgorithmRuntimeStateResponse)
async def get_runtime_state(
    algorithm_id: UUID,
    svc=Depends(get_lifecycle_service),  # noqa: B008
) -> AlgorithmRuntimeStateResponse:
    st = await svc.get_runtime_state(algorithm_id)
    if not st:
        raise HTTPException(status_code=404, detail="Runtime state not found")
    return AlgorithmRuntimeStateResponse(
        algorithm_id=st.algorithm_id,
        algorithm_name=st.algorithm_name,
        state=st.state.value,
        version=st.version,
        last_error=st.last_error,
        error_count=st.error_count,
        last_state_change=st.last_state_change,
    )


@router.post("/{algorithm_id}/activate", response_model=dict[str, Any])
async def activate_algorithm(
    algorithm_id: UUID,
    req: AlgorithmActivateRequest,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        # Get algorithm to check mode for policy
        s = await repo.get_by_id(algorithm_id)
        if not s:
            raise HTTPException(status_code=404, detail=f"Algorithm {algorithm_id} not found")

        # Policy check: live mode requires admin
        check_live_mode_policy(s.mode, auth)

        ok = await svc.activate_algorithm(algorithm_id, req.version, req.metadata or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to activate")
        return {"message": f"Algorithm {algorithm_id} activated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Activation failed: {e}") from None


@router.post("/{algorithm_id}/deactivate", response_model=dict[str, Any])
async def deactivate_algorithm(
    algorithm_id: UUID,
    req: dict[str, Any] | None = None,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        ok = await svc.deactivate_algorithm(algorithm_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to deactivate")
        return {"message": f"Algorithm {algorithm_id} deactivated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Deactivation failed: {e}") from None


@router.post("/{algorithm_id}/pause", response_model=dict[str, Any])
async def pause_algorithm(
    algorithm_id: UUID,
    req: dict[str, Any] | None = None,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        ok = await svc.pause_algorithm(algorithm_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to pause")
        return {"message": f"Algorithm {algorithm_id} paused"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pause failed: {e}") from None


@router.post("/{algorithm_id}/resume", response_model=dict[str, Any])
async def resume_algorithm(
    algorithm_id: UUID,
    req: dict[str, Any] | None = None,
    svc=Depends(get_lifecycle_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    try:
        ok = await svc.resume_algorithm(algorithm_id, req or {})
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to resume")
        return {"message": f"Algorithm {algorithm_id} resumed"}
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


@router.get("/{algorithm_id}/events", response_model=list[LifecycleEventResponse])
async def get_lifecycle_events(
    algorithm_id: UUID,
    limit: int = 100,
    svc=Depends(get_lifecycle_service),  # noqa: B008
) -> list[LifecycleEventResponse]:
    events = await svc.get_lifecycle_events(algorithm_id, limit=limit)
    return [
        LifecycleEventResponse(
            algorithm_id=e.algorithm_id,
            algorithm_name=e.algorithm_name,
            algorithm_version=e.algorithm_version,
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
    """Request model for LLM algorithm generation."""

    description: str = Field(
        ..., min_length=10, description="Natural language algorithm description"
    )
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDC"], description="Trading symbols")
    timeframe: str = Field(default="1M", description="Candle timeframe")
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    created_by: str = Field(default="llm", max_length=255)


class LLMModifyRequest(BaseModel):
    """Request model for LLM algorithm modification."""

    change_request: str = Field(..., min_length=5, description="Natural language change request")
    modified_by: str = Field(default="llm", max_length=255)


@router.post("/generate", summary="Generate algorithm config via LLM")
async def generate_algorithm_config(
    req: LLMGenerateRequest,
    llm_svc=Depends(get_llm_service),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    """Generate algorithm configuration from natural language using LLM."""
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

    # Save as draft algorithm
    try:
        algorithm = await llm_svc.save_generated_algorithm(
            config=result.config,
            created_by=req.created_by,
        )
        return {
            "message": "Algorithm generated successfully",
            "algorithm_id": str(algorithm.id),
            "config": result.config,
            "validation_issues": [{"path": i.path, "message": i.message} for i in result.issues],
        }
    except Exception as e:
        logger.error(f"Failed to save generated algorithm: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save algorithm: {str(e)}",
        ) from None


@router.post("/{algorithm_id}/modify", summary="Modify algorithm via LLM")
async def modify_algorithm(
    algorithm_id: UUID,
    req: LLMModifyRequest,
    llm_svc=Depends(get_llm_service),  # noqa: B008
    repo: AlgorithmRepository = Depends(get_algorithm_repo),  # noqa: B008
    auth: AuthContext = Depends(require_trader),  # noqa: B008
) -> dict[str, Any]:
    """Modify existing algorithm configuration using LLM."""
    s = await repo.get_by_id(algorithm_id)
    if not s:
        raise HTTPException(status_code=404, detail="Algorithm not found")

    # Get current config version
    versions = await repo.list_versions(algorithm_id)
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
            algorithm_id=algorithm_id,
            config=result.config,
            schema_version=current_version.schema_version,
            created_by=req.modified_by,
        )
        return {
            "message": "Algorithm modified successfully",
            "algorithm_id": str(algorithm_id),
            "version": new_version.version,
            "config": result.config,
            "validation_issues": [{"path": i.path, "message": i.message} for i in result.issues],
        }
    except Exception as e:
        logger.error(f"Failed to save modified algorithm: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save modified algorithm: {str(e)}",
        ) from None
