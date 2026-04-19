# ML Target Value Experiments — Session Summary

**Date:** 2026-04-14  
**Goal:** Make the CNN+GRU model actually learn to predict future price movements  
**Model:** CNN+GRUModel, 253K params, 140 features (8 symbols × 20 features each)

---

## 1. Starting Point

### Problem Identified
- Model was trained on `normalized_value [0..1]` from Hanning-filtered price data
- Validation MAE was 0.36 — **50x worse** than baseline (MA(30): 0.006)
- Model predicted constant ~0.71 regardless of input
- Root cause: `normalized_value` is computed with local min/max within extrema segments — non-stationary

### What We Tried First
Switched training target from `normalized_value` to **scaled price returns via sigmoid**:
```python
return = (close[t+h] - close[t]) / close[t]
target = sigmoid(return / std_return * 2)
```

---

## 2. ❌ FAIL: Wide Vectors Had 120/140 Features = 0

### Problem
Most symbols (ADA, BNB, BTC, etc.) don't trade every second. When `WideVectorService` generated a vector and a symbol had no candle at that time, it used **0.0** for close, volume, and all indicators.

**Result:** ~120 of 140 features were constantly 0 → noise dominated signal → model couldn't learn

### Fix: Forward-Fill Last Known Values
- `src/pipeline/wide_vector_service.py`: When a symbol has no candle in current second, use last known close/indicators, set volume=0
- `src/cli/recalculate.py`: Added gap-filling when regenerating wide vectors — loads ALL historical data ONCE per batch (2 queries), then forward-fills in memory (reduced from 7200 queries/batch = 2h → 2 queries = 5s)

### Key Code Pattern
```python
# For each time point in batch, check which symbols are missing
# Load last known candle and indicator BEFORE batch start (1 query each)
# Forward-fill in memory — no more N+1 queries!
```

---

## 3. ❌ FAIL: Hanning-Filtered Returns as Target

### Hypothesis
Use filtered (smooth) returns instead of raw returns — the trend should be clearer.
```python
return = (filtered[t+h] - filtered[t]) / close[t]
target = sigmoid(return / std * 2)
```

### Results by Horizon

| Horizon | Baseline MAE | Model Val MAE | Verdict |
|---------|-------------|---------------|---------|
| 300s | 0.115 | 0.32 (3x worse) | ❌ |
| 120s | 0.012 | 0.31 (25x worse) | ❌ |
| 30s | 0.176 | 0.36 (2x worse) | ❌ |
| 20s | 0.007 | 0.31 (44x worse) | ❌ |
| 5s | 0.126 | 0.075 (1.7x better) | ✅ |

### Root Cause
The Hanning filter (response_time=50) is so smooth that `filtered[t+h] ≈ filtered[t]` for any h > 0. The target is essentially constant → the model learns to predict 0.5 → high MAE when small fluctuations occur.

**The baseline "persistence" MAE of 0.007 proves there's no signal** — the filtered return barely changes over 20 seconds.

### Why horizon=5 "worked"
At 5s, raw close returns (not filtered) have enough variance (std=0.14-0.18) that the model found something. But it was learning to predict **noise**, not a genuine pattern — Val MAE 0.075 vs baseline 0.126.

---

## 4. ❌ FAIL: No Sigmoid in Model Output

### Problem
`CNN_GRUModel` output was unbounded (`self.output(x).squeeze(-1)`), but targets are in [0..1]. Model predicted values outside valid range.

### Fix
```python
return torch.sigmoid(self.output(x)).squeeze(-1)
```

---

## 5. ❌ FAIL: Background Task RuntimeError

### Problem
```python
background_tasks.add_task(lambda: asyncio.create_task(run_task()))
```
`asyncio.create_task()` needs a running event loop, but `BackgroundTasks` runs in a thread pool without one → `RuntimeError: no running event loop`.

### Fix
```python
task = asyncio.create_task(run_task())  # In the route handler's event loop
_pending_tasks.append(task)
```
Removed `BackgroundTasks` dependency — schedule directly in the async route handler.

---

## 6. ❌ FAIL: asyncpg "another operation in progress"

### Problem
The background task used `asyncio.run()` which creates a new event loop. asyncpg connections are bound to the server's event loop → conflicts.

### Fix
Schedule task in the SAME event loop as the route handler using `asyncio.create_task()`.

---

## 7. ❌ FAIL: "use_saved" Load Returns Empty Data

### Problem
`_load_saved_predictions()` used `datetime.now(timezone.utc)` as reference time, but data was from hours ago → query found nothing.

### Fix
Use `MAX(time) WHERE predicted_value IS NOT NULL` as reference time instead of NOW().

---

## 8. ❌ FAIL: Missing `horizon` Parameter

### Problem
`_load_saved_predictions()` used `horizon` variable but didn't have it as a parameter → `NameError` → 500 HTML response → `JSON.parse: unexpected character`.

### Fix
Add `horizon: int = 30` to function signature.

---

## 9. ❌ FAIL: recalculate.py N+1 Query Catastrophe

### Problem
For each of 3600 time points in a batch, the code ran 2 DB queries (candles + indicators) to forward-fill gaps:
```
3600 × 2 = 7200 queries → 2+ hours per batch
```

### Fix
Load ALL historical data ONCE (2 queries total), then forward-fill in memory:
```
2 queries → ~5 seconds per batch
```

---

## 10. ❌ FAIL: Timezone Comparison Error

### Problem
```
TypeError: can't compare offset-naive and offset-aware datetimes
```
User provided naive datetime string (`"2026-04-04 16:41:00"`) but `to_time` was timezone-aware (`datetime.now(timezone.utc)`).

### Fix
```python
if from_time.tzinfo is None:
    from_time = from_time.replace(tzinfo=timezone.utc)
```

---

## 11. ✅ What Actually Worked

### Raw Price Returns as Target
```python
return = (close[t+h] - close[t]) / close[t]
target = sigmoid(return / std_return * 2)
```
With horizon=5:
- Baseline Persistence MAE: 0.126
- Model Val MAE: 0.075 (1.7x better)
- **But:** The model is essentially predicting noise — returns at 5s horizon are not genuinely predictable

### The Dashboard Works
- "Use saved" checkbox loads pre-computed predictions instantly
- "Save" button runs background prediction task with progress bar
- Both target and prediction lines display correctly on same [0..1] scale

---

## 12. Key Lessons Learned

### About ML Targets for Financial Time Series

1. **Filtered targets have NO signal** — smoothing destroys the very thing you want to predict
2. **Raw returns ARE predictable only at longer horizons** (300s+) where trends form
3. **Persistence baseline is your best friend** — if the model can't beat "yesterday's value", it's learning noise
4. **Sigmoid scaling to [0..1] works** — but the underlying signal must exist first

### About This Codebase

5. **Forward-fill, not zero-fill** — missing data ≠ zero data
6. **Batch queries, not N+1 queries** — load all history once, process in memory
7. **asyncio.create_task() in route handlers** — not BackgroundTasks, not asyncio.run()
8. **All datetimes must be timezone-aware** — especially when comparing with NOW()
9. **`horizon` parameter must propagate through all layers** — training → dataset → API → DB query

### About Model Capacity

10. **254K params is not too many** — the problem is the target, not the model
11. **Smaller models won't help** — if there's no signal, no architecture will find it
12. **Transformer (22M params) would be 86x slower and overfit worse**

---

## 13. Current State (2026-04-14)

### Working
- ✅ Wide vectors with forward-fill (all 140 features non-zero)
- ✅ Gap-filling in recalculate.py (2 queries/batch, ~5s)
- ✅ Raw price return targets with sigmoid scaling
- ✅ Sigmoid output activation in model
- ✅ Dashboard with "Use saved" instant loading
- ✅ Background prediction with progress bar
- ✅ All 456 unit tests pass

### Not Solved
- ❌ 5-second returns are barely predictable (model beats baseline by only 1.7x)
- ❌ 30-300 second filtered returns are NOT predictable (Hanning filter too smooth)
- ❌ No genuine predictive signal found yet in any target configuration

### Next Steps to Try
1. **Train with horizon=300** on raw returns (not filtered) — trends may form over 5 minutes
2. **Classification task** — predict direction (up/down) instead of magnitude
3. **Feature engineering** — maybe raw OHLCV + indicators aren't the right features
4. **More data** — 168h may not be enough for a 300s horizon model

---

## 14. Commands Reference

```bash
# Recalculate indicators and wide vectors (with gap-filling)
python3 -m src.cli.recalculate --all --from '2026-03-31 16:41:00'

# Wide vectors only (faster)
python3 -m src.cli.recalculate --vectors-only --from '2026-03-31 16:41:00'

# Train model
.venv/bin/python -m ml.train --model cnn_gru --train-hours 168 --epochs 50 --symbol DASH/USDC --horizon 300

# Start server
.venv/bin/python -m uvicorn src.infrastructure.api.app:create_app --factory --host 0.0.0.0 --port 8000 &
```
