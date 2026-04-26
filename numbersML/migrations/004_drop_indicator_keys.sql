-- Migration: Drop indicator_keys column from candle_indicators
-- The indicator_keys information is already stored in the values JSONB column
-- Keeping it in sync creates redundancy and potential for inconsistency
-- Keys are now derived from values using jsonb_object_keys() at query time

-- Drop the GIN index on indicator_keys first
DROP INDEX IF EXISTS idx_candle_indicators_keys;

-- Drop the indicator_keys column
ALTER TABLE candle_indicators
    DROP COLUMN indicator_keys;

-- Verify column is removed
-- \d+ candle_indicators
