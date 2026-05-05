"""
Algorithm runtime lifecycle domain events and snapshots.

Provides lifecycle event tracking and runtime snapshots for algorithms.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from src.domain.algorithms.algorithm_instance import AlgorithmInstanceState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlgorithmLifecycleEvent:
    """Domain event for algorithm lifecycle changes.

    Records all state transitions for audit and replay purposes.
    """

    algorithm_id: UUID
    algorithm_name: str
    algorithm_version: int
    from_state: AlgorithmInstanceState
    to_state: AlgorithmInstanceState
    trigger: str  # "system", "api", "error", etc.
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        """Get event type from class name."""
        return self.__class__.__name__
        return "AlgorithmLifecycleEvent"


@dataclass(frozen=True)
class AlgorithmRuntimeSnapshot:
    """Snapshot of algorithm runtime statistics."""

    algorithm_id: UUID
    state: AlgorithmInstanceState
    ticks_processed: int = 0
    signals_generated: int = 0
    orders_placed: int = 0
    error_count: int = 0
    last_tick_at: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
