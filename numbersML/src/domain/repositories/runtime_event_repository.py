"""Repository port for algorithm runtime event persistence."""

from abc import abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.repositories.base import Repository
from src.domain.algorithms.runtime import AlgorithmLifecycleEvent


class AlgorithmRuntimeEventRepository(Repository[AlgorithmLifecycleEvent, UUID]):
    """Repository contract for algorithm runtime lifecycle events.

    Persists all state transitions for algorithms during execution.
    Used for audit trails, debugging, and replaying events.
    """

    @abstractmethod
    async def get_events_for_algorithm(
        self,
        algorithm_id: UUID,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        event_types: list[str] | None = None,
        limit: int = 1000,
    ) -> list[AlgorithmLifecycleEvent]:
        """Fetch lifecycle events for a specific algorithm.

        Args:
            algorithm_id: The algorithm to get events for
            from_time: Optional start time filter (inclusive)
            to_time: Optional end time filter (exclusive)
            event_types: Optional filter by event type names
            limit: Maximum number of events to return

        Returns:
            List of lifecycle events, most recent first
        """

    @abstractmethod
    async def get_events_by_type(
        self,
        event_type: str,
        from_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[AlgorithmLifecycleEvent]:
        """Fetch events of a specific type across all algorithms.

        Args:
            event_type: Event type name to filter by
            from_time: Optional start time filter (inclusive)
            limit: Maximum number of events to return

        Returns:
            List of matching events, most recent first
        """

    @abstractmethod
    async def get_current_states(self) -> list[dict[str, Any]]:
        """Get the most recent state for each algorithm.

        Returns:
            List of dicts with algorithm_id, state, and last_state_change
        """

    @abstractmethod
    async def get_error_events(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AlgorithmLifecycleEvent]:
        """Get recent error state transitions.

        Args:
            since: Optional filter for events after this time
            limit: Maximum number of errors to return

        Returns:
            List of error events, most recent first
        """
