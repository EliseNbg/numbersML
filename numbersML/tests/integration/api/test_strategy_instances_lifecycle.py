"""
Integration tests for StrategyInstance API lifecycle.

Tests cover:
- Create StrategyInstance (link Algorithm + ConfigurationSet)
- Read StrategyInstance
- List StrategyInstances with filters
- Start/Stop/Pause/Resume (hot-plug controls)
- Delete StrategyInstance
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
os.environ["API_KEY_ADMIN"] = "admin-secret-key"
os.environ["API_KEY_TRADER"] = "trader-secret-key"
os.environ["API_KEY_READ"] = "read-secret-key"

# Reload modules to pick up env keys
for mod in list(sys.modules.keys()):
    if "src.infrastructure.api" in mod or "src.infrastructure.database" in mod:
        del sys.modules[mod]

from src.infrastructure.api.auth import API_KEY_STORE
from src.infrastructure.api.app import app

# Update API_KEY_STORE with test keys
API_KEY_STORE.update(
    {
        "admin-secret-key": {"roles": ["admin"], "name": "Admin Key"},
        "trader-secret-key": {"roles": ["trader", "read"], "name": "Trader Key"},
        "read-secret-key": {"roles": ["read"], "name": "Read Key"},
    }
)

# Module-level mock repo
mock_repo = None


@pytest.fixture(scope="module")
def client():
    """Provide TestClient with dependency overrides."""
    global mock_repo
    mock_repo = MagicMock()

    # Define override as async generator to match original
    async def mock_get_repo():
        yield mock_repo

    # Import the real dependency
    from src.infrastructure.api.routes.strategy_instances import (
        get_instance_repository,
    )

    # Override the dependency
    app.dependency_overrides[get_instance_repository] = mock_get_repo

    with TestClient(app) as c:
        yield c

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    return {"X-API-Key": "admin-secret-key"}


@pytest.fixture
def trader_headers():
    return {"X-API-Key": "trader-secret-key"}


@pytest.fixture
def read_headers():
    return {"X-API-Key": "read-secret-key"}


@pytest.fixture
def strategy_instance_payload():
    return {
        "algorithm_id": "123e4567-e89b-12d3-a456-426614174000",
        "config_set_id": "223e4567-e89b-12d3-a456-426614174001",
    }


# ============================================================================
# Lifecycle Tests
# ============================================================================


class TestStrategyInstanceLifecycle:
    """Test StrategyInstance full lifecycle via API."""

    def test_create_and_list_instances(
        self, client, trader_headers, strategy_instance_payload
    ):
        """Test creating a StrategyInstance and listing it."""
        # Mock get_by_algorithm_and_config to return None (no duplicate)
        mock_repo.get_by_algorithm_and_config = AsyncMock(return_value=None)

        # Mock saved instance
        mock_instance = MagicMock()
        mock_instance.id = UUID("323e4567-e89b-12d3-a456-426614174002")
        mock_instance.algorithm_id = UUID(strategy_instance_payload["algorithm_id"])
        mock_instance.config_set_id = UUID(strategy_instance_payload["config_set_id"])
        mock_instance.status.value = "stopped"
        mock_instance.runtime_stats.to_dict.return_value = {}
        mock_instance.started_at = None
        mock_instance.stopped_at = None
        mock_instance.created_at.isoformat.return_value = "2026-05-04T20:00:00"
        mock_instance.updated_at.isoformat.return_value = "2026-05-04T20:00:00"

        mock_repo.save = AsyncMock(return_value=mock_instance)

        # Create
        create_resp = client.post(
            "/api/algorithm-instances",
            json=strategy_instance_payload,
            headers=trader_headers,
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.json()}"
        created = create_resp.json()
        assert created["status"] == "stopped"

        # List
        mock_repo.list_all = AsyncMock(return_value=[mock_instance])
        list_resp = client.get("/api/algorithm-instances", headers=read_headers)
        assert list_resp.status_code == 200
        assert isinstance(list_resp.json(), list)

    def test_get_instance_by_id(
        self, client, read_headers, strategy_instance_payload
    ):
        """Test getting a StrategyInstance by ID."""
        mock_instance = MagicMock()
        mock_instance.id = UUID("323e4567-e89b-12d3-a456-426614174002")
        mock_instance.status.value = "stopped"
        mock_instance.runtime_stats.to_dict.return_value = {}
        mock_instance.started_at = None
        mock_instance.stopped_at = None
        mock_instance.created_at.isoformat.return_value = "2026-05-04T20:00:00"
        mock_instance.updated_at.isoformat.return_value = "2026-05-04T20:00:00"

        mock_repo.get_by_id = AsyncMock(return_value=mock_instance)

        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        get_resp = client.get(
            f"/api/algorithm-instances/{instance_id}", headers=read_headers
        )
        assert get_resp.status_code == 200, f"Get failed: {get_resp.json()}"

    def test_get_nonexistent_instance_returns_404(self, client, read_headers):
        """Test that getting a non-existent instance returns 404."""
        mock_repo.get_by_id = AsyncMock(return_value=None)

        fake_id = "123e4567-e89b-12d3-a456-426614174000"
        resp = client.get(
            f"/api/algorithm-instances/{fake_id}", headers=read_headers
        )
        assert resp.status_code == 404

    def test_start_instance(self, client, trader_headers):
        """Test starting a StrategyInstance (hot-plug)."""
        mock_instance = MagicMock()
        mock_instance.id = UUID("323e4567-e89b-12d3-a456-426614174002")
        mock_instance.status.value = "stopped"
        mock_instance.start = MagicMock()

        mock_repo.get_by_id = AsyncMock(return_value=mock_instance)
        mock_repo.save = AsyncMock()

        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        start_resp = client.post(
            f"/api/algorithm-instances/{instance_id}/start", headers=trader_headers
        )
        assert start_resp.status_code == 200
        assert "started" in start_resp.json()["message"].lower()
        mock_instance.start.assert_called_once()

    def test_stop_instance(self, client, trader_headers):
        """Test stopping a running StrategyInstance (unplug)."""
        mock_instance = MagicMock()
        mock_instance.status.value = "running"
        mock_instance.stop = MagicMock()

        mock_repo.get_by_id = AsyncMock(return_value=mock_instance)
        mock_repo.save = AsyncMock()

        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        stop_resp = client.post(
            f"/api/algorithm-instances/{instance_id}/stop", headers=trader_headers
        )
        assert stop_resp.status_code == 200
        assert "stopped" in stop_resp.json()["message"].lower()
        mock_instance.stop.assert_called_once()

    def test_pause_instance(self, client, trader_headers):
        """Test pausing a running StrategyInstance."""
        mock_instance = MagicMock()
        mock_instance.status.value = "running"
        mock_instance.pause = MagicMock()

        mock_repo.get_by_id = AsyncMock(return_value=mock_instance)
        mock_repo.save = AsyncMock()

        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        pause_resp = client.post(
            f"/api/algorithm-instances/{instance_id}/pause", headers=trader_headers
        )
        assert pause_resp.status_code == 200
        assert "paused" in pause_resp.json()["message"].lower()
        mock_instance.pause.assert_called_once()

    def test_resume_instance(self, client, trader_headers):
        """Test resuming a paused StrategyInstance."""
        mock_instance = MagicMock()
        mock_instance.status.value = "paused"
        mock_instance.resume = MagicMock()

        mock_repo.get_by_id = AsyncMock(return_value=mock_instance)
        mock_repo.save = AsyncMock()

        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        resume_resp = client.post(
            f"/api/algorithm-instances/{instance_id}/resume", headers=trader_headers
        )
        assert resume_resp.status_code == 200
        assert "resumed" in resume_resp.json()["message"].lower()
        mock_instance.resume.assert_called_once()

    def test_delete_instance(self, client, trader_headers):
        """Test deleting a StrategyInstance."""
        mock_repo.delete = AsyncMock(return_value=True)

        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        delete_resp = client.delete(
            f"/api/algorithm-instances/{instance_id}", headers=trader_headers
        )
        assert delete_resp.status_code == 204


# ============================================================================
# Authorization Tests
# ============================================================================


class TestStrategyInstanceAuth:
    """Test authorization for StrategyInstance endpoints."""

    def test_create_requires_auth(self, client, strategy_instance_payload):
        resp = client.post(
            "/api/algorithm-instances", json=strategy_instance_payload
        )
        assert resp.status_code == 401

    def test_read_requires_auth(self, client):
        resp = client.get("/api/algorithm-instances/some-uid")
        assert resp.status_code == 401

    def test_read_key_can_list(self, client, read_headers):
        mock_repo.list_all = AsyncMock(return_value=[])

        resp = client.get("/api/algorithm-instances", headers=read_headers)
        assert resp.status_code == 200

    def test_start_requires_trader_role(self, client, read_headers):
        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        resp = client.post(
            f"/api/algorithm-instances/{instance_id}/start", headers=read_headers
        )
        assert resp.status_code == 403


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestStrategyInstanceErrors:
    """Test error handling for StrategyInstance endpoints."""

    def test_create_invalid_uuid_returns_400(self, client, trader_headers):
        invalid_payload = {
            "algorithm_id": "not-a-uuid",
            "config_set_id": "223e4567-e89b-12d3-a456-426614174001",
        }
        resp = client.post(
            "/api/algorithm-instances", json=invalid_payload, headers=trader_headers
        )
        assert resp.status_code == 400

    def test_start_nonexistent_instance_returns_404(self, client, trader_headers):
        mock_repo.get_by_id = AsyncMock(return_value=None)

        instance_id = "123e4567-e89b-12d3-a456-426614174000"
        resp = client.post(
            f"/api/algorithm-instances/{instance_id}/start", headers=trader_headers
        )
        assert resp.status_code == 404

    def test_start_stopped_instance_returns_400(self, client, trader_headers):
        """Test that starting an already running instance returns 400."""
        mock_instance = MagicMock()
        mock_instance.status.value = "running"  # Already running
        mock_instance.start = MagicMock(
            side_effect=ValueError("Instance is already running")
        )

        mock_repo.get_by_id = AsyncMock(return_value=mock_instance)

        instance_id = "323e4567-e89b-12d3-a456-426614174002"
        resp = client.post(
            f"/api/algorithm-instances/{instance_id}/start", headers=trader_headers
        )
        assert resp.status_code == 400
