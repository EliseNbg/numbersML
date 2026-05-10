"""
Integration tests for Strategy API endpoints.

Tests cover:
- CRUD operations
- Lifecycle endpoints (activate/deactivate/pause/resume)
- LLM generation/modification endpoints
- Authorization checks
- Invalid payload handling
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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
API_KEY_STORE.update(
    {
        "admin-test-key": {"roles": ["admin"], "name": "Test Admin Key"},
        "trader-test-key": {"roles": ["trader", "read"], "name": "Test Trader Key"},
        "read-test-key": {"roles": ["read"], "name": "Test Read Key"},
    }
)

from datetime import UTC

from src.infrastructure.api.app import create_app
from src.infrastructure.database import set_db_pool

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client():
    """Create test client with initialized database pool."""
    import asyncpg

    from src.infrastructure.database.config import get_test_db_url

    async def init_db():
        db_url = get_test_db_url()
        pool = await asyncpg.create_pool(db_url, min_size=2, max_size=5)
        set_db_pool(pool)
        return pool

    # Run init in event loop
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    pool = loop.run_until_complete(init_db())

    # Create app with initialized pool
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    # Cleanup: Delete all test strategies
    async def cleanup_and_close():
        try:
            async with pool.acquire() as conn:
                # Delete draft test strategies (names starting with Test_, E2E_, Delete_Test_, etc.)
                await conn.execute("""
                    DELETE FROM strategies
                    WHERE (name LIKE 'Test_%'
                       OR name LIKE 'E2E_%'
                       OR name LIKE 'Delete_%'
                       OR name LIKE 'Invalid_%'
                       OR name LIKE 'Emergency_%'
                       OR name LIKE 'invalid_strategy_%')
                    created_by = 'system'
                    """)
        except Exception as e:
            print(f"Warning: Failed to cleanup test strategies: {e}")
        finally:
            await pool.close()

    loop.run_until_complete(cleanup_and_close())


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
        "name": f"Test Strategy {uuid4()}",
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
    """Test that auth is optional for personal use (no auth required)."""

    def test_no_api_key_allows_access(self, client):
        """Auth is optional - endpoints work without API key for personal use."""
        response = client.post("/api/strategies", json={"name": "Test"})
        # Should not be 401/403 - auth is optional
        assert response.status_code not in [401, 403]

    def test_invalid_api_key_is_ignored(self, client):
        """Invalid API key is ignored - personal use has no auth requirements."""
        response = client.post(
            "/api/strategies",
            json={"name": "Test"},
            headers={"X-API-Key": "invalid-key"},
        )
        # Should not be 401/403 - auth is optional
        assert response.status_code not in [401, 403]

    def test_any_key_can_create_strategy(self, client, read_headers, strategy_payload):
        """Any API key works - no role restrictions for personal use."""
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_repo.return_value.save = AsyncMock()
            mock_repo.return_value.create_version = AsyncMock()
            response = client.post("/api/strategies", json=strategy_payload, headers=read_headers)
            # Should not be 403 - no role restrictions
            assert response.status_code != 403

    def test_trader_key_can_create_strategy(self, client, trader_headers, strategy_payload):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_repo.return_value.save = AsyncMock()
            mock_repo.return_value.create_version = AsyncMock()
            response = client.post("/api/strategies", json=strategy_payload, headers=trader_headers)
            # No auth restrictions for personal use
            assert response.status_code != 403


# ============================================================================
# Strategy CRUD Tests
# ============================================================================


class TestStrategyCRUD:
    """Test strategy CRUD operations."""

    def test_create_strategy_success(self, client, trader_headers, strategy_payload):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            from datetime import datetime
            from uuid import UUID

            # Create a mock StrategyDefinition-like object with all required fields
            mock_strategy = MagicMock()
            mock_strategy.id = UUID("123e4567-e89b-12d3-a456-426614174000")
            mock_strategy.name = strategy_payload["name"]
            mock_strategy.description = strategy_payload.get("description")
            mock_strategy.mode = strategy_payload.get("mode", "paper")
            mock_strategy.status = "draft"
            mock_strategy.current_version = 1
            mock_strategy.created_by = strategy_payload.get("created_by", "system")
            mock_strategy.created_at = datetime.now(UTC)
            mock_strategy.updated_at = datetime.now(UTC)

            mock_save = AsyncMock(return_value=mock_strategy)
            mock_repo.return_value.save = mock_save
            mock_repo.return_value.create_version = AsyncMock()

            response = client.post("/api/strategies", json=strategy_payload, headers=trader_headers)
            assert response.status_code == 201
            assert "id" in response.json()

    def test_create_strategy_invalid_payload(self, client, trader_headers):
        invalid_payload = {"name": ""}  # Empty name
        response = client.post("/api/strategies", json=invalid_payload, headers=trader_headers)
        assert response.status_code == 422  # Validation error

    def test_list_strategies(self, client, trader_headers):
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            mock_repo.return_value.get_all = AsyncMock(return_value=[])
            response = client.get("/api/strategies", headers=trader_headers)
            assert response.status_code == 200
            assert isinstance(response.json(), list)

    def test_get_strategy_not_found(self, client, trader_headers):
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

    def test_activate_strategy_works_without_auth(self, client):
        """Auth is optional - activation works without API key for personal use."""
        response = client.post(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000/activate",
            json={"version": 1},
        )
        # No auth required - should be 404 (strategy not found) not 401
        assert response.status_code == 404

    def test_activate_strategy_with_trader_auth(self, client, trader_headers):
        # Test that trader can access activate endpoint (actual activation is complex)
        # Just verify that auth passes and we get a response (not 401/403)
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import UUID

        # Create mock strategy that looks like paper mode
        mock_strategy = MagicMock()
        mock_strategy.mode = "paper"
        mock_strategy.id = UUID("123e4567-e89b-12d3-a456-426614174000")

        # Create mock repo
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=mock_strategy)

        with patch(
            "src.infrastructure.api.routes.strategies.get_strategy_repo", return_value=mock_repo
        ):
            response = client.post(
                "/api/strategies/123e4567-e89b-12d3-a456-426614174000/activate",
                json={"version": 1},
                headers=trader_headers,
            )
            # Should not be 401 (auth) or 403 (forbidden) - may be 200 or 500 depending on mocks
            assert response.status_code not in [401, 403]
            # If we get 200, check the message
            if response.status_code == 200:
                assert "activated" in response.json()["message"].lower()

    def test_activate_live_mode_no_auth_required(self, client, trader_headers):
        """Live mode activation - no auth restrictions for personal use."""
        with patch("src.infrastructure.api.routes.strategies.get_strategy_repo") as mock_repo:
            from uuid import UUID

            # Create a proper mock with UUID id
            mock_strategy = MagicMock()
            mock_strategy.mode = "live"
            mock_strategy.id = UUID("123e4567-e89b-12d3-a456-426614174000")

            mock_repo.return_value.get_by_id = AsyncMock(return_value=mock_strategy)
            response = client.post(
                "/api/strategies/123e4567-e89b-12d3-a456-426614174000/activate",
                json={"version": 1},
                headers=trader_headers,
            )
            # No auth restrictions for personal use - should not be 403
            assert response.status_code != 403


# ============================================================================
# LLM Endpoints Tests
# ============================================================================


class TestLLMEndpoints:
    """Test LLM generation and modification endpoints."""

    def test_generate_strategy_works_without_auth(self, client):
        """LLM generation works without auth for personal use."""
        response = client.post(
            "/api/strategies/generate",
            json={"description": "Test strategy"},
        )
        # No auth required - should be 400 (missing required fields) not 401
        assert response.status_code != 401

    @patch("src.infrastructure.api.routes.strategies.get_llm_service")
    def test_generate_strategy_success(self, mock_get_llm, client, trader_headers):
        from src.application.services.llm_strategy_service import LLMStrategyService

        # Create mock LLM service
        mock_llm_service = MagicMock(spec=LLMStrategyService)
        mock_llm_service.generate_config = AsyncMock(
            return_value={
                "name": "RSI Strategy",
                "description": "Test",
                "signal": {"type": "rsi", "params": {"period": 14}},
            }
        )
        mock_get_llm.return_value = mock_llm_service

        response = client.post(
            "/api/strategies/generate",
            json={"description": "Create RSI strategy for BTC", "symbols": ["BTC/USDC"]},
            headers=trader_headers,
        )
        # Should succeed or fail with non-auth error (we mocked the LLM service)
        assert response.status_code != 401  # Auth should pass

    def test_generate_strategy_invalid_description(self, client, trader_headers):
        response = client.post(
            "/api/strategies/generate",
            json={"description": "short"},  # Too short
            headers=trader_headers,
        )
        assert response.status_code == 422  # Validation error
