"""
Tests for Algorithm (Algorithm) API endpoints.

Uses FastAPI's TestClient for endpoint testing.
Covers: CRUD, versions, lifecycle, runtime state, events, LLM generation.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.api.routes.algorithms import router


@pytest.fixture
def app():
    """Create FastAPI app with algorithms router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_repo():
    """Mock AlgorithmRepository."""
    return AsyncMock()


@pytest.fixture
def mock_event_repo():
    """Mock AlgorithmRuntimeEventRepository."""
    return AsyncMock()


@pytest.fixture
def mock_lifecycle_svc():
    """Mock AlgorithmLifecycleService."""
    svc = MagicMock()
    svc.get_runtime_state = AsyncMock(return_value=None)
    svc.get_all_runtime_states = AsyncMock(return_value=[])
    svc.get_lifecycle_events = AsyncMock(return_value=[])
    svc.activate_algorithm = AsyncMock(return_value=True)
    svc.deactivate_algorithm = AsyncMock(return_value=True)
    svc.pause_algorithm = AsyncMock(return_value=True)
    svc.resume_algorithm = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def mock_llm_svc():
    """Mock LLMAlgorithmService."""
    svc = AsyncMock()
    return svc


@pytest.fixture
def mock_auth():
    """Mock AuthContext for require_trader."""
    from src.infrastructure.api.auth import AuthContext

    return AuthContext(api_key="test_key", roles=["trader"], name="test")


@pytest.fixture
def client(app, mock_repo, mock_event_repo, mock_lifecycle_svc, mock_llm_svc, mock_auth):
    """Create test client with dependency overrides."""
    from src.infrastructure.api.routes.algorithms import (
        get_event_repo,
        get_lifecycle_service,
        get_llm_service,
        get_algorithm_repo,
    )
    from src.infrastructure.api.auth import require_trader

    app.dependency_overrides[get_algorithm_repo] = lambda: mock_repo
    app.dependency_overrides[get_event_repo] = lambda: mock_event_repo
    app.dependency_overrides[get_lifecycle_service] = lambda: mock_lifecycle_svc
    app.dependency_overrides[get_llm_service] = lambda: mock_llm_svc
    app.dependency_overrides[require_trader] = lambda: mock_auth
    yield TestClient(app, headers={"X-API-Key": "test-secret-key"})
    app.dependency_overrides.clear()


@pytest.fixture
def sample_algorithm_data():
    """Sample data for creating a algorithm."""
    return {
        "name": "Test Algorithm",
        "description": "A test algorithm",
        "mode": "paper",
        "config": {
            "meta": {"schema_version": 1},
            "universe": {},
            "signal": {},
            "risk": {},
            "execution": {},
            "mode": "paper",
            "status": "draft",
        },
        "created_by": "test",
    }


class TestCreateAlgorithm:
    """Tests for POST /api/algorithms"""

    def test_create_success(self, client, mock_repo, sample_algorithm_data):
        """Test creating a algorithm successfully."""
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(
            name=sample_algorithm_data["name"],
            description=sample_algorithm_data["description"],
            mode=sample_algorithm_data["mode"],
        )
        mock_repo.save.return_value = algorithm
        mock_repo.create_version = AsyncMock()

        response = client.post("/api/algorithms", json=sample_algorithm_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_algorithm_data["name"]

    def test_create_invalid_data(self, client):
        """Test creating with invalid data returns 422."""
        invalid_data = {"name": ""}  # Too short

        response = client.post("/api/algorithms", json=invalid_data)

        assert response.status_code == 422


class TestListAlgorithms:
    """Tests for GET /api/algorithms"""

    def test_list_empty(self, client, mock_repo):
        """Test listing when no algorithms exist."""
        mock_repo.get_all.return_value = []

        response = client.get("/api/algorithms")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_with_data(self, client, mock_repo):
        """Test listing algorithms."""
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(name="Test", description="Test desc", mode="paper")
        mock_repo.get_all.return_value = [algorithm]

        response = client.get("/api/algorithms")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test"

    def test_list_filter_by_status(self, client, mock_repo):
        """Test listing with status filter."""
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(name="Test", description="Test desc", mode="paper", status="active")
        mock_repo.get_all.return_value = [algorithm]

        response = client.get("/api/algorithms?status=active")

        assert response.status_code == 200
        mock_repo.get_all.assert_called_once()

    def test_list_filter_by_mode(self, client, mock_repo):
        """Test listing with mode filter."""
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(name="Test", description="Test desc", mode="live")
        mock_repo.get_all.return_value = [algorithm]

        response = client.get("/api/algorithms?mode=live")

        assert response.status_code == 200


class TestGetAlgorithm:
    """Tests for GET /api/algorithms/{id}"""

    def test_get_existing(self, client, mock_repo):
        """Test getting an existing algorithm."""
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(name="Test", description="Test desc", mode="paper")
        mock_repo.get_by_id.return_value = algorithm

        response = client.get(f"/api/algorithms/{algorithm.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test"
        assert data["id"] == str(algorithm.id)

    def test_get_nonexistent(self, client, mock_repo):
        """Test getting non-existent algorithm returns 404."""
        mock_repo.get_by_id.return_value = None

        response = client.get(f"/api/algorithms/{uuid4()}")

        assert response.status_code == 404


class TestUpdateAlgorithm:
    """Tests for PUT /api/algorithms/{id}"""

    def test_update_name(self, client, mock_repo):
        """Test updating algorithm name."""
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(name="Old", description="Old desc", mode="paper")
        mock_repo.get_by_id.return_value = algorithm
        mock_repo.save.return_value = algorithm

        response = client.put(
            f"/api/algorithms/{algorithm.id}",
            json={"name": "New Name"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_update_nonexistent(self, client, mock_repo):
        """Test updating non-existent returns 404."""
        mock_repo.get_by_id.return_value = None

        response = client.put(
            f"/api/algorithms/{uuid4()}",
            json={"name": "New"},
        )

        assert response.status_code == 404

    def test_update_no_fields(self, client, mock_repo):
        """Test updating with no fields returns 400."""
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(name="Test", description="Test desc", mode="paper")
        mock_repo.get_by_id.return_value = algorithm

        response = client.put(
            f"/api/algorithms/{algorithm.id}",
            json={},
        )

        assert response.status_code == 400


class TestAlgorithmVersions:
    """Tests for version endpoints."""

    def test_create_version(self, client, mock_repo):
        """Test creating a new version."""
        from src.domain.algorithms.algorithm_config import (
            AlgorithmConfigVersion,
            AlgorithmDefinition,
        )

        algorithm = AlgorithmDefinition(name="Test", description="Test desc", mode="paper")
        mock_repo.get_by_id.return_value = algorithm

        version = AlgorithmConfigVersion(
            algorithm_id=algorithm.id,
            version=2,
            schema_version=1,
            config={"test": True},
        )
        mock_repo.create_version.return_value = version

        response = client.post(
            f"/api/algorithms/{algorithm.id}/versions",
            json={
                "config": {"meta": {"schema_version": 1}},
                "schema_version": 1,
            },
        )

        assert response.status_code == 201

    def test_list_versions(self, client, mock_repo):
        """Test listing algorithm versions."""
        from src.domain.algorithms.algorithm_config import AlgorithmConfigVersion

        version = AlgorithmConfigVersion(
            algorithm_id=uuid4(),
            version=1,
            schema_version=1,
            config={"test": True},
        )
        mock_repo.list_versions.return_value = [version]

        response = client.get(f"/api/algorithms/{uuid4()}/versions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_activate_version(self, client, mock_repo):
        """Test activating a specific version."""
        mock_repo.set_active_version = AsyncMock(return_value=True)

        response = client.post(
            f"/api/algorithms/{uuid4()}/versions/1/activate",
        )

        assert response.status_code == 200
        assert "activated" in response.json()["message"]


class TestLifecycleEndpoints:
    """Tests for activate/deactivate/pause/resume endpoints."""

    def test_activate_algorithm(self, client, mock_lifecycle_svc):
        """Test activating a algorithm."""
        response = client.post(
            f"/api/algorithms/{uuid4()}/activate",
            json={"version": 1},
        )

        assert response.status_code == 200
        assert "activated" in response.json()["message"]

    def test_deactivate_algorithm(self, client, mock_lifecycle_svc):
        """Test deactivating a algorithm."""
        response = client.post(
            f"/api/algorithms/{uuid4()}/deactivate",
        )

        assert response.status_code == 200
        assert "deactivated" in response.json()["message"]

    def test_pause_algorithm(self, client, mock_lifecycle_svc):
        """Test pausing a algorithm."""
        response = client.post(
            f"/api/algorithms/{uuid4()}/pause",
        )

        assert response.status_code == 200
        assert "paused" in response.json()["message"]

    def test_resume_algorithm(self, client, mock_lifecycle_svc):
        """Test resuming a algorithm."""
        response = client.post(
            f"/api/algorithms/{uuid4()}/resume",
        )

        assert response.status_code == 200
        assert "resumed" in response.json()["message"]


class TestRuntimeState:
    """Tests for runtime state endpoints."""

    def test_get_runtime_state(self, client, mock_lifecycle_svc):
        """Test getting runtime state for a algorithm."""
        from src.domain.algorithms.algorithm_instance import AlgorithmInstanceState

        # Mock the service to return an object with attributes
        state = MagicMock()
        state.algorithm_id = uuid4()
        state.algorithm_name = "Test"
        state.state = AlgorithmInstanceState.RUNNING  # Enum with .value
        state.version = 1
        state.last_error = None
        state.error_count = 0
        state.last_state_change = None
        mock_lifecycle_svc.get_runtime_state.return_value = state

        response = client.get(f"/api/algorithms/{uuid4()}/runtime")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "running"

    def test_get_runtime_state_not_found(self, client, mock_lifecycle_svc):
        """Test getting runtime state when not found."""
        mock_lifecycle_svc.get_runtime_state.return_value = None

        response = client.get(f"/api/algorithms/{uuid4()}/runtime")

        assert response.status_code == 404

    def test_get_all_runtime_states(self, client, mock_lifecycle_svc):
        """Test getting all runtime states."""
        from src.domain.algorithms.algorithm_instance import AlgorithmInstanceState

        # Mock the service to return objects with attributes
        state1 = MagicMock()
        state1.algorithm_id = uuid4()
        state1.algorithm_name = "Test"
        state1.state = AlgorithmInstanceState.RUNNING
        state1.version = 1
        state1.last_error = None
        state1.error_count = 0
        state1.last_state_change = None

        mock_lifecycle_svc.get_all_runtime_states.return_value = [state1]

        response = client.get("/api/algorithms/runtime")

        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestLifecycleEvents:
    """Tests for events endpoint."""

    def test_get_events(self, client, mock_lifecycle_svc):
        """Test getting lifecycle events."""
        response = client.get(f"/api/algorithms/{uuid4()}/events")

        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestLLMGeneration:
    """Tests for LLM generation endpoints."""

    def test_generate_algorithm(self, client, mock_llm_svc):
        """Test generating algorithm via LLM."""
        from src.application.services.llm_algorithm_service import LLMGenerationResult
        from src.domain.algorithms.config_schema import ValidationIssue

        result = LLMGenerationResult(
            success=True,
            config={"meta": {"schema_version": 1}},
            issues=[],
            raw_response="generated config",
        )
        mock_llm_svc.generate_config.return_value = result

        # Mock save_generated_algorithm
        from src.domain.algorithms.algorithm_config import AlgorithmDefinition

        algorithm = AlgorithmDefinition(name="Generated", description="Generated desc", mode="paper")
        mock_llm_svc.save_generated_algorithm = AsyncMock(return_value=algorithm)

        response = client.post(
            "/api/algorithms/generate",
            json={
                "description": "Create a simple moving average algorithm",
                "symbols": ["BTC/USDC"],
            },
        )

        assert response.status_code == 200
        assert "generated" in response.json()["message"]

    def test_generate_algorithm_failure(self, client, mock_llm_svc):
        """Test LLM generation failure returns 400."""
        from src.application.services.llm_algorithm_service import LLMGenerationResult

        result = LLMGenerationResult(
            success=False,
            config=None,
            issues=[],
            raw_response="",
            error_message="Invalid description",
        )
        mock_llm_svc.generate_config.return_value = result

        response = client.post(
            "/api/algorithms/generate",
            json={
                "description": "This is a bad algorithm description",
                "symbols": ["BTC/USDC"],
            },
        )

        assert response.status_code == 400
