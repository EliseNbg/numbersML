"""
Algorithm backtest API endpoints (REAL implementation).

Provides REST API for algorithm backtesting:
- Submit backtest job with StrategyInstance
- Check job status
- Retrieve backtest results

Architecture: Infrastructure Layer (API)
Dependencies: BacktestService, StrategyInstance repository, Auth
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src.application.services.backtest_service import BacktestService
from src.domain.repositories.strategy_instance_repository import StrategyInstanceRepository
from src.infrastructure.api.auth import require_read, require_trader
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.strategy_instance_repository_pg import (
    StrategyInstanceRepositoryPG,
)

router = APIRouter(prefix="/api/algorithm-backtests", tags=["algorithm-backtests"])
logger = logging.getLogger(__name__)

# In-memory job store (in production, use Redis or DB)
_backtest_jobs: dict[str, dict[str, Any]] = {}


# Time range presets
TIME_RANGE_PRESETS = {
    "4h": timedelta(hours=4),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


# ============================================================================
# Pydantic Models
# ============================================================================


class BacktestSubmitRequest(BaseModel):
    """Request to submit a backtest job."""

    strategy_instance_id: str = Field(..., description="StrategyInstance UUID")
    time_range: str = Field(..., description="Preset (4h, 12h, 1d, 3d, 7d, 30d) or custom")
    custom_start: datetime | None = None
    custom_end: datetime | None = None
    initial_balance: float = Field(default=10000.0, gt=0)

    @field_validator("time_range")
    def validate_time_range(cls, v: str) -> str:  # noqa: N805
        valid_presets = list(TIME_RANGE_PRESETS.keys())
        if v not in valid_presets and v != "custom":
            raise ValueError(f"Invalid time range. Use: {', '.join(valid_presets)} or 'custom'")
        return v


class BacktestJobResponse(BaseModel):
    """Response for job submission."""

    job_id: str
    status: str
    message: str
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None


# ============================================================================
# Dependencies
# ============================================================================


async def get_backtest_service() -> BacktestService:
    """Get BacktestService instance."""
    db_pool = await get_db_pool_async()
    return BacktestService(db_pool)


async def get_instance_repository() -> AsyncGenerator[StrategyInstanceRepository, None]:
    """Get StrategyInstanceRepository instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        yield StrategyInstanceRepositoryPG(conn)


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/jobs",
    response_model=BacktestJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_backtest_job(
    req: BacktestSubmitRequest,
    service: BacktestService = Depends(get_backtest_service),  # noqa: B008
    instance_repo: StrategyInstanceRepository = Depends(get_instance_repository),  # noqa: B008
    _auth: None = Depends(require_trader),
) -> BacktestJobResponse:
    """
    Submit a backtest job for asynchronous execution.

    Args:
        req: Backtest submission request
        service: BacktestService instance
        instance_repo: StrategyInstance repository

    Returns:
        Job submission confirmation

    Raises:
        404: StrategyInstance not found
        400: Invalid time range
        500: Failed to submit job
    """
    try:
        instance_id = UUID(req.strategy_instance_id)
        instance = await instance_repo.get_by_id(instance_id)
        if not instance:
            raise HTTPException(
                status_code=404,
                detail=f"StrategyInstance {instance_id} not found",
            )

        now = datetime.now(tz=UTC)
        if req.time_range == "custom":
            if not req.custom_start or not req.custom_end:
                raise HTTPException(
                    status_code=400,
                    detail="Custom time range requires custom_start and custom_end",
                )
            start_time = req.custom_start
            end_time = req.custom_end
        else:
            end_time = now
            start_time = end_time - TIME_RANGE_PRESETS[req.time_range]

        if start_time >= end_time:
            raise HTTPException(
                status_code=400,
                detail="Start time must be before end time",
            )

        import uuid

        job_id = str(uuid.uuid4())[:16]

        _backtest_jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0.0,
            "strategy_instance_id": instance_id,
            "algorithm_name": "Unknown",
            "time_range_start": start_time,
            "time_range_end": end_time,
            "initial_balance": req.initial_balance,
            "result": None,
            "error": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }

        asyncio.create_task(
            _execute_real_backtest(
                job_id, service, instance, start_time, end_time, req.initial_balance
            )
        )

        logger.info(f"Backtest job {job_id} submitted for instance {instance_id}")

        return BacktestJobResponse(
            job_id=job_id,
            status="pending",
            message=f"Backtest job {job_id} submitted successfully",
            time_range_start=start_time,
            time_range_end=end_time,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Failed to submit backtest job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit backtest job") from None


async def _execute_real_backtest(
    job_id: str,
    service: BacktestService,
    instance: Any,
    start_time: datetime,
    end_time: datetime,
    initial_balance: float,
) -> None:
    """
    Execute a backtest job asynchronously using real BacktestService.

    Args:
        job_id: Job identifier
        service: BacktestService instance
        instance: StrategyInstance to backtest
        start_time: Start of backtest period
        end_time: End of backtest period
        initial_balance: Starting capital
    """
    try:
        job = _backtest_jobs[job_id]
        job["status"] = "running"
        job["started_at"] = datetime.now(tz=UTC)
        job["progress"] = 0.1

        logger.info(f"Starting backtest job {job_id}")

        result = await service.run_backtest(
            job_id=job_id,
            strategy_instance=instance,
            time_range_start=start_time,
            time_range_end=end_time,
            initial_balance=initial_balance,
        )

        job["status"] = "completed"
        job["progress"] = 1.0
        job["completed_at"] = datetime.now(tz=UTC)
        job["result"] = result.to_dict()

        logger.info(f"Backtest job {job_id} completed. Return: {result.total_return_pct:.2f}%")

    except Exception as e:
        logger.error(f"Backtest job {job_id} failed: {e}", exc_info=True)
        if job_id in _backtest_jobs:
            _backtest_jobs[job_id]["status"] = "failed"
            _backtest_jobs[job_id]["error"] = str(e)


@router.get(
    "/jobs/{job_id}",
    response_model=dict[str, Any],
)
async def get_job_status(
    job_id: str,
    _auth: None = Depends(require_read),
) -> dict[str, Any]:
    """
    Get backtest job status or results.

    Args:
        job_id: Job identifier

    Returns:
        Job status or completed results

    Raises:
        404: Job not found
    """
    if job_id not in _backtest_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _backtest_jobs[job_id]

    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "strategy_instance_id": str(job["strategy_instance_id"]),
        "created_at": job["created_at"].isoformat(),
    }

    if job["started_at"]:
        response["started_at"] = job["started_at"].isoformat()
    if job["completed_at"]:
        response["completed_at"] = job["completed_at"].isoformat()
    if job["error"]:
        response["error"] = job["error"]

    if job["status"] == "completed" and job["result"]:
        response["result"] = job["result"]

    return response


@router.get("/jobs", response_model=list[dict[str, Any]])
async def list_backtest_jobs(
    _auth: None = Depends(require_read),
) -> list[dict[str, Any]]:
    """List all backtest jobs."""
    return [
        {
            "job_id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "strategy_instance_id": str(job["strategy_instance_id"]),
            "created_at": job["created_at"].isoformat(),
        }
        for job_id, job in _backtest_jobs.items()
    ]
