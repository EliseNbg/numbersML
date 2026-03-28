-- Migration: 004_remove_plpgsql_indicators
-- Description: Remove PL/pgSQL indicator calculation trigger, use Python EnrichmentService
-- Date: 2026-03-22
-- 
-- This migration:
-- 1. Drops the PL/pgSQL calculate_indicators_on_insert() function
-- 2. Drops the calculate_indicators_trigger trigger
-- 3. Creates a lightweight NOTIFY-only trigger for EnrichmentService
--
-- After this migration:
-- - Indicators are calculated by Python EnrichmentService (not PL/pgSQL)
-- - ticker_24hr_stats INSERT fires NOTIFY new_tick
-- - EnrichmentService receives notification and calculates indicators
-- - EnrichmentService fires NOTIFY enrichment_complete when done

-- =============================================================================
-- STEP 1: DROP OLD TRIGGER AND FUNCTION
-- =============================================================================

-- Drop trigger (keeps existing data, stops future PL/pgSQL calculations)
DROP TRIGGER IF EXISTS calculate_indicators_trigger ON ticker_24hr_stats;

-- Drop PL/pgSQL calculation function (no longer needed)
DROP FUNCTION IF EXISTS calculate_indicators_on_insert();

-- Also drop old notify function if it exists
DROP FUNCTION IF EXISTS notify_new_tick();

-- =============================================================================
-- STEP 2: CREATE LIGHTWEIGHT NOTIFY-ONLY TRIGGER
-- =============================================================================

-- Create simple NOTIFY function (no calculation, just notification)
CREATE OR REPLACE FUNCTION notify_new_tick()
RETURNS TRIGGER AS $$
BEGIN
    -- Notify EnrichmentService of new tick
    -- Payload includes symbol_id and time for processing
    PERFORM pg_notify('new_tick', json_build_object(
        'symbol_id', NEW.symbol_id,
        'time', NEW.time,
        'inserted_at', NEW.inserted_at
    )::text);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create lightweight trigger (NOTIFY only, no calculation)
CREATE TRIGGER notify_new_tick_trigger
    AFTER INSERT ON ticker_24hr_stats
    FOR EACH ROW
    EXECUTE FUNCTION notify_new_tick();

-- =============================================================================
-- STEP 3: ADD COMMENTS AND DOCUMENTATION
-- =============================================================================

-- Document the new function
COMMENT ON FUNCTION notify_new_tick() IS 
'Notify EnrichmentService of new tick in ticker_24hr_stats.
This function ONLY sends a notification - it does NOT calculate indicators.
Indicator calculation is performed by Python EnrichmentService asynchronously.

Flow:
1. INSERT into ticker_24hr_stats
2. This trigger fires NOTIFY new_tick
3. Python EnrichmentService receives notification
4. EnrichmentService loads tick history and calculates indicators
5. EnrichmentService stores in candle_indicators table
6. EnrichmentService fires NOTIFY enrichment_complete

See: src/application/services/enrichment_service.py';

-- Document the trigger
COMMENT ON TRIGGER notify_new_tick_trigger ON ticker_24hr_stats IS 
'Lightweight trigger to notify EnrichmentService of new ticks.
Replaces the old calculate_indicators_trigger which did PL/pgSQL calculation.
This trigger only sends notification - calculation is done in Python.';

-- =============================================================================
-- STEP 4: VERIFICATION QUERIES
-- =============================================================================

-- Verify old trigger is removed (should return 0 rows)
-- SELECT tgname FROM pg_trigger WHERE tgname = 'calculate_indicators_trigger';

-- Verify new trigger exists (should return 1 row)
-- SELECT tgname FROM pg_trigger WHERE tgname = 'notify_new_tick_trigger';

-- Verify function exists
-- SELECT proname FROM pg_proc WHERE proname = 'notify_new_tick';

-- =============================================================================
-- STEP 5: ROLLBACK INSTRUCTIONS
-- =============================================================================

-- To rollback (restore PL/pgSQL calculation):
-- 
-- 1. Drop new trigger:
--    DROP TRIGGER IF EXISTS notify_new_tick_trigger ON ticker_24hr_stats;
--    DROP FUNCTION IF EXISTS notify_new_tick();
--
-- 2. Restore old trigger:
--    Run migrations/003_indicator_calculation_trigger_fixed.sql
--
-- 3. Stop Python EnrichmentService:
--    docker stop crypto-data-enricher
--
-- WARNING: Rollback will cause duplicate calculations if EnrichmentService is running!

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
