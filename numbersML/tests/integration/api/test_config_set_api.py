"""
Integration tests for ConfigurationSet API lifecycle.

Tests cover:
- Create ConfigurationSet
- Read ConfigurationSet
- Update ConfigurationSet
- Activate/Deactivate ConfigurationSet
- List ConfigurationSets
- Delete (soft delete) ConfigurationSet

Uses test database and real API endpoints.
"""

import os
import sys
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

# Set environment variables BEFORE importing app
TEST_DB_URL = os.environ.get(
    "TEST_DB_URL", "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"
)
os.environ["API_KEY_ADMIN"] = "test-admin-key"
os.environ["API_KEY_TRADER"] = "test-trader-key"
os.environ["API_KEY_READ"] = "test-read-key"

# Reload modules to pick up env keys
for mod in list(sys.modules.keys()):
    if "src.infrastructure.api" in mod or "src.infrastructure.database" in mod:
        del sys.modules[mod]

from src.infrastructure.api.app import app  # noqa: E402
from src.infrastructure.api.auth import API_KEY_STORE  # noqa: E402

# Update API_KEY_STORE with test keys
API_KEY_STORE.update(
    {
        "test-admin-key": {"roles": ["admin"], "name": "Test Admin Key"},
        "test-trader-key": {"roles": ["trader", "read"], "name": "Test Trader Key"},
        "test-read-key": {"roles": ["read"], "name": "Test Read Key"},
    }
)

# Update DATABASE_URL in the app module to point to test database
import src.infrastructure.api.app as app_module  # noqa: E402

app_module.DATABASE_URL = TEST_DB_URL


# Fixture to provide TestClient with proper lifespan handling
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def admin_headers():
    return {"X-API-Key": "test-admin-key"}


@pytest.fixture
def trader_headers():
    return {"X-API-Key": "test-trader-key"}


@pytest.fixture
def read_headers():
    return {"X-API-Key": "test-read-key"}


@pytest.fixture
def config_set_payload():
    import time

    unique_name = f"Test Config Set {int(time.time())}"
    return {
        "name": unique_name,
        "description": "Test configuration for integration tests",
        "config": {
            "symbols": ["TEST/USDT"],
            "initial_balance": 10000.0,
            "risk": {"max_position_size_pct": 10, "stop_loss_pct": 5},
        },
        "created_by": "test",
    }


# ============================================================================
# Lifecycle Tests
# ============================================================================


class TestConfigurationSetLifecycle:
    """Test ConfigurationSet full lifecycle via API."""

    def test_lifecycle(self, client, admin_headers, read_headers, config_set_payload):
        """Test complete ConfigurationSet lifecycle: CRUD + activate/deactivate."""

        # 1. Create ConfigurationSet
        create_resp = client.post(
            "/api/config-sets", json=config_set_payload, headers=admin_headers
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.json()}"
        created = create_resp.json()
        assert created["name"] == config_set_payload["name"]
        assert created["config"]["symbols"] == ["TEST/USDT"]
        config_set_id = created["id"]

        # Verify it's a valid UUID
        UUID(config_set_id)

        # 2. Get ConfigurationSet by ID
        get_resp = client.get(f"/api/config-sets/{config_set_id}", headers=admin_headers)
        assert get_resp.status_code == 200, f"Get failed: {get_resp.json()}"
        fetched = get_resp.json()
        assert fetched["id"] == config_set_id
        assert fetched["name"] == config_set_payload["name"]
        assert fetched["is_active"] is True

        # 3. List ConfigurationSets (should contain our config set)
        list_resp = client.get("/api/config-sets", headers=read_headers)
        assert list_resp.status_code == 200
        config_sets = list_resp.json()
        assert any(cs["id"] == config_set_id for cs in config_sets)

        # 4. Update ConfigurationSet
        update_payload = {
            "config": {
                "symbols": ["TEST/USDT", "BTC/USDT"],
                "initial_balance": 20000.0,
                "risk": {"max_position_size_pct": 15, "stop_loss_pct": 10},
            }
        }
        update_resp = client.put(
            f"/api/config-sets/{config_set_id}",
            json=update_payload,
            headers=admin_headers,
        )
        assert update_resp.status_code == 200, f"Update failed: {update_resp.json()}"
        updated = update_resp.json()
        assert updated["config"]["symbols"] == ["TEST/USDT", "BTC/USDT"]
        assert updated["config"]["initial_balance"] == 20000.0

        # 5. Activate ConfigurationSet
        activate_resp = client.post(
            f"/api/config-sets/{config_set_id}/activate", headers=admin_headers
        )
        assert activate_resp.status_code == 200
        assert "activated" in activate_resp.json()["message"].lower()

        # 6. Deactivate ConfigurationSet
        deactivate_resp = client.post(
            f"/api/config-sets/{config_set_id}/deactivate", headers=admin_headers
        )
        assert deactivate_resp.status_code == 200
        assert "deactivated" in deactivate_resp.json()["message"].lower()

        # 7. List only active (should not contain our deactivated config set)
        list_active_resp = client.get(
            "/api/config-sets?active_only=true", headers=read_headers
        )
        assert list_active_resp.status_code == 200
        active_config_sets = list_active_resp.json()
        assert not any(cs["id"] == config_set_id for cs in active_config_sets)

        # 8. Delete (soft delete) ConfigurationSet
        delete_resp = client.delete(
            f"/api/config-sets/{config_set_id}", headers=admin_headers
        )
        assert delete_resp.status_code == 204

        # 9. Verify it's soft-deleted (should return 404 or is_active=False)
        get_after_delete = client.get(
            f"/api/config-sets/{config_set_id}", headers=admin_headers
        )
        # After soft delete, the config set should not be found via GET
        # (depending on implementation - some return with is_active=False)
        if get_after_delete.status_code == 200:
            assert get_after_delete.json()["is_active"] is False


# ============================================================================
# Authorization Tests
# ============================================================================


class TestConfigurationSetAuth:
    """Test authorization for ConfigurationSet endpoints."""

    def test_create_requires_auth(self, client, config_set_payload):
        resp = client.post("/api/config-sets", json=config_set_payload)
        assert resp.status_code == 401

    def test_read_requires_auth(self, client):
        resp = client.get("/api/config-sets/some-uuid")
        assert resp.status_code == 401

    def test_read_key_can_list(self, client, read_headers):
        resp = client.get("/api/config-sets", headers=read_headers)
        assert resp.status_code == 200

    def test_trader_can_create(self, client, trader_headers, config_set_payload):
        resp = client.post(
            "/api/config-sets", json=config_set_payload, headers=trader_headers
        )
        # Should succeed (201) or conflict (400) if already exists
        assert resp.status_code in (201, 400)


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestConfigurationSetErrors:
    """Test error handling for ConfigurationSet endpoints."""

    def test_get_nonexistent_returns_404(self, client, admin_headers):
        fake_id = "123e4567-e89b-12d3-a456-426614174000"
        resp = client.get(f"/api/config-sets/{fake_id}", headers=admin_headers)
        assert resp.status_code == 404

    def test_create_duplicate_name_returns_400(
        self, client, admin_headers
    ):
        import time

        # Use a unique name to avoid conflicts from previous runs
        unique_name = f"Duplicate Test {int(time.time() * 1000)}"
        payload = {
            "name": unique_name,
            "description": "Test configuration for duplicate test",
            "config": {
                "symbols": ["TEST/USDT"],
                "initial_balance": 10000.0,
            },
            "created_by": "test",
        }

        # Create first time
        resp1 = client.post(
            "/api/config-sets", json=payload, headers=admin_headers
        )
        assert resp1.status_code == 201, f"First create failed: {resp1.json()}"

        # Try to create again with same name
        resp2 = client.post(
            "/api/config-sets", json=payload, headers=admin_headers
        )
        assert resp2.status_code == 400
        assert "already exists" in resp2.json()["detail"].lower()

    def test_update_nonexistent_returns_404(self, client, admin_headers):
        fake_id = "123e4567-e89b-12d3-a456-426614174000"
        resp = client.put(
            f"/api/config-sets/{fake_id}",
            json={"config": {"symbols": ["BTC/USDT"]}},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_create_invalid_payload_returns_422(self, client, admin_headers):
        invalid_payload = {"name": "", "config": {}}  # Empty name  # Empty config
        resp = client.post(
            "/api/config-sets", json=invalid_payload, headers=admin_headers
        )
        assert resp.status_code == 422  # Validation error
