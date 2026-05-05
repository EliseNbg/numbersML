"""
Unit tests for AlgorithmInstanceService.

Follows TDD approach: tests first, then implementation.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.services.algorithm_instance_service import AlgorithmInstanceService
from src.domain.algorithms.algorithm_instance import AlgorithmInstance, AlgorithmInstanceState


@pytest.fixture
def instance_repo():
    """Mock AlgorithmInstanceRepository."""
    return AsyncMock()


@pytest.fixture
def algorithm_repo():
    """Mock AlgorithmRepository."""
    return AsyncMock()


@pytest.fixture
def config_set_repo():
    """Mock ConfigSetRepository."""
    return AsyncMock()


@pytest.fixture
def algorithm_manager():
    """Mock AlgorithmManager."""
    manager = AsyncMock()
    manager.add_instance = MagicMock()
    manager.remove_instance = MagicMock()
    return manager


@pytest.fixture
def service(instance_repo, algorithm_repo, config_set_repo, algorithm_manager):
    """Create AlgorithmInstanceService with mocks."""
    return AlgorithmInstanceService(
        instance_repo=instance_repo,
        algorithm_repo=algorithm_repo,
        config_set_repo=config_set_repo,
        algorithm_manager=algorithm_manager,
    )


@pytest.fixture
def sample_instance():
    """Create a sample AlgorithmInstance."""
    return AlgorithmInstance(
        algorithm_id=uuid4(),
        config_set_id=uuid4(),
    )


class TestHotPlug:
    """Tests for hot_plug method."""

    async def test_hot_plug_success(
        self, service, instance_repo, algorithm_manager, sample_instance
    ):
        """Test successfully hot-plugging an instance."""
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.hot_plug(sample_instance.id)

        assert result is True
        algorithm_manager.add_instance.assert_called_once_with(sample_instance)
        instance_repo.save.assert_called_once()

    async def test_hot_plug_not_found(self, service, instance_repo):
        """Test hot-plug with non-existent instance."""
        instance_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.hot_plug(uuid4())

    async def test_hot_plug_cannot_start(self, service, instance_repo, sample_instance):
        """Test hot-plug when instance cannot start."""
        sample_instance._status = AlgorithmInstanceState.RUNNING  # Already running

        instance_repo.get_by_id.return_value = sample_instance

        with pytest.raises(ValueError, match="Cannot start"):
            await service.hot_plug(sample_instance.id)


class TestUnplug:
    """Tests for unplug method."""

    async def test_unplug_success(self, service, instance_repo, algorithm_manager, sample_instance):
        """Test successfully unplugging an instance."""
        sample_instance._status = AlgorithmInstanceState.RUNNING
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.unplug(sample_instance.id)

        assert result is True
        algorithm_manager.remove_instance.assert_called_once_with(sample_instance.id)
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
        sample_instance._status = AlgorithmInstanceState.RUNNING
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.pause_instance(sample_instance.id)

        assert result is True
        instance_repo.save.assert_called_once()

    async def test_resume_success(self, service, instance_repo, sample_instance):
        """Test resuming a paused instance."""
        sample_instance._status = AlgorithmInstanceState.PAUSED
        instance_repo.get_by_id.return_value = sample_instance

        result = await service.resume_instance(sample_instance.id)

        assert result is True
        instance_repo.save.assert_called_once()
