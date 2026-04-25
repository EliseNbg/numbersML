"""Unit tests for StrategyRepositoryPG."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.strategies.strategy_config import StrategyDefinition
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG


@pytest.fixture
def mock_connection() -> AsyncMock:
    """Build a mocked asyncpg connection."""
    return AsyncMock()


class TestStrategyRepositoryPG:
    """Validate repository behavior against mocked asyncpg connection."""

    @pytest.mark.asyncio
    async def test_save_and_get_by_id(self, mock_connection: AsyncMock) -> None:
        strategy_id = uuid4()
        now = datetime.now(timezone.utc)
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

        repo = StrategyRepositoryPG(mock_connection)
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

    @pytest.mark.asyncio
    async def test_create_version_increments(self, mock_connection: AsyncMock) -> None:
        strategy_id = uuid4()
        now = datetime.now(timezone.utc)
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

        repo = StrategyRepositoryPG(mock_connection)
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
    async def test_set_active_version_returns_false_if_missing(self, mock_connection: AsyncMock) -> None:
        strategy_id = uuid4()
        mock_connection.fetchrow.return_value = None

        repo = StrategyRepositoryPG(mock_connection)
        updated = await repo.set_active_version(strategy_id=strategy_id, version=3)

        assert updated is False
        mock_connection.execute.assert_not_called()
