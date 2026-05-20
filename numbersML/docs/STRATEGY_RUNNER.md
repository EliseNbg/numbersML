# Strategy Runner

Parallel strategy execution engine within the real-time trade pipeline.

## Overview

The `StrategyRunner` sits as **Step 5** (`PipelineStep.STRATEGY`) in the pipeline, executing after wide vector generation. It loads active strategies from the database, runs them in parallel against each symbol's tick data, collects signals, and routes them to `MarketService` for order placement.

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

## Components

| File | Description |
|------|-------------|
| `src/pipeline/strategy_runner.py` | Core `StrategyRunner` orchestrator |
| `src/pipeline/strategy_executor.py` | Per-strategy async executor with isolation and stdout capture |
| `src/domain/strategies/price_statistics.py` | Symbol average price tracker (day/week) |
| `src/domain/strategies/signal.py` | `TradeSignal` domain model |
| `src/domain/strategies/base.py` | `Strategy` ABC with `get_avg_price()` helper |

## StrategyRunner

### Initialization

```python
runner = StrategyRunner(
    db_pool=db_pool,              # asyncpg connection pool
    market_service=market_svc,    # MarketService for order placement
    timeout_seconds=0.5,          # per-strategy execution timeout
    reload_interval=5.0,          # seconds between hot-reload checks
    dedup_window_seconds=60,      # signal deduplication window
)
```

### execute_tick()

Called by the pipeline for each symbol candle:

```python
signals = await runner.execute_tick(
    symbol="BTC/USDC",
    candle_time=datetime.now(UTC),
    tick_indicators={"rsi": 45.2, "macd": -0.001, ...},
    current_price=Decimal("67500.00"),
)
```

Flow per tick:

1. **Hot-reload** — checks DB for strategy changes if `reload_interval` elapsed
2. **Filter** — selects strategies that are active and trade this symbol
3. **Record price** — feeds current price into `SymbolPriceStatistics` (cached refresh, max once/hour)
4. **Execute** — runs all eligible strategies in parallel via `asyncio.gather(..., return_exceptions=True)`
5. **Collect** — gathers signals, checks deduplication, updates strategy context
6. **Route** — sends each signal to `MarketService.place_order()`
7. **Persist** — writes signal to `strategy_signals` table

### Hot-Reload

Every `reload_interval` seconds, `hot_reload()` compares DB active strategies with the in-memory list:

- **Newly activated** → instantiated, initialized, started
- **Deactivated** → gracefully stopped, removed from memory
- **Errors** during reload are logged; current strategy list is preserved

### Signal Deduplication

A signal is considered duplicate if the same `(strategy_id, symbol, side)` tuple was emitted within `dedup_window_seconds` (default 60s). Duplicates are silently dropped and counted in stats.

### Statistics

```python
stats = runner.get_stats()
# {
#     "active_strategies": 3,
#     "tick_count": 12500,
#     "signals": {
#         "signals_emitted": 42,
#         "signals_executed": 38,
#         "signals_rejected": 2,
#         "signals_failed": 2,
#         "strategy_errors": 1,
#         "deduplicated": 5,
#     },
#     "strategies": {
#         "uuid-1": {
#             "name": "MACDPeakStrategy",
#             "mode": "paper",
#             "signals_today": 12,
#             "last_signal_at": "2026-05-20T10:30:00Z",
#             "stdout_lines": 150,
#             "is_active": True,
#         },
#         ...
#     },
# }
```

## StrategyExecutor

Wraps each strategy's `on_tick()` call in an isolated sandbox:

- **stdout/stderr capture** via `contextlib.redirect_stdout` + `io.StringIO`
- **Timeout enforcement** via `asyncio.wait_for()` (default 500ms)
- **Error isolation** — exceptions are caught and returned as `StrategyResult.error`

```python
@dataclass
class StrategyResult:
    strategy_id: str
    strategy_name: str
    symbol: str
    signal: TradeSignal | None = None
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    error: str | None = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
```

## SymbolPriceStatistics

Shared tracker that computes average prices per symbol for configurable time windows. Managed entirely by the framework — strategies only read.

### How it works

- `StrategyRunner.execute_tick()` calls `record_price()` and `refresh()` on every tick
- `refresh()` is a no-op unless 1 hour has passed since last computation for that symbol
- Old entries (>7 days) are pruned automatically

### Strategy API

Strategies access averages via the base class helper:

```python
class MyStrategy(Strategy):
    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        avg_day = self.get_avg_price(tick.symbol, "day")
        avg_week = self.get_avg_price(tick.symbol, "week")

        if avg_day is not None and float(tick.price) < float(avg_day) * 0.98:
            # price is 2% below daily average — potential buy
            ...
```

| Method | Description |
|--------|-------------|
| `get_avg_price(symbol, "day")` | Cached average price over last 24 hours |
| `get_avg_price(symbol, "week")` | Cached average price over last 7 days |
| `get_price_statistics().get_stats(symbol)` | Dict with both `"day"` and `"week"` values |

Returns `None` if insufficient data is available (e.g., pipeline just started).

### Direct API (for tests or external use)

```python
from src.domain.strategies.base import get_price_statistics, reset_price_statistics

stats = get_price_statistics()
stats.record_price("BTC/USDC", Decimal("67500"), datetime.now(UTC))
stats.refresh()
avg = stats.get_avg_price("BTC/USDC", "day")
```

## Strategy Lifecycle

Strategies are loaded from the `strategies` table where `status='active'` and `strategy_type='class'`:

```sql
SELECT s.id, s.name, s.mode, s.status, s.class_path, sv.config
FROM strategies s
JOIN strategy_versions sv ON sv.strategy_id = s.id AND sv.is_active = true
WHERE s.status = 'active' AND s.strategy_type = 'class'
AND s.class_path IS NOT NULL
```

Each strategy class is dynamically imported via `importlib` and instantiated:

```python
# class_path: "src.strategies.user.macd_peak_strategy.MACDPeakStrategy"
module = importlib.import_module("src.strategies.user.macd_peak_strategy")
cls = getattr(module, "MACDPeakStrategy")
instance = cls(strategy_id=str(row["id"]), symbols=["BTC/USDC"])
```

Symbols are read from the strategy's config JSON (`config -> symbols`).

## Signal Routing

When a strategy emits a `Signal`, the runner:

1. Converts it to `TradeSignal` (via `StrategyExecutor._to_trade_signal`)
2. Checks deduplication
3. Creates an `OrderRequest` and calls `MarketService.place_order()`
4. Updates signal status to `EXECUTED`, `REJECTED`, or `FAILED`
5. Persists to `strategy_signals` table

If no `MarketService` is configured, all signals are rejected with reason `"No market service configured"`.

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `timeout_seconds` | `0.5` | Max execution time per strategy per tick |
| `reload_interval` | `5.0` | Seconds between DB hot-reload checks |
| `dedup_window_seconds` | `60` | Window for signal deduplication |
| `MAX_STDOUT_BUFFER` | `1000` | Max stdout lines retained per strategy |
| `_max_signal_history` | `500` | Max signals retained in memory |

## Database Schema

Signals are persisted to `strategy_signals`:

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
    created_at TIMESTAMPTZ DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    error_message TEXT
);
```

## Helper Methods

| Method | Description |
|--------|-------------|
| `get_stdout(strategy_id, limit=100)` | Get last N stdout lines for a strategy |
| `clear_stdout(strategy_id)` | Clear stdout buffer |
| `get_recent_signals(strategy_id, symbol, limit=50)` | Query in-memory signal history |
| `get_stats()` | Full runner statistics dict |

## Tests

```bash
.venv/bin/python -m pytest tests/unit/pipeline/test_strategy_runner.py -v
.venv/bin/python -m pytest tests/unit/pipeline/test_strategy_executor.py -v
```

Key test scenarios:

| Test | Description |
|------|-------------|
| `test_execute_single_strategy_returns_signal` | Happy path: strategy emits BUY signal |
| `test_execute_multiple_strategies_in_parallel` | Multiple strategies run concurrently |
| `test_strategy_failure_does_not_crash_others` | One failure doesn't affect others |
| `test_signal_deduplication` | Duplicate signals within window are dropped |
| `test_market_order_signal_has_no_price` | MARKET signal price is None |
| `test_limit_order_signal_has_price` | LIMIT signal carries price |
| `test_inactive_strategy_not_executed` | Inactive strategies are skipped |
