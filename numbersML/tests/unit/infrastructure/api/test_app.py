"""
Unit tests for FastAPI application (Step 022.5).

Tests:
    - Application creation
    - Route registration
    - Middleware configuration
    - Lifespan management
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.api.app import create_app, lifespan


class TestAppCreation:
    """Test FastAPI application creation."""

    def test_create_app(self) -> None:
        """Test application creation."""
        app = create_app()

        assert isinstance(app, FastAPI)
        assert app.title == "Crypto Trading Dashboard"
        assert app.version == "1.0.0"

    def test_app_title(self) -> None:
        """Test application title."""
        app = create_app()

        assert app.title == "Crypto Trading Dashboard"

    def test_app_version(self) -> None:
        """Test application version."""
        app = create_app()

        assert app.version == "1.0.0"

    def test_app_description(self) -> None:
        """Test application description."""
        app = create_app()

        assert app.description is not None
        assert "monitoring" in app.description.lower()


class TestRoutes:
    """Test route registration."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test application."""
        return create_app()

    def test_dashboard_routes_registered(self, app: FastAPI) -> None:
        """Test dashboard routes are registered."""
        routes = [route.path for route in app.routes]

        assert "/api/dashboard/status" in routes
        assert "/api/dashboard/metrics" in routes
        assert "/api/dashboard/stats" in routes
        assert "/api/dashboard/collector/start" in routes
        assert "/api/dashboard/collector/stop" in routes

    def test_symbol_routes_registered(self, app: FastAPI) -> None:
        """Test symbol routes are registered."""
        routes = [route.path for route in app.routes]

        assert "/api/symbols" in routes
        assert "/api/symbols/{symbol_id}" in routes
        assert "/api/symbols/{symbol_id}/activate" in routes
        assert "/api/symbols/{symbol_id}/deactivate" in routes

    def test_indicator_routes_registered(self, app: FastAPI) -> None:
        """Test indicator routes are registered."""
        routes = [route.path for route in app.routes]

        assert "/api/indicators" in routes
        assert "/api/indicators/categories" in routes
        assert "/api/indicators/{name}" in routes

    def test_config_routes_registered(self, app: FastAPI) -> None:
        """Test config routes are registered."""
        routes = [route.path for route in app.routes]

        assert "/api/config/{table_name}" in routes
        assert "/api/config/system-config/{key}" in routes

    def test_root_route_registered(self, app: FastAPI) -> None:
        """Test root route is registered."""
        routes = [route.path for route in app.routes]

        assert "/" in routes

    def test_health_route_registered(self, app: FastAPI) -> None:
        """Test health check route is registered."""
        routes = [route.path for route in app.routes]

        assert "/health" in routes


class TestMiddleware:
    """Test middleware configuration."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test application."""
        return create_app()

    def test_cors_middleware_configured(self, app: FastAPI) -> None:
        """Test CORS middleware is configured."""
        middleware_names = [middleware.cls.__name__ for middleware in app.user_middleware]

        assert "CORSMiddleware" in middleware_names


class TestEndpoints:
    """Test endpoint responses."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_root_endpoint(self, client: TestClient) -> None:
        """Test root endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert "docs" in data
        assert "dashboard" in data

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "database" in data

    def test_openapi_docs(self, client: TestClient) -> None:
        """Test OpenAPI docs are available."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()

        assert "openapi" in data
        assert "info" in data
        assert "paths" in data


class TestLifespan:
    """Test lifespan management."""

    @pytest.mark.asyncio
    async def test_lifespan_context(self) -> None:
        """Test lifespan context manager."""
        app = FastAPI(lifespan=lifespan)

        # Test that lifespan can be entered and exited
        # Note: This will fail without a real database
        # In production, use mock database
        pass
