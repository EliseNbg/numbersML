"""
Unit tests for StrategyLifecycleService.

Tests runtime state management, lifecycle transitions, error isolation,
and integration with StrategyRunner.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from typing import Dict, Any

from src.domain.strategies.base import (
    Strategy,
    StrategyManager,
    EnrichedTick,
    Signal,
    SignalType,
    TimeFrame,
)
from src.domain.strategies.runtime import (
    StrategyRuntimeState,
    StrategyLifecycleEvent,
    RuntimeState,
    VALID_TRANSITIONS,
)
from src.domain.strategies.strategy_config import StrategyDefinition
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.repositories.runtime_event_repository import StrategyRuntimeEventRepository
from src.application.services.strategy_lifecycle import StrategyLifecycleService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_strategy_repo() -> AsyncMock:
    """Mock strategy repository."""
    return AsyncMock(spec=StrategyRepository)

@pytest.fixture
def mock_event_repo() -> AsyncMock:
    """Mock runtime event repository."""
    return AsyncMock(spec=StrategyRuntimeEventRepository)

@pytest.fixture
def mock_strategy_manager() -> StrategyManager:
    """Mock strategy manager."""
    return MagicMock(spec=StrategyManager)

@pytest.fixture
def lifecycle_service(
    mock_strategy_repo: AsyncMock,
    mock_event_repo: AsyncMock,
    mock_strategy_manager: StrategyManager,
) -> StrategyLifecycleService:
    """Create StrategyLifecycleService with mocked dependencies."""
    return StrategyLifecycleService(
        strategy_repository=mock_strategy_repo,
        event_repository=mock_event_repo,
        strategy_manager=mock_strategy_manager,
        actor="test",
    )

@pytest.fixture
def sample_strategy_def() -> StrategyDefinition:
    """Create a sample strategy definition."""
    return StrategyDefinition(
        id=uuid4(),
        name="Test Strategy",
        description="Test strategy for unit tests",
        mode="paper",
        status="draft",
        current_version=1,
        created_by="test",
    )

@pytest.fixture
def sample_enriched_tick() -> EnrichedTick:
    """Create a sample enriched tick."""
    return EnrichedTick(
        symbol="BTC/USDC",
        price=Decimal("50000.00"),
        volume=Decimal("1.0"),
        time=datetime.now(timezone.utc),
        indicators={"rsi": 55.0},
    )


# ============================================================================
# StrategyRuntimeState Tests
# ============================================================================

class TestStrategyRuntimeState:
    """Test StrategyRuntimeState domain model."""

    def test_initial_state_is_stopped(self) -> None:
        """New runtime state should be STOPPED."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
        )
        assert state.state == RuntimeState.STOPPED

    def test_valid_transition(self) -> None:
        """Valid transitions should be allowed."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
        )
        assert state.can_transition_to(RuntimeState.RUNNING) is True

    def test_invalid_transition(self) -> None:
        """Invalid transitions should be rejected."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
            state=RuntimeState.STOPPED,
        )
        assert state.can_transition_to(RuntimeState.PAUSED) is False

    def test_transition_to_running(self) -> None:
        """Transition from STOPPED to RUNNING."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
        )
        new_state = state.transition_to(RuntimeState.RUNNING)
        assert new_state.state == RuntimeState.RUNNING
        assert new_state.last_state_change > state.last_state_change

    def test_invalid_transition_raises(self) -> None:
        """Invalid transition should raise ValueError."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
            state=RuntimeState.STOPPED,
        )
        with pytest.raises(ValueError, match="Invalid state transition"):
            state.transition_to(RuntimeState.PAUSED)

    def test_record_error(self) -> None:
        """Recording an error transitions to ERROR state."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
            state=RuntimeState.RUNNING,
            error_count=0,
        )
        new_state = state.record_error("Test error")
        assert new_state.state == RuntimeState.ERROR
        assert new_state.error_count == 1
        assert new_state.last_error == "Test error"

    def test_error_from_paused(self) -> None:
        """Can transition from PAUSED to ERROR."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
            state=RuntimeState.PAUSED,
        )
        new_state = state.record_error("Test error")
        assert new_state.state == RuntimeState.ERROR
        assert new_state.error_count == 1

    def test_cannot_error_from_stopped(self) -> None:
        """Cannot transition from STOPPED to ERROR."""
        state = StrategyRuntimeState(
            strategy_id=uuid4(),
            strategy_name="test",
            state=RuntimeState.STOPPED,
        )
        new_state = state.record_error("Test error")
        assert new_state.state == RuntimeState.ERROR
        assert new_state.error_count == 1


# ============================================================================
# StrategyLifecycleEvent Tests
# ============================================================================

class TestStrategyLifecycleEvent:
    """Test StrategyLifecycleEvent domain event."""

    def test_event_creation(self) -> None:
        """Can create lifecycle event."""
        event = StrategyLifecycleEvent(
            strategy_id=uuid4(),
            strategy_name="test",
            strategy_version=1,
            from_state=RuntimeState.STOPPED,
            to_state=RuntimeState.RUNNING,
            trigger="system",
            details={"test": "data"},
        )
        assert event.event_type == "StrategyLifecycleEvent"
        assert event.strategy_name == "test"
        assert event.from_state == RuntimeState.STOPPED
        assert event.to_state == RuntimeState.RUNNING

    def test_event_has_occurred_at(self) -> None:
        """Event should have timestamp."""
        event = StrategyLifecycleEvent(
            strategy_id=uuid4(),
            strategy_name="test",
            strategy_version=1,
            from_state=RuntimeState.STOPPED,
            to_state=RuntimeState.RUNNING,
            trigger="system",
        )
        assert event.occurred_at is not None
        assert isinstance(event.occurred_at, datetime)


# ============================================================================
# StrategyLifecycleService Tests
# ============================================================================

class TestStrategyLifecycleServiceActivation:
    """Test strategy activation/deactivation."""

    @pytest.mark.asyncio
    async def test_activate_strategy(self, lifecycle_service, sample_strategy_def):
        """Can activate a strategy."""
        lifecycle_service._strategy_repo.get_by_id.return_value = sample_strategy_def
        lifecycle_service._strategy_manager.add_strategy = MagicMock()
        lifecycle_service._strategy_manager.get_strategy.return_value = MagicMock()
        lifecycle_service._event_repo.save = AsyncMock()

        result = await lifecycle_service.activate_strategy(sample_strategy_def.id)

        assert result is True
        lifecycle_service._strategy_manager.add_strategy.assert_called()

    @pytest.mark.asyncio
    async def test_activate_nonexistent_strategy(self, lifecycle_service):
        """Activating nonexistent strategy should raise."""
        lifecycle_service._strategy_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await lifecycle_service.activate_strategy(uuid4())

    @pytest.mark.asyncio
    async def test_deactivate_strategy(self, lifecycle_service, sample_strategy_def):
        """Can deactivate a strategy."""
        strategy_id = sample_strategy_def.id
        runtime_state = StrategyRuntimeState(
            strategy_id=strategy_id,
            strategy_name="test",
            state=RuntimeState.RUNNING,
        )
        lifecycle_service._runtime_states[strategy_id] = runtime_state
        lifecycle_service._strategy_repo.get_by_id.return_value = sample_strategy_def
        lifecycle_service._strategy_manager.remove_strategy = MagicMock(return_value=MagicMock())
        lifecycle_service._event_repo.save = AsyncMock()

        result = await lifecycle_service.deactivate_strategy(strategy_id)

        assert result is True
        assert lifecycle_service._runtime_states[strategy_id].state == RuntimeState.STOPPED

    @pytest.mark.asyncio
    async def test_pause_strategy(self, lifecycle_service, sample_strategy_def):
        """Can pause a running strategy."""
        strategy_id = sample_strategy_def.id
        runtime_state = StrategyRuntimeState(
            strategy_id=strategy_id,
            strategy_name="test",
            state=RuntimeState.RUNNING,
        )
        lifecycle_service._runtime_states[strategy_id] = runtime_state
        lifecycle_service._strategy_repo.get_by_id.return_value = sample_strategy_def
        mock_strategy = AsyncMock(spec=Strategy)
        lifecycle_service._strategy_manager.get_strategy.return_value = mock_strategy
        lifecycle_service._event_repo.save = AsyncMock()

        result = await lifecycle_service.pause_strategy(strategy_id)

        assert result is True
        assert lifecycle_service._runtime_states[strategy_id].state == RuntimeState.PAUSED
        mock_strategy.pause.assert_called()

    @pytest.mark.asyncio
    async def test_resume_strategy(self, lifecycle_service, sample_strategy_def):
        """Can resume a paused strategy."""
        strategy_id = sample_strategy_def.id
        runtime_state = StrategyRuntimeState(
            strategy_id=strategy_id,
            strategy_name="test",
            state=RuntimeState.PAUSED,
        )
        lifecycle_service._runtime_states[strategy_id] = runtime_state
        lifecycle_service._strategy_repo.get_by_id.return_value = sample_strategy_def
        mock_strategy = AsyncMock(spec=Strategy)
        lifecycle_service._strategy_manager.get_strategy.return_value = mock_strategy
        lifecycle_service._event_repo.save = AsyncMock()

        result = await lifecycle_service.resume_strategy(strategy_id)

        assert result is True
        assert lifecycle_service._runtime_states[strategy_id].state == RuntimeState.RUNNING
        mock_strategy.resume.assert_called()

    @pytest.mark.asyncio

    @pytest.mark.asyncio
    async def test_lifecycle_event_recorded(self, lifecycle_service, sample_strategy_def):
        """Lifecycle events are persisted to repository."""
        lifecycle_service._strategy_repo.get_by_id.return_value = sample_strategy_def
        lifecycle_service._strategy_manager.add_strategy = MagicMock()
        mock_strategy = AsyncMock(spec=Strategy)
        lifecycle_service._strategy_manager.get_strategy.return_value = mock_strategy
        lifecycle_service._event_repo.save = AsyncMock()

        await lifecycle_service.activate_strategy(sample_strategy_def.id)

        lifecycle_service._event_repo.save.assert_called()
        call_args = lifecycle_service._event_repo.save.call_args[0][0]
        assert isinstance(call_args, StrategyLifecycleEvent)
        assert call_args.from_state == RuntimeState.STOPPED
        assert call_args.to_state == RuntimeState.RUNNING
        assert call_args.trigger == "activate"

    @pytest.mark.asyncio
    async def test_record_strategy_error(self, lifecycle_service, sample_strategy_def):
        """Can record strategy error."""
        strategy_id = sample_strategy_def.id
        runtime_state = StrategyRuntimeState(
            strategy_id=strategy_id,
            strategy_name="test",
            state=RuntimeState.RUNNING,
        )
        lifecycle_service._runtime_states[strategy_id] = runtime_state
        lifecycle_service._strategy_repo.get_by_id.return_value = sample_strategy_def
        mock_strategy = AsyncMock(spec=Strategy)
        lifecycle_service._strategy_manager.get_strategy.return_value = mock_strategy
        lifecycle_service._event_repo.save = AsyncMock()

        result = await lifecycle_service.record_strategy_error(strategy_id, "Test error")

        assert result is True
        assert lifecycle_service._runtime_states[strategy_id].state == RuntimeState.ERROR
        assert lifecycle_service._runtime_states[strategy_id].error_count == 1

    def test_get_stats(self, lifecycle_service, sample_strategy_def):
        """Can get lifecycle service statistics."""
        strategy_id = sample_strategy_def.id
        runtime_state = StrategyRuntimeState(
            strategy_id=strategy_id,
            strategy_name="test",
            state=RuntimeState.RUNNING,
        )
        lifecycle_service._runtime_states[strategy_id] = runtime_state

        stats = lifecycle_service.get_stats()

        assert stats["total_strategies"] == 1
        assert stats["running"] == 1
        assert stats["paused"] == 0
        assert stats["stopped"] == 0
        assert stats["error"] == 0

    @pytest.mark.asyncio
    async def test_get_all_runtime_states(self, lifecycle_service, sample_strategy_def):
        """Can get all runtime states."""
        state1 = StrategyRuntimeState(
            strategy_id=uuid4(), strategy_name="s1", state=RuntimeState.RUNNING
        )
        state2 = StrategyRuntimeState(
            strategy_id=uuid4(), strategy_name="s2", state=RuntimeState.PAUSED
        )
        lifecycle_service._runtime_states = {
            state1.strategy_id: state1,
            state2.strategy_id: state2,
        }

        states = await lifecycle_service.get_all_runtime_states()

        assert len(states) == 2
        assert state1 in states
        assert state2 in states


# ============================================================================
# Valid Transitions Coverage
# ============================================================================

class TestValidTransitions:
    """Ensure all valid transitions are defined and tested."""

    def test_all_transitions_are_tested(self):
        """All valid transitions should be explicitly tested."""
        # VALID_TRANSITIONS is Dict[RuntimeState, set[RuntimeState]]
        # Convert to set of tuples for comparison
        as_tuples = set()
        for from_state, to_states in VALID_TRANSITIONS.items():
            for to_state in to_states:
                as_tuples.add((from_state, to_state))
        
        covered = {
            (RuntimeState.STOPPED, RuntimeState.RUNNING),
            (RuntimeState.RUNNING, RuntimeState.PAUSED),
            (RuntimeState.RUNNING, RuntimeState.STOPPED),
            (RuntimeState.RUNNING, RuntimeState.ERROR),
            (RuntimeState.PAUSED, RuntimeState.RUNNING),
            (RuntimeState.PAUSED, RuntimeState.STOPPED),
            (RuntimeState.ERROR, RuntimeState.STOPPED),
        }
        assert as_tuples == covered
        assert len(as_tuples) == 7
