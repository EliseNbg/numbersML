# Step 3 Implementation Summary: Strategy Runtime Lifecycle

## Overview
Implemented Step 3 of Phase 3: Strategy Runtime and Lifecycle Management for the crypto trading pipeline.

## Files Created

### 1. `src/domain/strategies/runtime.py`
- **StrategyRuntimeState**: Entity tracking runtime state of strategy instances
  - States: STOPPED, RUNNING, PAUSED, ERROR
  - Tracks errors, last state change, metadata
  - Validates state transitions via VALID_TRANSITIONS
  - Methods: `transition_to()`, `record_error()`

- **StrategyLifecycleEvent**: Domain event for audit trail
  - Records all state transitions (from_state → to_state)
  - Immutable (frozen dataclass)
  - Includes trigger, details, timestamp

- **VALID_TRANSITIONS**: State machine definition
  - STOPPED → RUNNING
  - RUNNING → PAUSED, STOPPED, ERROR  
  - PAUSED → RUNNING, STOPPED
  - ERROR → STOPPED

### 2. `src/domain/repositories/runtime_event_repository.py`
- **StrategyRuntimeEventRepository**: Repository port for lifecycle events
  - Persists events to PostgreSQL (strategy_events table)
  - Query methods: by strategy, by type, error events, current states
  - Append-only (events are immutable audit records)

### 3. `src/infrastructure/repositories/runtime_event_repository_pg.py`
- **StrategyRuntimeEventRepositoryPG**: PostgreSQL implementation
  - Uses asyncpg for database operations
  - Maps DB rows to StrategyLifecycleEvent objects
  - Supports filtering by time range and event type

### 4. `src/application/services/strategy_lifecycle.py`
- **StrategyLifecycleService**: Application service for lifecycle management
  
  **Core Operations:**
  - `activate_strategy()`: STOPPED → RUNNING (load, init, start strategy)
  - `deactivate_strategy()`: RUNNING → STOPPED (stop, remove strategy)
  - `pause_strategy()`: RUNNING → PAUSED (pause strategy)
  - `resume_strategy()`: PAUSED → RUNNING (resume strategy)
  - `record_strategy_error()`: RUNNING/PAUSED → ERROR (error isolation)
  
  **Features:**
  - Validates state transitions before execution
  - Persists lifecycle events to repository
  - Coordinates with StrategyManager
  - Per-strategy error tracking
  - Strategy instance loading from config

### 5. `src/application/services/strategy_runner_enhanced.py`
- **EnhancedStrategyRunner**: Extends StrategyRunner with lifecycle integration
  
  **Enhancements:**
  - Per-strategy error isolation (exceptions don't crash runner)
  - Coordinates with StrategyLifecycleService
  - Tracks runtime states
  - Graceful cancellation with asyncio task management
  - Risk rule integration points

### 6. `tests/unit/application/services/test_strategy_lifecycle.py`
- Comprehensive test suite (20 tests)
- Tests for state transitions, error isolation, lifecycle events
- Mock-based unit tests with AsyncMock

## Files Modified

### `src/domain/strategies/base.py`
- Updated `StrategyManager.remove_strategy()` parameter type: `str` → `UUID`
- Updated `StrategyManager.get_strategy()` parameter type: `str` → `UUID`  
- Updated `StrategyManager.list_strategies()` return type: `List[str]` → `List[UUID]`
- Added `from uuid import UUID` import

### `src/domain/strategies/__init__.py`
- Exported new runtime classes: StrategyRuntimeState, StrategyLifecycleEvent, RuntimeState, VALID_TRANSITIONS
- Exported strategy config classes: StrategyDefinition, StrategyConfigVersion

## Key Design Decisions

1. **Separation of Concerns**: StrategyRuntimeState tracks runtime state separately from persisted StrategyDefinition. This allows activation/deactivation without modifying persisted config.

2. **Event Sourcing Pattern**: All lifecycle changes recorded as immutable StrategyLifecycleEvent objects. Enables audit trail, debugging, and potential replay.

3. **Error Isolation**: Each strategy's exceptions are caught and recorded individually. A failing strategy doesn't affect others.

4. **State Machine**: Explicit VALID_TRANSITIONS ensures only valid state changes (e.g., can't pause a stopped strategy).

5. **DDD Layers**: 
   - **Domain**: StrategyRuntimeState, StrategyLifecycleEvent, RuntimeState
   - **Repository Ports**: StrategyRuntimeEventRepository  
   - **Infrastructure**: StrategyRuntimeEventRepositoryPG
   - **Application**: StrategyLifecycleService, EnhancedStrategyRunner

## Acceptance Criteria Met

✅ **Toggle strategy state while system is running**: activate/deactivate/pause/resume operations

✅ **Deactivated strategy cannot emit new orders**: Removed from StrategyManager, stops processing ticks

✅ **Single strategy failure does not crash global runner**: Per-strategy error isolation in EnhancedStrategyRunner

✅ **Write strategy lifecycle events to audit stream/table**: StrategyLifecycleEvent persisted to strategy_events table

✅ **Lifecycle service with strict state transition rules**: VALID_TRANSITIONS validation in StrategyRuntimeState

✅ **StrategyRunner that subscribes/processes market events**: EnhancedStrategyRunner extends existing StrategyRunner

✅ **Error isolation and graceful shutdown logic**: Per-strategy try/except, asyncio task cancellation handling

## Testing

- 139 tests pass (unit tests)
- 496 unit tests pass (full suite)
- 15 integration tests pass (existing)
- All new lifecycle tests: 20/20 pass
- No regressions in existing code

## Database Schema

Uses existing `strategy_events` table from Step 1 migrations:
```sql
CREATE TABLE strategy_events (
    id UUID PRIMARY KEY,
    strategy_id UUID REFERENCES strategies(id),
    strategy_version_id UUID REFERENCES strategy_versions(id),
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

## Usage Example

```python
# Create lifecycle service
lifecycle = StrategyLifecycleService(
    strategy_repository=repo,
    event_repository=event_repo,
    strategy_manager=strategy_manager,
    actor="trader"
)

# Activate a strategy
await lifecycle.activate_strategy(strategy_id)

# Process ticks (via EnhancedStrategyRunner)
runner = EnhancedStrategyRunner(lifecycle_service=lifecycle)
await runner.start()

# Pause a strategy
await lifecycle.pause_strategy(strategy_id)

# Resume
await lifecycle.resume_strategy(strategy_id)

# Deactivate
await lifecycle.deactivate_strategy(strategy_id)
```

## Next Steps (Out of Scope for Step 3)

- REST API endpoints (Step 5)
- Dashboard GUI (Step 6)
- Backtest engine (Step 7)
- Risk rule enforcement (integration with MarketService)
