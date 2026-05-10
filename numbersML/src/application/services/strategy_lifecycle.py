"""
Strategy Lifecycle Service - manages runtime activation/deactivation of strategies.

Provides high-level operations for managing strategy lifecycles:
- Activate/deactivate/pause/resume strategies
- Validate state transitions
- Persist lifecycle events
- Coordinate with StrategyRunner

Follows DDD principles: Application layer orchestrating domain objects
and infrastructure services.
"""

import logging
from typing import Any, cast
from uuid import UUID

from src.application.services.strategy_loader import load_strategy_instance
from src.domain.repositories.runtime_event_repository import StrategyRuntimeEventRepository
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.base import (
    Strategy,
    StrategyManager,
)
from src.domain.strategies.runtime import (
    VALID_TRANSITIONS,
    RuntimeState,
    StrategyLifecycleEvent,
    StrategyRuntimeState,
)
from src.domain.strategies.strategy_config import StrategyDefinition

logger = logging.getLogger(__name__)


class StrategyLifecycleService:
    """Manages strategy lifecycle operations at runtime.

    Coordinates between:
    - Strategy definitions (persisted configs)
    - Strategy runtime states (in-memory)
    - StrategyManager (tick processing)
    - Event repository (audit trail)

    Responsibilities:
    1. Validate and execute state transitions
    2. Persist lifecycle events
    3. Manage StrategyManager registration
    4. Provide error isolation per strategy
    """

    # Valid state transitions at the service level
    _ALLOWED_TRANSITIONS = VALID_TRANSITIONS

    def __init__(
        self,
        strategy_repository: StrategyRepository,
        event_repository: StrategyRuntimeEventRepository,
        strategy_manager: StrategyManager,
        actor: str = "system",
    ) -> None:
        """Initialize the lifecycle service.

        Args:
            strategy_repository: Repository for strategy definitions
            event_repository: Repository for lifecycle events
            strategy_manager: Manager for active strategy instances
            actor: Default actor for operations (for audit trail)
        """
        self._strategy_repo = strategy_repository
        self._event_repo = event_repository
        self._strategy_manager = strategy_manager
        self._actor = actor

        # Runtime state tracking: strategy_id -> StrategyRuntimeState
        self._runtime_states: dict[UUID, StrategyRuntimeState] = {}

        logger.info("StrategyLifecycleService initialized")

    async def activate_strategy(
        self,
        strategy_id: UUID,
        version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Activate a strategy (start processing ticks).

        Transitions: STOPPED -> RUNNING

        Args:
            strategy_id: ID of strategy to activate
            version: Optional specific version (defaults to active version)
            metadata: Optional metadata for the activation event

        Returns:
            True if activation succeeded

        Raises:
            ValueError: If strategy doesn't exist or transition is invalid
            RuntimeError: If activation fails
        """
        # Fetch strategy definition
        strategy_def = await self._strategy_repo.get_by_id(strategy_id)
        if strategy_def is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Get or create runtime state
        runtime_state = self._runtime_states.get(strategy_id)
        if runtime_state is None:
            runtime_state = StrategyRuntimeState(
                strategy_id=strategy_id,
                strategy_name=strategy_def.name,
                state=RuntimeState.STOPPED,
                version=version or strategy_def.current_version,
            )
            self._runtime_states[strategy_id] = runtime_state
        else:
            # Validate transition
            if not runtime_state.can_transition_to(RuntimeState.RUNNING):
                raise ValueError(
                    f"Cannot activate strategy {strategy_id}: "
                    f"invalid transition from {runtime_state.state.value} to RUNNING"
                )

        # Load and register strategy instance
        try:
            strategy_instance = await self._load_strategy_instance(
                strategy_def, runtime_state.version
            )
            self._strategy_manager.add_strategy(strategy_instance)
        except Exception as e:
            logger.error(f"Failed to load strategy {strategy_id}: {e}")
            raise RuntimeError(f"Strategy load failed: {e}") from e

        # Initialize strategy
        try:
            await strategy_instance.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize strategy {strategy_id}: {e}")
            self._strategy_manager.remove_strategy(strategy_id)
            raise RuntimeError(f"Strategy initialization failed: {e}") from e

        # Start the strategy
        try:
            await strategy_instance.start()
        except Exception as e:
            logger.error(f"Failed to start strategy {strategy_id}: {e}")
            self._strategy_manager.remove_strategy(strategy_id)
            raise RuntimeError(f"Strategy start failed: {e}") from e

        # Transition state
        old_state = runtime_state.state
        new_state = runtime_state.transition_to(RuntimeState.RUNNING)
        self._runtime_states[strategy_id] = new_state

        # Persist status change
        strategy_def.status = "active"
        await self._strategy_repo.save(strategy_def)

        # Persist event
        await self._record_lifecycle_event(
            strategy_def=strategy_def,
            runtime_state=new_state,
            from_state=old_state,
            to_state=RuntimeState.RUNNING,
            trigger="activate",
            details={"version": new_state.version, **(metadata or {})},
        )

        logger.info(f"Strategy {strategy_id} activated (version {new_state.version})")
        return True

    async def deactivate_strategy(
        self,
        strategy_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Deactivate a strategy (stop processing ticks).

        Transitions: RUNNING -> STOPPED
        Idempotent: returns True if already STOPPED or no runtime state.

        Args:
            strategy_id: ID of strategy to deactivate
            metadata: Optional metadata for the deactivation event

        Returns:
            True if deactivation succeeded (or already stopped)

        Raises:
            ValueError: If strategy not found
        """
        # Check if strategy exists first
        strategy_def = await self._strategy_repo.get_by_id(strategy_id)
        if strategy_def is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        runtime_state = self._runtime_states.get(strategy_id)
        if runtime_state is None:
            # Strategy exists but never activated — update status and treat as already stopped
            logger.info(f"Strategy {strategy_id} has no runtime state (already stopped)")
            if strategy_def.status == "active":
                strategy_def.status = "validated"
                await self._strategy_repo.save(strategy_def)
                logger.info(f"Strategy {strategy_id} status updated to 'validated'")
            return True

        # Already stopped? Idempotent — treat as success
        if runtime_state.state == RuntimeState.STOPPED:
            logger.info(f"Strategy {strategy_id} already stopped")
            return True

        if not runtime_state.can_transition_to(RuntimeState.STOPPED):
            raise ValueError(
                f"Cannot deactivate strategy {strategy_id}: "
                f"invalid transition from {runtime_state.state.value}"
            )

        old_state = runtime_state.state

        # Remove from manager (stops tick processing)
        removed = self._strategy_manager.remove_strategy(strategy_id)
        if removed is None:
            logger.warning(f"Strategy {strategy_id} not in manager during deactivation")

        # Update state
        new_state = runtime_state.transition_to(RuntimeState.STOPPED)
        self._runtime_states[strategy_id] = new_state

        # Persist status change
        logger.warning(f"[LIFECYCLE] About to save strategy {strategy_id}, current status='{strategy_def.status}'")
        strategy_def.status = "validated"
        logger.warning(f"[LIFECYCLE] Set status to 'validated', now calling save()")
        saved = await self._strategy_repo.save(strategy_def)
        logger.warning(f"[LIFECYCLE] Save completed, returned status='{saved.status}'")

        # Persist event
        await self._record_lifecycle_event(
            strategy_def=strategy_def,
            runtime_state=new_state,
            from_state=old_state,
            to_state=RuntimeState.STOPPED,
            trigger="deactivate",
            details=metadata or {},
        )

        logger.info(f"Strategy {strategy_id} deactivated")
        return True

    async def pause_strategy(
        self,
        strategy_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Pause a running strategy.

        Transitions: RUNNING -> PAUSED
        Idempotent: returns True if already PAUSED or STOPPED.

        Args:
            strategy_id: ID of strategy to pause
            metadata: Optional metadata for the pause event

        Returns:
            True if pause succeeded

        Raises:
            ValueError: If strategy not found
        """
        # Check if strategy exists first
        strategy_def = await self._strategy_repo.get_by_id(strategy_id)
        if strategy_def is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        runtime_state = self._runtime_states.get(strategy_id)
        if runtime_state is None:
            # Strategy exists but never activated — treat as already stopped
            logger.info(f"Strategy {strategy_id} has no runtime state (cannot pause, already stopped)")
            return True

        # Already paused? Idempotent — treat as success
        if runtime_state.state == RuntimeState.PAUSED:
            logger.info(f"Strategy {strategy_id} already paused")
            return True

        if not runtime_state.can_transition_to(RuntimeState.PAUSED):
            raise ValueError(
                f"Cannot pause strategy {strategy_id}: "
                f"invalid transition from {runtime_state.state.value}"
            )

        old_state = runtime_state.state

        # Pause the strategy instance
        strategy_instance = self._strategy_manager.get_strategy(strategy_id)
        if strategy_instance:
            await strategy_instance.pause()

        # Update state
        new_state = runtime_state.transition_to(RuntimeState.PAUSED)
        self._runtime_states[strategy_id] = new_state

        # Persist status change
        strategy_def.status = "paused"
        await self._strategy_repo.save(strategy_def)

        # Persist event
        await self._record_lifecycle_event(
            strategy_def=strategy_def,
            runtime_state=new_state,
            from_state=old_state,
            to_state=RuntimeState.PAUSED,
            trigger="pause",
            details=metadata or {},
        )

        logger.info(f"Strategy {strategy_id} paused")
        return True

    async def resume_strategy(
        self,
        strategy_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Resume a paused strategy.

        Transitions: PAUSED -> RUNNING
        Idempotent: returns True if already RUNNING.

        Args:
            strategy_id: ID of strategy to resume
            metadata: Optional metadata for the resume event

        Returns:
            True if resume succeeded

        Raises:
            ValueError: If strategy not found
        """
        # Check if strategy exists first
        strategy_def = await self._strategy_repo.get_by_id(strategy_id)
        if strategy_def is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        runtime_state = self._runtime_states.get(strategy_id)
        if runtime_state is None:
            # Strategy exists but never activated — treat as already stopped
            logger.info(f"Strategy {strategy_id} has no runtime state (cannot resume, already stopped)")
            return True

        # If already running, treat as success (idempotent)
        if runtime_state.state == RuntimeState.RUNNING:
            logger.info(f"Strategy {strategy_id} already running")
            return True

        if not runtime_state.can_transition_to(RuntimeState.RUNNING):
            raise ValueError(
                f"Cannot resume strategy {strategy_id}: "
                f"invalid transition from {runtime_state.state.value}"
            )

        old_state = runtime_state.state

        # Resume the strategy instance
        strategy_instance = self._strategy_manager.get_strategy(strategy_id)
        if strategy_instance:
            await strategy_instance.resume()

        # Update state
        new_state = runtime_state.transition_to(RuntimeState.RUNNING)
        self._runtime_states[strategy_id] = new_state

        # Persist status change
        strategy_def.status = "active"
        await self._strategy_repo.save(strategy_def)

        # Persist event
        await self._record_lifecycle_event(
            strategy_def=strategy_def,
            runtime_state=new_state,
            from_state=old_state,
            to_state=RuntimeState.RUNNING,
            trigger="resume",
            details=metadata or {},
        )

        logger.info(f"Strategy {strategy_id} resumed")
        return True

    async def record_strategy_error(
        self,
        strategy_id: UUID,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record an error for a strategy and transition to ERROR state.

        Transitions: RUNNING/PAUSED -> ERROR

        Args:
            strategy_id: ID of strategy with error
            error: Error description
            metadata: Optional metadata for the error event

        Returns:
            True if error recorded

        Raises:
            ValueError: If strategy not found
        """
        runtime_state = self._runtime_states.get(strategy_id)
        if runtime_state is None:
            raise ValueError(f"No runtime state for strategy {strategy_id}")

        old_state = runtime_state.state

        # Only transition to ERROR from RUNNING or PAUSED
        if old_state not in (RuntimeState.RUNNING, RuntimeState.PAUSED):
            logger.warning(
                f"Strategy {strategy_id} in state {old_state.value}, " f"not transitioning to ERROR"
            )
            return False

        # Pause strategy first
        strategy_instance = self._strategy_manager.get_strategy(strategy_id)
        if strategy_instance and old_state == RuntimeState.RUNNING:
            await strategy_instance.pause()

        # Update state with error info
        new_state = runtime_state.record_error(error)
        self._runtime_states[strategy_id] = new_state

        strategy_def = await self._strategy_repo.get_by_id(strategy_id)
        if strategy_def:
            await self._record_lifecycle_event(
                strategy_def=strategy_def,
                runtime_state=new_state,
                from_state=old_state,
                to_state=RuntimeState.ERROR,
                trigger="error",
                details={"error": error, **(metadata or {})},
            )

        logger.error(f"Strategy {strategy_id} entered ERROR state: {error}")
        return True

    async def get_runtime_state(
        self,
        strategy_id: UUID,
    ) -> StrategyRuntimeState | None:
        """Get current runtime state for a strategy."""
        return self._runtime_states.get(strategy_id)

    async def get_all_runtime_states(self) -> list[StrategyRuntimeState]:
        """Get runtime states for all strategies."""
        return list(self._runtime_states.values())

    async def get_lifecycle_events(
        self,
        strategy_id: UUID,
        limit: int = 100,
    ) -> list[StrategyLifecycleEvent]:
        """Get lifecycle events for a strategy."""
        return await self._event_repo.get_events_for_strategy(strategy_id, limit=limit)

    async def _load_strategy_instance(
        self,
        strategy_def: StrategyDefinition,
        version: int,
    ) -> Strategy:
        """Load a strategy instance from its configuration.

        Supports two strategy types:
        1. class-based: User-written Python class (strategy_type="class")
        2. config-based: Legacy config-driven strategy (strategy_type="config")

        Args:
            strategy_def: Strategy definition
            version: Config version to use

        Returns:
            Strategy instance

        Raises:
            NotImplementedError: If signal type not supported
            ValueError: If class not found or invalid config
        """
        # Fetch versioned config
        versions = await self._strategy_repo.list_versions(strategy_def.id)
        config_version = next((v for v in versions if v.version == version), None)

        if config_version is None:
            raise ValueError(f"Version {version} not found for strategy {strategy_def.id}")
        return cast(Strategy, load_strategy_instance(strategy_def, config_version))

    async def _record_lifecycle_event(
        self,
        strategy_def: StrategyDefinition,
        runtime_state: StrategyRuntimeState,
        from_state: RuntimeState,
        to_state: RuntimeState,
        trigger: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a lifecycle event in the repository."""
        event = StrategyLifecycleEvent(
            strategy_id=strategy_def.id,
            strategy_name=strategy_def.name,
            strategy_version=runtime_state.version,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            details=details or {},
        )
        await self._event_repo.save(event)

    def get_stats(self) -> dict[str, Any]:
        """Get lifecycle service statistics."""
        states = self._runtime_states.values()
        return {
            "total_strategies": len(states),
            "running": sum(1 for s in states if s.state == RuntimeState.RUNNING),
            "paused": sum(1 for s in states if s.state == RuntimeState.PAUSED),
            "stopped": sum(1 for s in states if s.state == RuntimeState.STOPPED),
            "error": sum(1 for s in states if s.state == RuntimeState.ERROR),
        }
