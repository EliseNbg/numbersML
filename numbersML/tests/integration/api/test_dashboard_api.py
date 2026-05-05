"""
Integration tests for Dashboard API endpoints.

Tests cover:
- Get collector status
- Start/Stop collector
- Get SLA metrics
- Get dashboard stats

Uses FastAPI TestClient with dependency overrides for mocking.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

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

# Module-level mock monitor
_mock_monitor = None


@pytest.fixture(scope="module")
def client():
    """Provide TestClient with dependency overrides."""
    global _mock_monitor
    _mock_monitor = MagicMock()

    # Override dependency
    from src.infrastructure.api.routes.dashboard import get_pipeline_monitor

    app.dependency_overrides[get_pipeline_monitor] = lambda: _mock_monitor

    with TestClient(app) as c:
        yield c

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    return {"X-API-Key": "test-admin-key"}


@pytest.fixture
def trader_headers():
    return {"X-API-Key": "test-trader-key"}


@pytest.fixture
def read_headers():
    return {"X-API-Key": "test-read-key"}


# ============================================================================
# Dashboard Endpoint Tests
# ============================================================================


class TestDashboardStatus:
    """Test collector status endpoint."""

    def test_get_collector_status(self, client, read_headers):
        """Test getting collector status."""
        from src.domain.models.dashboard import CollectorStatus

        _mock_monitor.get_collector_status = AsyncMock(
            return_value=CollectorStatus(
                is_running=True,
                pid=12345,
                uptime_seconds=3600.0,
                last_tick_time="2026-05-04T20:00:00",
                ticks_processed=86400,
                errors=0,
            )
        )

        resp = client.get("/api/dashboard/status", headers=read_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "is_running" in data
        assert "pid" in data

    def test_get_status_requires_auth(self, client):
        """Test that auth is required."""
        resp = client.get("/api/dashboard/status")
        assert resp.status_code == 401


class TestDashboardCollectorControl:
    """Test collector start/stop endpoints."""

    def test_start_collector(self, client, admin_headers):
        """Test starting collector."""
        from unittest.mock import AsyncMock

        _mock_monitor.start_collector = AsyncMock(return_value=True)

        resp = client.post("/api/dashboard/collector/start", headers=admin_headers)
        assert resp.status_code == 200
        assert "started" in resp.json()["message"].lower()

    def test_stop_collector(self, client, admin_headers):
        """Test stopping collector."""
        from unittest.mock import AsyncMock

        _mock_monitor.stop_collector = AsyncMock(return_value=True)

        resp = client.post("/api/dashboard/collector/stop", headers=admin_headers)
        assert resp.status_code == 200
        assert "stopped" in resp.json()["message"].lower()

    def test_start_requires_admin(self, client, trader_headers):
        """Test that starting collector requires admin role."""
        resp = client.post("/api/dashboard/collector/start", headers=trader_headers)
        assert resp.status_code == 403


class TestDashboardMetrics:
    """Test SLA metrics endpoint."""

    def test_get_metrics(self, client, read_headers):
        """Test getting SLA metrics."""
        from src.domain.models.dashboard import SLAMetric

        _mock_monitor.get_sla_metrics = AsyncMock(
            return_value=[
                SLAMetric(
                    timestamp="2026-05-04T12:00:00Z",
                    avg_time_ms=150.5,
                    max_time_ms=450.0,
                    sla_violations=0,
                    ticks_processed=60,
                )
            ]
        )

        resp = client.get("/api/dashboard/metrics?seconds=60", headers=read_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_metrics_invalid_range(self, client, read_headers):
        """Test that invalid seconds returns 400."""
        resp = client.get("/api/dashboard/metrics?seconds=999", headers=read_headers)
        assert resp.status_code == 400

    def test_get_metrics_requires_auth(self, client):
        """Test that auth is required."""
        resp = client.get("/api/dashboard/metrics?seconds=60")
        assert resp.status_code == 401


class TestDashboardStats:
    """Test dashboard stats endpoint."""

    def test_get_stats(self, client, read_headers):
        """Test getting dashboard stats."""
        from src.domain.models.dashboard import DashboardStats

        _mock_monitor.get_dashboard_stats = AsyncMock(
            return_value=DashboardStats(
                ticks_per_minute=60.0,
                avg_processing_time_ms=150.5,
                sla_compliance_pct=99.5,
                active_symbols_count=20,
                active_indicators_count=6,
            )
        )

        resp = client.get("/api/dashboard/stats", headers=read_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "ticks_per_minute" in data or "sla_compliance_pct" in data

    def test_get_stats_requires_auth(self, client):
        """Test that auth is required."""
        resp = client.get("/api/dashboard/stats")
        assert resp.status_code == 401
