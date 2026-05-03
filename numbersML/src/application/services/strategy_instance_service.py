"""
StrategyInstance application service.

Handles hot-plug of StrategyInstances into the pipeline.
Follows DDD: Application Layer service.
"""

import logging
from typing import Any
from uuid import UUID

from src.domain.repositories.config_set_repository import ConfigSetRepository
from src.domain.repositories.strategy_instance_repository import (
    StrategyInstanceRepository,
)
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.base import StrategyManager
from src.domain.strategies.strategy_instance import StrategyInstanceState

logger = logging.getLogger(__name__)


class StrategyInstanceService:
    """
    Application service for StrategyInstance lifecycle.

    Handles hot-plug/unplug from running pipeline.
    """

    def __init__(
        self,
        instance_repo: StrategyInstanceRepository,
        strategy_repo: StrategyRepository,
        config_set_repo: ConfigSetRepository,
        strategy_manager: StrategyManager,
    ) -> None:
        """
        Initialize with repositories and manager.

        Args:
            instance_repo: StrategyInstance repository
            strategy_repo: Algorithm repository
            config_set_repo: ConfigSet repository
            strategy_manager: Running StrategyManager
        """
        self._instance_repo = instance_repo
        self._strategy_repo = strategy_repo
        self._config_set_repo = config_set_repo
        self._strategy_manager = strategy_manager

    async def hot_plug(self, instance_id: UUID) -> bool:
        """
        Hot-plug a StrategyInstance into the pipeline.

        Args:
            instance_id: StrategyInstance ID to start

        Returns:
            True if successful

        Raises:
            ValueError: If instance not found or cannot start
        """
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if not instance.can_start():
            raise ValueError(f"Cannot start instance from state: {instance.status.value}")

        # TODO: Load Algorithm by ID from repository
        # TODO: Load ConfigurationSet by ID from repository

        self._strategy_manager.add_instance(instance)
        instance.start()
        await self._instance_repo.save(instance)

        logger.info(f"Instance {instance_id} hot-plugged into pipeline")
        return True

    async def unplug(self, instance_id: UUID) -> bool:
        """
        Unplug a StrategyInstance from the pipeline.

        Args:
            instance_id: StrategyInstance ID to stop

        Returns:
            True if successful

        Raises:
            ValueError: If instance not found or cannot stop
        """
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if not instance.can_stop():
            raise ValueError(f"Cannot stop instance from state: {instance.status.value}")

        self._strategy_manager.remove_instance(instance_id)
        instance.stop()
        await self._instance_repo.save(instance)

        logger.info(f"Instance {instance_id} unplugged from pipeline")
        return True

    async def pause_instance(self, instance_id: UUID) -> bool:
        """Pause a running instance."""
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if not instance.can_pause():
            raise ValueError(f"Cannot pause instance from state: {instance.status.value}")

        instance.pause()
        await self._instance_repo.save(instance)

        logger.info(f"Instance {instance_id} paused")
        return True

    async def resume_instance(self, instance_id: UUID) -> bool:
        """Resume a paused instance."""
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if instance.status != StrategyInstanceState.PAUSED:
            raise ValueError(f"Cannot resume instance from state: {instance.status.value}")

        instance.resume()
        await self._instance_repo.save(instance)

        logger.info(f"Instance {instance_id} resumed")
        return True

    async def get_stats(self, instance_id: UUID) -> dict[str, Any] | None:
        """Get runtime statistics for an instance."""
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            return None

        return instance.runtime_stats.to_dict()
