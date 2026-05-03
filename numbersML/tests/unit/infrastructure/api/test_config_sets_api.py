"""
Tests for ConfigurationSet API endpoints.

Uses FastAPI's TestClient for endpoint testing.
Follows TDD: tests first, then implementation.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.api.app import app


@pytest.fixture
def client():
    """Create TestClient for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_repository():
    """Create a mock ConfigSetRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def sample_config_set_data():
    """Sample data for creating ConfigurationSet."""
    return {
        "name": "Test Config",
        "description": "Test description",
        "config": {"symbols": ["BTC/USDT"], "risk": {"max_position_size_pct": 10}},
        "created_by": "test",
    }


class TestListConfigSets:
    """Tests for GET /api/config-sets"""

    def test_list_empty(self, client, mock_repository):
        """Test listing when no config sets exist."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        mock_repository.list_all.return_value = []

        response = client.get("/api/config-sets")

        assert response.status_code == 200
        assert response.json() == []

        app.dependency_overrides.clear()

    def test_list_with_data(self, client, mock_repository):
        """Test listing config sets."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        cs = ConfigurationSet(
            name="Test",
            config={"key": "value"},
        )

        mock_repository.list_all.return_value = [cs]

        response = client.get("/api/config-sets")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test"

        app.dependency_overrides.clear()

    def test_list_active_only(self, client, mock_repository):
        """Test listing with active_only filter."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        mock_repository.list_all.return_value = []

        response = client.get("/api/config-sets?active_only=true")

        assert response.status_code == 200
        call_args = mock_repository.list_all.call_args
        assert call_args[1]["active_only"] is True

        app.dependency_overrides.clear()


class TestCreateConfigSet:
    """Tests for POST /api/config-sets"""

    def test_create_success(self, client, mock_repository, sample_config_set_data):
        """Test creating a ConfigurationSet successfully."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        mock_repository.get_by_name.return_value = None

        cs = ConfigurationSet(**sample_config_set_data)
        mock_repository.save.return_value = cs

        response = client.post("/api/config-sets", json=sample_config_set_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_config_set_data["name"]
        assert data["config"] == sample_config_set_data["config"]

        app.dependency_overrides.clear()

    def test_create_duplicate_name(self, client, mock_repository, sample_config_set_data):
        """Test creating with duplicate name returns 400."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        existing = ConfigurationSet(**sample_config_set_data)
        mock_repository.get_by_name.return_value = existing

        response = client.post("/api/config-sets", json=sample_config_set_data)

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

        app.dependency_overrides.clear()

    def test_create_invalid_data(self, client, mock_repository):
        """Test creating with invalid data returns 422."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        invalid_data = {"name": "Test"}

        response = client.post("/api/config-sets", json=invalid_data)

        assert response.status_code == 422

        app.dependency_overrides.clear()


class TestGetConfigSet:
    """Tests for GET /api/config-sets/{id}"""

    def test_get_existing(self, client, mock_repository):
        """Test getting an existing ConfigurationSet."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        cs = ConfigurationSet(name="Test", config={"key": "value"})
        mock_repository.get_by_id.return_value = cs

        response = client.get(f"/api/config-sets/{cs.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test"
        assert data["id"] == str(cs.id)

        app.dependency_overrides.clear()

    def test_get_nonexistent(self, client, mock_repository):
        """Test getting non-existent ConfigurationSet returns 404."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        mock_repository.get_by_id.return_value = None

        response = client.get(f"/api/config-sets/{uuid4()}")

        assert response.status_code == 404

        app.dependency_overrides.clear()


class TestUpdateConfigSet:
    """Tests for PUT /api/config-sets/{id}"""

    def test_update_config(self, client, mock_repository):
        """Test updating ConfigurationSet config."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        cs = ConfigurationSet(name="Test", config={"old": "value"})
        mock_repository.get_by_id.return_value = cs
        mock_repository.save.return_value = cs

        response = client.put(
            f"/api/config-sets/{cs.id}",
            json={"config": {"new": "value"}},
        )

        assert response.status_code == 200

        app.dependency_overrides.clear()

    def test_update_nonexistent(self, client, mock_repository):
        """Test updating non-existent returns 404."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        mock_repository.get_by_id.return_value = None

        response = client.put(
            f"/api/config-sets/{uuid4()}",
            json={"config": {"new": "value"}},
        )

        assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_update_no_fields(self, client, mock_repository):
        """Test updating with no fields returns 400."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        cs = ConfigurationSet(name="Test", config={"key": "value"})
        mock_repository.get_by_id.return_value = cs

        response = client.put(
            f"/api/config-sets/{cs.id}",
            json={},
        )

        assert response.status_code == 400

        app.dependency_overrides.clear()


class TestDeleteConfigSet:
    """Tests for DELETE /api/config-sets/{id}"""

    def test_delete_existing(self, client, mock_repository):
        """Test deleting an existing ConfigurationSet."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        mock_repository.delete.return_value = True

        response = client.delete(f"/api/config-sets/{uuid4()}")

        assert response.status_code == 204

        app.dependency_overrides.clear()

    def test_delete_nonexistent(self, client, mock_repository):
        """Test deleting non-existent returns 404."""
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        mock_repository.delete.return_value = False

        response = client.delete(f"/api/config-sets/{uuid4()}")

        assert response.status_code == 404

        app.dependency_overrides.clear()


class TestActivateDeactivateConfigSet:
    """Tests for activate/deactivate endpoints."""

    def test_activate(self, client, mock_repository):
        """Test activating a ConfigurationSet."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        cs = ConfigurationSet(name="Test", config={"key": "value"})
        mock_repository.get_by_id.return_value = cs
        mock_repository.save.return_value = cs

        response = client.post(f"/api/config-sets/{cs.id}/activate")

        assert response.status_code == 200
        assert "activated" in response.json()["message"]

        app.dependency_overrides.clear()

    def test_deactivate(self, client, mock_repository):
        """Test deactivating a ConfigurationSet."""
        from src.domain.strategies.config_set import ConfigurationSet
        from src.infrastructure.api.routes.config_sets import get_config_set_repository

        app.dependency_overrides[get_config_set_repository] = lambda: mock_repository

        cs = ConfigurationSet(name="Test", config={"key": "value"})
        mock_repository.get_by_id.return_value = cs
        mock_repository.save.return_value = cs

        response = client.post(f"/api/config-sets/{cs.id}/deactivate")

        assert response.status_code == 200
        assert "deactivated" in response.json()["message"]

        app.dependency_overrides.clear()
