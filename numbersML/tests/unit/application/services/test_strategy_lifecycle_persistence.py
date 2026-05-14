"""Test that strategy lifecycle operations persist status to database correctly."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.application.services.strategy_lifecycle import StrategyLifecycleService
from src.domain.strategies.runtime import RuntimeState, StrategyRuntimeState
from src.domain.strategies.strategy_config import StrategyDefinition


@pytest.fixture
def mock_strategy_repo():
    """Mock strategy repository that tracks saved status."""
    repo = AsyncMock()
    repo.saved_strategies = []

    async def mock_save(entity):
        repo.saved_strategies.append(entity)
        return entity

    async def mock_get_by_id(entity_id):
        # Return a strategy that matches the ID if we have saved ones
        for strategy in repo.saved_strategies:
            if strategy.id == entity_id:
                return strategy
        return None

    async def mock_list_versions(strategy_id):
        # Return a default version for testing
        from src.domain.strategies.strategy_config import StrategyConfigVersion
        from datetime import UTC, datetime

        return [
            StrategyConfigVersion(
                strategy_id=strategy_id,
                version=1,
                schema_version=1,
                config={"meta": {"name": "Test"}, "universe": {"symbols": ["BTC/USDC"]}},
                is_active=True,
                created_by="test",
                created_at=datetime.now(UTC),
            )
        ]

    repo.save = mock_save
    repo.get_by_id = mock_get_by_id
    repo.list_versions = mock_list_versions
    return repo


@pytest.fixture
def mock_event_repo():
    """Mock event repository."""
    return AsyncMock()


@pytest.fixture
def mock_strategy_manager():
    """Mock strategy manager."""
    manager = MagicMock()
    manager.remove_strategy = MagicMock(return_value=MagicMock())
    return manager


@pytest.fixture
def sample_strategy():
    """Create an active sample strategy."""
    return StrategyDefinition(
        id=uuid4(),
        name="Test Strategy",
        description="Test",
        mode="paper",
        status="active",  # Initially active
        current_version=1,
        created_by="test",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def running_runtime_state(sample_strategy):
    """Create a running runtime state."""
    return StrategyRuntimeState(
        strategy_id=sample_strategy.id,
        strategy_name=sample_strategy.name,
        state=RuntimeState.RUNNING,
        version=1,
    )


class TestDeactivatePersistsToDatabase:
    """Test that deactivate operation persists status to database."""

    @pytest.mark.asyncio
    async def test_deactivate_sets_status_validated_in_database(
        self,
        mock_strategy_repo,
        mock_event_repo,
        mock_strategy_manager,
        sample_strategy,
        running_runtime_state,
    ):
        """Verify that deactivating a strategy sets status='validated' in DB."""
        # Setup - first save the strategy so it exists in the repo
        await mock_strategy_repo.save(sample_strategy)
        mock_strategy_repo.get_by_id.return_value = sample_strategy

        # Create service with pre-populated runtime state (as if activated)
        service = StrategyLifecycleService(
            strategy_repository=mock_strategy_repo,
            event_repository=mock_event_repo,
            strategy_manager=mock_strategy_manager,
            actor="test",
        )
        service._runtime_states[sample_strategy.id] = running_runtime_state

        # Execute deactivate
        result = await service.deactivate_strategy(sample_strategy.id)

        # Verify success
        assert result is True

        # Verify save was called
        assert len(mock_strategy_repo.saved_strategies) >= 1
        saved = mock_strategy_repo.saved_strategies[-1]  # Get the most recently saved

        # Verify status was set to 'validated'
        assert saved.status == "validated"
        assert saved.id == sample_strategy.id
        print(f"✓ Status correctly persisted as '{saved.status}' in database")

    @pytest.mark.asyncio
    async def test_pause_sets_status_paused_in_database(
        self,
        mock_strategy_repo,
        mock_event_repo,
        mock_strategy_manager,
        sample_strategy,
        running_runtime_state,
    ):
        """Verify that pausing a strategy sets status='paused' in DB."""
        # Setup - first save the strategy so it exists in the repo
        await mock_strategy_repo.save(sample_strategy)
        mock_strategy_repo.get_by_id.return_value = sample_strategy

        # Mock strategy instance for pause
        mock_instance = AsyncMock()
        mock_strategy_manager.get_strategy.return_value = mock_instance

        # Create service with pre-populated runtime state
        service = StrategyLifecycleService(
            strategy_repository=mock_strategy_repo,
            event_repository=mock_event_repo,
            strategy_manager=mock_strategy_manager,
            actor="test",
        )
        service._runtime_states[sample_strategy.id] = running_runtime_state

        # Execute pause
        result = await service.pause_strategy(sample_strategy.id)

        # Verify success
        assert result is True

        # Verify save was called
        assert len(mock_strategy_repo.saved_strategies) >= 1
        saved = mock_strategy_repo.saved_strategies[-1]  # Get the most recently saved

        # Verify status was set to 'paused'
        assert saved.status == "paused"
        assert saved.id == sample_strategy.id
        print(f"✓ Status correctly persisted as '{saved.status}' in database")

    @pytest.mark.asyncio
    async def test_activate_sets_status_active_in_database(
        self,
        mock_strategy_repo,
        mock_event_repo,
        mock_strategy_manager,
        sample_strategy,
    ):
        """Verify that activating a strategy sets status='active' in DB."""
        # Setup - first save the strategy so it exists in the repo
        sample_strategy.status = "validated"  # Initially validated
        await mock_strategy_repo.save(sample_strategy)
        mock_strategy_repo.get_by_id.return_value = sample_strategy
        mock_strategy_manager.add_strategy = MagicMock()
        mock_strategy_manager.get_strategy = MagicMock(return_value=None)

        # Mock strategy instance
        mock_instance = AsyncMock()
        mock_instance.id = sample_strategy.id

        with patch(
            "src.application.services.strategy_lifecycle.load_strategy_instance",
            return_value=mock_instance,
        ):
            service = StrategyLifecycleService(
                strategy_repository=mock_strategy_repo,
                event_repository=mock_event_repo,
                strategy_manager=mock_strategy_manager,
                actor="test",
            )

            # Execute activate
            result = await service.activate_strategy(sample_strategy.id)

            # Verify success
            assert result is True

            # Verify save was called
            assert len(mock_strategy_repo.saved_strategies) >= 1
            saved = mock_strategy_repo.saved_strategies[-1]  # Get the most recently saved

            # Verify status was set to 'active'
            assert saved.status == "active"
            assert saved.id == sample_strategy.id
            print(f"✓ Status correctly persisted as '{saved.status}' in database")

    @pytest.mark.asyncio
    async def test_deactivate_no_runtime_state_updates_status(
        self,
        mock_strategy_repo,
        mock_event_repo,
        mock_strategy_manager,
        sample_strategy,
    ):
        """BUG FIX: Deactivating a strategy with no runtime state should still update DB status."""
        # Setup - strategy is 'active' but never activated (no runtime state)
        sample_strategy.status = "active"
        await mock_strategy_repo.save(sample_strategy)
        mock_strategy_repo.get_by_id.return_value = sample_strategy
        # No runtime state in _runtime_states

        service = StrategyLifecycleService(
            strategy_repository=mock_strategy_repo,
            event_repository=mock_event_repo,
            strategy_manager=mock_strategy_manager,
            actor="test",
        )
        # Ensure no runtime state exists
        assert service._runtime_states.get(sample_strategy.id) is None

        # Execute deactivate
        result = await service.deactivate_strategy(sample_strategy.id)

        # Verify success
        assert result is True

        # Verify save WAS called to update status (BUG FIX)
        assert len(mock_strategy_repo.saved_strategies) >= 1
        saved = mock_strategy_repo.saved_strategies[-1]  # Get the most recently saved
        assert saved.status == "validated"
        assert saved.id == sample_strategy.id
        print(
            f"✓ BUG FIX: Deactivate with no runtime state correctly updates status to '{saved.status}'"
        )


class TestStatusTransitions:
    """Test status transitions are correct."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_status_changes(
        self,
        mock_strategy_repo,
        mock_event_repo,
        mock_strategy_manager,
        sample_strategy,
    ):
        """Test complete lifecycle: validated -> active -> paused -> validated."""
        sample_strategy.status = "validated"
        # Setup - first save the strategy so it exists in the repo
        await mock_strategy_repo.save(sample_strategy)
        mock_strategy_repo.get_by_id.return_value = sample_strategy
        mock_strategy_manager.add_strategy = MagicMock()
        mock_strategy_manager.get_strategy = MagicMock(return_value=None)

        mock_instance = AsyncMock()
        mock_instance.id = sample_strategy.id

        with patch(
            "src.application.services.strategy_lifecycle.load_strategy_instance",
            return_value=mock_instance,
        ):
            service = StrategyLifecycleService(
                strategy_repository=mock_strategy_repo,
                event_repository=mock_event_repo,
                strategy_manager=mock_strategy_manager,
                actor="test",
            )

            statuses = []

            # 1. Activate
            await service.activate_strategy(sample_strategy.id)
            statuses.append(mock_strategy_repo.saved_strategies[-1].status)

            # 2. Pause
            await service.pause_strategy(sample_strategy.id)
            statuses.append(mock_strategy_repo.saved_strategies[-1].status)

            # 3. Resume (back to active)
            await service.resume_strategy(sample_strategy.id)
            statuses.append(mock_strategy_repo.saved_strategies[-1].status)

            # 4. Deactivate
            await service.deactivate_strategy(sample_strategy.id)
            statuses.append(mock_strategy_repo.saved_strategies[-1].status)

            # Verify sequence
            assert statuses == ["active", "paused", "active", "validated"]
            print(f"✓ Full lifecycle status sequence: {' -> '.join(statuses)}")
