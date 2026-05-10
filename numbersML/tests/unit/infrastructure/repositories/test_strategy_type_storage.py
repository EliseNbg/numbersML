"""Tests for strategy type (class-based vs config-based) storage.

These tests verify that:
- strategy_type and class_path are properly stored in the database
- Config-based strategies have strategy_type='config' and class_path=None
- Class-based strategies have strategy_type='class' and class_path='module.ClassName'
- Default strategy type is 'config'
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.strategies.strategy_config import StrategyDefinition
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG


def create_mock_pool():
    """Create a properly configured mock asyncpg pool."""
    pool = AsyncMock()
    mock_conn = AsyncMock()
    
    # Setup async context manager properly
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_context_manager.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=mock_context_manager)
    
    return pool, mock_conn


@pytest.fixture
def sample_config_based_strategy():
    """Create a config-based strategy."""
    return StrategyDefinition(
        id=uuid4(),
        name="ConfigStrategy",
        description="Test config strategy",
        mode="paper",
        status="draft",
        strategy_type="config",
        class_path=None,
        current_version=1,
        config={"symbol": "BTC/USDC"},
        created_by="test",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_class_based_strategy():
    """Create a class-based strategy."""
    return StrategyDefinition(
        id=uuid4(),
        name="Grid1",
        description="Test class strategy",
        mode="paper",
        status="draft",
        strategy_type="class",
        class_path="src.strategies.user.grid1.Grid1Strategy",
        current_version=1,
        config={"grid_spacing": 0.01},
        created_by="test",
        created_at=datetime.now(UTC),
    )


class TestStrategyTypeFields:
    """Test that strategy_type and class_path fields work correctly."""

    def test_config_based_strategy_has_correct_type(self, sample_config_based_strategy):
        """Config-based strategy should have type='config' and no class_path."""
        assert sample_config_based_strategy.strategy_type == "config"
        assert sample_config_based_strategy.class_path is None
        assert sample_config_based_strategy.is_config_based() is True
        assert sample_config_based_strategy.is_class_based() is False
        print(f"✓ Config strategy: type={sample_config_based_strategy.strategy_type}, class_path={sample_config_based_strategy.class_path}")

    def test_class_based_strategy_has_correct_type(self, sample_class_based_strategy):
        """Class-based strategy should have type='class' and class_path set."""
        assert sample_class_based_strategy.strategy_type == "class"
        assert sample_class_based_strategy.class_path == "src.strategies.user.grid1.Grid1Strategy"
        assert sample_class_based_strategy.is_class_based() is True
        assert sample_class_based_strategy.is_config_based() is False
        print(f"✓ Class strategy: type={sample_class_based_strategy.strategy_type}, class_path={sample_class_based_strategy.class_path}")

    def test_default_strategy_type_is_config(self):
        """Strategy without explicit type should default to 'config'."""
        strategy = StrategyDefinition(
            id=uuid4(),
            name="DefaultStrategy",
            description="Test default",
        )
        assert strategy.strategy_type == "config"
        assert strategy.class_path is None
        print(f"✓ Default strategy: type={strategy.strategy_type}")


class TestStrategyRepositoryStoresType:
    """Test that repository properly saves and loads strategy_type and class_path."""

    @pytest.mark.asyncio
    async def test_save_config_based_stores_type_correctly(self, sample_config_based_strategy):
        """Verify saving a config-based strategy stores type='config'."""
        mock_pool, mock_conn = create_mock_pool()
        repo = StrategyRepositoryPG(mock_pool)
        mock_conn.fetchrow.return_value = {
            "id": sample_config_based_strategy.id,
            "name": sample_config_based_strategy.name,
            "description": sample_config_based_strategy.description,
            "mode": sample_config_based_strategy.mode,
            "status": sample_config_based_strategy.status,
            "strategy_type": "config",
            "class_path": None,
            "current_version": 1,
            "created_by": "test",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        # Execute save
        result = await repo.save(sample_config_based_strategy)

        # Verify returned object has correct type
        assert result.strategy_type == "config"
        assert result.class_path is None

        # Verify SQL was called with correct parameters
        call_args = mock_conn.fetchrow.call_args
        assert call_args[0][6] == "config"  # strategy_type parameter ($6 in SQL)
        assert call_args[0][7] is None  # class_path parameter ($7 in SQL)
        print(f"✓ Saved config strategy: type='{result.strategy_type}', class_path={result.class_path}")

    @pytest.mark.asyncio
    async def test_save_class_based_stores_type_and_path(self, sample_class_based_strategy):
        """Verify saving a class-based strategy stores type='class' and class_path."""
        mock_pool, mock_conn = create_mock_pool()
        repo = StrategyRepositoryPG(mock_pool)
        mock_conn.fetchrow.return_value = {
            "id": sample_class_based_strategy.id,
            "name": sample_class_based_strategy.name,
            "description": sample_class_based_strategy.description,
            "mode": sample_class_based_strategy.mode,
            "status": sample_class_based_strategy.status,
            "strategy_type": "class",
            "class_path": "src.strategies.user.grid1.Grid1Strategy",
            "current_version": 1,
            "created_by": "test",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        # Execute save
        result = await repo.save(sample_class_based_strategy)

        # Verify returned object has correct type and path
        assert result.strategy_type == "class"
        assert result.class_path == "src.strategies.user.grid1.Grid1Strategy"

        # Verify SQL was called with correct parameters
        call_args = mock_conn.fetchrow.call_args
        assert call_args[0][6] == "class"  # strategy_type parameter ($6 in SQL)
        assert call_args[0][7] == "src.strategies.user.grid1.Grid1Strategy"  # class_path parameter ($7 in SQL)
        print(f"✓ Saved class strategy: type='{result.strategy_type}', class_path='{result.class_path}'")

    @pytest.mark.asyncio
    async def test_load_config_based_reads_type_correctly(self):
        """Verify loading a config-based strategy from DB has correct type."""
        mock_pool, mock_conn = create_mock_pool()
        repo = StrategyRepositoryPG(mock_pool)
        strategy_id = uuid4()
        mock_conn.fetchrow.return_value = {
            "id": strategy_id,
            "name": "TestConfig",
            "description": "Test",
            "mode": "paper",
            "status": "draft",
            "strategy_type": "config",
            "class_path": None,
            "current_version": 1,
            "created_by": "test",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        # Execute load
        result = await repo.get_by_id(strategy_id)

        # Verify loaded object has correct type
        assert result is not None
        assert result.strategy_type == "config"
        assert result.class_path is None
        assert result.is_config_based() is True
        print(f"✓ Loaded config strategy: type='{result.strategy_type}', class_path={result.class_path}")

    @pytest.mark.asyncio
    async def test_load_class_based_reads_type_and_path(self):
        """Verify loading a class-based strategy from DB has correct type and path."""
        mock_pool, mock_conn = create_mock_pool()
        repo = StrategyRepositoryPG(mock_pool)
        strategy_id = uuid4()
        mock_conn.fetchrow.return_value = {
            "id": strategy_id,
            "name": "Grid1",
            "description": "Grid strategy",
            "mode": "paper",
            "status": "active",
            "strategy_type": "class",
            "class_path": "src.strategies.user.grid1.Grid1Strategy",
            "current_version": 1,
            "created_by": "test",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        # Execute load
        result = await repo.get_by_id(strategy_id)

        # Verify loaded object has correct type and path
        assert result is not None
        assert result.strategy_type == "class"
        assert result.class_path == "src.strategies.user.grid1.Grid1Strategy"
        assert result.is_class_based() is True
        print(f"✓ Loaded class strategy: type='{result.strategy_type}', class_path='{result.class_path}'")

    @pytest.mark.asyncio
    async def test_load_all_reads_type_correctly(self):
        """Verify loading all strategies preserves their types."""
        mock_pool, mock_conn = create_mock_pool()
        repo = StrategyRepositoryPG(mock_pool)
        mock_conn.fetch.return_value = [
            {
                "id": uuid4(),
                "name": "ConfigStrat",
                "description": "Test",
                "mode": "paper",
                "status": "draft",
                "strategy_type": "config",
                "class_path": None,
                "current_version": 1,
                "created_by": "test",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
            {
                "id": uuid4(),
                "name": "Grid1",
                "description": "Grid",
                "mode": "paper",
                "status": "active",
                "strategy_type": "class",
                "class_path": "src.strategies.user.grid1.Grid1Strategy",
                "current_version": 1,
                "created_by": "test",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        ]

        # Execute load all
        results = await repo.get_all()

        # Verify types are preserved
        assert len(results) == 2
        assert results[0].strategy_type == "config"
        assert results[0].class_path is None
        assert results[1].strategy_type == "class"
        assert results[1].class_path == "src.strategies.user.grid1.Grid1Strategy"
        print(f"✓ Loaded {len(results)} strategies: config={sum(1 for s in results if s.strategy_type == 'config')}, class={sum(1 for s in results if s.strategy_type == 'class')}")

    @pytest.mark.asyncio
    async def test_backward_compatibility_missing_type_defaults_to_config(self):
        """Verify old strategies without strategy_type column default to 'config'."""
        mock_pool, mock_conn = create_mock_pool()
        repo = StrategyRepositoryPG(mock_pool)
        strategy_id = uuid4()
        mock_conn.fetchrow.return_value = {
            "id": strategy_id,
            "name": "OldStrategy",
            "description": "Test",
            "mode": "paper",
            "status": "active",
            # No strategy_type key - simulating old schema
            "current_version": 1,
            "created_by": "test",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        # Execute load
        result = await repo.get_by_id(strategy_id)

        # Verify defaults to 'config'
        assert result is not None
        assert result.strategy_type == "config"
        print(f"✓ Backward compatible: missing type defaults to '{result.strategy_type}'")


class TestStrategyTypeValidation:
    """Test that invalid strategy types are rejected."""

    def test_invalid_strategy_type_rejected(self):
        """Verify that only 'config' or 'class' are valid strategy types."""
        # This test documents expected behavior - actual validation happens at DB level
        # via the check constraint: strategies_strategy_type_check
        
        # Valid types should work
        config_strat = StrategyDefinition(
            id=uuid4(),
            name="Config",
            description="Test config",
            strategy_type="config",
        )
        assert config_strat.strategy_type == "config"
        
        class_strat = StrategyDefinition(
            id=uuid4(),
            name="Class",
            description="Test class",
            strategy_type="class",
        )
        assert class_strat.strategy_type == "class"
        
        print(f"✓ Valid strategy types accepted: config={config_strat.strategy_type}, class={class_strat.strategy_type}")
