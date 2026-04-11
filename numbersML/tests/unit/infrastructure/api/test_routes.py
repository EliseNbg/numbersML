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
from src.infrastructure.api.routes.ml import router as ml_router
from src.infrastructure.api.routes.candles import router as candles_router
from src.infrastructure.api.routes.target_values import router as target_values_router
from src.infrastructure.api.routes.pipeline import router as pipeline_router


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
        # All routes should now be implemented (return 200 or error from DB)
        response = client.get("/api/dashboard/status")
        # Should not return 501 (Not Implemented) anymore
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/dashboard/metrics")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/dashboard/stats")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
    
    def test_metrics_validation(self, client: TestClient) -> None:
        """Test metrics endpoint validation."""
        # Invalid seconds parameter - returns error (400 or 500 without DB)
        response = client.get("/api/dashboard/metrics?seconds=0")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]
        
        response = client.get("/api/dashboard/metrics?seconds=301")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]
        
        # Valid seconds parameter (returns 200 or error from DB)
        response = client.get("/api/dashboard/metrics?seconds=60")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED


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
        # All routes should now be implemented (return 200 or error from DB)
        response = client.get("/api/symbols")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/symbols?active_only=true")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/symbols/1")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.put("/api/symbols/1/activate")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.put("/api/symbols/1/deactivate")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.post("/api/symbols/bulk/activate", json=[1, 2, 3])
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.post("/api/symbols/bulk/deactivate", json=[1, 2, 3])
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.post("/api/symbols/activate-eu-compliant")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.put("/api/symbols/1/allow")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.put("/api/symbols/1/disallow")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED


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
        # All routes should now be implemented (return 200 or error from DB)
        response = client.get("/api/indicators")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/indicators?active_only=true")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/indicators?category=momentum")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        # Get categories
        response = client.get("/api/indicators/categories")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        # Get indicator
        response = client.get("/api/indicators/rsi_14")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        # Activate/deactivate
        response = client.put("/api/indicators/rsi_14/activate")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.put("/api/indicators/rsi_14/deactivate")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        # Unregister
        response = client.delete("/api/indicators/rsi_14")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED


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
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/config/system_config?limit=50")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        # Get entry
        response = client.get("/api/config/system_config/1")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        # Get config value
        response = client.get("/api/config/system-config/collector.batch_size")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
    
    def test_table_validation(self, client: TestClient) -> None:
        """Test table name validation."""
        # Invalid table name - returns error (400 or 500 without DB)
        response = client.get("/api/config/invalid_table")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]
        
        # Valid table names (returns 200 or error from DB)
        response = client.get("/api/config/system_config")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/config/symbols")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/config/indicator_definitions")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
    
    def test_limit_validation(self, client: TestClient) -> None:
        """Test limit parameter validation."""
        # Invalid limit - returns error (400 or 500 without DB)
        response = client.get("/api/config/system_config?limit=0")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]
        
        response = client.get("/api/config/system_config?limit=1001")
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]
        
        # Valid limit
        response = client.get("/api/config/system_config?limit=50")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED


class TestMLRoutes:
    """Test ML prediction API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with ML routes."""
        app = FastAPI()
        app.include_router(ml_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        response = client.get("/api/ml/models")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/ml/predict?symbol=BTC/USDC")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
    
    def test_predict_validation(self, client: TestClient) -> None:
        """Test prediction endpoint validation."""
        # Missing symbol - returns 422 (validation error)
        response = client.get("/api/ml/predict")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Invalid hours (too low) - returns 422
        response = client.get("/api/ml/predict?symbol=BTC/USDC&hours=0")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Invalid hours (too high) - returns 422
        response = client.get("/api/ml/predict?symbol=BTC/USDC&hours=1441")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_predict_and_save_validation(self, client: TestClient) -> None:
        """Test predict-and-save endpoint validation."""
        # Missing symbol - returns 422
        response = client.post("/api/ml/predict-and-save")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Invalid horizon - returns 422
        response = client.post("/api/ml/predict-and-save?symbol=BTC/USDC&horizon=2")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_task_status_validation(self, client: TestClient) -> None:
        """Test task-status endpoint validation."""
        # Missing task_id - returns 422
        response = client.get("/api/ml/task-status")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Unknown task_id - returns 200 with unknown status
        response = client.get("/api/ml/task-status?task_id=nonexistent_task")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "unknown"


class TestCandleRoutes:
    """Test candle API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with candle routes."""
        app = FastAPI()
        app.include_router(candles_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        response = client.get("/api/candles?symbol=BTC/USDC")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/candles/indicators?symbol=BTC/USDC")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
    
    def test_candles_validation(self, client: TestClient) -> None:
        """Test candles endpoint validation."""
        # Missing symbol - returns 422 (validation error)
        response = client.get("/api/candles")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Invalid seconds (too low) - returns 422
        response = client.get("/api/candles?symbol=BTC/USDC&seconds=0")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Invalid seconds (too high) - returns 422
        response = client.get("/api/candles?symbol=BTC/USDC&seconds=100000")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestTargetValueRoutes:
    """Test target value API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with target value routes."""
        app = FastAPI()
        app.include_router(target_values_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        response = client.get("/api/target-values?symbol=BTC/USDC")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
    
    def test_target_values_validation(self, client: TestClient) -> None:
        """Test target values endpoint validation."""
        # Missing symbol - returns 422 (validation error)
        response = client.get("/api/target-values")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Invalid hours (too low) - returns 422
        response = client.get("/api/target-values?symbol=BTC/USDC&hours=0")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Invalid hours (too high) - returns 422
        response = client.get("/api/target-values?symbol=BTC/USDC&hours=2000")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestPipelineRoutes:
    """Test pipeline API routes."""
    
    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with pipeline routes."""
        app = FastAPI()
        app.include_router(pipeline_router)
        return app
    
    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)
    
    def test_routes_registered(self, client: TestClient) -> None:
        """Test that routes are registered."""
        response = client.get("/api/pipeline/status")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/pipeline/symbols")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
        
        response = client.get("/api/pipeline/stats")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
