"""
Unit tests for StrategyInstance API endpoints.

Uses FastAPI's TestClient with mocked repository.
"""

from uuid import uuid4

import pytest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from src.domain.strategies.strategy_instance import StrategyInstance
from src.infrastructure.api.routes.strategy_instances import get_instance_repository, router


@pytest.fixture
def app():
    """Create FastAPI app with test router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_repo():
    """Mock StrategyInstanceRepository."""
    return AsyncMock()


@pytest.fixture
def client(app, mock_repo):
    """Create test client with dependency override."""
    app.dependency_overrides[get_instance_repository] = lambda: mock_repo
    return TestClient(app)


def test_list_instances(client, mock_repo):
    """Test listing instances."""
    sample_instance = StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )
    mock_repo.list_all.return_value = [sample_instance]

    response = client.get("/api/strategy-instances")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_instance(client, mock_repo):
    """Test creating a new instance."""
    strategy_id = uuid4()
    config_set_id = uuid4()
    mock_repo.get_by_strategy_and_config.return_value = None
    mock_repo.save.return_value = StrategyInstance(
        strategy_id=strategy_id,
        config_set_id=config_set_id,
    )

    response = client.post(
        "/api/strategy-instances",
        json={"strategy_id": str(strategy_id), "config_set_id": str(config_set_id)},
    )

    assert response.status_code == 201
    assert response.json()["strategy_id"] == str(strategy_id)


def test_create_duplicate_instance(client, mock_repo):
    """Test creating duplicate instance returns 400."""
    existing = StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )
    mock_repo.get_by_strategy_and_config.return_value = existing

    response = client.post(
        "/api/strategy-instances",
        json={"strategy_id": str(existing.strategy_id), "config_set_id": str(existing.config_set_id)},
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_get_instance(client, mock_repo):
    """Test getting instance by ID."""
    instance = StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )
    mock_repo.get_by_id.return_value = instance

    response = client.get(f"/api/strategy-instances/{instance.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(instance.id)


def test_get_nonexistent_instance(client, mock_repo):
    """Test getting non-existent instance returns 404."""
    mock_repo.get_by_id.return_value = None

    response = client.get(f"/api/strategy-instances/{uuid4()}")

    assert response.status_code == 404


def test_start_instance(client, mock_repo):
    """Test starting an instance."""
    instance = StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )
    mock_repo.get_by_id.return_value = instance
    mock_repo.save.return_value = instance

    response = client.post(f"/api/strategy-instances/{instance.id}/start")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_start_nonexistent_instance(client, mock_repo):
    """Test starting non-existent instance returns 404."""
    mock_repo.get_by_id.return_value = None

    response = client.post(f"/api/strategy-instances/{uuid4()}/start")

    assert response.status_code == 404


def test_stop_instance(client, mock_repo):
    """Test stopping an instance."""
    instance = StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )
    instance.start()
    mock_repo.get_by_id.return_value = instance
    mock_repo.save.return_value = instance

    response = client.post(f"/api/strategy-instances/{instance.id}/stop")

    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


def test_pause_instance(client, mock_repo):
    """Test pausing a running instance."""
    instance = StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )
    instance.start()
    mock_repo.get_by_id.return_value = instance
    mock_repo.save.return_value = instance

    response = client.post(f"/api/strategy-instances/{instance.id}/pause")

    assert response.status_code == 200
    assert response.json()["status"] == "paused"


def test_resume_instance(client, mock_repo):
    """Test resuming a paused instance."""
    instance = StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )
    instance.start()
    instance.pause()
    mock_repo.get_by_id.return_value = instance
    mock_repo.save.return_value = instance

    response = client.post(f"/api/strategy-instances/{instance.id}/resume")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_delete_instance(client, mock_repo):
    """Test deleting an instance."""
    mock_repo.delete.return_value = True

    response = client.delete(f"/api/strategy-instances/{uuid4()}")

    assert response.status_code == 204


def test_delete_nonexistent_instance(client, mock_repo):
    """Test deleting non-existent instance returns 404."""
    mock_repo.delete.return_value = False

    response = client.delete(f"/api/strategy-instances/{uuid4()}")

    assert response.status_code == 404
