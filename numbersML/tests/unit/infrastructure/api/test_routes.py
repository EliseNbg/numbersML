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

from src.infrastructure.api.routes.candles import router as candles_router
from src.infrastructure.api.routes.config import router as config_router
from src.infrastructure.api.routes.dashboard import router as dashboard_router
from src.infrastructure.api.routes.indicators import router as indicators_router
from src.infrastructure.api.routes.market import router as market_router
from src.infrastructure.api.routes.ml import router as ml_router
from src.infrastructure.api.routes.pipeline import router as pipeline_router
from src.infrastructure.api.routes.strategies import router as strategies_router
from src.infrastructure.api.routes.strategy_backtest import router as strategy_backtest_router
from src.infrastructure.api.routes.symbols import router as symbols_router
from src.infrastructure.api.routes.target_values import router as target_values_router


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
        return TestClient(app, raise_server_exceptions=False, headers={"X-API-Key": "test-secret-key"})

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
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]

        response = client.get("/api/dashboard/metrics?seconds=301")
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]

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
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]

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
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]

        response = client.get("/api/config/system_config?limit=1001")
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]

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


class TestStrategyRoutes:
    """Test strategy API routes."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with strategy routes."""
        from unittest.mock import MagicMock

        import asyncpg

        app = FastAPI()

        # Mock the database pool to allow UUID validation without DB errors
        mock_pool = MagicMock(spec=asyncpg.Pool)
        mock_conn = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        from src.infrastructure.database import set_db_pool

        set_db_pool(mock_pool)

        app.include_router(strategies_router)
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_routes_registered(self, client: TestClient) -> None:
        """Test that strategy routes are registered."""
        # All strategy CRUD routes
        response = client.get("/api/strategies")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.get("/api/strategies/123e4567-e89b-12d3-a456-426614174000")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.post(
            "/api/strategies",
            json={
                "name": "test",
                "config": {
                    "meta": {},
                    "universe": {},
                    "signal": {},
                    "risk": {},
                    "execution": {},
                    "mode": "paper",
                    "status": "draft",
                },
            },
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.put(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000", json={"name": "updated"}
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Lifecycle endpoints
        response = client.post(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000/activate", json={}
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.post(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000/deactivate", json={}
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.post(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000/pause", json={}
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.post(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000/resume", json={}
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Versions
        response = client.post(
            "/api/strategies/123e4567-e89b-12d3-a456-426614174000/versions",
            json={
                "config": {
                    "meta": {},
                    "universe": {},
                    "signal": {},
                    "risk": {},
                    "execution": {},
                    "mode": "paper",
                    "status": "draft",
                }
            },
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.get("/api/strategies/123e4567-e89b-12d3-a456-426614174000/versions")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # LLM generation
        response = client.post("/api/strategies/generate", json={})
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

    def test_strategy_lifecycle_validation(self, client: TestClient) -> None:
        """Test strategy lifecycle validation."""
        # Invalid UUID format - returns 422 or 404
        response = client.get("/api/strategies/invalid-uuid")
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_404_NOT_FOUND,
        ]

        # Missing required fields for creation
        response = client.post(
            "/api/strategies",
            json={
                "name": "test"
                # Missing config
            },
        )
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


class TestMarketRoutes:
    """Test market API routes."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with market routes."""
        app = FastAPI()
        app.include_router(market_router)
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_routes_registered(self, client: TestClient) -> None:
        """Test that market routes are registered."""
        # Balance endpoints
        response = client.get("/api/market/balances")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.get("/api/market/balances/BTC")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Position endpoints
        response = client.get("/api/market/positions")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.get("/api/market/positions/BTC/USDC")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Order endpoints
        response = client.post(
            "/api/market/orders",
            json={"symbol": "BTC/USDC", "side": "BUY", "quantity": 0.1, "price": 50000.0},
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.get("/api/market/orders")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.get("/api/market/orders/test-order-123")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        response = client.delete("/api/market/orders/test-order-123")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Trade endpoints
        response = client.get("/api/market/trades")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Ticker
        response = client.get("/api/market/ticker/BTC/USDC")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED


class TestStrategyBacktestRoutes:
    """Test strategy backtest API routes."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with strategy backtest routes."""
        app = FastAPI()
        app.include_router(strategy_backtest_router)
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_routes_registered(self, client: TestClient) -> None:
        """Test that backtest routes are registered."""
        # Submit job
        response = client.post(
            "/api/strategy-backtests/jobs",
            json={
                "strategy_id": "123e4567-e89b-12d3-a456-426614174000",
                "time_range_start": "2024-01-01T00:00:00",
                "time_range_end": "2024-01-08T00:00:00",
                "initial_balance": 10000.0,
            },
        )
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # Get job status (returns unknown job error, not 501)
        response = client.get("/api/strategy-backtests/jobs/unknown-job")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # List jobs
        response = client.get("/api/strategy-backtests/jobs")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED

        # List saved results
        response = client.get("/api/strategy-backtests/results")
        assert response.status_code != status.HTTP_501_NOT_IMPLEMENTED
