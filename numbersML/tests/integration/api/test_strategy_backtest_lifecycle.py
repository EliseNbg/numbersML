"""
Integration tests for Strategy Backtest API lifecycle.

Tests cover:
- Submit backtest job
- Check job status (pending, running, completed, failed)
- List all backtest jobs
- Time range presets and custom range
- Authorization checks
- Error handling

Uses FastAPI TestClient with dependency overrides for mocking.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

# Set environment variables BEFORE importing app
os.environ["API_KEY_ADMIN"] = "test-admin-key"
os.environ["API_KEY_TRADER"] = "test-trader-key"
os.environ["API_KEY_READ"] = "test-read-key"

# Reload modules to pick up env keys
for mod in list(sys.modules.keys()):
    if "src.infrastructure.api" in mod or "src.infrastructure.database" in mod:
        del sys.modules[mod]

from src.infrastructure.api.app import app
from src.infrastructure.api.auth import API_KEY_STORE

# Update API_KEY_STORE with test keys
API_KEY_STORE.update(
    {
        "test-admin-key": {"roles": ["admin"], "name": "Test Admin Key"},
        "test-trader-key": {"roles": ["trader", "read"], "name": "Test Trader Key"},
        "test-read-key": {"roles": ["read"], "name": "Test Read Key"},
    }
)

# Module-level mock repo and service
_mock_repo = None
_mock_service = None


@pytest.fixture(scope="module")
def setup_mocks():
    """Create mock repository and service for all tests."""
    global _mock_repo, _mock_service
    _mock_repo = MagicMock()
    _mock_service = MagicMock()
    return _mock_repo, _mock_service


@pytest.fixture(scope="module")
def client(setup_mocks):
    """Provide TestClient with dependency overrides."""

    # Define override functions
    def mock_get_repo():
        return _mock_repo

    def mock_get_service():
        return _mock_service

    # Import the real dependencies
    from src.infrastructure.api.routes.strategy_backtest import (
        get_backtest_service,
        get_instance_repository,
    )

    # Override the dependencies
    app.dependency_overrides[get_instance_repository] = mock_get_repo
    app.dependency_overrides[get_backtest_service] = mock_get_service

    with TestClient(app) as c:
        yield c

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def trader_headers():
    return {"X-API-Key": "test-trader-key"}


@pytest.fixture
def read_headers():
    return {"X-API-Key": "test-read-key"}


@pytest.fixture
def backtest_job_payload():
    return {
        "strategy_instance_id": "323e4567-e89b-12d3-a456-426614174002",
        "time_range": "1d",
        "initial_balance": 10000.0,
    }


@pytest.fixture
def custom_range_payload():
    return {
        "strategy_instance_id": "323e4567-e89b-12d3-a456-426614174002",
        "time_range": "custom",
        "custom_start": "2026-05-03T00:00:00",
        "custom_end": "2026-05-04T00:00:00",
        "initial_balance": 5000.0,
    }


# ============================================================================
# Lifecycle Tests
# ============================================================================


class TestBacktestLifecycle:
    """Test Backtest job lifecycle via API."""

    def test_submit_and_check_job_status(self, client, trader_headers, backtest_job_payload):
        """Test submitting a backtest job and checking its status."""
        # Setup mocks
        mock_instance = MagicMock()
        mock_instance.id = UUID("323e4567-e89b-12d3-a456-426614174002")
        _mock_repo.get_by_id = AsyncMock(return_value=mock_instance)

        # Mock the backtest service to avoid actual execution
        async def mock_run_backtest(**kwargs):
            return MagicMock(
                total_return_pct=10.5, to_dict=MagicMock(return_value={"total_return_pct": 10.5})
            )

        _mock_service.run_backtest = mock_run_backtest

        # Submit job
        submit_resp = client.post(
            "/api/strategy-backtests/jobs",
            json=backtest_job_payload,
            headers=trader_headers,
        )
        assert submit_resp.status_code == 202, f"Submit failed: {submit_resp.json()}"
        job_data = submit_resp.json()
        assert "job_id" in job_data
        assert job_data["status"] == "pending"
        job_id = job_data["job_id"]

        # Check job status
        status_resp = client.get(f"/api/strategy-backtests/jobs/{job_id}", headers=trader_headers)
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["job_id"] == job_id
        assert status_data["status"] in ("pending", "running", "completed", "failed")

    def test_submit_with_custom_time_range(self, client, trader_headers, custom_range_payload):
        """Test submitting a backtest with custom time range."""
        # Setup mocks
        mock_instance = MagicMock()
        _mock_repo.get_by_id = AsyncMock(return_value=mock_instance)

        # Submit job with custom range
        submit_resp = client.post(
            "/api/strategy-backtests/jobs",
            json=custom_range_payload,
            headers=trader_headers,
        )
        assert submit_resp.status_code == 202, f"Submit failed: {submit_resp.json()}"
        job_data = submit_resp.json()
        assert job_data["status"] == "pending"
        assert "time_range_start" in job_data
        assert "time_range_end" in job_data

    def test_submit_with_all_time_presets(self, client, trader_headers):
        """Test submitting backtest with all time range presets."""
        mock_instance = MagicMock()
        _mock_repo.get_by_id = AsyncMock(return_value=mock_instance)

        time_presets = ["4h", "12h", "1d", "3d", "7d", "30d"]

        for preset in time_presets:
            payload = {
                "strategy_instance_id": "323e4567-e89b-12d3-a456-426614174002",
                "time_range": preset,
                "initial_balance": 10000.0,
            }
            resp = client.post(
                "/api/strategy-backtests/jobs",
                json=payload,
                headers=trader_headers,
            )
            assert resp.status_code == 202, f"Failed for preset {preset}: {resp.json()}"

    def test_list_jobs(self, client, read_headers):
        """Test listing all backtest jobs."""
        resp = client.get("/api/strategy-backtests/jobs", headers=read_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ============================================================================
# Authorization Tests
# ============================================================================


class TestBacktestAuth:
    """Test authorization for Backtest endpoints."""

    def test_submit_requires_auth(self, client, backtest_job_payload):
        resp = client.post("/api/strategy-backtests/jobs", json=backtest_job_payload)
        assert resp.status_code == 401

    def test_read_requires_auth(self, client):
        resp = client.get("/api/strategy-backtests/jobs/some-job-id")
        assert resp.status_code == 401

    def test_read_key_can_list(self, client, read_headers):
        resp = client.get("/api/strategy-backtests/jobs", headers=read_headers)
        assert resp.status_code == 200


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestBacktestErrors:
    """Test error handling for Backtest endpoints."""

    def test_submit_invalid_time_range(self, client, trader_headers):
        """Test that invalid time range returns 422."""
        payload = {
            "strategy_instance_id": "323e4567-e89b-12d3-a456-426614174002",
            "time_range": "invalid-range",
            "initial_balance": 10000.0,
        }
        resp = client.post(
            "/api/strategy-backtests/jobs",
            json=payload,
            headers=trader_headers,
        )
        assert resp.status_code == 422

    def test_submit_custom_range_without_dates(self, client, trader_headers):
        """Test that custom range without dates returns 400."""
        payload = {
            "strategy_instance_id": "323e4567-e89b-12d3-a456-426614174002",
            "time_range": "custom",
            "initial_balance": 10000.0,
        }
        resp = client.post(
            "/api/strategy-backtests/jobs",
            json=payload,
            headers=trader_headers,
        )
        assert resp.status_code == 400
        assert "custom_start" in resp.json()["detail"].lower()

    def test_submit_nonexistent_instance(self, client, trader_headers):
        """Test that non-existent instance returns 404."""
        _mock_repo.get_by_id = AsyncMock(return_value=None)

        payload = {
            "strategy_instance_id": "123e4567-e89b-12d3-a456-426614174000",
            "time_range": "1d",
            "initial_balance": 10000.0,
        }
        resp = client.post(
            "/api/strategy-backtests/jobs",
            json=payload,
            headers=trader_headers,
        )
        assert resp.status_code == 404

    def test_get_nonexistent_job_returns_404(self, client, read_headers):
        """Test that non-existent job returns 404."""
        fake_job_id = "nonexistent-job-id"
        resp = client.get(f"/api/strategy-backtests/jobs/{fake_job_id}", headers=read_headers)
        assert resp.status_code == 404

    def test_submit_invalid_uuid_returns_400(self, client, trader_headers):
        """Test that invalid UUID returns 400."""
        payload = {
            "strategy_instance_id": "not-a-uuid",
            "time_range": "1d",
            "initial_balance": 10000.0,
        }
        resp = client.post(
            "/api/strategy-backtests/jobs",
            json=payload,
            headers=trader_headers,
        )
        assert resp.status_code == 400
