"""
Strategy backtest API endpoints.

Provides REST API for strategy backtesting:
- Start backtest jobs (async)
- Check job status
- Retrieve backtest results

Architecture: Infrastructure Layer (API)
Dependencies: Application services, Domain models
"""

import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from typing import Union

from src.domain.strategies.strategy_config import StrategyDefinition, StrategyConfigVersion
from src.domain.repositories.strategy_repository import StrategyRepository
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG
from src.infrastructure.repositories.strategy_backtest_repository_pg import (
    StrategyBacktestRepositoryPG,
)

router = APIRouter(prefix="/api/strategy-backtests", tags=["strategy-backtests"])

logger = logging.getLogger(__name__)

# In-memory job store (in production, use Redis or DB)
_backtest_jobs: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Pydantic Models
# ============================================================================


class StrategyBacktestRequest(BaseModel):
    """Request model for strategy backtest."""

    strategy_id: UUID
    strategy_version: Optional[int] = Field(
        None, ge=1, description="Specific version (defaults to active)"
    )
    time_range_start: datetime = Field(..., description="Start time for backtest")
    time_range_end: datetime = Field(..., description="End time for backtest")
    initial_balance: float = Field(default=10000.0, gt=0, description="Initial capital")
    symbol: Optional[str] = Field(None, description="Optional symbol filter")
    include_equity_curve: bool = Field(default=True, description="Include equity curve in results")
    include_trades: bool = Field(default=True, description="Include individual trades")
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("time_range_end")
    def validate_time_range(cls, v, info):
        if "time_range_start" in info.data and v <= info.data["time_range_start"]:
            raise ValueError("time_range_end must be after time_range_start")
        return v


class BacktestJobSubmitResponse(BaseModel):
    """Response when submitting a backtest job."""

    job_id: str
    status: str
    message: str


class BacktestJobStatusResponse(BaseModel):
    """Response for backtest job status."""

    job_id: str
    status: str  # pending, running, completed, failed
    progress: float  # 0.0 to 1.0
    strategy_id: Optional[UUID] = None
    strategy_name: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class BacktestResultResponse(BaseModel):
    """Response for completed backtest results."""

    job_id: str
    status: str
    strategy_id: UUID
    strategy_name: str
    strategy_version: int
    time_range_start: datetime
    time_range_end: datetime
    initial_balance: float
    final_balance: float
    metrics: Dict[str, Any]
    trades: Optional[List[Dict[str, Any]]] = None
    equity_curve: Optional[List[Dict[str, Any]]] = None
    created_at: datetime


# ============================================================================
# Dependency injections
# ============================================================================


async def get_strategy_repository() -> StrategyRepository:
    """Get StrategyRepository instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        return StrategyRepositoryPG(conn)


async def get_backtest_repository():
    """Get StrategyBacktestRepository instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        return StrategyBacktestRepositoryPG(conn)


# ============================================================================
# Backtest Job Management
# ============================================================================


@router.post(
    "/jobs",
    response_model=BacktestJobSubmitResponse,
    summary="Submit backtest job",
    description="Submit a strategy backtest job for asynchronous execution.",
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_backtest_job(
    request: StrategyBacktestRequest,
    repository: StrategyRepository = Depends(get_strategy_repository),
) -> BacktestJobSubmitResponse:
    """
    Submit a strategy backtest job.

    The job is queued for asynchronous execution. Use the job_id to check status
    and retrieve results.

    Args:
        request: Backtest parameters
        repository: Strategy repository instance

    Returns:
        Job submission confirmation with job_id

    Raises:
        404: Strategy not found
        400: Invalid time range
        500: Failed to submit job
    """
    try:
        # Validate strategy exists
        strategy = await repository.get_by_id(request.strategy_id)
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {request.strategy_id} not found",
            )

        # Generate job ID
        import uuid

        job_id = str(uuid.uuid4())[:16]

        # Store job
        _backtest_jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0.0,
            "strategy_id": request.strategy_id,
            "strategy_name": strategy.name,
            "strategy_version": request.strategy_version or strategy.current_version,
            "time_range_start": request.time_range_start,
            "time_range_end": request.time_range_end,
            "initial_balance": request.initial_balance,
            "symbol": request.symbol,
            "include_equity_curve": request.include_equity_curve,
            "include_trades": request.include_trades,
            "metadata": request.metadata or {},
            "created_at": datetime.now(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

        # Start async execution (non-blocking)
        asyncio.create_task(_execute_backtest_job(job_id))

        logger.info(f"Backtest job {job_id} submitted for strategy {request.strategy_id}")

        return BacktestJobSubmitResponse(
            job_id=job_id,
            status="pending",
            message=f"Backtest job {job_id} submitted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit backtest job: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit backtest job: {str(e)}",
        )


async def _execute_backtest_job(job_id: str) -> None:
    """
    Execute a backtest job asynchronously.

    This function simulates backtest execution. In production, this would:
    1. Fetch historical candle data
    2. Apply strategy signals
    3. Simulate trades
    4. Calculate performance metrics
    5. Persist results to database

    Args:
        job_id: Job identifier
    """
    try:
        job = _backtest_jobs[job_id]
        job["status"] = "running"
        job["started_at"] = datetime.now()
        job["progress"] = 0.1

        logger.info(f"Starting backtest job {job_id}")

        # Simulate backtest steps
        steps = [
            ("fetching_data", 0.3),
            ("processing_signals", 0.5),
            ("simulating_trades", 0.7),
            ("calculating_metrics", 0.9),
            ("persisting_results", 1.0),
        ]

        for step_name, progress in steps:
            # Simulate work
            await asyncio.sleep(0.5)
            job["progress"] = progress
            logger.debug(f"Job {job_id}: {step_name} complete")

        # Generate simulated results (in production, use real data)
        import random

        random.seed(job_id)

        initial_balance = job["initial_balance"]
        total_return = random.uniform(-0.2, 0.5)  # -20% to +50%
        final_balance = initial_balance * (1 + total_return)

        num_trades = random.randint(10, 100)
        wins = int(num_trades * random.uniform(0.4, 0.7))

        # Simulate trades
        trades = []
        equity_curve = [{"time": job["time_range_start"].isoformat(), "balance": initial_balance}]

        running_balance = initial_balance
        for i in range(num_trades):
            pnl = random.uniform(-0.05, 0.08)
            running_balance *= 1 + pnl

            trades.append(
                {
                    "entry_time": (job["time_range_start"].timestamp() + i * 3600) / 1000,
                    "exit_time": (job["time_range_start"].timestamp() + (i + 1) * 3600) / 1000,
                    "pnl": pnl,
                    "pnl_percent": pnl * 100,
                }
            )

            equity_curve.append(
                {
                    "time": (job["time_range_start"].timestamp() + (i + 1) * 3600) / 1000,
                    "balance": running_balance,
                }
            )

        equity_curve.append(
            {
                "time": job["time_range_end"].isoformat(),
                "balance": final_balance,
            }
        )

        # Calculate metrics
        win_rate = wins / num_trades if num_trades > 0 else 0
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        max_drawdown = random.uniform(0, 0.15)
        sharpe_ratio = random.uniform(0.5, 2.5)

        metrics = {
            "total_trades": num_trades,
            "win_rate": win_rate,
            "total_return": total_return,
            "final_balance": final_balance,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "avg_trade_return": total_return / num_trades if num_trades > 0 else 0,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
        }

        # Persist to database (if repository available)
        try:
            db_pool = await get_db_pool_async()
            async with db_pool.acquire() as conn:
                backtest_repo = StrategyBacktestRepositoryPG(conn)
                await backtest_repo.save(
                    strategy_id=job["strategy_id"],
                    strategy_version_id=None,  # Would need to fetch
                    time_range_start=job["time_range_start"],
                    time_range_end=job["time_range_end"],
                    initial_balance=job["initial_balance"],
                    final_balance=final_balance,
                    metrics=metrics,
                    trades=trades if job["include_trades"] else [],
                    equity_curve=equity_curve if job["include_equity_curve"] else [],
                    metadata=job["metadata"],
                    created_by="api",
                )
        except Exception as db_error:
            logger.warning(f"Failed to persist backtest results to DB: {db_error}")

        # Store results
        job["status"] = "completed"
        job["progress"] = 1.0
        job["completed_at"] = datetime.now()
        job["result"] = {
            "metrics": metrics,
            "trades": trades if job["include_trades"] else None,
            "equity_curve": equity_curve if job["include_equity_curve"] else None,
        }

        logger.info(f"Backtest job {job_id} completed. Return: {total_return:.2%}")

    except Exception as e:
        logger.error(f"Backtest job {job_id} failed: {e}", exc_info=True)
        if job_id in _backtest_jobs:
            _backtest_jobs[job_id]["status"] = "failed"
            _backtest_jobs[job_id]["error"] = str(e)


@router.get(
    "/jobs/{job_id}",
    response_model=Union[BacktestJobStatusResponse, BacktestResultResponse],
    summary="Get job status or results",
    description="Get backtest job status. Returns results if completed.",
)
async def get_job_status(
    job_id: str,
) -> Union[BacktestJobStatusResponse, BacktestResultResponse]:
    """
    Get backtest job status or results.

    Args:
        job_id: Job identifier

    Returns:
        Job status or completed results

    Raises:
        404: Job not found
    """
    try:
        if job_id not in _backtest_jobs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )

        job = _backtest_jobs[job_id]

        if job["status"] == "completed":
            result = job["result"] or {}
            return BacktestResultResponse(
                job_id=job_id,
                status="completed",
                strategy_id=job["strategy_id"],
                strategy_name=job["strategy_name"],
                strategy_version=job["strategy_version"],
                time_range_start=job["time_range_start"],
                time_range_end=job["time_range_end"],
                initial_balance=job["initial_balance"],
                final_balance=result.get("metrics", {}).get(
                    "final_balance", job["initial_balance"]
                ),
                metrics=result.get("metrics", {}),
                trades=result.get("trades"),
                equity_curve=result.get("equity_curve"),
                created_at=job["created_at"],
            )
        else:
            return BacktestJobStatusResponse(
                job_id=job_id,
                status=job["status"],
                progress=job["progress"],
                strategy_id=job["strategy_id"],
                strategy_name=job["strategy_name"],
                created_at=job["created_at"],
                started_at=job["started_at"],
                completed_at=job["completed_at"],
                error=job["error"],
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id} status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}",
        )


@router.get(
    "/jobs",
    response_model=List[BacktestJobStatusResponse],
    summary="List all jobs",
    description="List all backtest jobs with their current status.",
)
async def list_backtest_jobs() -> List[BacktestJobStatusResponse]:
    """
    List all backtest jobs.

    Returns:
        List of job statuses
    """
    return [
        BacktestJobStatusResponse(
            job_id=job_id,
            status=job["status"],
            progress=job["progress"],
            strategy_id=job["strategy_id"],
            strategy_name=job["strategy_name"],
            created_at=job["created_at"],
            started_at=job["started_at"],
            completed_at=job["completed_at"],
            error=job["error"],
        )
        for job_id, job in _backtest_jobs.items()
    ]


# ============================================================================
# Saved Backtest Results (from database)
# ============================================================================


@router.get(
    "/results",
    response_model=List[Dict[str, Any]],
    summary="List saved backtest results",
    description="List all saved backtest results from the database.",
)
async def list_saved_backtests(
    strategy_id: Optional[UUID] = None,
    limit: int = 50,
    backtest_repo=Depends(get_backtest_repository),
) -> List[Dict[str, Any]]:
    """
    List saved backtest results from the database.

    Args:
        strategy_id: Optional strategy filter
        limit: Maximum number of results to return
        backtest_repo: Backtest repository instance

    Returns:
        List of backtest results

    Raises:
        500: Failed to fetch results
    """
    try:
        # Note: The repository's get method would need to be implemented
        # For now, returning empty list
        return []

    except Exception as e:
        logger.error(f"Failed to list saved backtests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch backtest results: {str(e)}",
        )
