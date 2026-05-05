"""
Unit tests for ConfigSetRepositoryPG.

Uses unittest.mock to mock asyncpg.Connection.
Follows TDD: tests first, then implementation.
"""

import datetime
from datetime import UTC
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from src.domain.algorithms.config_set import ConfigurationSet
from src.infrastructure.repositories.config_set_repository_pg import ConfigSetRepositoryPG


@pytest.fixture
def mock_connection():
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    return conn


@pytest.fixture
def repository(mock_connection):
    """Create repository with mock connection."""
    return ConfigSetRepositoryPG(mock_connection)


@pytest.fixture
def sample_config_set():
    """Create a sample ConfigurationSet for testing."""
    return ConfigurationSet(
        name="Test Config",
        config={"symbols": ["BTC/USDT"], "risk": {"max_position_size_pct": 10}},
        description="Test description",
        created_by="test",
    )


class TestConfigSetRepositoryPGSave:
    """Tests for save method."""

    @pytest.mark.asyncio
    async def test_save_new_config_set(self, repository, mock_connection, sample_config_set):
        """Test saving a new ConfigurationSet."""
        # Mock the fetchrow to return the saved row
        mock_connection.fetchrow.return_value = {
            "id": sample_config_set.id,
            "name": sample_config_set.name,
            "description": sample_config_set.description,
            "config": sample_config_set.to_dict()["config"],
            "is_active": sample_config_set.is_active,
            "created_by": sample_config_set.created_by,
            "created_at": datetime.datetime.now(UTC),
            "updated_at": datetime.datetime.now(UTC),
            "version": 1,
        }

        result = await repository.save(sample_config_set)

        assert result is not None
        assert result.id == sample_config_set.id
        assert result.name == sample_config_set.name
        assert mock_connection.fetchrow.called

    @pytest.mark.asyncio
    async def test_save_existing_config_set(self, repository, mock_connection, sample_config_set):
        """Test updating an existing ConfigurationSet."""
        # Mock the upsert to return updated row
        mock_connection.fetchrow.return_value = {
            "id": sample_config_set.id,
            "name": sample_config_set.name,
            "description": sample_config_set.description,
            "config": sample_config_set.to_dict()["config"],
            "is_active": sample_config_set.is_active,
            "created_by": sample_config_set.created_by,
            "created_at": datetime.datetime.now(UTC),
            "updated_at": datetime.datetime.now(UTC),
            "version": 1,
        }

        result = await repository.save(sample_config_set)

        assert result is not None
        assert result.id == sample_config_set.id

    @pytest.mark.asyncio
    async def test_save_duplicate_name_raises_error(
        self, repository, mock_connection, sample_config_set
    ):
        """Test that duplicate name raises ValueError."""
        mock_connection.fetchrow.side_effect = asyncpg.UniqueViolationError("unique_violation")

        with pytest.raises(ValueError, match="already exists"):
            await repository.save(sample_config_set)


class TestConfigSetRepositoryPGGetById:
    """Tests for get_by_id method."""

    @pytest.mark.asyncio
    async def test_get_existing_config_set(self, repository, mock_connection, sample_config_set):
        """Test getting an existing ConfigurationSet by ID."""
        mock_connection.fetchrow.return_value = {
            "id": sample_config_set.id,
            "name": sample_config_set.name,
            "description": sample_config_set.description,
            "config": sample_config_set.to_dict()["config"],
            "is_active": True,
            "created_by": "test",
            "created_at": datetime.datetime.now(UTC),
            "updated_at": datetime.datetime.now(UTC),
            "version": 1,
        }

        result = await repository.get_by_id(sample_config_set.id)

        assert result is not None
        assert result.id == sample_config_set.id
        assert result.name == sample_config_set.name

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, repository, mock_connection):
        """Test that getting non-existent ID returns None."""
        mock_connection.fetchrow.return_value = None

        result = await repository.get_by_id(uuid4())

        assert result is None


class TestConfigSetRepositoryPGGetAll:
    """Tests for get_all method."""

    @pytest.mark.asyncio
    async def test_get_all_config_sets(self, repository, mock_connection):
        """Test getting all ConfigurationSets."""
        id1, id2 = uuid4(), uuid4()
        mock_connection.fetch.return_value = [
            {
                "id": id1,
                "name": "Config 1",
                "description": "Desc 1",
                "config": {"key": "value1"},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.datetime.now(UTC),
                "updated_at": datetime.datetime.now(UTC),
                "version": 1,
            },
            {
                "id": id2,
                "name": "Config 2",
                "description": "Desc 2",
                "config": {"key": "value2"},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.datetime.now(UTC),
                "updated_at": datetime.datetime.now(UTC),
                "version": 1,
            },
        ]

        results = await repository.get_all()

        assert len(results) == 2
        assert results[0].name == "Config 1"
        assert results[1].name == "Config 2"


class TestConfigSetRepositoryPGGetByName:
    """Tests for get_by_name method."""

    @pytest.mark.asyncio
    async def test_get_existing_by_name(self, repository, mock_connection, sample_config_set):
        """Test getting an existing ConfigurationSet by name."""
        mock_connection.fetchrow.return_value = {
            "id": sample_config_set.id,
            "name": sample_config_set.name,
            "description": sample_config_set.description,
            "config": sample_config_set.to_dict()["config"],
            "is_active": True,
            "created_by": "test",
            "created_at": datetime.datetime.now(UTC),
            "updated_at": datetime.datetime.now(UTC),
            "version": 1,
        }

        result = await repository.get_by_name(sample_config_set.name)

        assert result is not None
        assert result.name == sample_config_set.name

    @pytest.mark.asyncio
    async def test_get_nonexistent_by_name_returns_none(self, repository, mock_connection):
        """Test that getting non-existent name returns None."""
        mock_connection.fetchrow.return_value = None

        result = await repository.get_by_name("nonexistent")

        assert result is None


class TestConfigSetRepositoryPGListAll:
    """Tests for list_all method."""

    @pytest.mark.asyncio
    async def test_list_all_config_sets(self, repository, mock_connection):
        """Test listing all ConfigurationSets."""
        mock_connection.fetch.return_value = [
            {
                "id": uuid4(),
                "name": "Config 1",
                "description": "Desc 1",
                "config": {"key": "value1"},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.datetime.now(UTC),
                "updated_at": datetime.datetime.now(UTC),
                "version": 1,
            },
            {
                "id": uuid4(),
                "name": "Config 2",
                "description": "Desc 2",
                "config": {"key": "value2"},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.datetime.now(UTC),
                "updated_at": datetime.datetime.now(UTC),
                "version": 1,
            },
        ]

        results = await repository.list_all()

        assert len(results) == 2
        assert results[0].name == "Config 1"
        assert results[1].name == "Config 2"

    @pytest.mark.asyncio
    async def test_list_active_only(self, repository, mock_connection):
        """Test listing only active ConfigurationSets."""
        mock_connection.fetch.return_value = [
            {
                "id": uuid4(),
                "name": "Active Config",
                "description": None,
                "config": {"key": "value"},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.datetime.now(UTC),
                "updated_at": datetime.datetime.now(UTC),
                "version": 1,
            },
        ]

        results = await repository.list_all(active_only=True)

        assert len(results) == 1
        assert results[0].is_active is True
        # Verify query included WHERE is_active = true
        call_args = mock_connection.fetch.call_args
        assert "is_active" in call_args[0][0]


class TestConfigSetRepositoryPGDelete:
    """Tests for delete method (soft delete)."""

    @pytest.mark.asyncio
    async def test_delete_existing_config_set(self, repository, mock_connection):
        """Test soft deleting an existing ConfigurationSet."""
        mock_connection.execute.return_value = "UPDATE 1"

        result = await repository.delete(uuid4())

        assert result is True
        # Verify UPDATE was called with is_active = false
        call_args = mock_connection.execute.call_args
        assert "is_active" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, repository, mock_connection):
        """Test that deleting non-existent returns False."""
        mock_connection.execute.return_value = "UPDATE 0"

        result = await repository.delete(uuid4())

        assert result is False


class TestConfigSetRepositoryPGUpdateConfig:
    """Tests for update_config method."""

    @pytest.mark.asyncio
    async def test_update_config_success(self, repository, mock_connection):
        """Test successfully updating configuration."""
        config_set_id = uuid4()
        new_config = {"symbols": ["ETH/USDT"], "risk": {"max_position_size_pct": 20}}

        # Mock the update and then the get_by_id
        mock_connection.execute.return_value = "UPDATE 1"
        mock_connection.fetchrow.return_value = {
            "id": config_set_id,
            "name": "Test",
            "description": None,
            "config": new_config,
            "is_active": True,
            "created_by": "test",
            "created_at": datetime.datetime.now(UTC),
            "updated_at": datetime.datetime.now(UTC),
            "version": 2,  # Incremented
        }

        result = await repository.update_config(config_set_id, new_config)

        assert result is not None
        assert result.version == 2
        # Verify UPDATE was called with version increment
        call_args = mock_connection.execute.call_args
        assert "version = version + 1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_config_nonexistent_returns_none(self, repository, mock_connection):
        """Test updating non-existent config set returns None."""
        mock_connection.execute.return_value = "UPDATE 0"

        result = await repository.update_config(uuid4(), {"new": "config"})

        assert result is None
