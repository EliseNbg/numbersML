-- Migration: Add predicted_value column for storing ML predictions
-- Date: 2026-04-11
-- Purpose: Store ML model predictions alongside actual target values
--          to enable comparison and avoid recalculation.

ALTER TABLE candles_1s ADD COLUMN IF NOT EXISTS predicted_value JSONB;

-- Index for fast lookup of candles with predictions
CREATE INDEX IF NOT EXISTS idx_candles_predicted_value_not_null
    ON candles_1s (symbol_id, time)
    WHERE predicted_value IS NOT NULL;

COMMENT ON COLUMN candles_1s.predicted_value IS 'ML prediction output: {
    "value": 0.0023,
    "model": "cnn_gru_140_DASHUSDC_20260411",
    "horizon": 30,
    "features_count": 140,
    "predicted_at": "2026-04-11T12:00:00Z"
}';
