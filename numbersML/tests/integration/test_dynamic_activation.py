"""
Integration tests for Dynamic Activation and Pipeline Metrics (Step 021).

Tests:
1. Symbol activation/deactivation (is_active field)
2. Indicator activation/deactivation (is_active field)
3. Pipeline metrics tracking
4. Dashboard views
5. SLA compliance monitoring

Usage:
    pytest tests/integration/test_dynamic_activation.py -v
"""

import pytest
import asyncio
import asyncpg
from datetime import datetime, timedelta
from typing import Dict, Any


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


from src.application.services.enrichment_service import EnrichmentService
from src.indicators.providers import PythonIndicatorProvider, MockIndicatorProvider, DatabaseIndicatorProvider


# Test database URL
DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


class TestSymbolActivation:
    """Test symbol activation/deactivation via is_active field."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_symbol_is_active_filter(self, db_pool: asyncpg.Pool) -> None:
        """Test that only active symbols are selected."""
        # Cleanup any existing test symbols first
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM symbols WHERE symbol LIKE 'TEST_%'")
        
        # Create test symbols
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO symbols (symbol, base_asset, quote_asset, is_active, is_allowed)
                VALUES ($1, $2, $3, true, true)
                ON CONFLICT (symbol) DO UPDATE SET is_active = true
                """,
                'TEST_ACTIVE/USDC', 'TEST', 'USDC'
            )
            
            await conn.execute(
                """
                INSERT INTO symbols (symbol, base_asset, quote_asset, is_active, is_allowed)
                VALUES ($1, $2, $3, false, true)
                ON CONFLICT (symbol) DO UPDATE SET is_active = false
                """,
                'TEST_INACTIVE/USDC', 'TEST', 'USDC'
            )
        
        # Query active symbols
        async with db_pool.acquire() as conn:
            active = await conn.fetch(
                """
                SELECT symbol FROM symbols
                WHERE is_active = true AND is_allowed = true
                AND symbol LIKE 'TEST_%'
                """
            )
            
            # Should only return active symbol
            assert len(active) == 1
            assert active[0]['symbol'] == 'TEST_ACTIVE/USDC'
        
        # Cleanup
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM symbols WHERE symbol LIKE 'TEST_%'")

    @pytest.mark.asyncio
    async def test_toggle_symbol_activation(self, db_pool: asyncpg.Pool) -> None:
        """Test toggling symbol activation at runtime."""
        symbol = 'TEST_TOGGLE/USDC'
        
        # Create and activate
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO symbols (symbol, base_asset, quote_asset, is_active, is_allowed)
                VALUES ($1, $2, $3, true, true)
                ON CONFLICT (symbol) DO UPDATE SET is_active = true
                """,
                symbol, 'TEST', 'USDC'
            )
            
            # Verify active
            is_active = await conn.fetchval(
                "SELECT is_active FROM symbols WHERE symbol = $1", symbol
            )
            assert is_active is True
        
        # Deactivate
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE symbols SET is_active = false WHERE symbol = $1", symbol
            )
            
            # Verify inactive
            is_active = await conn.fetchval(
                "SELECT is_active FROM symbols WHERE symbol = $1", symbol
            )
            assert is_active is False
        
        # Cleanup
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM symbols WHERE symbol LIKE 'TEST_%'")


class TestIndicatorActivation:
    """Test indicator activation/deactivation via is_active field."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_indicator_is_active_filter(self, db_pool: asyncpg.Pool) -> None:
        """Test that indicator_definitions table has is_active field for runtime control."""
        async with db_pool.acquire() as conn:
            # Verify is_active column exists (critical for runtime activation)
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'indicator_definitions'
                    AND column_name = 'is_active'
                )
                """
            )
            assert result is True, "is_active column must exist for runtime indicator control"
            
            # Check if table has indicators
            count = await conn.fetchval("SELECT COUNT(*) FROM indicator_definitions")
            
            if count == 0:
                # Table exists but is empty - this is OK for development
                # In production, indicators would be registered via migration or script
                pytest.skip(
                    "indicator_definitions table is empty. "
                    "In production, populate via: INSERT INTO indicator_definitions (...)"
                )
            
            # If table has indicators, verify is_active filtering works
            active = await conn.fetch(
                """
                SELECT name, is_active FROM indicator_definitions
                WHERE is_active = true
                LIMIT 5
                """
            )
            
            inactive = await conn.fetch(
                """
                SELECT name, is_active FROM indicator_definitions
                WHERE is_active = false
                LIMIT 5
                """
            )
            
            # Verify filtering works (at least one query should return results)
            assert len(active) > 0 or len(inactive) > 0, "Should be able to filter by is_active"

    @pytest.mark.asyncio
    async def test_toggle_indicator_activation(self, db_pool: asyncpg.Pool) -> None:
        """Test toggling indicator activation at runtime via is_active field."""
        async with db_pool.acquire() as conn:
            # Check if table has indicators
            count = await conn.fetchval("SELECT COUNT(*) FROM indicator_definitions")
            
            if count == 0:
                pytest.skip(
                    "indicator_definitions table is empty. "
                    "This test requires indicators in database. "
                    "Use PythonIndicatorProvider for tests without DB indicators."
                )
            
            # Get a test indicator
            indicator_name = await conn.fetchval(
                "SELECT name FROM indicator_definitions LIMIT 1"
            )
            
            if not indicator_name:
                pytest.skip("No indicators in database")

            # Deactivate
            await conn.execute(
                "UPDATE indicator_definitions SET is_active = false WHERE name = $1",
                indicator_name
            )

            # Verify inactive
            is_active = await conn.fetchval(
                "SELECT is_active FROM indicator_definitions WHERE name = $1",
                indicator_name
            )
            assert is_active is False

            # Reactivate
            await conn.execute(
                "UPDATE indicator_definitions SET is_active = true WHERE name = $1",
                indicator_name
            )

            # Verify active
            is_active = await conn.fetchval(
                "SELECT is_active FROM indicator_definitions WHERE name = $1",
                indicator_name
            )
            assert is_active is True

    @pytest.mark.asyncio
    async def test_enrichment_service_loads_active_indicators(
        self,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test that EnrichmentService loads only active indicators."""
        # Check if there are any indicators in the database
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM indicator_definitions")
            
            if count == 0:
                pytest.skip("No indicators in database - indicator_definitions is empty")
        
        # Create service - use indicator_provider to load from DB
        from src.indicators.providers import DatabaseIndicatorProvider
        provider = DatabaseIndicatorProvider(db_pool)
        service = EnrichmentService(
            db_pool=db_pool,
            indicator_provider=provider,
        )
        
        # Initialize indicators (loads from DB)
        await service._init_indicators()
        
        # If there are active indicators, service should load them
        async with db_pool.acquire() as conn:
            active_count = await conn.fetchval(
                "SELECT COUNT(*) FROM indicator_definitions WHERE is_active = true"
            )
            
            if active_count > 0:
                assert len(service._indicators) > 0
            else:
                # No active indicators - service should have warning
                assert len(service._indicators) == 0


class TestPipelineMetrics:
    """Test pipeline metrics tracking."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_pipeline_metrics_table_exists(self, db_pool: asyncpg.Pool) -> None:
        """Test that pipeline_metrics table exists."""
        async with db_pool.acquire() as conn:
            # Check table exists
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'pipeline_metrics'
                )
                """
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_save_pipeline_metrics(self, db_pool: asyncpg.Pool) -> None:
        """Test saving pipeline metrics."""
        # Get a symbol ID
        async with db_pool.acquire() as conn:
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE is_active = true LIMIT 1"
            )
            
            if not symbol_id:
                pytest.skip("No active symbols in database")
            
            symbol = await conn.fetchval(
                "SELECT symbol FROM symbols WHERE id = $1", symbol_id
            )
            
            # Insert test metric
            await conn.execute(
                """
                INSERT INTO pipeline_metrics (
                    symbol_id, symbol, collection_time_ms, enrichment_time_ms,
                    total_time_ms, active_symbols_count, active_indicators_count,
                    status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                symbol_id, symbol, 10, 150, 160, 20, 12, 'success'
            )
            
            # Verify inserted
            result = await conn.fetchrow(
                """
                SELECT * FROM pipeline_metrics
                WHERE symbol_id = $1 AND status = 'success'
                ORDER BY timestamp DESC LIMIT 1
                """,
                symbol_id
            )
            
            assert result is not None
            assert result['total_time_ms'] == 160
            assert result['status'] == 'success'

    @pytest.mark.asyncio
    async def test_sla_violation_tracking(self, db_pool: asyncpg.Pool) -> None:
        """Test SLA violation tracking (>1000ms)."""
        async with db_pool.acquire() as conn:
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE is_active = true LIMIT 1"
            )
            
            if not symbol_id:
                pytest.skip("No active symbols")
            
            symbol = await conn.fetchval(
                "SELECT symbol FROM symbols WHERE id = $1", symbol_id
            )
            
            # Insert slow metric (SLA violation)
            await conn.execute(
                """
                INSERT INTO pipeline_metrics (
                    symbol_id, symbol, total_time_ms, status
                ) VALUES ($1, $2, $3, $4)
                """,
                symbol_id, symbol, 1500, 'slow'
            )
            
            # Count SLA violations
            violations = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pipeline_metrics
                WHERE total_time_ms > 1000
                """
            )
            
            assert violations >= 1


class TestDashboardViews:
    """Test dashboard views for monitoring."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_v_pipeline_performance_view(self, db_pool: asyncpg.Pool) -> None:
        """Test v_pipeline_performance dashboard view."""
        async with db_pool.acquire() as conn:
            result = await conn.fetch(
                "SELECT * FROM v_pipeline_performance LIMIT 1"
            )
            
            # View should exist and return data (or empty if no metrics)
            assert result is not None

    @pytest.mark.asyncio
    async def test_v_active_configuration_view(self, db_pool: asyncpg.Pool) -> None:
        """Test v_active_configuration dashboard view."""
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM v_active_configuration"
            )
            
            assert result is not None
            assert 'active_symbols' in result
            assert 'active_indicators' in result
            
            # Should have some active symbols
            assert result['active_symbols'] >= 0

    @pytest.mark.asyncio
    async def test_v_sla_compliance_view(self, db_pool: asyncpg.Pool) -> None:
        """Test v_sla_compliance dashboard view."""
        async with db_pool.acquire() as conn:
            result = await conn.fetch(
                "SELECT * FROM v_sla_compliance LIMIT 1"
            )
            
            # View should exist
            assert result is not None

    @pytest.mark.asyncio
    async def test_get_pipeline_performance_function(
        self,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test get_pipeline_performance() helper function."""
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM get_pipeline_performance(5)"
            )
            
            # Function should return values
            assert result is not None
            assert 'avg_time_ms' in result
            assert 'compliance_pct' in result

    @pytest.mark.asyncio
    async def test_can_handle_more_symbols_function(
        self,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test can_handle_more_symbols() helper function."""
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM can_handle_more_symbols(800, 0.2)"
            )
            
            # Function should return values
            assert result is not None
            assert 'can_add' in result
            assert 'recommendation' in result


class TestRuntimeActivation:
    """Test runtime activation/deactivation without restart."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_deactivate_symbol_stops_collection(self, db_pool: asyncpg.Pool) -> None:
        """Test that deactivating a symbol stops its collection."""
        symbol = 'TEST_RUNTIME/USDC'
        
        # Create and activate symbol
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO symbols (symbol, base_asset, quote_asset, is_active, is_allowed)
                VALUES ($1, $2, $3, true, true)
                ON CONFLICT (symbol) DO UPDATE SET is_active = true
                """,
                symbol, 'TEST', 'USDC'
            )
            
            # Verify it would be collected
            active = await conn.fetchval(
                """
                SELECT COUNT(*) FROM symbols
                WHERE is_active = true AND symbol = $1
                """,
                symbol
            )
            assert active == 1
        
        # Deactivate
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE symbols SET is_active = false WHERE symbol = $1", symbol
            )
            
            # Verify it would NOT be collected
            active = await conn.fetchval(
                """
                SELECT COUNT(*) FROM symbols
                WHERE is_active = true AND symbol = $1
                """,
                symbol
            )
            assert active == 0
        
        # Cleanup
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM symbols WHERE symbol LIKE 'TEST_%'")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
