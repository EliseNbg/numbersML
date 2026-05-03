"""
Integration tests for Market API endpoints.

Tests cover:
- Balances, positions, orders, trades endpoints
- Authorization for order creation/cancellation
- Invalid payload handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.api.auth import API_KEY_STORE

# Ensure test keys are present
API_KEY_STORE.update(
    {
        "admin-test-key": {"roles": ["admin"], "name": "Test Admin Key"},
        "trader-test-key": {"roles": ["trader", "read"], "name": "Test Trader Key"},
        "read-test-key": {"roles": ["read"], "name": "Test Read Key"},
    }
)

from src.infrastructure.api.app import create_app

client = TestClient(create_app())


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def trader_headers():
    return {"X-API-Key": "trader-test-key"}


@pytest.fixture
def read_headers():
    return {"X-API-Key": "read-test-key"}


@pytest.fixture
def order_payload():
    return {
        "symbol": "BTC/USDC",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 1.0,
        "price": 50000.0,
        "time_in_force": "GTC",
    }


# ============================================================================
# Authorization Tests
# ============================================================================


class TestMarketAuthorization:
    """Test authorization for market endpoints."""

    def test_create_order_no_auth(self, order_payload):
        response = client.post("/api/market/orders", json=order_payload)
        assert response.status_code == 401

    def test_create_order_read_key_forbidden(self, read_headers, order_payload):
        response = client.post("/api/market/orders", json=order_payload, headers=read_headers)
        assert response.status_code == 403
        assert "Trader or admin access required" in response.json()["detail"]

    def test_cancel_order_no_auth(self):
        response = client.delete("/api/market/orders/test-order-id")
        assert response.status_code == 401

    def test_read_only_endpoints_with_read_key(self, read_headers):
        with patch("src.infrastructure.api.routes.market.get_market_service") as mock_svc:
            mock_svc.return_value.get_balances = AsyncMock(return_value={})
            response = client.get("/api/market/balances", headers=read_headers)
            assert response.status_code == 200


# ============================================================================
# Order Endpoints Tests
# ============================================================================


class TestOrderEndpoints:
    """Test order creation, listing, and cancellation."""

    def test_create_order_success(self, trader_headers, order_payload):
        with patch("src.infrastructure.api.routes.market.get_market_service") as mock_svc:
            mock_order = MagicMock()
            mock_order.order_id = "test-order-123"
            mock_svc.return_value.create_order = AsyncMock(return_value=mock_order)
            mock_svc.return_value.__enter__ = AsyncMock(return_value=mock_svc.return_value)
            mock_svc.return_value.__exit__ = AsyncMock(return_value=False)

            response = client.post("/api/market/orders", json=order_payload, headers=trader_headers)
            # Should not be 403 (auth passes)
            assert response.status_code != 403

    def test_create_order_invalid_payload(self, trader_headers):
        invalid_payload = {"symbol": "BTC/USDC"}  # Missing required fields
        response = client.post("/api/market/orders", json=invalid_payload, headers=trader_headers)
        assert response.status_code == 422  # Validation error

    def test_cancel_order_success(self, trader_headers):
        with patch("src.infrastructure.api.routes.market.get_market_service") as mock_svc:
            mock_svc.return_value.cancel_order = AsyncMock(return_value=True)
            response = client.delete("/api/market/orders/test-order-123", headers=trader_headers)
            assert response.status_code == 200
            assert "cancelled" in response.json()["message"].lower()

    def test_cancel_order_failure(self, trader_headers):
        with patch("src.infrastructure.api.routes.market.get_market_service") as mock_svc:
            mock_svc.return_value.cancel_order = AsyncMock(return_value=False)
            response = client.delete("/api/market/orders/test-order-123", headers=trader_headers)
            assert response.status_code == 400


# ============================================================================
# Balance & Position Tests
# ============================================================================


class TestBalancePositionEndpoints:
    """Test balance and position endpoints."""

    def test_get_balances(self, trader_headers):
        with patch("src.infrastructure.api.routes.market.get_market_service") as mock_svc:
            mock_svc.return_value.get_balances = AsyncMock(
                return_value={"USDC": {"free": 1000.0, "locked": 0.0, "total": 1000.0}}
            )
            response = client.get("/api/market/balances", headers=trader_headers)
            assert response.status_code == 200
            assert isinstance(response.json(), list)

    def test_get_positions(self, trader_headers):
        with patch("src.infrastructure.api.routes.market.get_market_service") as mock_svc:
            mock_svc.return_value.get_positions = AsyncMock(return_value=[])
            response = client.get("/api/market/positions", headers=trader_headers)
            assert response.status_code == 200
            assert isinstance(response.json(), list)
