# Step 13: Pipeline Integration for Hot-Plug#

## Objective#
Integrate StrategyInstance hot-plug functionality into the running pipeline without restart.

## Context#
- Step 5 complete: StrategyInstance API with start/stop/pause/resume endpoints#
- Phase 3 complete: `StrategyManager` exists in `src/domain/strategies/base.py`#
- Pipeline exists in `src/pipeline/` or `src/main.py`#
- Need to modify pipeline to handle StrategyInstances (not just Strategies)#

## DDD Architecture Decision (ADR)#

**Decision**: Pipeline uses StrategyInstance, not just Algorithm#
- **Input**: StrategyInstance (contains strategy_id + config_set_id)#
- **Loading**: Load Algorithm from strategy_id, Config from config_set_id#
- **State Tracking**: Per-instance statistics in `runtime_stats`#
- **Hot-Plug**: Add/remove instances without restart#

**Key Design**:#
- `StrategyManager` updated to manage StrategyInstances#
- Pipeline subscribes to instance lifecycle events (Redis pub/sub)#
- When instance starts: Load strategy + config, add to active list#
- When instance stops: Remove from active list#

## TDD Approach#

1. **Red**: Write failing tests for hot-plug#
2. **Green**: Implement integration#
3. **Refactor**: Add error handling, optimization#

## Implementation Files#

### 1. Update `src/domain/strategies/base.py`#

Add StrategyInstance support to `StrategyManager`:

```python
# In StrategyManager class, add:

    async def add_instance(self, instance: StrategyInstance) -> None:
        """
        Add a StrategyInstance to the manager.
        
        Loads the Algorithm and ConfigurationSet,
        then adds to active strategies.
        
        Args:
            instance: StrategyInstance to add
            
        Raises:
            ValueError: If instance already exists or strategy/config not found
        """
        if instance.id in self._strategies:
            raise ValueError(f"Instance {instance.id} already exists")
        
        # TODO: Load Algorithm by ID from repository
        # TODO: Load ConfigurationSet by ID from repository
        # For now, assume strategy is already loaded
        
        self._strategies[instance.id] = strategy
        logger.info(f"Instance {instance.id} added to manager")
    
    async def remove_instance(self, instance_id: UUID) -> Optional[Algorithm]:
        """
        Remove a StrategyInstance from the manager.
        
        Args:
            instance_id: StrategyInstance ID to remove
            
        Returns:
            Removed Algorithm if existed, None otherwise
        """
        strategy = self._strategies.pop(instance_id, None)
        if strategy:
            try:
                await strategy.stop()
            except Exception as e:
                logger.error(f"Error stopping instance {instance_id}: {e}")
            logger.info(f"Instance {instance_id} removed from manager")
        return strategy
    
    def get_instance_ids(self) -> List[UUID]:
        """Get list of active instance IDs."""
        return list(self._strategies.keys())
```

### 2. Create `src/application/services/strategy_instance_service.py`#

```python
"""
StrategyInstance application service.

Handles hot-plug of StrategyInstances into the pipeline.
Follows DDD: Application Layer service.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.domain.strategies.base import StrategyManager, Algorithm
from src.domain.strategies.strategy_instance import (
    StrategyInstance,
    StrategyInstanceState,
)
from src.domain.repositories.strategy_instance_repository import (
    StrategyInstanceRepository,
)
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.repositories.config_set_repository import ConfigSetRepository

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
        # Load instance
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")
        
        # Check if can start
        if not instance.can_start():
            raise ValueError(f"Cannot start instance from state: {instance.status.value}")
        
        # Load strategy (TODO: Implement strategy loading)
        # strategy = await self._strategy_repo.get_by_id(instance.strategy_id)
        
        # Load config set (TODO: Implement config set loading)
        # config_set = await self._config_set_repo.get_by_id(instance.config_set_id)
        
        # Add to strategy manager
        await self._strategy_manager.add_instance(instance)
        
        # Update instance status
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
        # Load instance
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")
        
        # Check if can stop
        if not instance.can_stop():
            raise ValueError(f"Cannot stop instance from state: {instance.status.value}")
        
        # Remove from strategy manager
        await self._strategy_manager.remove_instance(instance_id)
        
        # Update instance status
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
    
    async def get_stats(self, instance_id: UUID) -> Optional[Dict[str, Any]]:
        """Get runtime statistics for an instance."""
        instance = await self._instance_repo.get_by_id(instance_id)
        if not instance:
            return None
        
        return instance.runtime_stats.to_dict()
```

### 3. Update Pipeline to use StrategyInstanceService#

In `src/main.py` or pipeline module:

```python
# Add to pipeline initialization:
from src.application.services.strategy_instance_service import StrategyInstanceService

# Initialize service
instance_service = StrategyInstanceService(
    instance_repo=instance_repo,
    strategy_repo=strategy_repo,
    config_set_repo=config_set_repo,
    strategy_manager=strategy_manager,
)

# When API calls /api/strategy-instances/{id}/start:
# This should call instance_service.hot_plug(instance_id)
```

### 4. `tests/unit/application/services/test_strategy_instance_service.py`#

```python
"""
Unit tests for StrategyInstanceService.

Follows TDD approach: tests first, then implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

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
    manager.add_instance = AsyncMock()
    manager.remove_instance = AsyncMock()
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
    
    @pytest.mark.asyncio
    async def test_hot_plug_success(self, service, instance_repo, strategy_manager, sample_instance):
        """Test successfully hot-plugging an instance."""
        instance_repo.get_by_id.return_value = sample_instance
        
        result = await service.hot_plug(sample_instance.id)
        
        assert result is True
        strategy_manager.add_instance.assert_called_once_with(sample_instance)
        instance_repo.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_hot_plug_not_found(self, service, instance_repo):
        """Test hot-plug with non-existent instance."""
        instance_repo.get_by_id.return_value = None
        
        with pytest.raises(ValueError, match="not found"):
            await service.hot_plug(uuid4())
    
    @pytest.mark.asyncio
    async def test_hot_plug_cannot_start(self, service, instance_repo, sample_instance):
        """Test hot-plug when instance cannot start."""
        from src.domain.strategies.strategy_instance import StrategyInstanceState
        
        sample_instance._status = StrategyInstanceState.RUNNING  # Already running
        
        instance_repo.get_by_id.return_value = sample_instance
        
        with pytest.raises(ValueError, match="Cannot start"):
            await service.hot_plug(sample_instance.id)


class TestUnplug:
    """Tests for unplug method."""
    
    @pytest.mark.asyncio
    async def test_unplug_success(self, service, instance_repo, strategy_manager, sample_instance):
        """Test successfully unplugging an instance."""
        sample_instance._status = StrategyInstanceState.RUNNING
        instance_repo.get_by_id.return_value = sample_instance
        
        result = await service.unplug(sample_instance.id)
        
        assert result is True
        strategy_manager.remove_instance.assert_called_once_with(sample_instance.id)
        instance_repo.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_unplug_not_found(self, service, instance_repo):
        """Test unplug with non-existent instance."""
        instance_repo.get_by_id.return_value = None
        
        with pytest.raises(ValueError, match="not found"):
            await service.unplug(uuid4())


class TestPauseResume:
    """Tests for pause/resume."""
    
    @pytest.mark.asyncio
    async def test_pause_success(self, service, instance_repo, sample_instance):
        """Test pausing a running instance."""
        sample_instance._status = StrategyInstanceState.RUNNING
        instance_repo.get_by_id.return_value = sample_instance
        
        result = await service.pause_instance(sample_instance.id)
        
        assert result is True
        instance_repo.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_resume_success(self, service, instance_repo, sample_instance):
        """Test resuming a paused instance."""
        sample_instance._status = StrategyInstanceState.PAUSED
        instance_repo.get_by_id.return_value = sample_instance
        
        result = await service.resume_instance(sample_instance.id)
        
        assert result is True
        instance_repo.save.assert_called_once()
```

## LLM Implementation Prompt#

```text
You are implementing Step 13 of Phase 4: Pipeline Integration for Hot-Plug.

## Your Task#

Integrate StrategyInstance hot-plug functionality into the running pipeline.

## Context#

- Step 5 complete: StrategyInstance API with start/stop/pause/resume#
- Phase 3 complete: StrategyManager in src/domain/strategies/base.py`

## Requirements#

1. Update `src/domain/strategies/base.py`#
   - Add `add_instance(instance)` method#
   - Add `remove_instance(instance_id)` method#
   - Add `get_instance_ids()` method#

2. Create `src/application/services/strategy_instance_service.py` with:#
   - StrategyInstanceService class#
   - __init__(instance_repo, strategy_repo, config_set_repo, strategy_manager)#
   - hot_plug(instance_id) -> bool:#
     * Load instance from repository#
     * Check can_start()#
     * Add to StrategyManager#
     * Update status to RUNNING#
   - unplug(instance_id) -> bool:#
     * Load instance, check can_stop()#
     * Remove from StrategyManager#
     * Update status to STOPPED#
   - pause_instance(instance_id) -> bool#
   - resume_instance(instance_id) -> bool#
   - get_stats(instance_id) -> Optional[Dict]#

3. Update pipeline (`src/main.py` or pipeline module):#
   - Initialize StrategyInstanceService#
   - Wire up API endpoints to use service methods#

4. Create `tests/unit/application/services/test_strategy_instance_service.py`:#
   - TestHotPlug: success, not found, cannot start#
   - TestUnplug: success, not found#
   - TestPauseResume: pause, resume#
   - Mock all repositories and StrategyManager#

## Constraints#

- Follow AGENTS.md coding standards#
- Use type hints on all public methods (mypy strict)#
- Use Google-style docstrings#
- Line length max 100 characters#
- Log with logger.info(f"message: {e}")#
- All methods must be async where appropriate#

## Acceptance Criteria#

1. StrategyInstanceService can hot-plug instances#
2. StrategyInstanceService can unplug instances#
3. Pause/resume work correctly#
4. StrategyManager updated to handle instances#
5. Pipeline can run without restart when adding/removing instances#
6. All unit tests pass#
7. mypy passes with no errors#
8. ruff check passes with no errors#
9. black formatting applied#

## Commands to Run#

```bash
# Format and lint
black src/application/services/strategy_instance_service.py tests/unit/application/services/test_strategy_instance_service.py
ruff check src/application/services/strategy_instance_service.py tests/unit/application/services/test_strategy_instance_service.py
mypy src/application/services/strategy_instance_service.py

# Run tests
.venv/bin/python -m pytest tests/unit/application/services/test_strategy_instance_service.py -v
```

## Output#

1. List of files created/modified#
2. Test results (passed/failed count)#
3. mypy/ruff output (no errors)#
4. Any issues encountered and how resolved#
```

## Success Criteria#

- [ ] StrategyInstanceService created with all methods#
- [ ] Pipeline integration complete (hot-plug/unplug)#
- [ ] StrategyManager updated to handle instances#
- [ ] All unit tests pass (mocked repositories)#
- [ ] mypy strict mode passes#
- [ ] ruff check passes#
- [ ] black formatting applied#
- [ ] Google-style docstrings on all public methods#