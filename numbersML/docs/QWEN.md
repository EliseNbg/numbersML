# Project State — numbersML (Updated: 2026-04-11)

## Database Schema

### candles_1s table — important columns
| Column | Type | Purpose |
|--------|------|---------|
| `target_value` | JSONB | Contains pre-calculated target data: `{filtered_value, close, diff, trend, velocity, normalized_value, norm_min, norm_max}` |
| `predicted_value` | JSONB | Stores ML model predictions: `{value, model, horizon, predicted_at}` |
| `processed` | boolean | Flags that indicators + wide_vector are calculated for this row |

### Migration files
- `migrations/001_target_value_to_jsonb.sql` — converted target_value from double to JSONB
- `migrations/002_add_predicted_value.sql` — added predicted_value JSONB column + index
- `migrations/CLEAN_SCHEMA.sql` — full schema dump (includes predicted_value)

### Apply migration manually:
```bash
PGPASSWORD=crypto_secret psql -h localhost -U crypto -d crypto_trading -f migrations/002_add_predicted_value.sql
```

## Target Value Calculation (`src/pipeline/target_value.py`)

### `batch_calculate_target_data()` returns per candle:
- `filtered_value` — Hanning-filtered trend (smooth)
- `close` — candle close price
- `diff` — close minus filtered_value
- `trend` — "up" / "down" / "flat"
- `velocity` — single-step filtered change
- `normalized_value` — local [0..1] normalization (used as ML target)
- `norm_min`, `norm_max` — local extrema for normalization

**No `trend_velocity` field** — was removed (no visual signal, not used for training).

## ML Training Pipeline (`ml/`)

### Target: Price Returns
`ml/dataset.py` computes targets as **price returns**:
```python
target[i] = (close[i + horizon] - close[i]) / close[i]
```
- **Stationary**: mean ≈ 0, stable std
- **Configurable horizon**: `--horizon 30` (default), options: 5, 10, 30, 60, 120, 300 seconds

### Data Loading
- Reads `close` from candles_1s via wide_vectors JOIN
- Computes price returns in-memory (no DB target_value needed for training)
- Normalizes features with StandardScaler, filters low-variance features (min_std = 1e-6)
- Applies horizon shift for prediction target

### Training command
```bash
.venv/bin/python -m ml.train --model cnn_gru --train-hours 168 --epochs 150 --symbol DASH/USDC --horizon 120
```

### Model Architecture (CNN_GRUModel) — `ml/model.py`
- Input: 140 features, seq_len=1000
- Feature proj: LayerNorm + Linear(140→64) + GELU + Dropout(0.2)
- Multi-scale CNN: 3 blocks (kernel 3,5,7) → each has Conv+BN+GELU
- Fusion: Conv1d + BN + GELU
- GRU: hidden=128, layers=2, dropout=0.2, **unidirectional** (no future leakage)
- Attention: Linear(128→64)+GELU+Linear(64→1)
- MLP: Linear(128→128)+GELU+LN+Dropout(0.2)+Linear(128→64)+GELU+LN+Dropout(0.2)
- Output: Linear(64→1) — **no tanh()**, raw output for regression

### Key Config Defaults (ml/config.py)
| Param | Default | Notes |
|-------|---------|-------|
| `sequence_length` | 1000 | seconds of context |
| `dropout` | 0.2 | reverted from 0.4 |
| `gru_dropout` | 0.2 | reverted from 0.4 |
| `prediction_horizon` | 30 | configurable via --horizon CLI |
| `weight_decay` | 1e-4 | reverted from 5e-3 |
| `batch_size` | 256 | |

## Prediction API (`src/infrastructure/api/routes/ml.py`)

### GET `/api/ml/predict`
- Loads model, runs sliding window prediction
- Computes target values from candle close prices as price returns
- Returns: candles, targets (price returns), predictions, stats
- **Parameters**: symbol, model, hours (float, >0), horizon (5-300), ensemble_size

### POST `/api/ml/predict-and-save`
- **Background task** — runs prediction and stores in `candles_1s.predicted_value`
- Returns `task_id` for polling
- Stores: `{"value": pred, "model": name, "horizon": N, "predicted_at": ISO}`
- **Parameters**: same as GET + POST method

### GET `/api/ml/task-status?task_id=X`
- Polls background task status: "running" / "completed" / "failed"

### Why predicted_value?
- Saves recomputation — expensive CNN+GRU inference runs once
- Enables direct comparison: `target_value` (actual) vs `predicted_value` (model)
- Both are JSONB, same time alignment

## Dashboard

### prediction.html
- **Two buttons**: "Load & Predict" (GET, live chart) + "Predict & Save" (POST, background)
- **Horizon selector**: 5s, 10s, 30s, 1min, 2min, 5min
- **Target scale**: price returns (not normalized [0..1])
- **Labels**: "Target Return" (orange), "ML Return Prediction" (blue)
- Legend: > 0 = Bullish, < 0 = Bearish

### target_value_chart.html
- Shows: Filtered Trend (orange) + Normalized [0..1] (green)
- No trend_velocity line (removed — no visual signal)

## Wide Vectors

### Format (140 features per vector)
- Per active symbol: `[close, volume, atr_14, atr_99, atr_999, bb_20_2, bb_200_2, bb_900_2, ema_12, ema_26, ema_450, ema_2000, macd_12_26_9, macd_120_260_29, macd_400_860_300, rsi_14, rsi_54, sma_20, sma_450, sma_2000]`
- Sorted alphabetically by symbol name
- **0.0 for symbols without indicators** — filtered out by feature mask if constant

### Active indicators (18)
ATR(14, 99, 999), BB(20, 200, 900), EMA(12, 26, 450, 2000), MACD(12/26/9, 120/260/29, 400/860/300), RSI(14, 54), SMA(20, 450, 2000)

## Server Commands

### Start API
```bash
cd /home/andy/projects/numbers/numbersML
.venv/bin/python -m uvicorn src.infrastructure.api.app:create_app --factory --host 0.0.0.0 --port 8000 &
```

### Start Training
```bash
.venv/bin/python -m ml.train --model cnn_gru --horizon 120 --epochs 150 --symbol DASH/USDC
```

### Recalculate Targets
```bash
.venv/bin/python -m src.cli.recalculate_targets --symbols "DASH/USDC" --response-time 50
```

## Known Issues
1. **DASH/USDC candles stale** — last candle 2026-04-11 05:05, pipeline not running. Need to restart pipeline for fresh data.
2. **Existing models trained on normalized_value [0..1]** — need retraining for price return targets
3. **ml/models/norm_params.npz** — binary file, should be in .gitignore

## Test Status
- **452 unit tests pass** (4 skipped)
- 2 new tests for predict-and-save validation
