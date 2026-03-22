"""
Tests for EnrichmentWaiter utility.

Tests the synchronization mechanism that waits for enrichment
to complete before generating wide vectors.

Note: These tests require a database connection and are skipped
when running in CI without PostgreSQL infrastructure.
"""

import pytest
import asyncio
import asyncpg
import json
from datetime import datetime, timezone
from typing import List

from src.application.services.enrichment_waiter import EnrichmentWaiter, wait_for_enrichment


# Test database URL
DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


@pytest.mark.skip(reason="Requires database connection - run locally or in integration tests")
class TestEnrichmentWaiter:
    """Test EnrichmentWaiter class."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
        yield pool
        await pool.close()

    @pytest.fixture
    def waiter(self, db_pool: asyncpg.Pool) -> EnrichmentWaiter:
        """Create EnrichmentWaiter instance."""
        return EnrichmentWaiter(db_pool, DB_URL, timeout=5.0)

    @pytest.mark.asyncio
    async def test_waiter_initialization(self, waiter: EnrichmentWaiter) -> None:
        """Test waiter initializes correctly."""
        assert waiter.timeout == 5.0
        assert waiter.db_pool is not None

    @pytest.mark.asyncio
    async def test_wait_for_empty_symbol_list(
        self,
        waiter: EnrichmentWaiter,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test waiting for empty symbol list returns True."""
        async with db_pool.acquire() as conn:
            result = await waiter.wait_for_enrichment([])
            assert result is True

    @pytest.mark.asyncio
    async def test_get_latest_ticks(
        self,
        waiter: EnrichmentWaiter,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test getting latest ticks for symbols."""
        # Get some real symbol IDs from database
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM symbols WHERE is_active = true LIMIT 3"
            )
            symbol_ids = [row['id'] for row in rows]

            if symbol_ids:
                ticks = await waiter._get_latest_ticks(conn, symbol_ids)
                # Should return set of (symbol_id, time) tuples
                assert isinstance(ticks, set)
                # Each tuple should have 2 elements
                for item in ticks:
                    assert len(item) == 2

    @pytest.mark.asyncio
    async def test_wait_for_nonexistent_symbols(
        self,
        waiter: EnrichmentWaiter
    ) -> None:
        """Test waiting for nonexistent symbols."""
        # Use invalid symbol IDs - returns True because no ticks found
        result = await waiter.wait_for_enrichment([999999, 999998])
        # Returns True when no ticks found (nothing to wait for)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_enrichment_status(
        self,
        waiter: EnrichmentWaiter,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test getting enrichment status."""
        status = await waiter.get_enrichment_status()

        assert isinstance(status, dict)
        assert 'total_ticks' in status
        assert 'enriched_ticks' in status
        assert 'enrichment_rate_pct' in status
        assert 'timestamp' in status

        # Rate should be between 0 and 100
        assert 0 <= status['enrichment_rate_pct'] <= 100

    @pytest.mark.asyncio
    async def test_wait_for_single_enrichment(
        self,
        waiter: EnrichmentWaiter,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test waiting for single symbol enrichment."""
        # Get a real symbol ID
        async with db_pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT id FROM symbols WHERE is_active = true LIMIT 1"
            )

            if row:
                result = await waiter.wait_for_single_enrichment(row)
                # Result depends on whether enrichment is running
                assert isinstance(result, bool)


class TestEnrichmentWaiterIntegration:
    """Integration tests for EnrichmentWaiter with real notifications."""

    @pytest.mark.skip(reason="Requires database connection - run locally or in integration tests")
    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_wait_receives_notification(
        self,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test that waiter receives enrichment_complete notifications."""
        # This test simulates the enrichment complete notification
        waiter = EnrichmentWaiter(db_pool, DB_URL, timeout=3.0)

        # Get a test symbol
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT symbol_id, time FROM ticker_24hr_stats
                WHERE symbol_id IN (SELECT id FROM symbols WHERE is_active = true)
                ORDER BY time DESC
                LIMIT 1
                """
            )

            if not row:
                pytest.skip("No ticker data available")

            symbol_id = row['symbol_id']
            tick_time = str(row['time'])

            # Start waiting in background
            async def wait_and_notify():
                # Wait for enrichment
                wait_task = asyncio.create_task(
                    waiter.wait_for_enrichment([symbol_id])
                )

                # Wait a bit then send notification
                await asyncio.sleep(0.5)

                # Send notification
                await conn.execute(
                    "SELECT pg_notify('enrichment_complete', $1)",
                    json.dumps({
                        'symbol_id': symbol_id,
                        'time': tick_time,
                        'processed_at': datetime.utcnow().isoformat()
                    })
                )

                # Wait for result
                return await wait_task

            result = await wait_and_notify()
            # Should receive notification and return True
            assert result is True


@pytest.mark.skip(reason="Requires database connection - run locally or in integration tests")
class TestWaitForEnrichmentFunction:
    """Test the convenience function."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_convenience_function(
        self,
        db_pool: asyncpg.Pool
    ) -> None:
        """Test wait_for_enrichment convenience function."""
        # Just test that the function can be called without error
        # Result depends on whether symbols exist and are enriched
        result = await wait_for_enrichment(
            db_pool,
            DB_URL,
            symbol_ids=[],  # Empty list returns True immediately
            timeout=1.0
        )
        assert result is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
