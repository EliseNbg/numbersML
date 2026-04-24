# Session Checkpoint 5 — Apr 24, 2026

## Objective
Fix TradingTCN Normalization — validation data showed massive distribution mismatch despite multiple attempts.

## Key Discovery: Column Index Mismatch Bug

**The real bug was NOT normalization method — it was a shifting schema in `WideVectorService`.**

### Root Cause
`WideVectorService.generate()` built `sorted_indicator_keys` **dynamically per-second** from whatever indicators existed in that timestep. If one second had indicators `{rsi, bb_upper, bb_middle, bb_lower}` but the next was missing `bb_lower` (e.g. calculation failure, gap, or different symbol subset), the sorted order shifted. Every feature index after the missing key pointed to a **different indicator**.

**Evidence:** DASH is ~$32, but feature 68 in validation showed $217 — impossible for DASH price. Feature 68 was `DASH_USDC_bb_20_2_middle` in train, but `ETH_USDC_close` in val due to schema shift.

### Impact
- Train and validation windows had **different column mappings** for the same index
- Normalization statistics (median/IQR) computed on feature X were applied to feature Y in validation
- Produced z-scores of 450 million and 100% clipping on some features

## Fixes Applied

### 1. Fixed Indicator Storage (multi-output indicators)
`src/pipeline/indicator_calculator.py`
- Changed from storing last key only (overwriting loop) to storing ALL sub-keys
- BollingerBands now stores: `bb_20_2_upper`, `bb_20_2_middle`, `bb_20_2_lower`, `bb_20_2_std`
- MACD now stores: `macd_12_26_9_macd_line`, `macd_12_26_9_signal_line`, `macd_12_26_9_histogram`
- Single-output indicators (ATR, RSI, OBV, etc.) unchanged

### 2. Fixed Shifting Schema Bug
`src/pipeline/wide_vector_service.py`
- Added `_load_indicator_schema()` — fetches ALL distinct indicator keys from `candle_indicators` table **once at startup**
- `generate()` now uses this **fixed global schema** (`self._indicator_keys`) instead of per-second dynamic set
- Missing keys in any second are filled from forward-fill cache or default to 0.0

### 3. Added Forward-Fill Cache
`src/pipeline/wide_vector_service.py`
- Added `self._last_known: Dict[str, Dict[str, float]]` in-memory cache
- When a symbol's candle or indicator is missing for a second, the last known regular value is reused
- Prevents 0.0 spikes from gaps
- Also fixed volume fallback bug: was hardcoded to 0.0, now properly forward-fills

### 4. Raised IQR Floor
`train_trading_tcn.py`
- Raised `feat_iqr_safe` floor from `1e-6` to `1.0`
- Prevents near-zero-IQR features from exploding to z-scores of 450 million in validation

### 5. Added Column Name Diagnostics
`ml/trading_dataset.py`
- Fetches `column_names` from DB and stores as `self.column_names`
`train_trading_tcn.py`
- All per-feature diagnostic logs now print actual column names (e.g. `DASH_USDC_bb_20_2_middle`) alongside index

### 6. Created Integration Test
`tests/integration/test_wide_vector_quality.py`
- Fetches last 24h of wide_vectors
- Validates physical ranges per indicator type (RSI 0-100, close > 0, etc.)
- Tests three normalization methods and flags dead features
- Prints per-feature table with IQR, clip counts, normalization stats

## Commit & Push Status
✅ **Committed and pushed** to `main` on GitHub
- Commit: `8d9394d` — "Fix wide vector schema stability, multi-key indicators, forward-fill, and diagnostics"

## Required Next Step

**Recalculate all wide_vectors** to fix the shifting schema in historical data:
```bash
.venv/bin/python -m src.cli.recalculate --all --from "2026-03-20 00:00:00"
```

After recalculation, re-run training:
```bash
.venv/bin/python train_trading_tcn.py --symbol DASH/USDC --hours 720 --seq-length 120 --horizon 600 --loss risk_adjusted --risk-penalty 0.05 --lr 0.0001 --epochs 40 --stride 60 --clip-returns 0.03
```

## Expected Outcome
With fixed schema + forward-fill + named diagnostics, validation normalization should finally show:
- `Val X: mean ≈ 0, std ≈ 1` (or close)
- No 100% clipped features
- Actual column names in diagnostics confirming feature 68 = `DASH_USDC_bb_20_2_middle` in both train and val

## Additional Fixes (Code Quality)

### 7. Fixed Unit Tests for WideVectorService
`tests/unit/pipeline/test_wide_vector_service.py`
- Changed `_indicator_keys` initialization from `[]` to `None` (None = not loaded yet)
- Fixed all 8 failing tests by pre-setting `service._indicator_keys` to skip schema load in mocks
- Fixed test assertions to match fixed schema behavior (external provider ordering, vector sizes)

### 8. Fixed recalculate.py Schema Bug
`src/cli/recalculate.py`
- Added `load_indicator_schema()` function to fetch fixed global indicator key list once at startup
- Changed from per-batch dynamic `sorted_indicator_keys` to fixed global `fixed_indicator_keys`
- Prevents column index shifts between 1-hour batches during historical recalculation

## Files Modified
- `src/pipeline/indicator_calculator.py` — multi-key indicator storage
- `src/pipeline/wide_vector_service.py` — fixed schema + forward-fill cache + None init
- `src/cli/recalculate.py` — fixed global schema for batch processing
- `ml/trading_dataset.py` — column_names fetching
- `train_trading_tcn.py` — named diagnostics + IQR floor
- `tests/integration/test_wide_vector_quality.py` — new integration test
- `tests/unit/pipeline/test_wide_vector_service.py` — fixed 8 tests for new behavior
