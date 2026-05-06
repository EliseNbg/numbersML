# Step 4: StrategyInstance Domain Model & Schema

## Objective
Create the `StrategyInstance` domain entity that links a Algorithm with a ConfigurationSet, enabling hot-plug functionality and runtime statistics tracking.

## Context
- Step 1-3 complete: ConfigurationSet entity, repository, and API endpoints exist
- Phase 3 complete: Algorithm domain models exist (`src/domain/algorithms/`)
- Need to link Algorithm + ConfigurationSet for independent operation
- StrategyInstance represents a "deployed" algorithm with specific configuration

## DDD Architecture Decision (ADR)

**Decision**: StrategyInstance is a Domain Entity with state machine
- **Identity**: UUID (not tied to Algorithm or ConfigSet alone)
- **State Machine**: stopped → running → paused → stopped (with error state)
- **Runtime Statistics**: Value object tracking PnL, trades, uptime
- **Lifecycle**: Managed by StrategyInstanceService (Application layer)

**Key Design Patterns**:
- StrategyInstance does NOT contain Algorithm logic (that's in Algorithm entity)
- StrategyInstance references Algorithm by ID and loads config from ConfigurationSet
- Hot-plug: Can start/stop without affecting other instances

**Data Structure**:
```python
StrategyInstance:
    id: UUID
    algorithm_id: UUID  # Reference to Algorithm
    config_set_id: UUID  # Reference to ConfigurationSet
    status: StrategyInstanceState  # stopped, running, paused, error
    runtime_stats: RuntimeStats  # PnL, trades, uptime
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
```

## TDD Approach

1. **Red**: Write failing tests for StrategyInstance and RuntimeStats
2. **Green**: Implement minimal code to pass tests
3. **Refactor**: Add state machine validation, docstrings

## Implementation Files

### 1. `src/domain/algorithms/strategy_instance.py`

```python
"""
StrategyInstance domain entity.

Represents a deployed algorithm with specific configuration.
Links Algorithm (logic) with ConfigurationSet (parameters).

Architecture: Domain Layer (pure Python, no external dependencies)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from src.domain.models.base import Entity


class StrategyInstanceState(str, Enum):
    """Algorithm instance lifecycle states."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


VALID_TRANSITIONS: Dict[StrategyInstanceState, set[StrategyInstanceState]] = {
    StrategyInstanceState.STOPPED: {StrategyInstanceState.RUNNING},
    StrategyInstanceState.RUNNING: {
        StrategyInstanceState.PAUSED,
        StrategyInstanceState.STOPPED,
        StrategyInstanceState.ERROR,
    },
    StrategyInstanceState.PAUSED: {
        StrategyInstanceState.RUNNING,
        StrategyInstanceState.STOPPED,
    },
    StrategyInstanceState.ERROR: {StrategyInstanceState.STOPPED},
}


@dataclass(frozen=True)
class RuntimeStats:
    """
    Immutable runtime statistics for a StrategyInstance.
    
    Tracks PnL, trades, and uptime for monitoring.
    """
    pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    uptime_seconds: float = 0.0
    last_tick_at: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None
    last_error: Optional[str] = None
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate as percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pnl": self.pnl,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "uptime_seconds": self.uptime_seconds,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_signal_at": self.last_signal_at.isoformat() if self.last_signal_at else None,
            "last_error": self.last_error,
        }


class StrategyInstance(Entity):
    """
    Domain entity for algorithm instances.
    
    Links a Algorithm (logic) with a ConfigurationSet (parameters).
    Manages lifecycle state and tracks runtime statistics.
    
    Lifecycle:
        Created → Stopped → Running → Paused → Stopped
        
    Example:
        >>> instance = StrategyInstance(
        ...     algorithm_id=uuid4(),
        ...     config_set_id=uuid4(),
        ... )
        >>> instance.can_start()
        True
        >>> instance.start()
        >>> instance.status
        <StrategyInstanceState.RUNNING: 'running'>
    """
    
    def __init__(
        self,
        algorithm_id: UUID,
        config_set_id: UUID,
        id: UUID = None,
        status: StrategyInstanceState = StrategyInstanceState.STOPPED,
        runtime_stats: Optional[RuntimeStats] = None,
        started_at: Optional[datetime] = None,
        stopped_at: Optional[datetime] = None,
    ) -> None:
        """
        Initialize StrategyInstance.
        
        Args:
            algorithm_id: UUID of the Algorithm
            config_set_id: UUID of the ConfigurationSet
            id: UUID (auto-generated if None)
            status: Initial status (default: STOPPED)
            runtime_stats: Initial runtime stats
            started_at: When instance was started
            stopped_at: When instance was stopped
            
        Raises:
            ValueError: If algorithm_id or config_set_id is None
        """
        super().__init__(id or uuid4())
        
        if not algorithm_id:
            raise ValueError("algorithm_id cannot be None")
        if not config_set_id:
            raise ValueError("config_set_id cannot be None")
        
        self._algorithm_id = algorithm_id
        self._config_set_id = config_set_id
        self._status = status
        self._runtime_stats = runtime_stats or RuntimeStats()
        self._started_at = started_at
        self._stopped_at = stopped_at
        self._created_at = datetime.now(timezone.utc)
        self._updated_at = self._created_at
    
    @property
    def algorithm_id(self) -> UUID:
        """Get algorithm ID."""
        return self._algorithm_id
    
    @property
    def config_set_id(self) -> UUID:
        """Get configuration set ID."""
        return self._config_set_id
    
    @property
    def status(self) -> StrategyInstanceState:
        """Get current status."""
        return self._status
    
    @property
    def runtime_stats(self) -> RuntimeStats:
        """Get runtime statistics (defensive copy not needed - frozen)."""
        return self._runtime_stats
    
    @property
    def started_at(self) -> Optional[datetime]:
        """Get start timestamp."""
        return self._started_at
    
    @property
    def stopped_at(self) -> Optional[datetime]:
        """Get stop timestamp."""
        return self._stopped_at
    
    @property
    def created_at(self) -> datetime:
        """Get creation timestamp."""
        return self._created_at
    
    @property
    def updated_at(self) -> datetime:
        """Get last update timestamp."""
        return self._updated_at
    
    def can_start(self) -> bool:
        """Check if instance can transition to RUNNING."""
        return self._status in VALID_TRANSITIONS.get(StrategyInstanceState.STOPPED, set())
    
    def can_stop(self) -> bool:
        """Check if instance can transition to STOPPED."""
        return self._status in VALID_TRANSITIONS.get(StrategyInstanceState.RUNNING, set()) or \
               self._status in VALID_TRANSITIONS.get(StrategyInstanceState.PAUSED, set())
    
    def can_pause(self) -> bool:
        """Check if instance can transition to PAUSED."""
        return self._status in VALID_TRANSITIONS.get(StrategyInstanceState.RUNNING, set())
    
    def start(self) -> None:
        """
        Start the instance (transition to RUNNING).
        
        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_start():
            raise ValueError(f"Cannot start from state: {self._status.value}")
        
        self._status = StrategyInstanceState.RUNNING
        self._started_at = datetime.now(timezone.utc)
        self._updated_at = self._started_at
    
    def stop(self) -> None:
        """
        Stop the instance (transition to STOPPED).
        
        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_stop():
            raise ValueError(f"Cannot stop from state: {self._status.value}")
        
        self._status = StrategyInstanceState.STOPPED
        self._stopped_at = datetime.now(timezone.utc)
        self._updated_at = self._stopped_at
    
    def pause(self) -> None:
        """
        Pause the instance (transition to PAUSED).
        
        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_pause():
            raise ValueError(f"Cannot pause from state: {self._status.value}")
        
        self._status = StrategyInstanceState.PAUSED
        self._updated_at = datetime.now(timezone.utc)
    
    def resume(self) -> None:
        """
        Resume from paused state (transition to RUNNING).
        
        Raises:
            ValueError: If not currently paused
        """
        if self._status != StrategyInstanceState.PAUSED:
            raise ValueError(f"Cannot resume from state: {self._status.value}")
        
        self._status = StrategyInstanceState.RUNNING
        self._updated_at = datetime.now(timezone.utc)
    
    def record_error(self, error: str) -> None:
        """
        Record an error and transition to ERROR state.
        
        Args:
            error: Error message
        """
        self._status = StrategyInstanceState.ERROR
        self._runtime_stats = RuntimeStats(
            pnl=self._runtime_stats.pnl,
            total_trades=self._runtime_stats.total_trades,
            winning_trades=self._runtime_stats.winning_trades,
            losing_trades=self._runtime_stats.losing_trades,
            uptime_seconds=self._runtime_stats.uptime_seconds,
            last_tick_at=self._runtime_stats.last_tick_at,
            last_signal_at=self._runtime_stats.last_signal_at,
            last_error=error,
        )
        self._updated_at = datetime.now(timezone.utc)
    
    def update_stats(self, **kwargs) -> None:
        """
        Update runtime statistics.
        
        Args:
            **kwargs: Fields to update (pnl, total_trades, etc.)
        """
        self._runtime_stats = RuntimeStats(
            pnl=kwargs.get("pnl", self._runtime_stats.pnl),
            total_trades=kwargs.get("total_trades", self._runtime_stats.total_trades),
            winning_trades=kwargs.get("winning_trades", self._runtime_stats.winning_trades),
            losing_trades=kwargs.get("losing_trades", self._runtime_stats.losing_trades),
            uptime_seconds=kwargs.get("uptime_seconds", self._runtime_stats.uptime_seconds),
            last_tick_at=kwargs.get("last_tick_at", self._runtime_stats.last_tick_at),
            last_signal_at=kwargs.get("last_signal_at", self._runtime_stats.last_signal_at),
            last_error=kwargs.get("last_error", self._runtime_stats.last_error),
        )
        self._updated_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        return {
            "id": str(self.id),
            "algorithm_id": str(self._algorithm_id),
            "config_set_id": str(self._config_set_id),
            "status": self._status.value,
            "runtime_stats": self._runtime_stats.to_dict(),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
            "created_at": self._created_at.isoformat(),
            "updated_at": self._updated_at.isoformat(),
        }
```

### 2. `tests/unit/domain/algorithms/test_strategy_instance.py`

```python
"""
Unit tests for StrategyInstance domain entity.

Follows TDD approach: tests first, then implementation.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID

from src.domain.algorithms.strategy_instance import (
    StrategyInstance,
    StrategyInstanceState,
    RuntimeStats,
)


class TestRuntimeStats:
    """Tests for RuntimeStats value object."""
    
    def test_create_default(self):
        """Test creating default RuntimeStats."""
        stats = RuntimeStats()
        
        assert stats.pnl == 0.0
        assert stats.total_trades == 0
        assert stats.winning_trades == 0
        assert stats.win_rate == 0.0
    
    def test_create_with_values(self):
        """Test creating RuntimeStats with values."""
        stats = RuntimeStats(
            pnl=100.50,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
        )
        
        assert stats.pnl == 100.50
        assert stats.total_trades == 10
        assert stats.winning_trades == 6
        assert stats.losing_trades == 4
        assert stats.win_rate == 60.0  # 6/10 * 100
    
    def test_win_rate_zero_trades(self):
        """Test win rate with zero trades."""
        stats = RuntimeStats(total_trades=0)
        assert stats.win_rate == 0.0
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        stats = RuntimeStats(pnl=50.0, total_trades=5)
        result = stats.to_dict()
        
        assert result["pnl"] == 50.0
        assert result["total_trades"] == 5
        assert "win_rate" in result


class TestStrategyInstanceCreation:
    """Tests for StrategyInstance creation."""
    
    def test_create_valid(self):
        """Test creating a valid StrategyInstance."""
        algorithm_id = uuid4()
        config_set_id = uuid4()
        
        instance = StrategyInstance(
            algorithm_id=algorithm_id,
            config_set_id=config_set_id,
        )
        
        assert isinstance(instance.id, UUID)
        assert instance.algorithm_id == algorithm_id
        assert instance.config_set_id == config_set_id
        assert instance.status == StrategyInstanceState.STOPPED
        assert instance.can_start() is True
    
    def test_create_with_custom_id(self):
        """Test creating with custom UUID."""
        custom_id = uuid4()
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
            id=custom_id,
        )
        
        assert instance.id == custom_id
    
    def test_create_with_status(self):
        """Test creating with specific status."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
            status=StrategyInstanceState.PAUSED,
        )
        
        assert instance.status == StrategyInstanceState.PAUSED
        assert instance.can_start() is False  # Can't start from PAUSED
    
    def test_create_missing_algorithm_id(self):
        """Test that missing algorithm_id raises ValueError."""
        with pytest.raises(ValueError, match="algorithm_id cannot be None"):
            StrategyInstance(
                algorithm_id=None,
                config_set_id=uuid4(),
            )
    
    def test_create_missing_config_set_id(self):
        """Test that missing config_set_id raises ValueError."""
        with pytest.raises(ValueError, match="config_set_id cannot be None"):
            StrategyInstance(
                algorithm_id=uuid4(),
                config_set_id=None,
            )


class TestStrategyInstanceLifecycle:
    """Tests for state transitions."""
    
    def test_start_from_stopped(self):
        """Test starting from STOPPED state."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        
        assert instance.status == StrategyInstanceState.STOPPED
        assert instance.can_start() is True
        
        instance.start()
        
        assert instance.status == StrategyInstanceState.RUNNING
        assert instance.started_at is not None
    
    def test_stop_from_running(self):
        """Test stopping from RUNNING state."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.start()
        
        instance.stop()
        
        assert instance.status == StrategyInstanceState.STOPPED
        assert instance.stopped_at is not None
    
    def test_pause_from_running(self):
        """Test pausing from RUNNING state."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.start()
        
        instance.pause()
        
        assert instance.status == StrategyInstanceState.PAUSED
    
    def test_resume_from_paused(self):
        """Test resuming from PAUSED state."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.start()
        instance.pause()
        
        instance.resume()
        
        assert instance.status == StrategyInstanceState.RUNNING
    
    def test_start_from_running_raises_error(self):
        """Test that starting from RUNNING raises ValueError."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.start()
        
        with pytest.raises(ValueError, match="Cannot start from state"):
            instance.start()
    
    def test_stop_from_stopped_raises_error(self):
        """Test that stopping from STOPPED raises ValueError."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        
        with pytest.raises(ValueError, match="Cannot stop from state"):
            instance.stop()
    
    def test_resume_from_running_raises_error(self):
        """Test that resuming from RUNNING raises ValueError."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.start()
        
        with pytest.raises(ValueError, match="Cannot resume from state"):
            instance.resume()


class TestStrategyInstanceStats:
    """Tests for runtime statistics updates."""
    
    def test_update_stats(self):
        """Test updating runtime statistics."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        
        instance.update_stats(pnl=100.0, total_trades=5, winning_trades=3)
        
        assert instance.runtime_stats.pnl == 100.0
        assert instance.runtime_stats.total_trades == 5
        assert instance.runtime_stats.winning_trades == 3
    
    def test_record_error(self):
        """Test recording an error."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.start()
        
        instance.record_error("Connection failed")
        
        assert instance.status == StrategyInstanceState.ERROR
        assert instance.runtime_stats.last_error == "Connection failed"
    
    def test_stats_preserved_on_error(self):
        """Test that stats are preserved when error recorded."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.update_stats(pnl=50.0, total_trades=2)
        instance.start()
        
        instance.record_error("Test error")
        
        assert instance.runtime_stats.pnl == 50.0
        assert instance.runtime_stats.total_trades == 2


class TestStrategyInstanceSerialization:
    """Tests for to_dict serialization."""
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        
        result = instance.to_dict()
        
        assert "id" in result
        assert "algorithm_id" in result
        assert "config_set_id" in result
        assert "status" in result
        assert "runtime_stats" in result
        assert result["status"] == "stopped"
    
    def test_to_dict_running(self):
        """Test to_dict when instance is running."""
        instance = StrategyInstance(
            algorithm_id=uuid4(),
            config_set_id=uuid4(),
        )
        instance.start()
        
        result = instance.to_dict()
        
        assert result["status"] == "running"
        assert result["started_at"] is not None
```

## LLM Implementation Prompt

```text
You are implementing Step 4 of Phase 4: StrategyInstance Domain Model & Schema.

## Your Task

Create the StrategyInstance domain entity with state machine and runtime statistics.

## Context

- Step 1-3 complete: ConfigurationSet entity, repository, and API exist
- Phase 3 complete: Algorithm domain models in src/domain/algorithms/
- StrategyInstance links Algorithm + ConfigurationSet for deployment
- Must follow DDD Entity pattern (extend base Entity class)

## Requirements

1. Create `src/domain/algorithms/strategy_instance.py` with:
   - StrategyInstanceState enum (STOPPED, RUNNING, PAUSED, ERROR)
   - VALID_TRANSITIONS dict defining allowed state changes
   - RuntimeStats frozen dataclass (pnl, total_trades, win_rate, etc.)
   - StrategyInstance entity class extending Entity base class
   - Properties: algorithm_id, config_set_id, status, runtime_stats, started_at, stopped_at
   - State methods: start(), stop(), pause(), resume(), record_error()
   - Validation methods: can_start(), can_stop(), can_pause()
   - update_stats(**kwargs) for updating runtime statistics
   - to_dict() for serialization
   - Validation in __init__: algorithm_id and config_set_id cannot be None

2. Create `tests/unit/domain/algorithms/test_strategy_instance.py` with TDD:
   - TestRuntimeStats: creation, win_rate calculation, to_dict
   - TestStrategyInstanceCreation: valid/invalid creation, custom ID
   - TestStrategyInstanceLifecycle: start, stop, pause, resume, error transitions
   - TestStrategyInstanceStats: update_stats, record_error
   - TestStrategyInstanceSerialization: to_dict

3. Add database migration `migrations/004_strategy_instances.sql`:
   - CREATE TABLE strategy_instances with all columns
   - Foreign keys to algorithms and configuration_sets
   - UNIQUE constraint on (algorithm_id, config_set_id)
   - Index on status for queries
   - Trigger for updated_at auto-update

## Constraints

- Follow AGENTS.md coding standards
- Use type hints on all public methods (mypy strict)
- Use Google-style docstrings
- No external dependencies in domain layer
- Use relative imports within package
- Line length max 100 characters
- RuntimeStats must be frozen dataclass (immutable)

## Acceptance Criteria

1. StrategyInstance can be created with valid algorithm_id and config_set_id
2. State transitions follow valid state machine
3. Invalid transitions raise ValueError
4. RuntimeStats is immutable and calculates win_rate
5. record_error() transitions to ERROR state
6. to_dict() returns proper serialization
7. All unit tests pass
8. mypy passes with no errors
9. ruff check passes with no errors
10. black formatting applied

## Commands to Run

```bash
# Format and lint
black src/domain/algorithms/strategy_instance.py tests/unit/domain/algorithms/test_strategy_instance.py
ruff check src/domain/algorithms/strategy_instance.py tests/unit/domain/algorithms/test_strategy_instance.py
mypy src/domain/algorithms/strategy_instance.py

# Run tests
.venv/bin/python -m pytest tests/unit/domain/algorithms/test_strategy_instance.py -v
```

## Output

1. List of files created/modified
2. Test results (passed/failed count)
3. mypy/ruff output (no errors)
4. Any issues encountered and how resolved
```

## Success Criteria

- [ ] StrategyInstance entity created with state machine
- [ ] RuntimeStats immutable value object created
- [ ] State transitions validated (can_start, can_stop, etc.)
- [ ] All unit tests pass (TDD approach)
- [ ] mypy strict mode passes
- [ ] ruff check passes (rules: E, W, F, I, N, UP, B, C4)
- [ ] black formatting applied
- [ ] Google-style docstrings on all public methods
- [ ] Follows DDD Entity pattern
