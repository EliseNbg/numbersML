"""Unit tests for strategy CRUD round-trip with strategy_type and class_path."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.strategies.strategy_config import StrategyDefinition


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


class TestStrategyRoundTrip:
    """Test that strategy_type and class_path persist correctly through full CRUD cycle."""

    @pytest.mark.asyncio
    async def test_class_based_strategy_stores_and_retrieves_strategy_type(
        self, mock_pool: MagicMock, mock_connection: AsyncMock
    ) -> None:
        """When creating a class-based strategy, strategy_type='class' must be retrievable."""
        from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG

        strategy_id = uuid4()
        now = datetime.now(UTC)

        # Mock strategy row (without config - config is in versions table)
        strategy_row = {
            "id": strategy_id,
            "name": "Test Class Strategy",
            "description": "A class-based strategy",
            "mode": "paper",
            "status": "draft",
            "current_version": 2,
            "created_by": "tester",
            "created_at": now,
            "updated_at": now,
        }

        # Mock version row WITH strategy_type and class_path in config
        version_row = {
            "strategy_id": strategy_id,
            "version": 2,
            "schema_version": 1,
            "config": {
                "strategy_type": "class",
                "class_path": "src.strategies.user.my_strategy.MyStrategy",
                "meta": {"name": "Test Class Strategy"},
            },
            "is_active": True,
            "created_by": "tester",
            "created_at": now,
        }

        # Setup mock responses
        mock_connection.fetchrow.side_effect = [strategy_row, version_row]
        mock_connection.fetch.return_value = [version_row]

        repo = StrategyRepositoryPG(mock_pool)

        # Create a strategy definition with config containing strategy_type
        original_config = {
            "strategy_type": "class",
            "class_path": "src.strategies.user.my_strategy.MyStrategy",
            "meta": {"name": "Test Class Strategy"},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
        }

        strategy = StrategyDefinition(
            id=strategy_id,
            name="Test Class Strategy",
            description="A class-based strategy",
            mode="paper",
            status="draft",
            current_version=2,
            config=original_config,
            created_by="tester",
            created_at=now,
            updated_at=now,
        )

        # Verify the strategy_type property works on the domain object
        assert strategy.strategy_type == "class"
        assert strategy.class_path == "src.strategies.user.my_strategy.MyStrategy"

        # Test via repository list_versions - this is how the API gets config
        versions = await repo.list_versions(strategy_id)
        assert len(versions) == 1
        assert versions[0].config["strategy_type"] == "class"
        assert versions[0].config["class_path"] == "src.strategies.user.my_strategy.MyStrategy"

    @pytest.mark.asyncio
    async def test_config_based_strategy_defaults_to_config(
        self, mock_pool: MagicMock, mock_connection: AsyncMock
    ) -> None:
        """When no strategy_type is specified, it should default to 'config'."""
        version_row = {
            "strategy_id": uuid4(),
            "version": 1,
            "schema_version": 1,
            "config": {
                "meta": {"name": "Config Strategy"},
                "universe": {"symbols": ["BTC/USDC"]},
            },
            "is_active": True,
            "created_by": "tester",
            "created_at": datetime.now(UTC),
        }

        mock_connection.fetch.return_value = [version_row]

        from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG

        repo = StrategyRepositoryPG(mock_pool)

        strategy_id = version_row["strategy_id"]
        versions = await repo.list_versions(strategy_id)

        assert len(versions) == 1
        # When strategy_type is not in config, it defaults to "config"
        config = versions[0].config
        assert config.get("strategy_type", "config") == "config"

    @pytest.mark.asyncio
    async def test_create_and_retrieve_exact_config_match(
        self, mock_pool: MagicMock, mock_connection: AsyncMock
    ) -> None:
        """Verify that creating a strategy with config preserves all fields exactly."""
        from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG

        strategy_id = uuid4()
        now = datetime.now(UTC)

        # Original config we want to store
        original_config = {
            "strategy_type": "class",
            "class_path": "src.strategies.user.test_strategy.TestStrategy",
            "meta": {"name": "Test Strategy", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC", "ETH/USDC"], "timeframe": "1M"},
            "signal": {"type": "test_signal"},
            "risk": {"max_position_size_pct": 10},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "draft",
        }

        # Strategy row returned from save
        strategy_row = {
            "id": strategy_id,
            "name": "Test Strategy",
            "description": None,
            "mode": "paper",
            "status": "draft",
            "current_version": 1,
            "created_by": "tester",
            "created_at": now,
            "updated_at": now,
        }

        # Version row returned from create_version
        version_row = {
            "strategy_id": strategy_id,
            "version": 1,
            "schema_version": 1,
            "config": original_config,
            "is_active": True,
            "created_by": "tester",
            "created_at": now,
        }

        # Mock fetchrow for save, create_version, and get_by_id
        mock_connection.fetchrow.side_effect = [strategy_row, strategy_row, version_row]
        mock_connection.fetch.return_value = [version_row]

        repo = StrategyRepositoryPG(mock_pool)

        # Create and save strategy
        strategy = StrategyDefinition(
            name="Test Strategy",
            description=None,
            mode="paper",
            status="draft",
            config=original_config,
            created_by="tester",
        )

        saved = await repo.save(strategy)

        # Create version with the config
        await repo.create_version(
            strategy_id=saved.id,
            config=original_config,
            schema_version=1,
            created_by="tester",
        )

        # Retrieve versions
        versions = await repo.list_versions(saved.id)
        assert len(versions) == 1

        retrieved_config = versions[0].config

        # Verify exact match
        assert retrieved_config["strategy_type"] == original_config["strategy_type"]
        assert retrieved_config["class_path"] == original_config["class_path"]
        assert retrieved_config["meta"] == original_config["meta"]
        assert retrieved_config["universe"] == original_config["universe"]
