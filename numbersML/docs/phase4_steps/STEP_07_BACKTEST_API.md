# Step 7: Backtest API & Integration

## Objective
Update the backtest API to use the real BacktestService and integrate with StrategyInstance.

## Context
- Step 6 complete: `BacktestService` with real historical data and no recalculation
- Step 5 complete: StrategyInstance API and repository exist
- Phase 3 partial: `src/infrastructure/api/routes/algorithm_backtest.py` exists but uses SIMULATED data
- Need to replace simulation with real BacktestService

## DDD Architecture Decision (ADR)

**Decision**: Backtest API updates to use real service
- **Input**: StrategyInstance ID (not just algorithm_id)
- **Service**: `BacktestService` (Application layer)
- **Persistence**: Update `algorithm_backtests` table with real results
- **Time Ranges**: Presets (4h, 12h, 1d, 3d, 7d, 30d) + custom range

**Key Requirement**: 
- Read indicators from `candle_indicators` (NO recalculation)
- Use existing pipeline Ticker data

## TDD Approach

1. **Red**: Write failing API tests expecting real backtest results
2. **Green**: Update API to use BacktestService
3. **Refactor**: Add error handling, validation, async job execution

## Implementation Files

### 1. Update `src/infrastructure/api/routes/algorithm_backtest.py`

Replace simulated backtest with real implementation:

```python
"""
Algorithm backtest API endpoints (REAL implementation).

Provides REST API for algorithm backtesting:
- Submit backtest job with StrategyInstance
- Check job status
- Retrieve backtest results

Architecture: Infrastructure Layer (API)
Dependencies: BacktestService, StrategyInstance repository
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src.application.services.backtest_service import BacktestService, BacktestResult
from src.domain.repositories.strategy_instance_repository import StrategyInstanceRepository
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.repositories.strategy_instance_repository_pg import (
    StrategyInstanceRepositoryPG,
)

router = APIRouter(prefix="/api/algorithm-backtests", tags=["algorithm-backtests"])
logger = logging.getLogger(__name__)

# In-memory job store (in production, use Redis or DB)
_backtest_jobs: Dict[str, Dict[str, Any]] = {}


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
    custom_start: Optional[datetime] = None
    custom_end: Optional[datetime] = None
    initial_balance: float = Field(default=10000.0, gt=0)
    
    @field_validator('time_range')
    def validate_time_range(cls, v):
        valid_presets = list(TIME_RANGE_PRESETS.keys())
        if v not in valid_presets and v != "custom":
            raise ValueError(f"Invalid time range. Use: {', '.join(valid_presets)} or 'custom'")
        return v


class BacktestJobResponse(BaseModel):
    """Response for job submission."""
    
    job_id: str
    status: str
    message: str
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None


# ============================================================================
# Dependencies
# ============================================================================

async def get_backtest_service() -> BacktestService:
    """Get BacktestService instance."""
    db_pool = await get_db_pool_async()
    return BacktestService(db_pool)


async def get_instance_repository() -> StrategyInstanceRepository:
    """Get StrategyInstanceRepository instance."""
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        return StrategyInstanceRepositoryPG(conn)


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
    service: BacktestService = Depends(get_backtest_service),
    instance_repo: StrategyInstanceRepository = Depends(get_instance_repository),
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
        # Validate StrategyInstance exists
        instance_id = UUID(req.strategy_instance_id)
        instance = await instance_repo.get_by_id(instance_id)
        if not instance:
            raise HTTPException(
                status_code=404,
                detail=f"StrategyInstance {instance_id} not found"
            )
        
        # Calculate time range
        now = datetime.now(tz=timezone.utc)
        if req.time_range == "custom":
            if not req.custom_start or not req.custom_end:
                raise HTTPException(
                    status_code=400,
                    detail="Custom time range requires custom_start and custom_end"
                )
            start_time = req.custom_start
            end_time = req.custom_end
        else:
            end_time = now
            start_time = end_time - TIME_RANGE_PRESETS[req.time_range]
        
        if start_time >= end_time:
            raise HTTPException(
                status_code=400,
                detail="Start time must be before end time"
            )
        
        # Generate job ID
        import uuid
        job_id = str(uuid.uuid4())[:16]
        
        # Store job
        _backtest_jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0.0,
            "strategy_instance_id": instance_id,
            "algorithm_name": "Unknown",  # TODO: Get from algorithm
            "time_range_start": start_time,
            "time_range_end": end_time,
            "initial_balance": req.initial_balance,
            "result": None,
            "error": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }
        
        # Start async execution
        asyncio.create_task(
            _execute_real_backtest(job_id, service, instance, start_time, end_time, req.initial_balance)
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
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to submit backtest job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit backtest job")


async def _execute_real_backtest(
    job_id: str,
    service: BacktestService,
    instance,
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
        job["started_at"] = datetime.now(tz=timezone.utc)
        job["progress"] = 0.1
        
        logger.info(f"Starting backtest job {job_id}")
        
        # Run real backtest
        result = await service.run_backtest(
            job_id=job_id,
            strategy_instance=instance,
            time_range_start=start_time,
            time_range_end=end_time,
            initial_balance=initial_balance,
        )
        
        # Update job with results
        job["status"] = "completed"
        job["progress"] = 1.0
        job["completed_at"] = datetime.now(tz=timezone.utc)
        job["result"] = result.to_dict()
        
        logger.info(f"Backtest job {job_id} completed. Return: {result.total_return_pct:.2f}%")
        
        # TODO: Persist to algorithm_backtests table
        
    except Exception as e:
        logger.error(f"Backtest job {job_id} failed: {e}", exc_info=True)
        if job_id in _backtest_jobs:
            _backtest_jobs[job_id]["status"] = "failed"
            _backtest_jobs[job_id]["error"] = str(e)


@router.get(
    "/jobs/{job_id}",
    response_model=Dict[str, Any],
)
async def get_job_status(job_id: str) -> Dict[str, Any]:
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
    
    # Include results if completed
    if job["status"] == "completed" and job["result"]:
        response["result"] = job["result"]
    
    return response


@router.get("/jobs", response_model=List[Dict[str, Any]])
async def list_backtest_jobs() -> List[Dict[str, Any]]:
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
```

### 2. `tests/unit/infrastructure/api/test_algorithm_backtest_api.py`

```python
"""
Tests for real backtest API endpoints.

Uses FastAPI's TestClient for endpoint testing.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from src.infrastructure.api.app import app


@pytest.fixture
def client():
    """Create TestClient for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_backtest_service():
    """Create a mock BacktestService."""
    service = AsyncMock()
    return service


@pytest.fixture
def mock_instance_repo():
    """Create a mock StrategyInstanceRepository."""
    repo = AsyncMock()
    return repo


class TestSubmitBacktestJob:
    """Tests for POST /api/algorithm-backtests/jobs"""
    
    def test_submit_with_preset(self, client, mock_backtest_service, mock_instance_repo):
        """Test submitting backtest with time preset."""
        from src.infrastructure.api.routes.algorithm_backtest import (
            get_backtest_service, get_instance_repository
        )
        from src.domain.algorithms.strategy_instance import StrategyInstance
        
        app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
        app.dependency_overrides[get_instance_repository] = lambda: mock_instance_repo
        
        # Mock instance
        instance = StrategyInstance(algorithm_id=uuid4(), config_set_id=uuid4())
        mock_instance_repo.get_by_id.return_value = instance
        
        # Mock backtest result
        from src.application.services.backtest_service import BacktestResult
        mock_result = BacktestResult(
            job_id="test",
            strategy_instance_id=instance.id,
            time_range_start=datetime.now(tz=timezone.utc),
            time_range_end=datetime.now(tz=timezone.utc),
            initial_balance=10000.0,
            final_balance=10500.0,
            total_return=500.0,
            total_return_pct=5.0,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=60.0,
            sharpe_ratio=1.5,
            max_drawdown=100.0,
            max_drawdown_pct=1.0,
            profit_factor=2.0,
            trades=[],
            equity_curve=[],
        )
        mock_backtest_service.run_backtest.return_value = mock_result
        
        response = client.post(
            "/api/algorithm-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "1d",
                "initial_balance": 10000.0,
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        assert "job_id" in data
        
        app.dependency_overrides.clear()
    
    def test_submit_invalid_preset(self, client):
        """Test submitting with invalid time preset."""
        response = client.post(
            "/api/algorithm-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "invalid",
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_submit_custom_range(self, client, mock_backtest_service, mock_instance_repo):
        """Test submitting with custom time range."""
        from src.infrastructure.api.routes.algorithm_backtest import (
            get_backtest_service, get_instance_repository
        )
        from src.domain.algorithms.strategy_instance import StrategyInstance
        
        app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
        app.dependency_overrides[get_instance_repository] = lambda: mock_instance_repo
        
        instance = StrategyInstance(algorithm_id=uuid4(), config_set_id=uuid4())
        mock_instance_repo.get_by_id.return_value = instance
        
        from datetime import datetime, timedelta
        now = datetime.now(tz=timezone.utc)
        
        response = client.post(
            "/api/algorithm-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "custom",
                "custom_start": (now - timedelta(days=1)).isoformat(),
                "custom_end": now.isoformat(),
                "initial_balance": 5000.0,
            }
        )
        
        assert response.status_code == 202
        
        app.dependency_overrides.clear()
    
    def test_submit_nonexistent_instance(self, client, mock_instance_repo):
        """Test submitting with non-existent StrategyInstance."""
        from src.infrastructure.api.routes.algorithm_backtest import get_instance_repository
        
        app.dependency_overrides[get_instance_repository] = lambda: mock_instance_repo
        mock_instance_repo.get_by_id.return_value = None
        
        response = client.post(
            "/api/algorithm-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "1d",
            }
        )
        
        assert response.status_code == 404
        
        app.dependency_overrides.clear()


class TestGetJobStatus:
    """Tests for GET /api/algorithm-backtests/jobs/{job_id}"""
    
    def test_get_existing_job(self, client):
        """Test getting an existing job."""
        from src.infrastructure.api.routes.algorithm_backtest import _backtest_jobs
        
        job_id = "test123"
        _backtest_jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
            "progress": 1.0,
            "strategy_instance_id": uuid4(),
            "created_at": datetime.now(tz=timezone.utc),
        }
        
        response = client.get(f"/api/algorithm-backtests/jobs/{job_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        
        del _backtest_jobs[job_id]
    
    def test_get_nonexistent_job(self, client):
        """Test getting non-existent job."""
        response = client.get("/api/algorithm-backtests/jobs/nonexistent")
        
        assert response.status_code == 404


class TestListBacktestJobs:
    """Tests for GET /api/algorithm-backtests/jobs"""
    
    def test_list_jobs(self, client):
        """Test listing all jobs."""
        from src.infrastructure.api.routes.algorithm_backtest import _backtest_jobs
        
        # Add some test jobs
        _backtest_jobs["job1"] = {
            "job_id": "job1",
            "status": "completed",
            "progress": 1.0,
            "strategy_instance_id": uuid4(),
            "created_at": datetime.now(tz=timezone.utc),
        }
        _backtest_jobs["job2"] = {
            "job_id": "job2",
            "status": "running",
            "progress": 0.5,
            "strategy_instance_id": uuid4(),
            "created_at": datetime.now(tz=timezone.utc),
        }
        
        response = client.get("/api/algorithm-backtests/jobs")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        # Clean up
        _backtest_jobs.clear()
```

## LLM Implementation Prompt

```text
You are implementing Step 7 of Phase 4: Backtest API & Integration.

## Your Task

Update the backtest API to use the real BacktestService (no more simulation).

## Context

- Step 6 complete: BacktestService in src/application/services/backtest_service.py
- Step 5 complete: StrategyInstance API and repository exist
- Phase 3 partial: algorithm_backtest.py exists but uses SIMULATED data
- **CRITICAL**: Must use real BacktestService, NOT simulation

## Requirements

1. Update `src/infrastructure/api/routes/algorithm_backtest.py`:
   - Replace simulated backtest with real BacktestService
   - Pydantic model: BacktestSubmitRequest with:
     * strategy_instance_id (UUID of StrategyInstance)
     * time_range (preset: 4h, 12h, 1d, 3d, 7d, 30d, or custom)
     * custom_start, custom_end (for custom range)
     * initial_balance
   - POST /api/algorithm-backtests/jobs:
     * Validate StrategyInstance exists
     * Calculate time range from preset or custom
     * Submit async job using BacktestService.run_backtest()
     * Return job_id with 202 status
   - GET /api/algorithm-backtests/jobs/{job_id}:
     * Return status or completed results
   - GET /api/algorithm-backtests/jobs: List all jobs
   - _execute_real_backtest(): Async task runner
   - TIME_RANGE_PRESETS dict for time conversion

2. Create `tests/unit/infrastructure/api/test_algorithm_backtest_api.py`:
   - TestSubmitBacktestJob: with preset, invalid preset, custom range, non-existent instance
   - TestGetJobStatus: existing job, non-existent job
   - TestListBacktestJobs: list jobs
   - Mock BacktestService and StrategyInstanceRepository
   - Use FastAPI TestClient

3. Key Implementation Details:
   - **NO recalculation**: BacktestService reads from candle_indicators
   - Time presets convert to timedelta (4h → timedelta(hours=4))
   - Async job execution with asyncio.create_task()
   - Store results in _backtest_jobs dict (use DB in production)

## Constraints

- Follow AGENTS.md coding standards
- Use type hints on all public methods (mypy strict)
- Use Google-style docstrings
- Line length max 100 characters
- Log errors with logger.error(f"message: {e}")
- Use asyncpg (not psycopg2)
- All endpoints must be async

## Acceptance Criteria

1. Backtest API uses real BacktestService (not simulation)
2. Time range presets work (4h, 12h, 1d, 3d, 7d, 30d)
3. Custom time range works with custom_start/custom_end
4. StrategyInstance validation (404 if not found)
5. Async job execution with status tracking
6. Results include PnL, trades, equity curve, metrics
7. All tests pass
8. mypy passes with no errors
9. ruff check passes with no errors
10. black formatting applied

## Commands to Run

```bash
# Format and lint
black src/infrastructure/api/routes/algorithm_backtest.py tests/unit/infrastructure/api/test_algorithm_backtest_api.py
ruff check src/infrastructure/api/routes/algorithm_backtest.py tests/unit/infrastructure/api/test_algorithm_backtest_api.py
mypy src/infrastructure/api/routes/algorithm_backtest.py

# Run tests
.venv/bin/python -m pytest tests/unit/infrastructure/api/test_algorithm_backtest_api.py -v
```

## Output

1. List of files created/modified
2. Test results (passed/failed count)
3. mypy/ruff output (no errors)
4. Any issues encountered and how resolved
```

## Success Criteria

- [ ] Backtest API uses real BacktestService
- [ ] Time range presets implemented (4h, 12h, 1d, 3d, 7d, 30d)
- [ ] Custom time range with validation
- [ ] StrategyInstance validation before starting backtest
- [ ] Async job execution with progress tracking
- [ ] Results include all metrics and trade data
- [ ] All tests pass (TestClient)
- [ ] mypy strict mode passes
- [ ] ruff check passes
- [ ] black formatting applied
