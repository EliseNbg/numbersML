"""
Strategy backtest API endpoints.

Provides REST API for strategy backtesting:
- Start backtest jobs (async)
- Check job status
- Retrieve backtest results

Architecture: Infrastructure Layer (API)
Dependencies: Application services, Domain models
"""

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src.application.services.backtest_engine import (
    BacktestEngine,
    serialize_debug_message,
    serialize_equity_point,
    serialize_metrics,
    serialize_price_point,
    serialize_trade_record,
)
from src.application.services.strategy_backtest_service import StrategyBacktestService
from src.domain.repositories.strategy_repository import StrategyRepository
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.strategy_backtest_repository_pg import (
    StrategyBacktestRepositoryPG,
)
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG

router = APIRouter(prefix="/api/strategy-backtests", tags=["strategy-backtests"])

logger = logging.getLogger(__name__)

# In-memory job store (in production, use Redis or DB)
_backtest_jobs: dict[str, dict[str, Any]] = {}


# ============================================================================
# Pydantic Models
# ============================================================================


class StrategyBacktestRequest(BaseModel):
    """Request model for strategy backtest."""

    strategy_id: UUID
    strategy_version: int | None = Field(
        None, ge=1, description="Specific version (defaults to active)"
    )
    time_range_start: datetime = Field(..., description="Start time for backtest")
    time_range_end: datetime = Field(..., description="End time for backtest")
    initial_balance: float = Field(default=10000.0, gt=0, description="Initial capital")
    symbol: str | None = Field(None, description="Optional symbol filter")
    include_equity_curve: bool = Field(default=True, description="Include equity curve in results")
    include_trades: bool = Field(default=True, description="Include individual trades")
    validate_with_binance: bool = Field(
        default=False, description="Validate orders against Binance testnet"
    )
    metadata: dict[str, Any] | None = None

    @field_validator("time_range_end")
    def validate_time_range(cls, v, info):  # noqa: N805
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
    strategy_id: UUID | None = None
    strategy_name: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


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
    metrics: dict[str, Any]
    config_snapshot: dict[str, Any]
    parameters: dict[str, Any]
    trades: list[dict[str, Any]] | None = None
    equity_curve: list[dict[str, Any]] | None = None
    price_series: list[dict[str, Any]] | None = None
    debug_messages: list[dict[str, Any]] | None = None
    created_at: datetime


# ============================================================================
# Dependency injections
# ============================================================================


async def get_strategy_repository() -> StrategyRepository:
    """Get StrategyRepository instance."""
    db_pool = await get_db_pool_async()
    return StrategyRepositoryPG(db_pool)


async def get_backtest_repository() -> StrategyBacktestRepositoryPG:
    """Get StrategyBacktestRepository instance."""
    db_pool = await get_db_pool_async()
    return StrategyBacktestRepositoryPG(db_pool)


async def get_backtest_service(
    repository: StrategyRepository = Depends(get_strategy_repository),
    backtest_repository: StrategyBacktestRepositoryPG = Depends(get_backtest_repository),
) -> StrategyBacktestService:
    """Build the application service used by the async job executor."""
    db_pool = await get_db_pool_async()
    engine = BacktestEngine(db_pool)
    return StrategyBacktestService(
        strategy_repository=repository,
        backtest_repository=backtest_repository,
        backtest_engine=engine,
        actor="api",
    )


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
    service: StrategyBacktestService = Depends(get_backtest_service),
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
            "validate_with_binance": request.validate_with_binance,
            "metadata": request.metadata or {},
            "created_at": datetime.now(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

        # Start async execution (non-blocking)
        asyncio.create_task(_execute_backtest_job(job_id, service))

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
        ) from e


async def _execute_backtest_job(
    job_id: str,
    service: StrategyBacktestService,
) -> None:
    """
    Execute a backtest job asynchronously.

    Args:
        job_id: Job identifier
    """
    try:
        job = _backtest_jobs[job_id]
        job["status"] = "running"
        job["started_at"] = datetime.now()
        job["progress"] = 0.1

        logger.info(f"Starting backtest job {job_id}")

        if job.get("validate_with_binance"):
            import os

            from src.infrastructure.market.binance_exchange_client import (
                BINANCE_TESTNET,
                BinanceExchangeClient,
            )

            api_key = os.getenv("BINANCE_TESTNET_API_KEY")
            api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
            if api_key and api_secret:
                binance_client = BinanceExchangeClient(
                    api_key=api_key,
                    api_secret=api_secret,
                    environment=BINANCE_TESTNET,
                )
                logger.info("Binance testnet validation enabled for backtest job")
            else:
                logger.warning(
                    "BINANCE_TESTNET_API_KEY/SECRET not set, skipping Binance validation"
                )
                binance_client = None
        else:
            binance_client = None

        db_pool = await get_db_pool_async()
        engine = BacktestEngine(db_pool=db_pool, binance_test_client=binance_client)
        backtest_repo = StrategyBacktestRepositoryPG(db_pool)
        strategy_repo = StrategyRepositoryPG(db_pool)
        job_service = StrategyBacktestService(
            strategy_repository=strategy_repo,
            backtest_repository=backtest_repo,
            backtest_engine=engine,
            actor="api",
        )

        result = await job_service.run_backtest(
            strategy_id=job["strategy_id"],
            strategy_version=job["strategy_version"],
            start_time=job["time_range_start"],
            end_time=job["time_range_end"],
            initial_balance=job["initial_balance"],
            symbol=job["symbol"],
            progress_callback=lambda progress: job.__setitem__("progress", progress),
        )

        # Store results
        job["status"] = "completed"
        job["progress"] = 1.0
        job["completed_at"] = datetime.now()
        job["result"] = {
            "final_balance": result.final_balance,
            "metrics": serialize_metrics(result.metrics),
            "config_snapshot": result.config_snapshot,
            "parameters": result.parameters,
            "trades": (
                [serialize_trade_record(trade) for trade in result.trades]
                if job["include_trades"]
                else None
            ),
            "equity_curve": (
                [serialize_equity_point(point) for point in result.equity_curve]
                if job["include_equity_curve"]
                else None
            ),
            "price_series": [serialize_price_point(point) for point in result.price_series],
            "debug_messages": [
                serialize_debug_message(message) for message in result.debug_messages
            ],
        }

        logger.info(
            "Backtest job %s completed. Return: %.2f%%",
            job_id,
            job["result"]["metrics"]["total_return_pct"],
        )

    except Exception as e:
        logger.error(f"Backtest job {job_id} failed: {e}", exc_info=True)
        if job_id in _backtest_jobs:
            _backtest_jobs[job_id]["status"] = "failed"
            _backtest_jobs[job_id]["error"] = str(e)


@router.get(
    "/jobs/{job_id}",
    response_model=BacktestJobStatusResponse | BacktestResultResponse,
    summary="Get job status or results",
    description="Get backtest job status. Returns results if completed.",
)
async def get_job_status(
    job_id: str,
) -> BacktestJobStatusResponse | BacktestResultResponse:
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
                final_balance=result.get("final_balance", job["initial_balance"]),
                metrics=result.get("metrics", {}),
                config_snapshot=result.get("config_snapshot", {}),
                parameters=result.get("parameters", {}),
                trades=result.get("trades"),
                equity_curve=result.get("equity_curve"),
                price_series=result.get("price_series"),
                debug_messages=result.get("debug_messages"),
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
        ) from e


@router.get(
    "/jobs",
    response_model=list[BacktestJobStatusResponse],
    summary="List all jobs",
    description="List all backtest jobs with their current status.",
)
async def list_backtest_jobs() -> list[BacktestJobStatusResponse]:
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
    response_model=list[dict[str, Any]],
    summary="List saved backtest results",
    description="List all saved backtest results from the database.",
)
async def list_saved_backtests(
    strategy_id: UUID | None = None,
    limit: int = 50,
    backtest_repo: StrategyBacktestRepositoryPG = Depends(get_backtest_repository),
) -> list[dict[str, Any]]:
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
        if strategy_id is not None:
            return await backtest_repo.list_for_strategy(strategy_id, limit=limit)
        return await backtest_repo.list_recent(limit=limit)

    except Exception as e:
        logger.error(f"Failed to list saved backtests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch backtest results: {str(e)}",
        ) from e


@router.delete(
    "/results/{backtest_id}",
    summary="Delete a backtest result",
    description="Delete a specific saved backtest result by ID.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_saved_backtest(
    backtest_id: UUID,
    backtest_repo: StrategyBacktestRepositoryPG = Depends(get_backtest_repository),
) -> None:
    """
    Delete a specific saved backtest result by ID.

    Args:
        backtest_id: The UUID of the backtest result to delete
        backtest_repo: Backtest repository instance

    Raises:
        404: Backtest not found
        500: Failed to delete
    """
    try:
        deleted = await backtest_repo.delete(backtest_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backtest {backtest_id} not found",
            )
        logger.info(f"Deleted backtest {backtest_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backtest {backtest_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backtest result: {str(e)}",
        ) from e


@router.post(
    "/results/bulk-delete",
    summary="Bulk delete backtest results",
    description="Delete multiple backtest results by IDs.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def bulk_delete_backtests(
    request: dict[str, list[UUID]],
    backtest_repo: StrategyBacktestRepositoryPG = Depends(get_backtest_repository),
) -> None:
    """
    Delete multiple backtest results by IDs.

    Args:
        request: Dict with 'backtest_ids' key containing list of UUIDs
        backtest_repo: Backtest repository instance

    Raises:
        400: Invalid request
        500: Failed to delete
    """
    try:
        backtest_ids = request.get("backtest_ids", [])
        if not isinstance(backtest_ids, list) or not backtest_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="backtest_ids must be a non-empty list",
            )

        deleted_count = await backtest_repo.delete_multiple(backtest_ids)
        logger.info(f"Bulk deleted {deleted_count} backtests")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk delete backtests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backtest results: {str(e)}",
        ) from e


@router.get(
    "/results/{backtest_id}",
    response_model=dict[str, Any],
    summary="Get single backtest result",
    description="Get detailed results for a specific saved backtest by ID.",
)
async def get_saved_backtest(
    backtest_id: UUID,
    backtest_repo: StrategyBacktestRepositoryPG = Depends(get_backtest_repository),
) -> dict[str, Any]:
    """
    Get a specific saved backtest result by ID.

    Args:
        backtest_id: The UUID of the backtest result
        backtest_repo: Backtest repository instance

    Returns:
        Complete backtest result with all trade data and price series

    Raises:
        404: Backtest not found
        500: Failed to fetch result
    """
    try:
        result = await backtest_repo.get_with_price_series(backtest_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backtest {backtest_id} not found",
            )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backtest {backtest_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch backtest result: {str(e)}",
        ) from e
