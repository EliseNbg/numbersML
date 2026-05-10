"""Unit tests for StrategyRepositoryPG."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.strategies.strategy_config import StrategyDefinition
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG


class MockConnection:
    """Mock asyncpg connection that supports async context manager."""

    def __init__(self, mock_conn: AsyncMock):
        self._conn = mock_conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def create_mock_pool(connection: AsyncMock) -> MagicMock:
    """Create a mock pool whose acquire() returns an async context manager yielding the given connection."""
    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield connection

    pool.acquire = MagicMock(side_effect=_acquire)
    return pool


@pytest.fixture
def mock_connection() -> AsyncMock:
    """Build a mocked asyncpg connection."""
    conn = AsyncMock()
    return conn


@pytest.fixture
def mock_pool(mock_connection: AsyncMock) -> MagicMock:
    """Build a mocked asyncpg pool that yields the mock connection."""
    return create_mock_pool(mock_connection)


class TestStrategyRepositoryPG:
    """Validate repository behavior against mocked asyncpg connection."""

    @pytest.mark.asyncio
    async def test_save_and_get_by_id(
        self, mock_pool: MagicMock, mock_connection: AsyncMock
    ) -> None:
        strategy_id = uuid4()
        now = datetime.now(UTC)
        row = {
            "id": strategy_id,
            "name": "test_strategy",
            "description": "example",
            "mode": "paper",
            "status": "draft",
            "current_version": 1,
            "created_by": "tester",
            "created_at": now,
            "updated_at": now,
        }
        mock_connection.fetchrow.return_value = row

        repo = StrategyRepositoryPG(mock_pool)
        saved = await repo.save(
            StrategyDefinition(
                id=strategy_id,
                name="test_strategy",
                description="example",
                mode="paper",
                status="draft",
                current_version=1,
                created_by="tester",
                created_at=now,
                updated_at=now,
            )
        )
        fetched = await repo.get_by_id(strategy_id)

        assert saved.id == strategy_id
        assert fetched is not None
        assert fetched.name == "test_strategy"
        # Verify acquire was called
        assert mock_pool.acquire.called

    @pytest.mark.asyncio
    async def test_create_version_increments(
        self, mock_pool: MagicMock, mock_connection: AsyncMock
    ) -> None:
        strategy_id = uuid4()
        now = datetime.now(UTC)
        strategy_row = {
            "id": strategy_id,
            "name": "s1",
            "description": None,
            "mode": "paper",
            "status": "draft",
            "current_version": 3,
            "created_by": "tester",
            "created_at": now,
            "updated_at": now,
        }
        version_row = {
            "strategy_id": strategy_id,
            "version": 4,
            "schema_version": 1,
            "config": {"meta": {"name": "s1", "schema_version": 1}},
            "is_active": False,
            "created_by": "tester",
            "created_at": now,
        }
        mock_connection.fetchrow.side_effect = [strategy_row, version_row]

        repo = StrategyRepositoryPG(mock_pool)
        version = await repo.create_version(
            strategy_id=strategy_id,
            config={"meta": {"name": "s1", "schema_version": 1}},
            schema_version=1,
            created_by="tester",
        )

        assert version.version == 4
        assert version.schema_version == 1
        mock_connection.execute.assert_called()

    @pytest.mark.asyncio
    async def test_set_active_version_returns_false_if_missing(
        self, mock_pool: MagicMock, mock_connection: AsyncMock
    ) -> None:
        strategy_id = uuid4()
        mock_connection.fetchrow.return_value = None

        repo = StrategyRepositoryPG(mock_pool)
        updated = await repo.set_active_version(strategy_id=strategy_id, version=3)

        assert updated is False
        mock_connection.execute.assert_not_called()
