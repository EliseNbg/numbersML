# PipelineTicket Architecture

The pipeline uses a **ticket-based step execution model**. Each second, the pipeline creates a `PipelineTicket` for every symbol's candle. The ticket controls which processing steps execute.

## Concept

Instead of hardcoded step logic, each candle carries a ticket that declares which steps to run:

```
WebSocket trades → Aggregator → Candle emitted → PipelineTicket created → Steps execute
```

## Steps

```python
class PipelineStep(IntEnum):
    CANDLE      = 1  # Write 1s OHLCV candle to database
    INDICATOR   = 2  # Calculate and store technical indicators
    WIDE_VECTOR = 3  # Build ML-ready vector (all symbols combined)
    ML_PREDICT  = 4  # Run ML model inference (future)
    TRADE_EXEC  = 5  # Execute trading signal (future)
    PAPER_TRADE = 6  # Paper trading for backtesting (future)
```

**Dependency chain**: Step 1 → Step 2 → Step 3 → Step 4 → Step 5

- Step 1 (candle) must run before Step 2 (indicators need candle data)
- Step 2 (indicators) must run before Step 3 (vector reads indicators)
- Step 3 (vector) is cross-symbol — runs once per tick after all per-symbol steps
- Steps 4-5 are future ML/trading integration points

## Presets

| Preset | Steps | Use case |
|--------|-------|----------|
| `LIVE_STEPS` | `{1, 2, 3}` | Live data collection |
| `BACKFILL_STEPS` | `{1, 2, 3}` | Historical gap filling |
| `BACKTEST_STEPS` | `{4, 6}` | Algorithm evaluation on historical data |
| Custom | `{3, 4}` | ML inference only (data already exists) |

```python
from src.pipeline.ticket import PipelineStep, PipelineTicket, LIVE_STEPS, BACKTEST_STEPS

# Live trading (default)
pipeline._active_steps = LIVE_STEPS

# Backtesting (ML + paper trading, no data collection)
pipeline._active_steps = BACKTEST_STEPS
```

## Execution Flow

```
_ticker_loop (every 1s)
  │
  ├─ tick_all() → {symbol: candle}  (pull model)
  │
  ├─ for each (symbol, candle):
  │     ticket = PipelineTicket(steps=_active_steps, symbol, candle_time, candle)
  │     _execute_ticket(ticket)
  │       ├─ if 1 in steps: write_candle() + flush()
  │       └─ if 2 in steps: calculate_indicators()
  │
  └─ if 3 in steps: wide_vector_service.generate(candle_time)
```

## Ticket Dataclass

```python
@dataclass(frozen=True)
class PipelineTicket:
    steps: FrozenSet[int]      # Which steps to execute
    symbol: str                # Trading pair (e.g., 'BTC/USDC')
    candle_time: datetime      # Time of the candle
    candle: TradeAggregation   # The OHLCV data

    def has(self, step: PipelineStep) -> bool:
        return step in self.steps
```

## Aggregator: Push → Pull

The aggregator was refactored from **push** (callbacks) to **pull** (return values):

**Before** (push):
```python
agg = MultiSymbolAggregator(on_candle=callback)
await agg.tick_all(now)  # callback fires for each candle
```

**After** (pull):
```python
agg = MultiSymbolAggregator()
emitted = await agg.tick_all(now)  # returns {symbol: candle}
for symbol, candle in emitted.items():
    # process candle directly
```

Inter-window candles (from `add_trade()` transitions) are queued in `_pending` and drained by `tick()`.

## Key Files

| File | Purpose |
|------|---------|
| `src/pipeline/ticket.py` | PipelineStep enum, PipelineTicket dataclass |
| `src/pipeline/aggregator.py` | TradeAggregator (pull model), MultiSymbolAggregator |
| `src/pipeline/service.py` | TradePipeline with `_execute_ticket()` |

## Future Steps

Steps 4-6 are placeholders for:

- **Step 4 (ML_PREDICT)**: Load trained model, run inference on wide_vector, produce prediction
- **Step 5 (TRADE_EXEC)**: Send buy/sell order to Binance based on ML prediction
- **Step 6 (PAPER_TRADE)**: Simulate trades against historical data for backtesting

Adding a new step:
1. Add to `PipelineStep` enum
2. Add handler in `_execute_ticket()` with `if ticket.has(PipelineStep.NEW_STEP):`
3. Add to appropriate preset (LIVE, BACKFILL, etc.)
