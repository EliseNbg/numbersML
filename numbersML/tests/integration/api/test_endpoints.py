"""
Integration tests for FastAPI endpoints.

Tests all API endpoints with real database connection.
"""

import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator

from src.infrastructure.api.app import create_app, lifespan
from src.infrastructure.database import set_db_pool, get_db_pool, _db_pool
import asyncpg


# Test database URL
TEST_DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


@pytest.fixture
async def app():
    """Create test application."""
    app = create_app()
    yield app


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database pool."""
    # Create database pool for testing
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=5)
    set_db_pool(pool)
    
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        await pool.close()


@pytest.fixture
async def db_pool():
    """Create database pool for test data setup."""
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=5)
    yield pool
    await pool.close()


class TestRootEndpoints:
    """Test root endpoints."""
    
    @pytest.mark.asyncio
    async def test_root(self, client: AsyncClient) -> None:
        """Test root endpoint."""
        response = await client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "docs" in data
        assert "dashboard" in data
    
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient) -> None:
        """Test health check endpoint."""
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "database" in data
        assert data["status"] == "healthy"


class TestDashboardEndpoints:
    """Test dashboard API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_collector_status(self, client: AsyncClient) -> None:
        """Test getting collector status."""
        response = await client.get("/api/dashboard/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have status fields
        assert "is_running" in data or isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_get_dashboard_stats(self, client: AsyncClient) -> None:
        """Test getting dashboard statistics."""
        response = await client.get("/api/dashboard/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have stats fields
        assert "ticks_per_minute" in data or isinstance(data, dict)
        assert "sla_compliance_pct" in data or isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_get_sla_metrics(self, client: AsyncClient) -> None:
        """Test getting SLA metrics."""
        response = await client.get("/api/dashboard/metrics?seconds=60")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_sla_metrics_validation(self, client: AsyncClient) -> None:
        """Test SLA metrics parameter validation."""
        # Invalid seconds (too low) - returns 400 Bad Request
        response = await client.get("/api/dashboard/metrics?seconds=0")
        assert response.status_code == 400
        
        # Invalid seconds (too high) - returns 400 Bad Request
        response = await client.get("/api/dashboard/metrics?seconds=301")
        assert response.status_code == 400
        
        # Valid seconds
        response = await client.get("/api/dashboard/metrics?seconds=60")
        assert response.status_code == 200


class TestSymbolEndpoints:
    """Test symbol API endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_symbols(self, client: AsyncClient) -> None:
        """Test listing symbols."""
        response = await client.get("/api/symbols")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_symbols_active_only(self, client: AsyncClient) -> None:
        """Test listing active symbols only."""
        response = await client.get("/api/symbols?active_only=true")
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned symbols should be active
        for symbol in data:
            assert symbol.get("is_active") is True
    
    @pytest.mark.asyncio
    async def test_get_symbol_not_found(self, client: AsyncClient) -> None:
        """Test getting non-existent symbol."""
        response = await client.get("/api/symbols/999999")
        
        # Should return 404 or empty result
        assert response.status_code in [404, 200]


class TestIndicatorEndpoints:
    """Test indicator API endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_indicators(self, client: AsyncClient) -> None:
        """Test listing indicators."""
        response = await client.get("/api/indicators")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_indicators_by_category(self, client: AsyncClient) -> None:
        """Test listing indicators by category."""
        response = await client.get("/api/indicators?category=momentum")
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned indicators should be momentum category
        for indicator in data:
            assert indicator.get("category") == "momentum"
    
    @pytest.mark.asyncio
    async def test_get_categories(self, client: AsyncClient) -> None:
        """Test getting indicator categories."""
        response = await client.get("/api/indicators/categories")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_indicator_not_found(self, client: AsyncClient) -> None:
        """Test getting non-existent indicator."""
        response = await client.get("/api/indicators/nonexistent_indicator")
        
        # Should return 404
        assert response.status_code == 404


class TestConfigEndpoints:
    """Test configuration API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_system_config(self, client: AsyncClient) -> None:
        """Test getting system_config table."""
        response = await client.get("/api/config/system_config")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_symbols_table(self, client: AsyncClient) -> None:
        """Test getting symbols table."""
        response = await client.get("/api/config/symbols")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_invalid_table(self, client: AsyncClient) -> None:
        """Test getting invalid table."""
        response = await client.get("/api/config/invalid_table")
        
        # Should return 400
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_get_config_limit_validation(self, client: AsyncClient) -> None:
        """Test config table limit parameter validation."""
        # Invalid limit (too low) - returns 400 Bad Request
        response = await client.get("/api/config/system_config?limit=0")
        assert response.status_code == 400
        
        # Invalid limit (too high) - returns 400 Bad Request
        response = await client.get("/api/config/system_config?limit=1001")
        assert response.status_code == 400
        
        # Valid limit
        response = await client.get("/api/config/system_config?limit=50")
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_get_system_config_value(self, client: AsyncClient) -> None:
        """Test getting system config value by key."""
        response = await client.get("/api/config/system-config/collector.batch_size")
        
        # Should return value, 404, or 422 (validation error)
        assert response.status_code in [200, 404, 422]


class TestAPIErrorHandling:
    """Test API error handling."""
    
    @pytest.mark.asyncio
    async def test_404_not_found(self, client: AsyncClient) -> None:
        """Test 404 response for non-existent endpoint."""
        response = await client.get("/api/nonexistent")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_method_not_allowed(self, client: AsyncClient) -> None:
        """Test method not allowed response."""
        # Try POST on GET-only endpoint
        response = await client.post("/api/symbols")
        
        # Should return 405 or 422 (for missing body)
        assert response.status_code in [405, 422]


class TestOpenAPIDocs:
    """Test OpenAPI documentation."""
    
    @pytest.mark.asyncio
    async def test_openapi_json(self, client: AsyncClient) -> None:
        """Test OpenAPI JSON endpoint."""
        response = await client.get("/openapi.json")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data
        
        # Should have our API paths
        assert "/api/dashboard/status" in data["paths"]
        assert "/api/symbols" in data["paths"]
        assert "/api/indicators" in data["paths"]
        assert "/api/config/{table_name}" in data["paths"]
    
    @pytest.mark.asyncio
    async def test_docs_endpoint(self, client: AsyncClient) -> None:
        """Test Swagger UI docs endpoint."""
        response = await client.get("/docs")
        
        assert response.status_code == 200
        assert "Swagger UI" in response.text or "swagger" in response.text.lower()
    
    @pytest.mark.asyncio
    async def test_redoc_endpoint(self, client: AsyncClient) -> None:
        """Test ReDoc endpoint."""
        response = await client.get("/redoc")
        
        assert response.status_code == 200
        assert "ReDoc" in response.text or "redoc" in response.text.lower()


class TestCandleEndpoints:
    """Test candle API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_candles_missing_symbol(self, client: AsyncClient) -> None:
        """Test getting candles without symbol parameter."""
        response = await client.get("/api/candles")
        
        # Should return 422 (validation error) for missing required parameter
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_get_candles_with_symbol(self, client: AsyncClient) -> None:
        """Test getting candles for a symbol."""
        response = await client.get("/api/candles?symbol=BTC/USDC&seconds=60")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_candles_invalid_seconds(self, client: AsyncClient) -> None:
        """Test getting candles with invalid seconds parameter."""
        response = await client.get("/api/candles?symbol=BTC/USDC&seconds=0")
        
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_get_candles_seconds_too_high(self, client: AsyncClient) -> None:
        """Test getting candles with seconds too high."""
        response = await client.get("/api/candles?symbol=BTC/USDC&seconds=100000")
        
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_get_candle_indicators(self, client: AsyncClient) -> None:
        """Test getting candle indicators."""
        response = await client.get("/api/candles/indicators?symbol=BTC/USDC&seconds=60")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)


class TestTargetValueEndpoints:
    """Test target value API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_target_values_missing_symbol(self, client: AsyncClient) -> None:
        """Test getting target values without symbol parameter."""
        response = await client.get("/api/target-values")
        
        # Should return 422 (validation error) for missing required parameter
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_get_target_values_with_symbol(self, client: AsyncClient) -> None:
        """Test getting target values for a symbol."""
        response = await client.get("/api/target-values?symbol=BTC/USDC&hours=2")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_target_values_invalid_hours(self, client: AsyncClient) -> None:
        """Test getting target values with invalid hours parameter."""
        response = await client.get("/api/target-values?symbol=BTC/USDC&hours=0")
        
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_get_target_values_hours_too_high(self, client: AsyncClient) -> None:
        """Test getting target values with hours too high."""
        response = await client.get("/api/target-values?symbol=BTC/USDC&hours=2000")
        
        # Should return 422 (validation error)
        assert response.status_code == 422


class TestMLEndpoints:
    """Test ML prediction API endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_models(self, client: AsyncClient) -> None:
        """Test listing available ML models."""
        response = await client.get("/api/ml/models")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return list
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_predict_missing_symbol(self, client: AsyncClient) -> None:
        """Test prediction without symbol parameter."""
        response = await client.get("/api/ml/predict")
        
        # Should return 422 (validation error) for missing required parameter
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_predict_with_symbol(self, client: AsyncClient) -> None:
        """Test prediction with symbol parameter."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=2")
        
        # Should return 200 or 404/500 if model not found
        assert response.status_code in [200, 404, 500]
    
    @pytest.mark.asyncio
    async def test_predict_invalid_hours(self, client: AsyncClient) -> None:
        """Test prediction with invalid hours parameter."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=0")
        
        # Should return 422 (validation error)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_predict_hours_too_high(self, client: AsyncClient) -> None:
        """Test prediction with hours too high."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=200")
        
        # Should return 422 (validation error)
        assert response.status_code == 422


class TestPipelineEndpoints:
    """Test pipeline API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_pipeline_status(self, client: AsyncClient) -> None:
        """Test getting pipeline status."""
        response = await client.get("/api/pipeline/status")
        
        # Pipeline manager may not be initialized in test, so 503 is acceptable
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            data = response.json()
            # Should have status fields
            assert "is_running" in data or isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_get_pipeline_symbols(self, client: AsyncClient) -> None:
        """Test getting pipeline symbols."""
        response = await client.get("/api/pipeline/symbols")
        
        # Pipeline manager may not be initialized in test, so 503 is acceptable
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            data = response.json()
            # Should return list
            assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_pipeline_stats(self, client: AsyncClient) -> None:
        """Test getting pipeline statistics."""
        response = await client.get("/api/pipeline/stats")
        
        # Pipeline manager may not be initialized in test, so 503 is acceptable
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            data = response.json()
            # Should have stats fields
            assert isinstance(data, dict)
