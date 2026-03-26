"""
Unit tests for API routes (Step 022.4).

Tests:
    - Route registration
    - Endpoint signatures
    - Response models
    - Error handling
"""

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from src.infrastructure.api.routes.dashboard import router as dashboard_router
from src.infrastructure.api.routes.symbols import router as symbols_router
from src.infrastructure.api.routes.indicators import router as indicators_router
from src.infrastructure.api.routes.config import router as config_router


class TestDashboardRoutes:
    """Test dashboard API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with dashboard routes."""
        app = FastAPI()
        app.include_router(dashboard_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        # All routes should return 501 (not implemented) because no db pool
        response = client.get("/api/dashboard/status")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/dashboard/metrics")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/dashboard/stats")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.post("/api/dashboard/collector/start")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.post("/api/dashboard/collector/stop")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
    
    def test_metrics_validation(self, client: TestClient) -> None:
        """Test metrics endpoint validation."""
        # Invalid seconds parameter
        response = client.get("/api/dashboard/metrics?seconds=0")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        response = client.get("/api/dashboard/metrics?seconds=301")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Valid seconds parameter (still returns 501 because no db pool)
        response = client.get("/api/dashboard/metrics?seconds=60")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


class TestSymbolRoutes:
    """Test symbol API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with symbol routes."""
        app = FastAPI()
        app.include_router(symbols_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        # List symbols
        response = client.get("/api/symbols")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/symbols?active_only=true")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Get symbol
        response = client.get("/api/symbols/1")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Activate/deactivate
        response = client.put("/api/symbols/1/activate")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.put("/api/symbols/1/deactivate")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Bulk operations
        response = client.post("/api/symbols/bulk/activate", json=[1, 2, 3])
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.post("/api/symbols/bulk/deactivate", json=[1, 2, 3])
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # EU compliant
        response = client.post("/api/symbols/activate-eu-compliant")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


class TestIndicatorRoutes:
    """Test indicator API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with indicator routes."""
        app = FastAPI()
        app.include_router(indicators_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        # List indicators
        response = client.get("/api/indicators")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/indicators?active_only=true")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/indicators?category=momentum")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Get categories
        response = client.get("/api/indicators/categories")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Get indicator
        response = client.get("/api/indicators/rsi_14")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Activate/deactivate
        response = client.put("/api/indicators/rsi_14/activate")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.put("/api/indicators/rsi_14/deactivate")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Unregister
        response = client.delete("/api/indicators/rsi_14")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


class TestConfigRoutes:
    """Test config API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with config routes."""
        app = FastAPI()
        app.include_router(config_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        # Get table data
        response = client.get("/api/config/system_config")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/config/system_config?limit=50")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Get entry
        response = client.get("/api/config/system_config/1")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        # Get config value
        response = client.get("/api/config/system-config/collector.batch_size")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
    
    def test_table_validation(self, client: TestClient) -> None:
        """Test table name validation."""
        # Invalid table name
        response = client.get("/api/config/invalid_table")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        # Valid table names (still returns 501 because no db pool)
        response = client.get("/api/config/system_config")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/config/symbols")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/config/indicator_definitions")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
    
    def test_limit_validation(self, client: TestClient) -> None:
        """Test limit parameter validation."""
        # Invalid limit
        response = client.get("/api/config/system_config?limit=0")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        response = client.get("/api/config/system_config?limit=1001")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Valid limit
        response = client.get("/api/config/system_config?limit=50")
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
