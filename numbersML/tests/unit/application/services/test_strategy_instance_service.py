"""
Unit tests for StrategyInstanceService.

Follows TDD approach: tests first, then implementation.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.services.strategy_instance_service import StrategyInstanceService
from src.domain.strategies.strategy_instance import StrategyInstance, StrategyInstanceState


@pytest.fixture
def instance_repo():
    """Mock StrategyInstanceRepository."""
    return AsyncMock()


@pytest.fixture
def strategy_repo():
    """Mock StrategyRepository."""
    return AsyncMock()


@pytest.fixture
def config_set_repo():
    """Mock ConfigSetRepository."""
    return AsyncMock()


@pytest.fixture
def strategy_manager():
    """Mock StrategyManager."""
    manager = AsyncMock()
    manager.add_instance = MagicMock()
    manager.remove_instance = MagicMock()
    return manager


@pytest.fixture
def service(instance_repo, strategy_repo, config_set_repo, strategy_manager):
    """Create StrategyInstanceService with mocks."""
    return StrategyInstanceService(
        instance_repo=instance_repo,
        strategy_repo=strategy_repo,
        config_set_repo=config_set_repo,
        strategy_manager=strategy_manager,
    )


@pytest.fixture
def sample_instance():
    """Create a sample StrategyInstance."""
    return StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )


class TestHotPlug:
    """Tests for hot_plug method."""

    async def test_hot_plug_success(
        self, service, instance_repo, strategy_manager, sample_instance
    ):
        """Test successfully hot-plugging an instance."""
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.hot_plug(sample_instance.id)

        assert result is True
        strategy_manager.add_instance.assert_called_once_with(sample_instance)
        instance_repo.save.assert_called_once()

    async def test_hot_plug_not_found(self, service, instance_repo):
        """Test hot-plug with non-existent instance."""
        instance_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.hot_plug(uuid4())

    async def test_hot_plug_cannot_start(self, service, instance_repo, sample_instance):
        """Test hot-plug when instance cannot start."""
        sample_instance._status = StrategyInstanceState.RUNNING  # Already running

        instance_repo.get_by_id.return_value = sample_instance

        with pytest.raises(ValueError, match="Cannot start"):
            await service.hot_plug(sample_instance.id)


class TestUnplug:
    """Tests for unplug method."""

    async def test_unplug_success(self, service, instance_repo, strategy_manager, sample_instance):
        """Test successfully unplugging an instance."""
        sample_instance._status = StrategyInstanceState.RUNNING
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.unplug(sample_instance.id)

        assert result is True
        strategy_manager.remove_instance.assert_called_once_with(sample_instance.id)
        instance_repo.save.assert_called_once()

    async def test_unplug_not_found(self, service, instance_repo):
        """Test unplug with non-existent instance."""
        instance_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.unplug(uuid4())


class TestPauseResume:
    """Tests for pause/resume."""

    async def test_pause_success(self, service, instance_repo, sample_instance):
        """Test pausing a running instance."""
        sample_instance._status = StrategyInstanceState.RUNNING
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.pause_instance(sample_instance.id)

        assert result is True
        instance_repo.save.assert_called_once()

    async def test_resume_success(self, service, instance_repo, sample_instance):
        """Test resuming a paused instance."""
        sample_instance._status = StrategyInstanceState.PAUSED
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.resume_instance(sample_instance.id)

        assert result is True
        instance_repo.save.assert_called_once()
