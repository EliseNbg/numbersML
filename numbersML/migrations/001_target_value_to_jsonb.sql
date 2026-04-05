-- Migration: Change target_value from double to JSONB for rich market state
-- Run this to upgrade from single float to JSON object

-- Step 1: Add new column
ALTER TABLE candles_1s ADD COLUMN IF NOT EXISTS target_data JSONB;

-- Step 2: Migrate existing data (convert double to JSON)
UPDATE candles_1s
SET target_data = jsonb_build_object(
    'filtered_value', target_value,
    'close', close,
    'diff', 0,
    'trend', 'unknown',
    'velocity', 0
)
WHERE target_value IS NOT NULL AND target_data IS NULL;

-- Step 3: Drop old column
ALTER TABLE candles_1s DROP COLUMN IF EXISTS target_value;

-- Step 4: Rename new column
ALTER TABLE candles_1s RENAME COLUMN target_data TO target_value;

-- Step 5: Add index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_candles_1s_target_trend
ON candles_1s USING gin (target_value)
WHERE (target_value->>'trend') IS NOT NULL;

-- Verify migration
SELECT
    COUNT(*) as total_candles,
    COUNT(target_value) as candles_with_target,
    target_value->>'trend' as trend,
    COUNT(*) as trend_count
FROM candles_1s
WHERE target_value IS NOT NULL
GROUP BY target_value->>'trend'
ORDER BY trend_count DESC
LIMIT 10;
