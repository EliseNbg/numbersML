-- Migration: 003_indicator_calculation_trigger (PL/pgSQL version)
-- Description: Calculate indicators automatically on ticker insert
-- Uses PL/pgSQL instead of PL/Python (no external dependencies)

-- Drop existing trigger and function
DROP TRIGGER IF EXISTS calculate_indicators_trigger ON ticker_24hr_stats;
DROP FUNCTION IF EXISTS calculate_indicators_on_insert();

-- =============================================================================
-- INDICATOR CALCULATION FUNCTION (PL/pgSQL)
-- =============================================================================

CREATE OR REPLACE FUNCTION calculate_indicators_on_insert()
RETURNS TRIGGER AS $$
DECLARE
    v_prices NUMERIC[];
    v_count INTEGER;
    v_sma_20 NUMERIC;
    v_sma_50 NUMERIC;
    v_ema_12 NUMERIC;
    v_ema_26 NUMERIC;
    v_macd NUMERIC;
    v_rsi NUMERIC;
    v_bb_middle NUMERIC;
    v_bb_upper NUMERIC;
    v_bb_lower NUMERIC;
    v_indicator_values JSONB;
    v_indicator_keys TEXT[];
    v_gain NUMERIC;
    v_loss NUMERIC;
    v_rs NUMERIC;
    i INTEGER;
    v_price NUMERIC;
BEGIN
    -- Get last 200 prices for this symbol (from ticker_24hr_stats)
    SELECT ARRAY_AGG(ts.last_price)
    INTO v_prices
    FROM (
        SELECT last_price
        FROM ticker_24hr_stats
        WHERE symbol_id = NEW.symbol_id
        ORDER BY inserted_at DESC
        LIMIT 200
    ) ts;
    
    v_count := array_length(v_prices, 1);
    
    -- Only calculate if we have enough data
    IF v_count IS NULL OR v_count < 50 THEN
        -- Not enough data, skip calculation
        RETURN NEW;
    END IF;
    
    -- Initialize indicators array
    v_indicator_values := '{}'::jsonb;
    v_indicator_keys := ARRAY[]::TEXT[];
    
    -- Calculate SMA 20
    IF v_count >= 20 THEN
        SELECT AVG(p) INTO v_sma_20 FROM unnest(v_prices[1:20]) as p;
        v_indicator_values := v_indicator_values || jsonb_build_object('sma_20', v_sma_20);
        v_indicator_keys := array_append(v_indicator_keys, 'sma_20');
    END IF;
    
    -- Calculate SMA 50
    IF v_count >= 50 THEN
        SELECT AVG(p) INTO v_sma_50 FROM unnest(v_prices[1:50]) as p;
        v_indicator_values := v_indicator_values || jsonb_build_object('sma_50', v_sma_50);
        v_indicator_keys := array_append(v_indicator_keys, 'sma_50');
    END IF;
    
    -- Calculate EMA 12 (simplified)
    IF v_count >= 12 THEN
        v_ema_12 := v_prices[1];
        FOR i IN 2..12 LOOP
            v_ema_12 := (v_prices[i] * (2.0/13.0)) + (v_ema_12 * (11.0/13.0));
        END LOOP;
        v_indicator_values := v_indicator_values || jsonb_build_object('ema_12', v_ema_12);
        v_indicator_keys := array_append(v_indicator_keys, 'ema_12');
    END IF;
    
    -- Calculate EMA 26 (simplified)
    IF v_count >= 26 THEN
        v_ema_26 := v_prices[1];
        FOR i IN 2..26 LOOP
            v_ema_26 := (v_prices[i] * (2.0/27.0)) + (v_ema_26 * (25.0/27.0));
        END LOOP;
        v_indicator_values := v_indicator_values || jsonb_build_object('ema_26', v_ema_26);
        v_indicator_keys := array_append(v_indicator_keys, 'ema_26');
    END IF;
    
    -- Calculate MACD (EMA12 - EMA26)
    IF v_ema_12 IS NOT NULL AND v_ema_26 IS NOT NULL THEN
        v_macd := v_ema_12 - v_ema_26;
        v_indicator_values := v_indicator_values || jsonb_build_object('macd', v_macd);
        v_indicator_keys := array_append(v_indicator_keys, 'macd');
    END IF;
    
    -- Calculate RSI (simplified 14-period)
    IF v_count >= 15 THEN
        v_gain := 0;
        v_loss := 0;
        
        FOR i IN 2..15 LOOP
            IF v_prices[i] > v_prices[i-1] THEN
                v_gain := v_gain + (v_prices[i] - v_prices[i-1]);
            ELSIF v_prices[i] < v_prices[i-1] THEN
                v_loss := v_loss + (v_prices[i-1] - v_prices[i]);
            END IF;
        END LOOP;
        
        v_gain := v_gain / 14.0;
        v_loss := v_loss / 14.0;
        
        IF v_loss > 0 THEN
            v_rs := v_gain / v_loss;
            v_rsi := 100.0 - (100.0 / (1.0 + v_rs));
        ELSIF v_gain > 0 THEN
            v_rsi := 100.0;
        ELSE
            v_rsi := 0.0;
        END IF;
        
        v_indicator_values := v_indicator_values || jsonb_build_object('rsi_14', v_rsi);
        v_indicator_keys := array_append(v_indicator_keys, 'rsi_14');
    END IF;
    
    -- Calculate Bollinger Bands (20, 2 std)
    IF v_count >= 20 THEN
        SELECT AVG(p), STDDEV(p) INTO v_bb_middle, v_bb_lower FROM unnest(v_prices[1:20]) as p;
        v_bb_upper := v_bb_middle + 2 * v_bb_lower;
        v_bb_lower := v_bb_middle - 2 * v_bb_lower;
        
        v_indicator_values := v_indicator_values || jsonb_build_object(
            'bb_middle', v_bb_middle,
            'bb_upper', v_bb_upper,
            'bb_lower', v_bb_lower
        );
        v_indicator_keys := array_append(v_indicator_keys, 'bb_middle');
        v_indicator_keys := array_append(v_indicator_keys, 'bb_upper');
        v_indicator_keys := array_append(v_indicator_keys, 'bb_lower');
    END IF;
    
    -- Insert into tick_indicators if we have any indicators
    IF array_length(v_indicator_keys, 1) > 0 THEN
        INSERT INTO tick_indicators (
            time, symbol_id, price, volume, values, indicator_keys, indicator_version
        ) VALUES (
            NOW(),
            NEW.symbol_id,
            NEW.last_price,
            0,  -- No volume in miniTicker
            v_indicator_values,
            v_indicator_keys,
            1  -- Version
        )
        ON CONFLICT (time, symbol_id) DO UPDATE SET
            values = EXCLUDED.values,
            indicator_keys = EXCLUDED.indicator_keys,
            updated_at = NOW();
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGER: Calculate indicators on ticker insert
-- =============================================================================

-- Create trigger - fires AFTER INSERT (once per insert)
CREATE TRIGGER calculate_indicators_trigger
    AFTER INSERT ON ticker_24hr_stats
    FOR EACH ROW
    EXECUTE FUNCTION calculate_indicators_on_insert();

-- =============================================================================
-- NOTES
-- =============================================================================

-- This trigger:
-- 1. Fires ONCE per INSERT into ticker_24hr_stats
-- 2. Calculates indicators using PL/pgSQL (no Python needed)
-- 3. Stores results in tick_indicators table
-- 4. Completes within the INSERT transaction

-- Indicators calculated:
-- - SMA 20, SMA 50
-- - EMA 12, EMA 26
-- - MACD (EMA12 - EMA26)
-- - RSI 14-period
-- - Bollinger Bands (20, 2 std)
