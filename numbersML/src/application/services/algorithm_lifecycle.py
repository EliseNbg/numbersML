"""
Algorithm Lifecycle Service - manages runtime activation/deactivation of algorithms.

Provides high-level operations for managing algorithm lifecycles:
- Activate/deactivate/pause/resume algorithms
- Validate state transitions
- Persist lifecycle events
- Coordinate with AlgorithmRunner

Follows DDD principles: Application layer orchestrating domain objects
and infrastructure services.
"""

import logging
from typing import Any
from uuid import UUID, uuid4

from src.domain.repositories.runtime_event_repository import AlgorithmRuntimeEventRepository
from src.domain.repositories.algorithm_repository import AlgorithmRepository
from src.domain.algorithms.base import (
    Algorithm,
    EnrichedTick,
    Signal,
    AlgorithmManager,
)
from src.domain.algorithms.runtime import (
    AlgorithmLifecycleEvent,
)
from src.domain.algorithms.algorithm_config import AlgorithmDefinition
from src.domain.algorithms.algorithm_instance import (
    VALID_TRANSITIONS,
    AlgorithmInstance,
    AlgorithmInstanceState,
)

logger = logging.getLogger(__name__)


class AlgorithmLifecycleService:
    """Manages algorithm lifecycle operations at runtime.

    Coordinates between:
    - Algorithm definitions (persisted configs)
    - Algorithm runtime states (in-memory)
    - AlgorithmManager (tick processing)
    - Event repository (audit trail)

    Responsibilities:
    1. Validate and execute state transitions
    2. Persist lifecycle events
    3. Manage AlgorithmManager registration
    4. Provide error isolation per algorithm
    """

    # Valid state transitions at the service level
    _ALLOWED_TRANSITIONS = VALID_TRANSITIONS

    def __init__(
        self,
        algorithm_repository: AlgorithmRepository,
        event_repository: AlgorithmRuntimeEventRepository,
        algorithm_manager: AlgorithmManager,
        actor: str = "system",
    ) -> None:
        """Initialize the lifecycle service.

        Args:
            algorithm_repository: Repository for algorithm definitions
            event_repository: Repository for lifecycle events
            algorithm_manager: Manager for active algorithm instances
            actor: Default actor for operations (for audit trail)
        """
        self._algorithm_repo = algorithm_repository
        self._event_repo = event_repository
        self._algorithm_manager = algorithm_manager
        self._actor = actor

        # Runtime state tracking: instance_id -> AlgorithmInstance
        self._instances: dict[UUID, AlgorithmInstance] = {}

        logger.info("AlgorithmLifecycleService initialized")

    async def activate_algorithm(
        self,
        algorithm_id: UUID,
        version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Activate a algorithm (start processing ticks).

        Transitions: STOPPED -> RUNNING

        Args:
            algorithm_id: ID of algorithm to activate
            version: Optional specific version (defaults to active version)
            metadata: Optional metadata for the activation event

        Returns:
            True if activation succeeded

        Raises:
            ValueError: If algorithm doesn't exist or transition is invalid
            RuntimeError: If activation fails
        """
        # Fetch algorithm definition
        algorithm_def = await self._algorithm_repo.get_by_id(algorithm_id)
        if algorithm_def is None:
            raise ValueError(f"Algorithm {algorithm_id} not found")

        # Get or create algorithm instance
        instance = self._instances.get(algorithm_id)
        if instance is None:
            # Load algorithm and create instance
            instance = await self._load_algorithm_instance(
                algorithm_def, version or algorithm_def.current_version
            )
            self._instances[algorithm_id] = instance
        else:
            # Validate transition
            if not instance.can_start():
                raise ValueError(
                    f"Cannot activate algorithm {algorithm_id}: "
                    f"invalid transition from {instance.status.value} to RUNNING"
                )

        # Add to manager (registers for tick processing)
        self._algorithm_manager.add_instance(instance)

        # Start the algorithm
        try:
            instance.start()
        except Exception as e:
            logger.error(f"Failed to start algorithm {algorithm_id}: {e}")
            self._algorithm_manager.remove_instance(algorithm_id)
            raise RuntimeError(f"Algorithm start failed: {e}") from e

        # Record lifecycle event
        old_state = AlgorithmInstanceState.STOPPED
        new_state = instance

        await self._record_lifecycle_event(
            algorithm_def=algorithm_def,
            runtime_state=new_state,
            from_state=old_state,
            to_state=AlgorithmInstanceState.RUNNING,
            trigger="activate",
            details={"version": version or algorithm_def.current_version, **(metadata or {})},
        )

        logger.info(f"Algorithm {algorithm_id} activated")
        return True

    async def deactivate_algorithm(
        self,
        algorithm_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Deactivate a algorithm (stop processing ticks).

        Transitions: RUNNING -> STOPPED

        Args:
            algorithm_id: ID of algorithm to deactivate
            metadata: Optional metadata for the deactivation event

        Returns:
            True if deactivation succeeded

        Raises:
            ValueError: If algorithm not found or transition invalid
        """
        runtime_state = self._instances.get(algorithm_id)
        if runtime_state is None:
            raise ValueError(f"No runtime state for algorithm {algorithm_id}")

        if not runtime_state.can_transition_to(AlgorithmInstanceState.STOPPED):
            raise ValueError(
                f"Cannot deactivate algorithm {algorithm_id}: "
                f"invalid transition from {runtime_state.state.value}"
            )

        algorithm_def = await self._algorithm_repo.get_by_id(algorithm_id)
        old_state = runtime_state.state

        # Remove from manager (stops tick processing)
        removed = self._algorithm_manager.remove_instance(algorithm_id)
        if removed is None:
            logger.warning(f"Algorithm {algorithm_id} not in manager during deactivation")

        # Update state
        new_state = runtime_state.transition_to(AlgorithmInstanceState.STOPPED)
        self._instances[algorithm_id] = new_state

        # Persist event
        if algorithm_def:
            await self._record_lifecycle_event(
                algorithm_def=algorithm_def,
                runtime_state=new_state,
                from_state=old_state,
                to_state=AlgorithmInstanceState.STOPPED,
                trigger="deactivate",
                details=metadata or {},
            )

        logger.info(f"Algorithm {algorithm_id} deactivated")
        return True

    async def pause_algorithm(
        self,
        algorithm_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Pause a running algorithm.

        Transitions: RUNNING -> PAUSED

        Args:
            algorithm_id: ID of algorithm to pause
            metadata: Optional metadata for the pause event

        Returns:
            True if pause succeeded

        Raises:
            ValueError: If algorithm not found or transition invalid
        """
        runtime_state = self._instances.get(algorithm_id)
        if runtime_state is None:
            raise ValueError(f"No runtime state for algorithm {algorithm_id}")

        if not runtime_state.can_transition_to(AlgorithmInstanceState.PAUSED):
            raise ValueError(
                f"Cannot pause algorithm {algorithm_id}: "
                f"invalid transition from {runtime_state.state.value}"
            )

        algorithm_def = await self._algorithm_repo.get_by_id(algorithm_id)
        old_state = runtime_state.state

        # Pause the algorithm instance
        algorithm_instance = self._algorithm_manager.get_instance(algorithm_id)
        if algorithm_instance:
            algorithm_instance.pause()

        # Update state
        new_state = runtime_state.transition_to(AlgorithmInstanceState.PAUSED)
        self._instances[algorithm_id] = new_state

        # Persist event
        if algorithm_def:
            await self._record_lifecycle_event(
                algorithm_def=algorithm_def,
                runtime_state=new_state,
                from_state=old_state,
                to_state=AlgorithmInstanceState.PAUSED,
                trigger="pause",
                details=metadata or {},
            )

        logger.info(f"Algorithm {algorithm_id} paused")
        return True

    async def resume_algorithm(
        self,
        algorithm_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Resume a paused algorithm.

        Transitions: PAUSED -> RUNNING

        Args:
            algorithm_id: ID of algorithm to resume
            metadata: Optional metadata for the resume event

        Returns:
            True if resume succeeded

        Raises:
            ValueError: If algorithm not found or transition invalid
        """
        runtime_state = self._instances.get(algorithm_id)
        if runtime_state is None:
            raise ValueError(f"No runtime state for algorithm {algorithm_id}")

        if not runtime_state.can_transition_to(AlgorithmInstanceState.RUNNING):
            raise ValueError(
                f"Cannot resume algorithm {algorithm_id}: "
                f"invalid transition from {runtime_state.state.value}"
            )

        algorithm_def = await self._algorithm_repo.get_by_id(algorithm_id)
        old_state = runtime_state.state

        # Resume the algorithm instance
        algorithm_instance = self._algorithm_manager.get_instance(algorithm_id)
        if algorithm_instance:
            algorithm_instance.resume()

        # Update state
        new_state = runtime_state.transition_to(AlgorithmInstanceState.RUNNING)
        self._instances[algorithm_id] = new_state

        # Persist event
        if algorithm_def:
            await self._record_lifecycle_event(
                algorithm_def=algorithm_def,
                runtime_state=new_state,
                from_state=old_state,
                to_state=AlgorithmInstanceState.RUNNING,
                trigger="resume",
                details=metadata or {},
            )

        logger.info(f"Algorithm {algorithm_id} resumed")
        return True

    async def record_algorithm_error(
        self,
        algorithm_id: UUID,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record an error for a algorithm and transition to ERROR state.

        Transitions: RUNNING/PAUSED -> ERROR

        Args:
            algorithm_id: ID of algorithm with error
            error: Error description
            metadata: Optional metadata for the error event

        Returns:
            True if error recorded

        Raises:
            ValueError: If algorithm not found
        """
        runtime_state = self._instances.get(algorithm_id)
        if runtime_state is None:
            raise ValueError(f"No runtime state for algorithm {algorithm_id}")

        old_state = runtime_state.state

        # Only transition to ERROR from RUNNING or PAUSED
        if old_state not in (AlgorithmInstanceState.RUNNING, AlgorithmInstanceState.PAUSED):
            logger.warning(
                f"Algorithm {algorithm_id} in state {old_state.value}, " f"not transitioning to ERROR"
            )
            return False

        # Pause algorithm first
        algorithm_instance = self._algorithm_manager.get_instance(algorithm_id)
        if algorithm_instance and old_state == AlgorithmInstanceState.RUNNING:
            algorithm_instance.pause()

        # Update state with error info
        new_state = runtime_state.record_error(error)
        self._instances[algorithm_id] = new_state

        algorithm_def = await self._algorithm_repo.get_by_id(algorithm_id)
        if algorithm_def:
            await self._record_lifecycle_event(
                algorithm_def=algorithm_def,
                runtime_state=new_state,
                from_state=old_state,
                to_state=AlgorithmInstanceState.ERROR,
                trigger="error",
                details={"error": error} | (metadata or {}),
            )

        logger.error(f"Algorithm {algorithm_id} entered ERROR state: {error}")
        return True

    async def get_runtime_state(
        self,
        algorithm_id: UUID,
    ) -> AlgorithmInstance | None:
        """Get current runtime state for a algorithm."""
        return self._instances.get(algorithm_id)

    async def get_all_instances(self) -> list[AlgorithmInstance]:
        """Get runtime states for all algorithms."""
        return list(self._instances.values())

    async def get_lifecycle_events(
        self,
        algorithm_id: UUID,
        limit: int = 100,
    ) -> list[AlgorithmLifecycleEvent]:
        """Get lifecycle events for a algorithm."""
        return await self._event_repo.get_events_for_algorithm(algorithm_id, limit=limit)

    async def _load_algorithm_instance(
        self,
        algorithm_def: AlgorithmDefinition,
        version: int,
    ) -> AlgorithmInstance:
        """Load a algorithm instance from its configuration.

        This is a simplified implementation. In production, this would:
        1. Fetch the versioned config from the repository
        2. Parse the signal config
        3. Instantiate the appropriate algorithm class (RSI, MACD, etc.)
        4. Apply parameters

        Args:
            algorithm_def: Algorithm definition
            version: Config version to use

        Returns:
            AlgorithmInstance with loaded algorithm

        Raises:
            NotImplementedError: If signal type not supported
        """
        # For now, create a generic algorithm based on definition
        from src.domain.algorithms.base import TimeFrame

        class DynamicAlgorithm(Algorithm):
            """Dynamically created algorithm from config."""

            def on_tick(self, tick: EnrichedTick) -> Signal | None:
                # Placeholder: real implementation would use signal config
                return None

        symbols = getattr(algorithm_def, "symbols", ["BTC/USDC"])
        algorithm = DynamicAlgorithm(
            algorithm_id=algorithm_def.id,
            symbols=symbols,
            time_frame=TimeFrame.TICK,
        )

        # Create AlgorithmInstance with the loaded algorithm
        from src.domain.algorithms.algorithm_instance import AlgorithmInstance

        instance = AlgorithmInstance(
            algorithm_id=algorithm_def.id,
            config_set_id=uuid4(),  # TODO: link to actual config set
            status=AlgorithmInstanceState.STOPPED,
        )
        instance._algorithm = algorithm
        return instance

    async def _record_lifecycle_event(
        self,
        algorithm_def: AlgorithmDefinition,
        runtime_state: AlgorithmInstance,
        from_state: AlgorithmInstanceState,
        to_state: AlgorithmInstanceState,
        trigger: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a lifecycle event in the repository."""
        event = AlgorithmLifecycleEvent(
            algorithm_id=algorithm_def.id,
            algorithm_name=algorithm_def.name,
            algorithm_version=algorithm_def.current_version,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            details=details or {},
        )
        await self._event_repo.save(event)

    def get_stats(self) -> dict[str, Any]:
        """Get lifecycle service statistics."""
        states = self._instances.values()
        return {
            "total_algorithms": len(states),
            "running": sum(1 for s in states if s.state == AlgorithmInstanceState.RUNNING),
            "paused": sum(1 for s in states if s.state == AlgorithmInstanceState.PAUSED),
            "stopped": sum(1 for s in states if s.state == AlgorithmInstanceState.STOPPED),
            "error": sum(1 for s in states if s.state == AlgorithmInstanceState.ERROR),
        }
