# Step 10: Strategy Runner & Pipeline Orchestration

## Objective

Integrate strategy execution into the real-time trade pipeline with hot-plug capability, parallel execution, stdout collection, and a management GUI for monitoring running strategies, signals, and cleanup.

## Scope

This step is split into **4 sub-steps** for manageable implementation:

- **10A**: Strategy Runner — core orchestration engine integrated into pipeline
- **10B**: Hot-Plug Manager — dynamic activate/deactivate without restart
- **10C**: Stdout Collector & Signal Aggregator — capture strategy output
- **10D**: Strategy Management GUI — web dashboard for strategy monitoring

---

## 10A: Strategy Runner — Core Orchestration Engine

### Architecture

The Strategy Runner sits as **Step 5** in the pipeline (`PipelineStep.STRATEGY`), executing after wide vector generation. It loads active strategies from the database and runs them in parallel against each symbol's tick data.

```
Pipeline Flow:
  Step 1 (candle) → Step 2 (indicators) → Step 3 (vector) → Step 4 (ML) → Step 5 (STRATEGY RUNNER)
                                                                                ↓
                                                                    ┌─────────────────────┐
                                                                    │  StrategyRunner     │
                                                                    │  ┌───────┐ ┌──────┐ │
                                                                    │  │Strat A │ │StratB│ │ ← parallel
                                                                    │  └───────┘ └──────┘ │
                                                                    │  ┌───────┐ ┌──────┐ │
                                                                    │  │Strat C │ │StratD│ │
                                                                    │  └───────┘ └──────┘ │
                                                                    └─────────────────────┘
                                                                                ↓
                                                                    Signal → MarketService.place_order()
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/pipeline/strategy_runner.py` | **NEW** | Core `StrategyRunner` class |
| `src/pipeline/strategy_executor.py` | **NEW** | Per-strategy async executor with isolation |
| `src/pipeline/service.py` | **MODIFY** | Add `StrategyRunner` to pipeline, add `PipelineStep.STRATEGY` |
| `src/pipeline/ticket.py` | **MODIFY** | Add `STRATEGY = 5` to `PipelineStep` enum, add to `LIVE_STEPS` |
| `src/domain/strategies/signal.py` | **NEW** | `TradeSignal` dataclass (domain model) |
| `tests/unit/pipeline/test_strategy_runner.py` | **NEW** | Unit tests for runner |
| `tests/unit/pipeline/test_strategy_executor.py` | **NEW** | Unit tests for executor |

### `TradeSignal` Domain Model

```python
@dataclass(frozen=True)
class TradeSignal:
    """Signal emitted by a strategy."""
    signal_id: UUID
    strategy_id: UUID
    strategy_name: str
    symbol: str
    side: OrderSide  # BUY or SELL
    order_type: OrderType  # MARKET or LIMIT
    quantity: Decimal
    price: Decimal | None  # None for MARKET orders
    timestamp: datetime
    metadata: dict[str, Any]  # e.g., expected_profit_price, reason, indicators_used
    status: SignalStatus  # PENDING, EXECUTED, REJECTED, FAILED
```

### `StrategyRunner` Class

```python
class StrategyRunner:
    """
    Orchestrates parallel strategy execution within the pipeline.

    - Loads active strategies from DB on each tick (or cached with refresh)
    - Runs each strategy in its own asyncio.Task for isolation
    - Collects signals and routes them to MarketService
    - Captures stdout/stderr from strategies
    - Logs every 500 ticks per strategy
    """

    async def execute_tick(
        self,
        symbol: str,
        candle_time: datetime,
        tick_indicators: dict[str, float],
        current_price: Decimal,
    ) -> list[TradeSignal]:
        """Run all active strategies for a symbol tick. Returns signals."""

    async def load_active_strategies(self) -> list[StrategyContext]:
        """Query DB for strategies with status='active'."""

    async def hot_reload(self) -> None:
        """Re-scan DB for strategy changes without restart."""
```

### `StrategyExecutor` Class

```python
class StrategyExecutor:
    """
    Executes a single strategy with full isolation.

    - Wraps strategy.on_tick() in try/except
    - Captures stdout/stderr via context manager
    - Enforces per-strategy timeout (default 500ms)
    - Returns TradeSignal or error
    """

    async def execute(
        self,
        strategy: BaseStrategy,
        symbol: str,
        tick_data: TickData,
    ) -> StrategyResult:
        """Execute strategy.on_tick() with isolation and stdout capture."""
```

### Key Design Decisions

1. **Parallel execution**: Each strategy runs in its own `asyncio.Task` via `asyncio.gather(..., return_exceptions=True)` — one failure doesn't crash others.
2. **Timeout per strategy**: 500ms default, configurable via `strategy_config`. Prevents slow strategies from blocking the pipeline.
3. **Stdout capture**: Use `contextlib.redirect_stdout` + `io.StringIO` to capture print statements from strategies. Store in `StrategyContext.stdout_buffer`.
4. **Signal deduplication**: Same strategy + symbol + side within 60 seconds = deduplicate (configurable).
5. **MarketService integration**: Signals are passed to `MarketService.place_order()` via the factory-built service (paper/live based on strategy mode).
6. **DB persistence**: Every signal is written to `strategy_signals` table (new migration).

### Database Migration: `strategy_signals` Table

```sql
CREATE TABLE strategy_signals (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    strategy_id UUID NOT NULL REFERENCES strategies(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
    quantity NUMERIC(20,10) NOT NULL,
    price NUMERIC(20,10),
    status TEXT NOT NULL DEFAULT 'PENDING',
    metadata JSONB DEFAULT '{}',
    stdout_capture TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX idx_strategy_signals_strategy ON strategy_signals(strategy_id);
CREATE INDEX idx_strategy_signals_symbol ON strategy_signals(symbol);
CREATE INDEX idx_strategy_signals_created ON strategy_signals(created_at DESC);
```

### Tests for 10A

| Test | Description |
|------|-------------|
| `test_execute_single_strategy_returns_signal` | Happy path: strategy emits BUY signal |
| `test_execute_multiple_strategies_in_parallel` | 3 strategies run concurrently, all signals collected |
| `test_strategy_failure_does_not_crash_others` | Strategy A raises, B and C still execute |
| `test_strategy_timeout_kills_slow_strategy` | Strategy takes >500ms, gets killed, others proceed |
| `test_stdout_capture_from_strategy` | Strategy prints, stdout is captured and stored |
| `test_signal_deduplication` | Same signal within 60s is deduplicated |
| `test_no_active_strategies_returns_empty` | No active strategies → empty list |
| `test_market_order_signal_has_no_price` | MARKET signal price is None |
| `test_limit_order_signal_has_price` | LIMIT signal has price from metadata |
| `test_signal_persisted_to_db` | Signal written to `strategy_signals` table |

---

## 10B: Hot-Plug Manager

### Purpose

Dynamically activate/deactivate strategies at runtime without restarting the pipeline or services.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/application/services/strategy_lifecycle_service.py` | **NEW** | `StrategyLifecycleService` for CRUD + state transitions |
| `src/pipeline/strategy_runner.py` | **MODIFY** | Add `hot_reload()` method, reactive strategy list |
| `src/infrastructure/api/routes/strategies.py` | **MODIFY** | Add activate/deactivate endpoints |
| `tests/unit/services/test_strategy_lifecycle.py` | **NEW** | Lifecycle state transition tests |

### State Machine

```
draft → validated → active → paused → active
                          ↓
                       archived
```

### Hot-Reload Mechanism

```python
class StrategyRunner:
    def __init__(self, ...):
        self._strategies: dict[UUID, StrategyContext] = {}
        self._reload_interval = 5.0  # seconds
        self._last_reload = 0.0
        self._lock = asyncio.Lock()

    async def execute_tick(self, ...):
        # Check if reload needed (every 5 seconds)
        if time.time() - self._last_reload > self._reload_interval:
            await self.hot_reload()
        # Execute with current strategy list
        ...

    async def hot_reload(self):
        """Compare DB active strategies with in-memory list.
        - Add newly activated strategies
        - Remove deactivated strategies (graceful stop)
        - Update config for changed strategies
        """
        async with self._lock:
            db_strategies = await self._load_active_strategies()
            # Diff and update
            for sid in self._strategies.keys() - db_strategies.keys():
                await self._stop_strategy(sid)
            for sid in db_strategies.keys() - self._strategies.keys():
                await self._start_strategy(sid, db_strategies[sid])
            self._last_reload = time.time()
```

### Tests for 10B

| Test | Description |
|------|-------------|
| `test_activate_strategy_adds_to_runner` | Activate → strategy appears in runner |
| `test_deactivate_strategy_removes_from_runner` | Deactivate → strategy removed gracefully |
| `test_hot_reload_detects_db_changes` | DB change detected within 5s |
| `test_concurrent_activate_deactivate` | Race condition handled safely |
| `test_deactivated_strategy_cannot_emit_signals` | Deactivated strategy signals are dropped |
| `test_state_transition_matrix` | All valid/invalid transitions tested |

---

## 10C: Stdout Collector & Signal Aggregator

### Purpose

Collect stdout from running strategies and aggregate signals for the GUI.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/pipeline/stdout_collector.py` | **NEW** | `StdoutCollector` class with per-strategy buffers |
| `src/pipeline/signal_aggregator.py` | **NEW** | `SignalAggregator` for recent signal history |
| `src/infrastructure/api/routes/signals.py` | **NEW** | API endpoints for signals and stdout |
| `tests/unit/pipeline/test_stdout_collector.py` | **NEW** | Tests for stdout capture |
| `tests/unit/pipeline/test_signal_aggregator.py` | **NEW** | Tests for signal history |

### `StdoutCollector`

```python
class StdoutCollector:
    """Thread-safe stdout collector per strategy."""

    MAX_BUFFER_SIZE = 100_000  # chars per strategy
    MAX_LINES = 1000

    def capture(self, strategy_id: UUID, text: str) -> None:
        """Append captured text to strategy buffer."""

    def get_output(self, strategy_id: UUID, limit: int = 100) -> list[str]:
        """Get last N lines of stdout for a strategy."""

    def clear(self, strategy_id: UUID) -> None:
        """Clear stdout buffer for a strategy."""
```

### `SignalAggregator`

```python
class SignalAggregator:
    """In-memory cache of recent signals for fast GUI access."""

    MAX_HISTORY = 500  # per strategy

    def add_signal(self, signal: TradeSignal) -> None:
        """Add signal to history."""

    def get_recent(self, strategy_id: UUID | None = None,
                   symbol: str | None = None,
                   limit: int = 50) -> list[TradeSignal]:
        """Get recent signals with optional filters."""

    def get_stats(self, strategy_id: UUID) -> SignalStats:
        """Get signal statistics for a strategy."""
```

### Tests for 10C

| Test | Description |
|------|-------------|
| `test_capture_and_retrieve_stdout` | Capture text, retrieve it |
| `test_buffer_size_limit` | Buffer doesn't exceed MAX_BUFFER_SIZE |
| `test_get_recent_signals` | Retrieve last N signals |
| `test_filter_signals_by_strategy` | Filter by strategy_id |
| `test_filter_signals_by_symbol` | Filter by symbol |
| `test_signal_stats_calculation` | Correct buy/sell counts |
| `test_concurrent_capture` | Thread-safe under concurrent writes |

---

## 10D: Strategy Management GUI

### Purpose

Web dashboard showing running strategies, their status, stdout, and generated signals. Plus cleanup functionality.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/infrastructure/api/routes/strategies_gui.py` | **NEW** | GUI-specific API endpoints |
| `src/infrastructure/web/gui/` | **NEW** | Static HTML/CSS/JS files for dashboard |
| `src/application/services/cleanup_service.py` | **NEW** | Cleanup service for artifacts |
| `tests/unit/services/test_cleanup_service.py` | **NEW** | Cleanup tests |

### GUI API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/strategies/dashboard` | GET | Full dashboard state (strategies, status, signals count) |
| `/api/strategies/{id}/stdout` | GET | Get stdout for a strategy |
| `/api/strategies/{id}/stdout/clear` | POST | Clear stdout buffer |
| `/api/strategies/{id}/signals` | GET | Get signals for a strategy |
| `/api/strategies/{id}/stats` | GET | Get strategy statistics |
| `/api/strategies/cleanup` | POST | Clean up artifacts (DB + disk) |

### Dashboard Data Model

```json
{
  "strategies": [
    {
      "id": "uuid",
      "name": "MACD Buy Strategy",
      "status": "active",
      "mode": "paper",
      "symbol": "BTC/USDC",
      "signals_today": 12,
      "last_signal_at": "2026-05-17T10:30:00Z",
      "uptime_seconds": 3600,
      "errors_last_hour": 0,
      "stdout_lines": 150
    }
  ],
  "recent_signals": [
    {
      "signal_id": "uuid",
      "strategy_name": "MACD Buy Strategy",
      "symbol": "BTC/USDC",
      "side": "BUY",
      "price": 67500.00,
      "quantity": 100.0,
      "status": "EXECUTED",
      "timestamp": "2026-05-17T10:30:00Z"
    }
  ],
  "pipeline_status": {
    "is_running": true,
    "symbols_count": 4,
    "active_strategies_count": 3
  }
}
```

### Cleanup Service

```python
class CleanupService:
    """Clean up strategy artifacts from DB and disk."""

    async def cleanup_strategy(self, strategy_id: UUID,
                               delete_signals: bool = True,
                               delete_stdout: bool = True,
                               delete_backtests: bool = False) -> CleanupResult:
        """Remove all artifacts for a strategy."""

    async def cleanup_all_stopped(self, older_than_hours: int = 24) -> CleanupResult:
        """Clean up all stopped/archived strategies older than N hours."""
```

### Tests for 10D

| Test | Description |
|------|-------------|
| `test_dashboard_returns_full_state` | Dashboard endpoint returns complete data |
| `test_stdout_endpoint_returns_lines` | Stdout endpoint returns captured lines |
| `test_clear_stdout_clears_buffer` | Clear endpoint empties buffer |
| `test_cleanup_deletes_signals` | Cleanup removes signal records |
| `test_cleanup_deletes_backtests` | Cleanup removes backtest records |
| `test_cleanup_does_not_delete_active` | Active strategy artifacts preserved |
| `test_gui_page_loads` | HTML dashboard loads correctly |

---

## Implementation Prompt for LLM Agent (Step 10)

```text
Implement Step 10: Strategy Runner & Pipeline Orchestration.

Project constraints:
- Python 3.14, asyncpg, DDD layering, asyncio for concurrency
- Follow existing code style: Google docstrings, type annotations, ruff/black
- Mirror src/ structure under tests/unit/
- Use relative imports within packages, absolute across packages

Tasks (implement in order 10A → 10B → 10C → 10D):

10A. Strategy Runner:
  1. Create TradeSignal domain model in src/domain/strategies/signal.py
  2. Create StrategyRunner in src/pipeline/strategy_runner.py:
     - Loads active strategies from DB (strategies table, status='active')
     - Executes strategies in parallel via asyncio.gather with return_exceptions=True
     - Per-strategy timeout (500ms default)
     - Routes signals to MarketService.place_order()
     - Persists signals to strategy_signals table
  3. Create StrategyExecutor in src/pipeline/strategy_executor.py:
     - Wraps strategy.on_tick() in try/except
     - Captures stdout via contextlib.redirect_stdout + io.StringIO
     - Enforces timeout via asyncio.wait_for()
  4. Add PipelineStep.STRATEGY = 5 to src/pipeline/ticket.py
  5. Integrate StrategyRunner into TradePipeline._execute_ticket() in src/pipeline/service.py
  6. Create migration: migrations/009_strategy_signals.sql

10B. Hot-Plug Manager:
  1. Create StrategyLifecycleService in src/application/services/strategy_lifecycle_service.py
  2. Implement hot_reload() in StrategyRunner (5-second refresh interval)
  3. Add activate/deactivate endpoints to src/infrastructure/api/routes/strategies.py

10C. Stdout Collector & Signal Aggregator:
  1. Create StdoutCollector in src/pipeline/stdout_collector.py
  2. Create SignalAggregator in src/pipeline/signal_aggregator.py
  3. Create API routes: src/infrastructure/api/routes/signals.py

10D. Strategy Management GUI:
  1. Create GUI API endpoints in src/infrastructure/api/routes/strategies_gui.py
  2. Create static HTML dashboard in src/infrastructure/web/gui/strategies.html
  3. Create CleanupService in src/application/services/cleanup_service.py

Tests:
  - All tests in tests/unit/pipeline/ and tests/unit/services/
  - Minimum 40 tests total across all sub-steps
  - Cover: happy path, failure isolation, timeout, deduplication, hot-reload, stdout capture

Output:
  - Files changed/created
  - Test results (pass/fail count)
  - ruff check + black results
```

## Acceptance Criteria

- [ ] Strategy runner executes all active strategies in parallel per tick
- [ ] Single strategy failure does not crash pipeline or other strategies
- [ ] Strategies can be activated/deactivated at runtime (hot-plug)
- [ ] Stdout from strategies is captured and accessible via API
- [ ] Signals are persisted to DB and visible in GUI
- [ ] Dashboard shows running strategies, status, signals, stdout
- [ ] Cleanup service removes artifacts from DB and disk
- [ ] All 40+ tests pass
- [ ] `ruff check` and `black` pass with no errors

## Dependencies

- Step 2: Market Service (already implemented)
- Step 3: Strategy Runtime Lifecycle (already implemented)
- Existing pipeline infrastructure (service.py, ticket.py)
- Existing strategy base class (src/domain/strategies/base.py)

## Out of Scope

- Binance order filter handling (Step 11)
- Live order execution modes (Step 11)
- API key management (Step 11)
