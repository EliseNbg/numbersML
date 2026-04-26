"""Integration tests for StrategyBacktestRepositoryPG against real PostgreSQL."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid

import asyncpg
import pytest

from src.infrastructure.repositories.strategy_backtest_repository_pg import (
    StrategyBacktestRepositoryPG,
)

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


async def _init_utc(conn: asyncpg.Connection) -> None:
    await conn.execute("SET timezone = 'UTC'")


async def _ensure_phase3_schema(conn: asyncpg.Connection) -> None:
    migration_path = (
        Path(__file__).resolve().parents[3] / "migrations" / "003_phase3_strategy_foundation.sql"
    )
    await conn.execute(migration_path.read_text(encoding="utf-8"))


@pytest.mark.integration
class TestStrategyBacktestRepositoryPGIntegration:
    """Repository integration tests with actual database."""

    @pytest.fixture
    async def db_conn(self) -> asyncpg.Connection:
        try:
            conn = await asyncpg.connect(DB_URL)
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable for integration test: {exc}")
        await _init_utc(conn)
        await _ensure_phase3_schema(conn)
        yield conn
        await conn.close()

    @pytest.fixture
    async def test_strategy_id(self, db_conn: asyncpg.Connection) -> uuid.UUID:
        """Create a test strategy and return its ID."""
        strategy_id = uuid.uuid4()
        await db_conn.execute(
            """
            INSERT INTO strategies (id, name, description, mode, status, created_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            strategy_id,
            f"test_strat_{uuid.uuid4().hex[:8]}",
            "test strategy",
            "paper",
            "draft",
            "pytest",
        )
        yield strategy_id
        await db_conn.execute("DELETE FROM strategies WHERE id = $1", strategy_id)

    @pytest.fixture
    async def test_strategy_version(
        self, db_conn: asyncpg.Connection, test_strategy_id: uuid.UUID
    ) -> int:
        """Create a test strategy version and return its version number."""
        await db_conn.execute(
            """
            INSERT INTO strategy_versions (strategy_id, version, schema_version, config, created_by)
            VALUES ($1, 1, 1, $2, 'pytest')
            """,
            test_strategy_id,
            '{"meta": {"name": "test"}}',
        )
        yield 1
        await db_conn.execute(
            "DELETE FROM strategy_versions WHERE strategy_id = $1", test_strategy_id
        )

    @pytest.mark.asyncio
    async def test_save_and_get_backtest(
        self,
        db_conn: asyncpg.Connection,
        test_strategy_id: uuid.UUID,
        test_strategy_version: int,
    ) -> None:
        """Test saving and retrieving a backtest result."""
        repo = StrategyBacktestRepositoryPG(db_conn)
        strategy_version_id = uuid.uuid4()  # Will get actual from DB below

        # Get actual version_id
        row = await db_conn.fetchrow(
            "SELECT id FROM strategy_versions WHERE strategy_id = $1 AND version = $2",
            test_strategy_id,
            test_strategy_version,
        )
        strategy_version_id = row["id"]

        backtest_id = uuid.uuid4()
        time_start = datetime.now(timezone.utc) - timedelta(days=7)
        time_end = datetime.now(timezone.utc)

        saved = await repo.save(
            strategy_id=test_strategy_id,
            strategy_version_id=strategy_version_id,
            time_range_start=time_start,
            time_range_end=time_end,
            initial_balance=10000.0,
            final_balance=10500.0,
            metrics={
                "total_trades": 50,
                "win_rate": 0.6,
                "total_return": 0.05,
                "profit_factor": 1.5,
                "max_drawdown": 0.02,
                "sharpe_ratio": 1.2,
            },
            trades=[
                {"entry_time": time_start, "exit_time": time_end, "pnl": 0.01},
            ],
            equity_curve=[
                {"time": time_start, "balance": 10000.0},
                {"time": time_end, "balance": 10500.0},
            ],
            metadata={"test_run": True},
            created_by="pytest",
        )

        assert "id" in saved
        assert saved["strategy_id"] == test_strategy_id
        assert saved["initial_balance"] == 10000.0
        assert saved["final_balance"] == 10500.0
        assert saved["metrics"]["total_return"] == 0.05

        retrieved = await repo.get(saved["id"])
        assert retrieved is not None
        assert retrieved["id"] == saved["id"]
        assert retrieved["strategy_id"] == test_strategy_id
        assert retrieved["metrics"]["total_return"] == 0.05


        # Cleanup
        await db_conn.execute(
            "DELETE FROM strategy_backtests WHERE strategy_id = $1",
            test_strategy_id,
        )

    @pytest.mark.asyncio
    async def test_list_for_strategy(
        self,
        db_conn: asyncpg.Connection,
        test_strategy_id: uuid.UUID,
        test_strategy_version: int,
    ) -> None:
        """Test listing backtests for a strategy."""
        repo = StrategyBacktestRepositoryPG(db_conn)

        row = await db_conn.fetchrow(
            "SELECT id FROM strategy_versions WHERE strategy_id = $1 AND version = $2",
            test_strategy_id,
            test_strategy_version,
        )
        strategy_version_id = row["id"]

        time_start = datetime.now(timezone.utc) - timedelta(days=7)
        time_end = datetime.now(timezone.utc)

        # Save multiple backtests
        for i in range(3):
            await repo.save(
                strategy_id=test_strategy_id,
                strategy_version_id=strategy_version_id,
                time_range_start=time_start,
                time_range_end=time_end,
                initial_balance=10000.0 + i * 1000,
                final_balance=10500.0 + i * 1000,
                metrics={"total_return": 0.05 + i * 0.01},
                trades=[],
                equity_curve=[],
                created_by="pytest",
            )

        backtests = await repo.list_for_strategy(test_strategy_id, limit=10)
        assert len(backtests) >= 3
        assert backtests[0]["strategy_id"] == test_strategy_id
        # Most recent first
        assert backtests[0]["initial_balance"] >= backtests[-1]["initial_balance"]

        # Cleanup
        await db_conn.execute(
            "DELETE FROM strategy_backtests WHERE strategy_id = $1",
            test_strategy_id,
        )
