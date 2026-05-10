"""
Integration tests for infrastructure repositories (Step 022.3).

Tests:
    - Repository initialization
    - Database queries with real database
    - CRUD operations

Requires: PostgreSQL running with test data
"""

import asyncpg
import pytest


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


from src.infrastructure.repositories.indicator_repo import IndicatorRepository
from src.infrastructure.repositories.pipeline_metrics_repo import PipelineMetricsRepository
from src.infrastructure.repositories.symbol_repo import SymbolRepository

# Test database URL
DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


class TestPipelineMetricsRepository:
    """Test PipelineMetricsRepository."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_init(self, db_pool: asyncpg.Pool) -> None:
        """Test repository initialization."""
        repo = PipelineMetricsRepository(db_pool)

        assert repo.db_pool is db_pool

    @pytest.mark.asyncio
    async def test_get_sla_metrics(self, db_pool: asyncpg.Pool) -> None:
        """Test fetching SLA metrics."""
        repo = PipelineMetricsRepository(db_pool)

        # Fetch metrics (may be empty if no data)
        metrics = await repo.get_sla_metrics(seconds=60)

        # Should return list (may be empty)
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_get_collector_pid(self, db_pool: asyncpg.Pool) -> None:
        """Test getting collector PID."""
        repo = PipelineMetricsRepository(db_pool)

        # May return None if collector not running
        pid = await repo.get_collector_pid()

        # Should return int or None
        assert pid is None or isinstance(pid, int)

    @pytest.mark.asyncio
    async def test_get_metrics_summary(self, db_pool: asyncpg.Pool) -> None:
        """Test getting metrics summary."""
        repo = PipelineMetricsRepository(db_pool)

        summary = await repo.get_metrics_summary(seconds=60)

        # Should return dict
        assert isinstance(summary, dict)


class TestSymbolRepository:
    """Test SymbolRepository."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.fixture
    async def test_symbol(self, db_pool: asyncpg.Pool):
        """Create test symbol."""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO symbols (symbol, base_asset, quote_asset, is_active, is_allowed)
                VALUES ($1, $2, $3, true, true)
                ON CONFLICT (symbol) DO UPDATE SET is_active = true
                RETURNING id
                """,
                "TEST/USDC",
                "TEST",
                "USDC",
            )

        yield row["id"] if row else None

        # Cleanup
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM symbols WHERE symbol = 'TEST/USDC'")

    @pytest.mark.asyncio
    async def test_init(self, db_pool: asyncpg.Pool) -> None:
        """Test repository initialization."""
        repo = SymbolRepository(db_pool)

        assert repo.db_pool is db_pool

    @pytest.mark.asyncio
    async def test_list_all(self, db_pool: asyncpg.Pool) -> None:
        """Test listing all symbols."""
        repo = SymbolRepository(db_pool)

        symbols = await repo.list_all()

        # Should return list
        assert isinstance(symbols, list)

    @pytest.mark.asyncio
    async def test_list_all_active_only(self, db_pool: asyncpg.Pool) -> None:
        """Test listing only active symbols."""
        repo = SymbolRepository(db_pool)

        symbols = await repo.list_all(active_only=True)

        # All returned symbols should be active
        for symbol in symbols:
            assert symbol.is_active is True

    @pytest.mark.asyncio
    async def test_get_by_id(self, db_pool: asyncpg.Pool, test_symbol: int) -> None:
        """Test getting symbol by ID."""
        repo = SymbolRepository(db_pool)

        symbol = await repo.get_by_id(test_symbol)

        assert symbol is not None
        assert symbol.symbol == "TEST/USDC"

    @pytest.mark.asyncio
    async def test_get_by_name(self, db_pool: asyncpg.Pool, test_symbol: int) -> None:
        """Test getting symbol by name."""
        repo = SymbolRepository(db_pool)

        symbol = await repo.get_by_name("TEST/USDC")

        assert symbol is not None
        assert symbol.symbol == "TEST/USDC"

    @pytest.mark.asyncio
    async def test_update_active(self, db_pool: asyncpg.Pool, test_symbol: int) -> None:
        """Test updating symbol active status."""
        repo = SymbolRepository(db_pool)

        # Deactivate
        result = await repo.update_active(test_symbol, False)
        assert result is True

        # Verify deactivated
        symbol = await repo.get_by_id(test_symbol)
        assert symbol is not None
        assert symbol.is_active is False

        # Reactivate
        result = await repo.update_active(test_symbol, True)
        assert result is True

        # Verify activated
        symbol = await repo.get_by_id(test_symbol)
        assert symbol is not None
        assert symbol.is_active is True

    @pytest.mark.asyncio
    async def test_count_active(self, db_pool: asyncpg.Pool) -> None:
        """Test counting active symbols."""
        repo = SymbolRepository(db_pool)

        count = await repo.count_active()

        # Should return non-negative integer
        assert count >= 0


class TestIndicatorRepository:
    """Test IndicatorRepository."""

    @pytest.fixture
    async def db_pool(self) -> asyncpg.Pool:
        """Create database pool."""
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5, init=_init_utc)
        yield pool
        await pool.close()

    @pytest.mark.asyncio
    async def test_init(self, db_pool: asyncpg.Pool) -> None:
        """Test repository initialization."""
        repo = IndicatorRepository(db_pool)

        assert repo.db_pool is db_pool

    @pytest.mark.asyncio
    async def test_list_all(self, db_pool: asyncpg.Pool) -> None:
        """Test listing all indicators."""
        repo = IndicatorRepository(db_pool)

        indicators = await repo.list_all()

        # Should return list
        assert isinstance(indicators, list)

    @pytest.mark.asyncio
    async def test_list_all_active_only(self, db_pool: asyncpg.Pool) -> None:
        """Test listing only active indicators."""
        repo = IndicatorRepository(db_pool)

        indicators = await repo.list_all(active_only=True)

        # All returned indicators should be active
        for indicator in indicators:
            assert indicator.is_active is True

    @pytest.mark.asyncio
    async def test_list_all_by_category(self, db_pool: asyncpg.Pool) -> None:
        """Test listing indicators by category."""
        repo = IndicatorRepository(db_pool)

        indicators = await repo.list_all(category="momentum")

        # All returned indicators should be momentum category
        for indicator in indicators:
            assert indicator.category == "momentum"

    @pytest.mark.asyncio
    async def test_get_categories(self, db_pool: asyncpg.Pool) -> None:
        """Test getting categories."""
        repo = IndicatorRepository(db_pool)

        categories = await repo.get_categories()

        # Should return list
        assert isinstance(categories, list)

    @pytest.mark.asyncio
    async def test_count(self, db_pool: asyncpg.Pool) -> None:
        """Test counting indicators."""
        repo = IndicatorRepository(db_pool)

        count = await repo.count()

        # Should return non-negative integer
        assert count >= 0
