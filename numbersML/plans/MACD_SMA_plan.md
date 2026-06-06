# MACD-SMA Indicator Plan

## Problem
Current MACD uses EMAs with a Python for-loop (`_calculate_ema`) over the entire price buffer every tick. For large periods (e.g., slow=86400 for 24h trends), this is O(n) per tick with n ~260k, and the EMA needs `slow_period × 3` data points for convergence — making the ring buffer ~3× larger than necessary.

## Solution
Replace the internal EMA calculations with SMA. SMAs:
- Can be computed with a single vectorized pass (numpy cumsum) — ~100× faster than the Python loop
- Need only `slow_period` data points (no convergence factor), so the ring buffer is 3× smaller
- Produce identical results regardless of data length (no seed‑influence drift)

## New Class: `MACDSMAIndicator`
Extends `Indicator` (ABC), lives in `src/indicators/trend.py`.

### Parameters
| Param | Type | Default | Min | Max |
|-------|------|---------|-----|-----|
| `fast_period` | int | 12 | 2 | 100000 |
| `slow_period` | int | 26 | 2 | 100000 |
| `signal_period` | int | 9 | 2 | 100000 |

### Output
Same structure as `MACDIndicator`:
- `values["macd"]` — SMA(fast) − SMA(slow)
- `values["signal"]` — SMA(signal_period) of the macd line
- `values["histogram"]` — macd − signal
- `metadata` — fast_period, slow_period, signal_period (no `buffer_insufficient` — SMA doesn't need convergence)

## Phases

### Phase 1 — Unit tests (TDD)
- File: `tests/unit/indicators/test_macd_sma_indicator.py`
- Tests:
  - basic calculation (all three output keys, correct lengths)
  - SMA correctness — verify SMA(fast) and SMA(slow) match standalone `SMAIndicator`
  - known values — hand‑verified MACD SMA values
  - large periods (fast=14400, slow=86400, signal=100) — verify output is valid, no NaN in last value
  - very large periods (fast=86400, slow=259200) — verify vectorized path works
  - params validation (min/max boundaries)
  - edge cases (constant prices, insufficient data < slow_period → NaN)

### Phase 2 — Indicator implementation
- File: `src/indicators/trend.py`
- Add `MACDSMAIndicator` class with:
  - `params_schema` — wide ranges (2–100000)
  - `_calculate_sma` — vectorized via `np.cumsum`
  - `calculate` — sma_fast, sma_slow, macd_line, signal_line, histogram
  - No `_check_buffer_size` guard (not needed for SMA)
- Update `_calculate_max_period` in `indicator_calculator.py`:
  - For `MACDSMAIndicator`: `max(max_period, int(slow_period) + int(signal_period) + 50)`
  - (No ×3 multiplier, just what SMA actually needs)

### Phase 3 — Verify existing tests pass
- `pytest tests/unit/indicators/` — no regressions
- `pytest tests/unit/` — no regressions

### Phase 4 — DB registration & strategy config (future)
- Register `macdsmaindicator_fast_period14400_slow_period86400_signal_period100` (or whatever periods) in the DB via `indicator_manager` API or migration
- Update strategy configs with the new `macd_indicator_name`

## Design Decisions

### Why not modify existing `MACDIndicator`?
Adding an `ma_type` parameter would change the existing class interface and risk breaking current MACD definitions in the DB. A separate class keeps backward compatibility and makes testing/validation independent.

### Why vectorized SMA instead of incremental sliding window?
The indicator is created fresh each tick (`cls(**params)` in `_run_indicators`), so we can't store a sliding-window deque. Vectorized cumsum is the simplest correct approach within the existing architecture.

### Buffer size
For slow=86400 (24h @ 1s), the ring buffer needs 86400 × 1 + 100 + 50 = ~86550 entries. Compare to EMA-MACD which needed 86400 × 3 + 100 + 500 = ~259800. That's a 3× reduction.
