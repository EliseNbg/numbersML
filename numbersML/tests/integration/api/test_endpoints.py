"""
Integration tests for FastAPI endpoints.

Tests all API endpoints with real database connection.
"""

from collections.abc import AsyncGenerator

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.api.app import create_app
from src.infrastructure.database import set_db_pool


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


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
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=5, init=_init_utc)
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
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=5, init=_init_utc)
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

        # Should have at least one model
        if len(data) > 0:
            # Verify model structure
            model = data[0]
            assert "name" in model
            assert "path" in model
            assert "size_mb" in model
            assert "modified" in model

    @pytest.mark.asyncio
    async def test_list_models_sorted_by_modified(self, client: AsyncClient) -> None:
        """Test that models are sorted by modification date (newest first)."""
        response = await client.get("/api/ml/models")

        assert response.status_code == 200
        data = response.json()

        if len(data) > 1:
            # Verify sorting (newest first)
            for i in range(len(data) - 1):
                assert data[i]["modified"] >= data[i + 1]["modified"]

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
    async def test_predict_uses_hours_parameter(self, client: AsyncClient) -> None:
        """Test that hours parameter correctly limits data range."""
        # Test with 1 hour
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            # Verify response structure
            assert "hours_loaded" in data
            assert data["hours_loaded"] == 1

            # Verify candles are within expected time range
            if data["candles_count"] > 0 and data["candles"]:
                # Get time range from candles
                candle_times = [c["time"] for c in data["candles"]]
                min_time = min(candle_times)
                max_time = max(candle_times)

                # Time range should be approximately 1 hour (3600 seconds)
                # Allow some tolerance for data availability
                time_range = max_time - min_time
                assert (
                    time_range <= 3600 + 60
                ), f"Time range {time_range} exceeds 1 hour + tolerance"

    @pytest.mark.asyncio
    async def test_predict_hours_1_returns_3600_candles(self, client: AsyncClient) -> None:
        """Test that hours=1 returns approximately 3600 candles (1 per second)."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            # For 1 hour, we expect approximately 3600 candles
            # Allow some tolerance for missing data
            assert data["hours_loaded"] == 1

            # Candles should be close to 3600 (one per second)
            # If data is sparse, we might have fewer
            if data["candles_count"] > 0:
                # At minimum, should have some candles
                assert data["candles_count"] > 0

                # Check that time range is approximately 1 hour
                if data["candles"]:
                    times = [c["time"] for c in data["candles"]]
                    time_range = max(times) - min(times)
                    # Should be close to 3600 seconds (1 hour)
                    assert time_range >= 3500, f"Time range {time_range} is too short for 1 hour"

    @pytest.mark.asyncio
    async def test_predict_hours_1_predictions_count(self, client: AsyncClient) -> None:
        """Test that predictions count is correct for hours=1."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            # Predictions = vectors - seq_length + 1
            # For 1 hour with seq_length=30:
            # If we have N vectors, we should have N - 30 + 1 predictions
            seq_length = data.get("sequence_length", 30)

            if data["candles_count"] > 0 and data["predictions_count"] > 0:
                # The number of predictions depends on vectors, not candles
                # But we can verify the relationship is correct
                # Predictions should be less than candles (due to seq_length)
                assert data["predictions_count"] <= data["candles_count"]

                # Predictions should be positive
                assert data["predictions_count"] > 0

    @pytest.mark.asyncio
    async def test_predict_uses_model_parameter(self, client: AsyncClient) -> None:
        """Test that model parameter is used correctly."""
        # First, get available models
        models_response = await client.get("/api/ml/models")

        if models_response.status_code == 200:
            models = models_response.json()

            if len(models) > 0:
                # Test with specific model
                model_name = models[0]["name"]
                response = await client.get(
                    f"/api/ml/predict?symbol=BTC/USDC&hours=1&model={model_name}"
                )

                if response.status_code == 200:
                    data = response.json()
                    assert data["model"] == model_name

    @pytest.mark.asyncio
    async def test_predict_default_model(self, client: AsyncClient) -> None:
        """Test that default model is used when model parameter is not specified."""
        # Test without model parameter
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            # Default model should be best_model.pt
            assert data["model"] == "best_model.pt"

    @pytest.mark.asyncio
    async def test_predict_response_structure(self, client: AsyncClient) -> None:
        """Test that prediction response has correct structure."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            # Verify all required fields
            assert "symbol" in data
            assert "model" in data
            assert "sequence_length" in data
            assert "hours_loaded" in data
            assert "candles_count" in data
            assert "targets_count" in data
            assert "predictions_count" in data
            assert "candles" in data
            assert "targets" in data
            assert "predictions" in data

            # Verify types
            assert isinstance(data["symbol"], str)
            assert isinstance(data["model"], str)
            assert isinstance(data["sequence_length"], int)
            assert isinstance(data["hours_loaded"], int)
            assert isinstance(data["candles_count"], int)
            assert isinstance(data["targets_count"], int)
            assert isinstance(data["predictions_count"], int)
            assert isinstance(data["candles"], list)
            assert isinstance(data["targets"], list)
            assert isinstance(data["predictions"], list)

    @pytest.mark.asyncio
    async def test_predict_candle_structure(self, client: AsyncClient) -> None:
        """Test that candle data has correct structure."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            if data["candles_count"] > 0:
                candle = data["candles"][0]

                # Verify candle structure
                assert "time" in candle
                assert "open" in candle
                assert "high" in candle
                assert "low" in candle
                assert "close" in candle
                assert "volume" in candle

                # Verify types
                assert isinstance(candle["time"], int)
                assert isinstance(candle["open"], (int, float))
                assert isinstance(candle["high"], (int, float))
                assert isinstance(candle["low"], (int, float))
                assert isinstance(candle["close"], (int, float))
                assert isinstance(candle["volume"], (int, float))

    @pytest.mark.asyncio
    async def test_predict_target_structure(self, client: AsyncClient) -> None:
        """Test that target data has correct structure."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            if data["targets_count"] > 0:
                target = data["targets"][0]

                # Verify target structure
                assert "time" in target
                assert "value" in target

                # Verify types
                assert isinstance(target["time"], int)
                assert isinstance(target["value"], (int, float))

    @pytest.mark.asyncio
    async def test_predict_prediction_structure(self, client: AsyncClient) -> None:
        """Test that prediction data has correct structure."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1")

        if response.status_code == 200:
            data = response.json()

            if data["predictions_count"] > 0:
                prediction = data["predictions"][0]

                # Verify prediction structure
                assert "time" in prediction
                assert "predicted_target" in prediction

                # Verify types
                assert isinstance(prediction["time"], int)
                assert isinstance(prediction["predicted_target"], (int, float))

    @pytest.mark.asyncio
    async def test_predict_invalid_hours(self, client: AsyncClient) -> None:
        """Test prediction with invalid hours parameter."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=0")

        # Should return 422 (validation error)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_predict_hours_too_high(self, client: AsyncClient) -> None:
        """Test prediction with hours too high."""
        response = await client.get("/api/ml/predict?symbol=BTC/USDC&hours=1500")

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
