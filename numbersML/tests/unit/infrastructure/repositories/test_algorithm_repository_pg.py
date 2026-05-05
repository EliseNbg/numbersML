"""Unit tests for AlgorithmRepositoryPG."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.algorithms.algorithm_config import AlgorithmDefinition
from src.infrastructure.repositories.algorithm_repository_pg import AlgorithmRepositoryPG


@pytest.fixture
def mock_connection() -> AsyncMock:
    """Build a mocked asyncpg connection."""
    return AsyncMock()


class TestAlgorithmRepositoryPG:
    """Validate repository behavior against mocked asyncpg connection."""

    @pytest.mark.asyncio
    async def test_save_and_get_by_id(self, mock_connection: AsyncMock) -> None:
        algorithm_id = uuid4()
        now = datetime.now(UTC)
        row = {
            "id": algorithm_id,
            "name": "test_algorithm",
            "description": "example",
            "mode": "paper",
            "status": "draft",
            "current_version": 1,
            "created_by": "tester",
            "created_at": now,
            "updated_at": now,
        }
        mock_connection.fetchrow.return_value = row

        repo = AlgorithmRepositoryPG(mock_connection)
        saved = await repo.save(
            AlgorithmDefinition(
                id=algorithm_id,
                name="test_algorithm",
                description="example",
                mode="paper",
                status="draft",
                current_version=1,
                created_by="tester",
                created_at=now,
                updated_at=now,
            )
        )
        fetched = await repo.get_by_id(algorithm_id)

        assert saved.id == algorithm_id
        assert fetched is not None
        assert fetched.name == "test_algorithm"

    @pytest.mark.asyncio
    async def test_create_version_increments(self, mock_connection: AsyncMock) -> None:
        algorithm_id = uuid4()
        now = datetime.now(UTC)
        algorithm_row = {
            "id": algorithm_id,
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
            "algorithm_id": algorithm_id,
            "version": 4,
            "schema_version": 1,
            "config": {"meta": {"name": "s1", "schema_version": 1}},
            "is_active": False,
            "created_by": "tester",
            "created_at": now,
        }
        mock_connection.fetchrow.side_effect = [algorithm_row, version_row]

        repo = AlgorithmRepositoryPG(mock_connection)
        version = await repo.create_version(
            algorithm_id=algorithm_id,
            config={"meta": {"name": "s1", "schema_version": 1}},
            schema_version=1,
            created_by="tester",
        )

        assert version.version == 4
        assert version.schema_version == 1
        mock_connection.execute.assert_called()

    @pytest.mark.asyncio
    async def test_set_active_version_returns_false_if_missing(
        self, mock_connection: AsyncMock
    ) -> None:
        algorithm_id = uuid4()
        mock_connection.fetchrow.return_value = None

        repo = AlgorithmRepositoryPG(mock_connection)
        updated = await repo.set_active_version(algorithm_id=algorithm_id, version=3)

        assert updated is False
        mock_connection.execute.assert_not_called()
