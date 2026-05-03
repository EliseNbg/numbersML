-- Test data script for integration tests
-- Run with: psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f migrations/test_data.sql
-- Or via pytest fixtures
-- Environment variables: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

SET timezone = 'UTC';

-- Create extensions if not exist
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. TEST SYMBOLS
-- ============================================

-- Insert test symbols (marked with is_test=true)
INSERT INTO symbols (
    symbol, base_asset, quote_asset, status, is_active, is_allowed,
    price_precision, quantity_precision, tick_size, step_size,
    min_notional, is_test
) VALUES
    ('BTC/USDC', 'BTC', 'USDC', 'TRADING', true, true, 2, 6, 0.01, 0.000001, 10.0, true),
    ('ETH/USDC', 'ETH', 'USDC', 'TRADING', true, true, 2, 6, 0.01, 0.000001, 10.0, true),
    ('DOGE/USDC', 'DOGE', 'USDC', 'TRADING', true, true, 6, 2, 0.000001, 1.0, 10.0, true),
    ('ADA/USDC', 'ADA', 'USDC', 'TRADING', true, true, 6, 2, 0.000001, 1.0, 10.0, true)
ON CONFLICT (symbol) DO UPDATE SET
    is_test = EXCLUDED.is_test,
    is_active = EXCLUDED.is_active,
    is_allowed = EXCLUDED.is_allowed;

-- ============================================
-- 2. COLLECTION CONFIG
-- ============================================

-- Insert collection config for test symbols
INSERT INTO collection_config (
    symbol_id, collect_ticks, collect_24hr_ticker, collect_orderbook, collect_candles,
    tick_snapshot_interval_sec, ticker_snapshot_interval_sec, candle_intervals,
    is_allowed, is_collecting
)
SELECT
    s.id,
    false,  -- collect_ticks
    true,   -- collect_24hr_ticker
    false,  -- collect_orderbook
    true,   -- collect_candles
    1,      -- tick_snapshot_interval_sec
    1,      -- ticker_snapshot_interval_sec
    ARRAY['1m', '5m', '15m', '1h'],  -- candle_intervals
    true,   -- is_allowed
    false   -- is_collecting
FROM symbols s
WHERE s.is_test = true
ON CONFLICT (symbol_id) DO NOTHING;

-- ============================================
-- 3. INDICATOR DEFINITIONS
-- ============================================

-- Insert common indicator definitions for testing
INSERT INTO indicator_definitions (
    name, class_name, module_path, category, description,
    params, params_schema, code_hash, is_active
) VALUES
    ('rsi', 'RSIIndicator', 'src.indicators.momentum', 'momentum',
     'Relative Strength Index',
     '{"period": 14}'::jsonb,
     '{"type": "object", "properties": {"period": {"type": "integer", "minimum": 2, "default": 14}}}'::jsonb,
     'hash_rsi_v1', true),
    ('sma', 'SMAIndicator', 'src.indicators.trend', 'trend',
     'Simple Moving Average',
     '{"period": 20}'::jsonb,
     '{"type": "object", "properties": {"period": {"type": "integer", "minimum": 2, "default": 20}}}'::jsonb,
     'hash_sma_v1', true),
    ('ema', 'EMAIndicator', 'src.indicators.trend', 'trend',
     'Exponential Moving Average',
     '{"period": 20}'::jsonb,
     '{"type": "object", "properties": {"period": {"type": "integer", "minimum": 2, "default": 20}}}'::jsonb,
     'hash_ema_v1', true),
    ('macd', 'MACDIndicator', 'src.indicators.trend', 'trend',
     'Moving Average Convergence Divergence',
     '{"fast_period": 12, "slow_period": 26, "signal_period": 9}'::jsonb,
     '{"type": "object", "properties": {"fast_period": {"type": "integer", "minimum": 2, "default": 12}, "slow_period": {"type": "integer", "minimum": 2, "default": 26}, "signal_period": {"type": "integer", "minimum": 2, "default": 9}}}'::jsonb,
     'hash_macd_v1', true),
    ('bollinger_bands', 'BollingerBandsIndicator', 'src.indicators.volatility_volume', 'volatility',
     'Bollinger Bands',
     '{"period": 20, "std_dev": 2.0}'::jsonb,
     '{"type": "object", "properties": {"period": {"type": "integer", "minimum": 2, "default": 20}, "std_dev": {"type": "number", "minimum": 0.1, "default": 2.0}}}'::jsonb,
     'hash_bb_v1', true)
ON CONFLICT (name) DO UPDATE SET
    is_active = EXCLUDED.is_active,
    params = EXCLUDED.params;

-- ============================================
-- 4. SYSTEM CONFIG
-- ============================================

INSERT INTO system_config (key, value, description, is_editable) VALUES
    ('pipeline.target_time_ms', '800'::jsonb, 'Target pipeline processing time in milliseconds', true),
    ('pipeline.max_symbols', '50'::jsonb, 'Maximum number of active symbols', true),
    ('pipeline.sla_threshold_ms', '1000'::jsonb, 'SLA threshold in milliseconds', true),
    ('indicators.default_list', '["rsi", "sma", "ema", "macd", "bollinger_bands"]'::jsonb, 'Default indicators for new symbols', true),
    ('features.enabled', 'true'::jsonb, 'Enable feature calculation', true)
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

-- ============================================
-- 5. SERVICE STATUS (initial)
-- ============================================

INSERT INTO service_status (service_name, status, is_healthy, metadata) VALUES
    ('pipeline', 'stopped', false, '{"version": "1.0.0"}'::jsonb),
    ('api', 'stopped', false, '{"version": "1.0.0"}'::jsonb),
    ('indicators', 'stopped', false, '{"version": "1.0.0"}'::jsonb)
ON CONFLICT (service_name) DO NOTHING;

-- ============================================
-- 6. SAMPLE CANDLES (for tests that need existing data)
-- ============================================

-- Insert sample 1-second candles for the last 5 minutes
WITH time_series AS (
    SELECT generate_series(
        date_trunc('minute', NOW() - INTERVAL '5 minutes'),
        date_trunc('minute', NOW()),
        INTERVAL '1 second'
    ) AS time
)
INSERT INTO candles_1s (time, symbol_id, open, high, low, close, volume, quote_volume, trade_count, target_value)
SELECT
    ts.time,
    s.id,
    50000.0 + (random() * 100)::numeric,  -- open
    50050.0 + (random() * 100)::numeric,  -- high
    49950.0 + (random() * 100)::numeric,  -- low
    50025.0 + (random() * 100)::numeric,  -- close
    1.0 + (random() * 10)::numeric,      -- volume
    (50000.0 + (random() * 100)) * (1.0 + random() * 10),  -- quote_volume
    (1 + random() * 100)::integer,       -- trade_count
    '{"trend": "up", "magnitude": 0.002}'::jsonb  -- target_value
FROM time_series ts
CROSS JOIN symbols s
WHERE s.is_test = true
ON CONFLICT (time, symbol_id) DO NOTHING;

-- ============================================
-- 7. SAMPLE INDICATORS (for tests that need existing data)
-- ============================================

INSERT INTO candle_indicators (time, symbol_id, price, volume, values)
SELECT
    c.time,
    c.symbol_id,
    c.close,
    c.volume,
    '{
        "rsi": {"value": 55.5, "metadata": {}},
        "sma": {"value": 50000.0, "metadata": {}},
        "ema": {"value": 50010.0, "metadata": {}}
    }'::jsonb
FROM candles_1s c
JOIN symbols s ON s.id = c.symbol_id
WHERE s.is_test = true
ON CONFLICT (time, symbol_id) DO NOTHING;

-- ============================================
-- 8. PIPELINE STATE (initial)
-- ============================================

INSERT INTO pipeline_state (symbol_id, last_trade_id, last_timestamp, is_recovering, trades_processed, gaps_detected)
SELECT
    s.id,
    0,
    NOW(),
    false,
    0,
    0
FROM symbols s
WHERE s.is_test = true
ON CONFLICT (symbol_id) DO NOTHING;

-- ============================================
-- 9. TEST/USDT SYMBOL FOR GRID STRATEGY
-- ============================================

-- Insert TEST/USDT symbol (if not exists)
INSERT INTO symbols (
    symbol, base_asset, quote_asset, status, is_active, is_allowed,
    price_precision, quantity_precision, tick_size, step_size,
    min_notional, is_test
) VALUES (
    'TEST/USDT', 'TEST', 'USDT', 'TRADING', true, true,
    2, 6, 0.01, 0.000001, 10.0, true
) ON CONFLICT (symbol) DO UPDATE SET
    is_test = EXCLUDED.is_test,
    is_active = EXCLUDED.is_active,
    is_allowed = EXCLUDED.is_allowed;


-- ============================================
-- 10. GRID STRATEGY CONFIGURATION SET
-- ============================================

INSERT INTO configuration_sets (name, description, config, is_active)
VALUES (
    'Grid TEST/USDT Default',
    'Default grid configuration for TEST/USDT with noised sin wave',
    '{
        "symbols": ["TEST/USDT"],
        "grid_levels": 5,
        "grid_spacing_pct": 1.0,
        "quantity": 0.01,
        "initial_balance": 10000.0,
        "risk": {
            "max_position_size_pct": 10,
            "max_daily_loss_pct": 5,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 0.5
        },
        "execution": {
            "order_type": "market",
            "slippage_bps": 10,
            "fee_bps": 10
        }
    }'::jsonb,
    true
) ON CONFLICT (name) DO UPDATE SET
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active;

-- ============================================
-- Done
-- ============================================

-- Show summary
SELECT 'Symbols' as table_name, count(*) as count FROM symbols WHERE is_test = true
UNION ALL
SELECT 'Collection Config', count(*) FROM collection_config cc JOIN symbols s ON s.id = cc.symbol_id WHERE s.is_test = true
UNION ALL
SELECT 'Indicator Definitions', count(*) FROM indicator_definitions WHERE is_active = true
UNION ALL
SELECT 'System Config', count(*) FROM system_config
UNION ALL
SELECT 'Sample Candles', count(*) FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id WHERE s.is_test = true
UNION ALL
SELECT 'Sample Indicators', count(*) FROM candle_indicators ci JOIN symbols s ON s.id = ci.symbol_id WHERE s.is_test = true;
