"""
Integration tests for pipeline API endpoints.

Tests:
- Pipeline start/stop
- Status endpoint
- Symbols endpoint
- Stats endpoint
"""

import pytest
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator

from src.infrastructure.api.app import create_app
from src.infrastructure.database import set_db_pool
from src.pipeline.service import PipelineManager, set_pipeline_manager
import asyncpg


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
    
    # Initialize pipeline manager
    pipeline_manager = PipelineManager(pool)
    set_pipeline_manager(pipeline_manager)
    
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        await pool.close()


class TestPipelineEndpoints:
    """Test pipeline API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_status(self, client: AsyncClient) -> None:
        """Test getting pipeline status."""
        response = await client.get("/api/pipeline/status")
        
        # Should return 200 (with data) or 503 (not initialized)
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            # Should have status fields
            assert 'is_running' in data or 'message' in data
    
    @pytest.mark.asyncio
    async def test_start_pipeline(self, client: AsyncClient) -> None:
        """Test starting pipeline."""
        response = await client.post("/api/pipeline/start")
        
        # Should return 200 (started), 400 (already running), or 503 (not initialized)
        assert response.status_code in [200, 400, 503]
        
        data = response.json()
        assert 'message' in data or 'detail' in data
    
    @pytest.mark.asyncio
    async def test_stop_pipeline(self, client: AsyncClient) -> None:
        """Test stopping pipeline."""
        response = await client.post("/api/pipeline/stop")
        
        # Should return 200 (stopped), 400 (not running), or 503 (not initialized)
        assert response.status_code in [200, 400, 503]
    
    @pytest.mark.asyncio
    async def test_get_symbols(self, client: AsyncClient) -> None:
        """Test getting active symbols."""
        response = await client.get("/api/pipeline/symbols")
        
        # Should return 200 (with data) or 503 (not initialized)
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            # Should return list
            assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_stats(self, client: AsyncClient) -> None:
        """Test getting detailed statistics."""
        response = await client.get("/api/pipeline/stats")
        
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
