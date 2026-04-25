"""
Strategy runtime lifecycle domain models and events.

Provides runtime state tracking, lifecycle events, and state transition
validation for strategies during execution.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Any
from uuid import UUID, uuid4

import logging

logger = logging.getLogger(__name__)


class RuntimeState(str, Enum):
    """Strategy runtime lifecycle states.
    
    These represent the operational state of a strategy instance
    during execution, separate from its persisted status.
    """
    STOPPED = "STOPPED"      # Not running
    RUNNING = "RUNNING"      # Active and processing ticks
    PAUSED = "PAUSED"          # Temporarily suspended
    ERROR = "ERROR"          # Failed state, requires intervention


VALID_TRANSITIONS: Dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.STOPPED: {RuntimeState.RUNNING},
    RuntimeState.RUNNING: {RuntimeState.PAUSED, RuntimeState.STOPPED, RuntimeState.ERROR},
    RuntimeState.PAUSED: {RuntimeState.RUNNING, RuntimeState.STOPPED},
    RuntimeState.ERROR: {RuntimeState.STOPPED},
}


@dataclass
class StrategyRuntimeState:
    """Runtime state of an active strategy instance.
    
    Tracks the operational lifecycle of a strategy during execution.
    Separate from the persisted StrategyDefinition (which is about
    configuration and versioning).
    """
    strategy_id: UUID
    strategy_name: str
    state: RuntimeState = RuntimeState.STOPPED
    version: int = 1
    error_count: int = 0
    last_error: Optional[str] = None
    last_state_change: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_transition_to(self, new_state: RuntimeState) -> bool:
        """Check if transition to new state is valid."""
        return new_state in VALID_TRANSITIONS.get(self.state, set())
    
    def transition_to(self, new_state: RuntimeState) -> "StrategyRuntimeState":
        """Create new state with updated runtime state.
        
        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Invalid state transition: {self.state.value} -> {new_state.value}. "
                f"Valid transitions from {self.state.value}: "
                f"{[s.value for s in VALID_TRANSITIONS.get(self.state, set())]}"
            )
        return StrategyRuntimeState(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            state=new_state,
            version=self.version,
            error_count=self.error_count,
            last_error=self.last_error,
            last_state_change=datetime.now(timezone.utc),
            metadata=self.metadata,
        )
    
    def record_error(self, error: str) -> "StrategyRuntimeState":
        """Record an error and transition to ERROR state."""
        return StrategyRuntimeState(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            state=RuntimeState.ERROR,
            version=self.version,
            error_count=self.error_count + 1,
            last_error=error,
            last_state_change=datetime.now(timezone.utc),
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class StrategyLifecycleEvent:
    """Domain event for strategy lifecycle changes.
    
    Records all state transitions for audit and replay purposes.
    """
    strategy_id: UUID
    strategy_name: str
    strategy_version: int
    from_state: RuntimeState
    to_state: RuntimeState
    trigger: str  # "system", "api", "error", etc.
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def event_type(self) -> str:
        """Get event type from class name."""
        return self.__class__.__name__
        return "StrategyLifecycleEvent"


@dataclass(frozen=True)
class StrategyRuntimeSnapshot:
    """Snapshot of strategy runtime statistics."""
    strategy_id: UUID
    state: RuntimeState
    ticks_processed: int = 0
    signals_generated: int = 0
    orders_placed: int = 0
    error_count: int = 0
    last_tick_at: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
