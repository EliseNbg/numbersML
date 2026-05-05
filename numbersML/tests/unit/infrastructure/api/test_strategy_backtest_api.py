"""
Tests for real backtest API endpoints.

Uses FastAPI's TestClient for endpoint testing.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.api.app import app
from src.infrastructure.api.routes.strategy_backtest import (
    _backtest_jobs,
    get_backtest_service,
    get_instance_repository,
)


@pytest.fixture(autouse=True)
def setup_dependency_overrides(mock_backtest_service, mock_instance_repo):
    """Set up dependency overrides for all tests."""
    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    app.dependency_overrides[get_instance_repository] = lambda: mock_instance_repo
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_backtest_jobs():
    """Clear backtest jobs before each test."""
    _backtest_jobs.clear()
    yield
    _backtest_jobs.clear()


@pytest.fixture
def client():
    """Create TestClient for FastAPI app."""
    return TestClient(app, headers={"X-API-Key": "test-secret-key"})


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
    """Tests for POST /api/strategy-backtests/jobs"""

    def test_submit_with_preset(self, client, mock_backtest_service, mock_instance_repo):
        """Test submitting backtest with time preset."""
        from src.domain.strategies.strategy_instance import StrategyInstance

        instance = StrategyInstance(strategy_id=uuid4(), config_set_id=uuid4())
        mock_instance_repo.get_by_id.return_value = instance

        from src.application.services.backtest_service import BacktestResult

        mock_result = BacktestResult(
            job_id="test",
            strategy_instance_id=instance.id,
            time_range_start=datetime.now(tz=UTC),
            time_range_end=datetime.now(tz=UTC),
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
            "/api/strategy-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "1d",
                "initial_balance": 10000.0,
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending"
        assert "job_id" in data

    def test_submit_invalid_preset(self, client):
        """Test submitting with invalid time preset."""
        response = client.post(
            "/api/strategy-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "invalid",
            },
        )

        assert response.status_code == 422

    def test_submit_custom_range(self, client, mock_backtest_service, mock_instance_repo):
        """Test submitting with custom time range."""
        from src.domain.strategies.strategy_instance import StrategyInstance

        instance = StrategyInstance(strategy_id=uuid4(), config_set_id=uuid4())
        mock_instance_repo.get_by_id.return_value = instance

        now = datetime.now(tz=UTC)

        response = client.post(
            "/api/strategy-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "custom",
                "custom_start": (now - timedelta(days=1)).isoformat(),
                "custom_end": now.isoformat(),
                "initial_balance": 5000.0,
            },
        )

        assert response.status_code == 202

    def test_submit_nonexistent_instance(self, client, mock_instance_repo):
        """Test submitting with non-existent StrategyInstance."""
        mock_instance_repo.get_by_id.return_value = None

        response = client.post(
            "/api/strategy-backtests/jobs",
            json={
                "strategy_instance_id": str(uuid4()),
                "time_range": "1d",
            },
        )

        assert response.status_code == 404


class TestGetJobStatus:
    """Tests for GET /api/strategy-backtests/jobs/{job_id}"""

    def test_get_existing_job(self, client):
        """Test getting an existing job."""
        job_id = "test123"
        _backtest_jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
            "progress": 1.0,
            "strategy_instance_id": uuid4(),
            "created_at": datetime.now(tz=UTC),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

        response = client.get(f"/api/strategy-backtests/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    def test_get_nonexistent_job(self, client):
        """Test getting non-existent job."""
        response = client.get("/api/strategy-backtests/jobs/nonexistent")

        assert response.status_code == 404


class TestListBacktestJobs:
    """Tests for GET /api/strategy-backtests/jobs"""

    def test_list_jobs(self, client):
        """Test listing all jobs."""
        _backtest_jobs["job1"] = {
            "job_id": "job1",
            "status": "completed",
            "progress": 1.0,
            "strategy_instance_id": uuid4(),
            "created_at": datetime.now(tz=UTC),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }
        _backtest_jobs["job2"] = {
            "job_id": "job2",
            "status": "running",
            "progress": 0.5,
            "strategy_instance_id": uuid4(),
            "created_at": datetime.now(tz=UTC),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

        response = client.get("/api/strategy-backtests/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
