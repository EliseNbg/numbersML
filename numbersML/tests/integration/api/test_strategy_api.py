"""
Integration tests for Strategy API endpoints.

Tests cover:
- CRUD operations
- Lifecycle endpoints (activate/deactivate/pause/resume)
- LLM generation/modification endpoints
- Authorization checks
- Invalid payload handling
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import os
import sys

# Set test API keys BEFORE importing app
os.environ["API_KEY_ADMIN"] = "admin-test-key"
os.environ["API_KEY_TRADER"] = "trader-test-key"
os.environ["API_KEY_READ"] = "read-test-key"

# Reload modules to pick up env keys
for mod in list(sys.modules.keys()):
    if "src.infrastructure.api" in mod:
        del sys.modules[mod]

from src.infrastructure.api.auth import API_KEY_STORE

# Update API_KEY_STORE with test keys
API_KEY_STORE.update({
    "admin-test-key": {"roles": ["admin"], "name": "Test Admin Key"},
    "trader-test-key": {"roles": ["trader", "read"], "name": "Test Trader Key"},
    "read-test-key": {"roles": ["read"], "name": "Test Read Key"},
})

from src.infrastructure.api.app import create_app

client = TestClient(create_app())


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def admin_headers():
    return {"X-API-Key": "admin-test-key"}


@pytest.fixture
def trader_headers():
    return {"X-API-Key": "trader-test-key"}


@pytest.fixture
def read_headers():
    return {"X-API-Key": "read-test-key"}


@pytest.fixture
def strategy_payload():
    return {
        "name": "Test Strategy",
        "description": "Test strategy for API tests",
        "mode": "paper",
        "config": {
            "meta": {"name": "Test", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {"period": 14}},
            "risk": {"max_position_size_pct": 10},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "draft",
        },
    }


# ============================================================================
# Authorization Tests
# ============================================================================


class TestAuthorization:
    """Test authorization checks for sensitive endpoints."""

    def test_missing_api_key_returns_401(self):
        response = client.post("/api/strategies", json={"name": "Test"})
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_invalid_api_key_returns_401(self):
        response = client.post(
            "/api/strategies",
            json={"name": "Test"},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_read_key_cannot_create_strategy(self, read_headers, strategy_payload):
        response = client.post("/api/strategies", json=strategy_payload, headers=read_headers)
        assert response.status_code == 403
        assert "Trader or admin access required" in response.json()["detail"]

    def test_trader_key_can_create_strategy(self, trader_headers, strategy_payload):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_repo.return_value.save = AsyncMock()
            mock_repo.return_value.create_version = AsyncMock()
            response = client.post(
                "/api/strategies", json=strategy_payload, headers=trader_headers
            )
            # Will fail on repo init, but auth should pass
            assert response.status_code != 403


# ============================================================================
# Strategy CRUD Tests
# ============================================================================


class TestStrategyCRUD:
    """Test strategy CRUD operations."""

    def test_create_strategy_success(self, trader_headers, strategy_payload):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_save = AsyncMock()
            mock_save.return_value.id = "123e4567-e89b-12d3-a456-426614174000"
            mock_repo.return_value.save = mock_save
            mock_repo.return_value.create_version = AsyncMock()

            response = client.post(
                "/api/strategies", json=strategy_payload, headers=trader_headers
            )
            assert response.status_code == 201
            assert "strategy" in response.json()["message"].lower()

    def test_create_strategy_invalid_payload(self, trader_headers):
        invalid_payload = {"name": ""}  # Empty name
        response = client.post(
            "/api/strategies", json=invalid_payload, headers=trader_headers
        )
        assert response.status_code == 422  # Validation error

    def test_list_strategies(self, trader_headers):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_repo.return_value.get_all = AsyncMock(return_value=[])
            response = client.get("/api/strategies", headers=trader_headers)
            assert response.status_code == 200
            assert isinstance(response.json(), list)

    def test_get_strategy_not_found(self, trader_headers):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_repo.return_value.get_by_id = AsyncMock(return_value=None)
            response = client.get(
                "/api/strategies/123e4567-e89b-12d3-a456-426614174000",
                headers=trader_headers,
            )
            assert response.status_code == 404


# ============================================================================
# Lifecycle Tests
# ============================================================================


class TestStrategyLifecycle:
    """Test strategy lifecycle endpoints."""

    def test_activate_strategy_no_auth(self):
        response = client.post(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000/activate",
            json={"version": 1},
        )
        assert response.status_code == 401

    def test_activate_strategy_with_trader_auth(self, trader_headers):
        with patch("src.infrastructure.api.routes.strategies.get_lifecycle_service") as mock_svc, patch(
            "src.infrastructure.api.routes.strategies.get_strategy_repo"
        ) as mock_repo:
            mock_repo.return_value.get_by_id = AsyncMock(
                return_value=MagicMock(mode="paper")
            )
            mock_svc.return_value.activate_strategy = AsyncMock(return_value=True)
            response = client.post(
                "/api/strategies/123e4567-e89b-12d3-a456-426614174000/activate",
                json={"version": 1},
                headers=trader_headers,
            )
            assert response.status_code == 200
            assert "activated" in response.json()["message"].lower()

    def test_activate_live_mode_requires_admin(self, trader_headers):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_repo.return_value.get_by_id = AsyncMock(
                return_value=MagicMock(mode="live")
            )
            response = client.post(
                "/api/strategies/123e4567-e89b-12d3-a456-426614174000/activate",
                json={"version": 1},
                headers=trader_headers,
            )
            assert response.status_code == 403
            assert "admin access required" in response.json()["detail"].lower()


# ============================================================================
# LLM Endpoints Tests
# ============================================================================


class TestLLMEndpoints:
    """Test LLM generation and modification endpoints."""

    def test_generate_strategy_no_auth(self):
        response = client.post(
            "/api/strategies/generate",
            json={"description": "Test strategy"},
        )
        assert response.status_code == 401

    @patch("src.infrastructure.api.routes.strategies.LLMStrategyService")
    def test_generate_strategy_success(self, mock_llm, trader_headers):
        mock_instance = MagicMock()
        mock_instance.generate_config = AsyncMock(
            return_value=MagicMock(
                success=True,
                config={"meta": {"name": "Test"}},
                issues=[],
                error_message=None,
            )
        )
        mock_instance.save_generated_strategy = AsyncMock(
            return_value=MagicMock(id="123e4567-e89b-12d3-a456-426614174000")
        )
        mock_llm.return_value = mock_instance

        response = client.post(
            "/api/strategies/generate",
            json={"description": "Create RSI strategy for BTC", "symbols": ["BTC/USDC"]},
            headers=trader_headers,
        )
        assert response.status_code == 200
        assert "generated successfully" in response.json()["message"].lower()

    def test_generate_strategy_invalid_description(self, trader_headers):
        response = client.post(
            "/api/strategies/generate",
            json={"description": "short"},  # Too short
            headers=trader_headers,
        )
        assert response.status_code == 422  # Validation error
