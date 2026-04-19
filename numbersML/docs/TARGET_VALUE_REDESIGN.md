# Target Value & ML Pipeline Redesign

## Overview
This document summarizes the redesign of the target value calculation and ML pipeline to provide smooth, predictable targets for model training and visualization.

## Key Changes

### 1. Unified Data Source: `candles_1s`
*   **Legacy Table Removed**: `ticker_24hr_stats` is no longer used.
*   **Single Source of Truth**: All indicators, wide vectors, and target values are now calculated directly from `candles_1s`.
*   **Deleted Files**: `src/cli/generate_wide_vector.py` and `ml/target_builder.py`.

### 2. Advanced Smoothing Filters
The system now supports three smoothing methods for trend detection:

| Method | Speed | Smoothness | Use Case |
|--------|-------|------------|----------|
| **Savitzky-Golay** | Fast | ★★★★★ | Best for ML targets and visualization |
| **Kalman Filter** | Fast | ★★★★☆ | Good for adaptive trend tracking |
| **Hanning** | Fast | ★★★☆☆ | Legacy support |

*   **Dashboard Default**: Hanning with `window_size=2000` and `use_future=true` (for visualization).
*   **Production Default**: Savitzky-Golay is now the standard for ML training targets.

### 3. Normalized Target (0-1)
*   **What**: A new `normalized_value` field is stored in `candles_1s.target_value` (JSONB).
*   **How**: It maps the current position in the trend cycle to a 0-1 range using peak/valley detection.
    *   `0.0` = Valley (Oversold)
    *   `0.5` = Midpoint
    *   `1.0` = Peak (Overbought)
*   **Benefit**: Provides a strong, stable signal for ML models to learn.

### 4. ML Pipeline Alignment
The training and inference pipelines now use the **exact same targets** stored in the database:
1.  **Training**: `ml/dataset.py` loads `normalized_value` from DB as the target $Y$.
2.  **Inference**: Model predicts the future `normalized_value`.
3.  **Visualization**: Dashboard plots the stored `normalized_value` (Orange) vs Prediction (Blue).

## Database Schema Update

The `candles_1s.target_value` column is now a JSONB structure:
```json
{
  "filtered_value": 105.5,      // Smoothed trend value
  "close": 103.2,               // Candle close price
  "diff": -2.3,                 // Deviation from trend
  "trend": "up",                // Trend direction
  "velocity": 0.15,             // Rate of change
  "normalized_value": 0.65,     // 0-1 cycle position
  "norm_min": 95.0,             // Recent trend minimum
  "norm_max": 115.0             // Recent trend maximum
}
```

## API Endpoints

### `GET /api/target-values`
Retrieve target data with configurable smoothing.
*   `method`: `savgol` (default), `kalman`, or `hanning`
*   `response_time`: Window size (default: 2000)
*   `use_future`: Enable centered smoothing for visualization (default: true)

### `POST /api/target-values/calculate`
Calculate and store targets. Automatically cleans up edge artifacts by setting `target_value = NULL` for the first and last `window_size` rows.

## Dashboard Usage

### Target Value Chart
1.  **Filter**: Select smoothing method (default: Hanning).
2.  **Window Size**: Set smoothing strength (default: 2000).
3.  **Use Future**: Check this for visualization (shows peaks/valleys perfectly).

### Prediction Chart
Shows two lines on the right scale:
*   **Orange**: `Target (Normalized 0-1)` - Actual historical trend position.
*   **Blue**: `ML Prediction (0-1)` - Model's predicted trend position.

## Migration Steps
1.  **Run Migration**: `psql -f migrations/001_target_value_to_jsonb.sql`
2.  **Recalculate**: Use the Dashboard "Calculate Target Values" button.
3.  **Retrain**: Run `python -m ml.train` to train on the new normalized targets.

## Tests
All unit tests pass (450 passed, 4 skipped).
Integration tests updated to use `candles_1s`.
