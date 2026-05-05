"""
Unit tests for AlgorithmInstanceRepositoryPG.

Uses unittest.mock.AsyncMock to mock asyncpg.Connection.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest

from src.domain.algorithms.algorithm_instance import (
    AlgorithmInstance,
    AlgorithmInstanceState,
)
from src.infrastructure.repositories.algorithm_instance_repository_pg import (
    AlgorithmInstanceRepositoryPG,
)


@pytest.fixture
def mock_conn():
    """Mock asyncpg.Connection."""
    return AsyncMock()


@pytest.fixture
def sample_instance():
    """Create a sample AlgorithmInstance."""
    return AlgorithmInstance(
        algorithm_id=uuid4(),
        config_set_id=uuid4(),
    )


class TestAlgorithmInstanceRepositoryPGSave:
    """Tests for save method."""

    async def test_save_new_instance(self, mock_conn, sample_instance):
        """Test saving a new AlgorithmInstance."""
        mock_conn.fetchrow.return_value = {
            "id": sample_instance.id,
            "algorithm_id": sample_instance.algorithm_id,
            "config_set_id": sample_instance.config_set_id,
            "status": sample_instance.status.value,
            "runtime_stats": sample_instance.runtime_stats.to_dict(),
            "started_at": None,
            "stopped_at": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        saved = await repo.save(sample_instance)

        assert saved.id == sample_instance.id
        assert saved.algorithm_id == sample_instance.algorithm_id
        mock_conn.fetchrow.assert_called_once()

    async def test_save_existing_instance(self, mock_conn, sample_instance):
        """Test updating an existing AlgorithmInstance."""
        sample_instance.start()
        mock_conn.fetchrow.return_value = {
            "id": sample_instance.id,
            "algorithm_id": sample_instance.algorithm_id,
            "config_set_id": sample_instance.config_set_id,
            "status": sample_instance.status.value,
            "runtime_stats": sample_instance.runtime_stats.to_dict(),
            "started_at": sample_instance.started_at,
            "stopped_at": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        saved = await repo.save(sample_instance)

        assert saved.status == AlgorithmInstanceState.RUNNING
        assert saved.started_at is not None

    async def test_save_unique_violation(self, mock_conn, sample_instance):
        """Test save raises ValueError on unique violation."""
        mock_conn.fetchrow.side_effect = asyncpg.UniqueViolationError("duplicate key")

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        with pytest.raises(ValueError, match="already exists"):
            await repo.save(sample_instance)


class TestAlgorithmInstanceRepositoryPGGetById:
    """Tests for get_by_id method."""

    async def test_get_existing_instance(self, mock_conn):
        """Test getting an existing instance by ID."""
        instance_id = uuid4()
        mock_conn.fetchrow.return_value = {
            "id": instance_id,
            "algorithm_id": uuid4(),
            "config_set_id": uuid4(),
            "status": "stopped",
            "runtime_stats": {},
            "started_at": None,
            "stopped_at": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instance = await repo.get_by_id(instance_id)

        assert instance is not None
        assert instance.id == instance_id
        assert instance.status == AlgorithmInstanceState.STOPPED

    async def test_get_nonexistent_instance(self, mock_conn):
        """Test getting a non-existent instance returns None."""
        mock_conn.fetchrow.return_value = None

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instance = await repo.get_by_id(uuid4())

        assert instance is None


class TestAlgorithmInstanceRepositoryPGGetByAlgorithmAndConfig:
    """Tests for get_by_algorithm_and_config method."""

    async def test_get_existing_combination(self, mock_conn):
        """Test getting instance by algorithm and config set IDs."""
        algorithm_id = uuid4()
        config_set_id = uuid4()
        mock_conn.fetchrow.return_value = {
            "id": uuid4(),
            "algorithm_id": algorithm_id,
            "config_set_id": config_set_id,
            "status": "running",
            "runtime_stats": {},
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instance = await repo.get_by_algorithm_and_config(algorithm_id, config_set_id)

        assert instance is not None
        assert instance.algorithm_id == algorithm_id
        assert instance.config_set_id == config_set_id

    async def test_get_nonexistent_combination(self, mock_conn):
        """Test getting non-existent combination returns None."""
        mock_conn.fetchrow.return_value = None

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instance = await repo.get_by_algorithm_and_config(uuid4(), uuid4())

        assert instance is None


class TestAlgorithmInstanceRepositoryPGListAll:
    """Tests for list_all method."""

    async def test_list_all_no_filter(self, mock_conn):
        """Test listing all instances without filter."""
        mock_conn.fetch.return_value = [
            {
                "id": uuid4(),
                "algorithm_id": uuid4(),
                "config_set_id": uuid4(),
                "status": "stopped",
                "runtime_stats": {},
                "started_at": None,
                "stopped_at": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            for _ in range(3)
        ]

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instances = await repo.list_all()

        assert len(instances) == 3

    async def test_list_all_with_status_filter(self, mock_conn):
        """Test listing instances with status filter."""
        mock_conn.fetch.return_value = [
            {
                "id": uuid4(),
                "algorithm_id": uuid4(),
                "config_set_id": uuid4(),
                "status": "running",
                "runtime_stats": {},
                "started_at": datetime.now(UTC),
                "stopped_at": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instances = await repo.list_all(status="running")

        assert len(instances) == 1
        assert instances[0].status == AlgorithmInstanceState.RUNNING


class TestAlgorithmInstanceRepositoryPGListByAlgorithm:
    """Tests for list_by_algorithm method."""

    async def test_list_by_algorithm(self, mock_conn):
        """Test listing instances for a specific algorithm."""
        algorithm_id = uuid4()
        mock_conn.fetch.return_value = [
            {
                "id": uuid4(),
                "algorithm_id": algorithm_id,
                "config_set_id": uuid4(),
                "status": "stopped",
                "runtime_stats": {},
                "started_at": None,
                "stopped_at": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            for _ in range(2)
        ]

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instances = await repo.list_by_algorithm(algorithm_id)

        assert len(instances) == 2
        assert all(i.algorithm_id == algorithm_id for i in instances)


class TestAlgorithmInstanceRepositoryPGDelete:
    """Tests for delete method."""

    async def test_delete_existing_instance(self, mock_conn):
        """Test deleting an existing instance."""
        mock_conn.execute.return_value = "DELETE 1"

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        result = await repo.delete(uuid4())

        assert result is True

    async def test_delete_nonexistent_instance(self, mock_conn):
        """Test deleting a non-existent instance returns False."""
        mock_conn.execute.return_value = "DELETE 0"

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        result = await repo.delete(uuid4())

        assert result is False


class TestAlgorithmInstanceRepositoryPGUpdateStatus:
    """Tests for update_status method."""

    async def test_update_status_with_runtime_stats(self, mock_conn):
        """Test updating status with runtime stats."""
        instance_id = uuid4()
        mock_conn.execute.return_value = "UPDATE 1"
        mock_conn.fetchrow.return_value = {
            "id": instance_id,
            "algorithm_id": uuid4(),
            "config_set_id": uuid4(),
            "status": "paused",
            "runtime_stats": {"pnl": 100.0},
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instance = await repo.update_status(instance_id, "paused", {"pnl": 100.0})

        assert instance is not None
        assert instance.status == AlgorithmInstanceState.PAUSED

    async def test_update_status_nonexistent_instance(self, mock_conn):
        """Test updating status for non-existent instance returns None."""
        mock_conn.execute.return_value = "UPDATE 0"

        repo = AlgorithmInstanceRepositoryPG(mock_conn)
        instance = await repo.update_status(uuid4(), "running")

        assert instance is None
