-- =============================================================================
-- numbersML - Database Initialization Script
-- =============================================================================
-- Description: Complete database schema for Phase 1 (Data Gathering)
-- Version: 1.0 (Phase 1 Complete Snapshot)
-- Date: March 22, 2026
--
-- Usage:
--   psql -U crypto -d numbersml -f init_database.sql
--
-- This script:
-- 1. Creates all tables for data collection
-- 2. Creates all tables for indicators
-- 3. Creates all tables for configuration
-- 4. Creates all tables for data quality
-- 5. Creates triggers for EnrichmentService
-- 6. Creates helper views and functions
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- CORE DOMAIN TABLES
-- =============================================================================

-- Symbols metadata (from Binance exchange)
CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL,

    -- Status
    status TEXT NOT NULL DEFAULT 'TRADING',
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_allowed BOOLEAN NOT NULL DEFAULT true,  -- EU compliance
    is_test BOOLEAN NOT NULL DEFAULT false,    -- Test symbols

    -- Price filters
    price_precision INTEGER NOT NULL DEFAULT 8,
    tick_size NUMERIC(20,10) NOT NULL DEFAULT 0.01,
    min_price NUMERIC(20,10),
    max_price NUMERIC(20,10),

    -- Quantity filters
    quantity_precision INTEGER NOT NULL DEFAULT 8,
    step_size NUMERIC(20,10) NOT NULL DEFAULT 0.00001,
    min_quantity NUMERIC(20,10),
    max_quantity NUMERIC(20,10),

    -- Notional value filters
    min_notional NUMERIC(20,10) DEFAULT 10.0,
    max_notional NUMERIC(20,10),

    -- Market data
    last_price NUMERIC(20,10),
    last_update_id BIGINT,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_sync_at TIMESTAMP
);

-- Trades (tick data)
CREATE TABLE IF NOT EXISTS trades (
    trade_id BIGINT NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    price NUMERIC(20,10) NOT NULL,
    quantity NUMERIC(20,10) NOT NULL,
    quote_quantity NUMERIC(30,10),
    time TIMESTAMP NOT NULL,
    is_buyer_maker BOOLEAN,

    -- Metadata
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_id, symbol_id)
);

-- =============================================================================
-- 24HR TICKER STATISTICS
-- =============================================================================

CREATE TABLE IF NOT EXISTS ticker_24hr_stats (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    symbol TEXT NOT NULL,  -- Denormalized for easier queries
    pair TEXT,

    -- Price data
    last_price NUMERIC(20,10) NOT NULL,
    open_price NUMERIC(20,10),
    high_price NUMERIC(20,10),
    low_price NUMERIC(20,10),

    -- Volume data
    total_volume NUMERIC(30,10),
    total_quote_volume NUMERIC(40,10),

    -- Price change
    price_change NUMERIC(20,10),
    price_change_pct NUMERIC(10,6),

    -- Additional data
    weighted_avg_price NUMERIC(20,10),
    last_quantity NUMERIC(20,10),

    -- Trade info
    first_trade_id BIGINT,
    last_trade_id BIGINT,
    total_trades INTEGER,

    -- Timing
    stats_open_time TIMESTAMP,
    stats_close_time TIMESTAMP,

    -- Metadata
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDICATOR TABLES
-- =============================================================================

-- Indicator definitions (dynamic)
CREATE TABLE IF NOT EXISTS indicator_definitions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    class_name TEXT NOT NULL,
    module_path TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,

    -- Parameters
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    params_schema JSONB NOT NULL,

    -- Versioning
    code_hash TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by TEXT DEFAULT 'system',
    updated_by TEXT
);

-- Calculated indicators (stored per tick)
CREATE TABLE IF NOT EXISTS candle_indicators (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    price NUMERIC(20,10) NOT NULL,
    volume NUMERIC(20,10) NOT NULL,

    -- All indicator values (dynamic)
    values JSONB NOT NULL DEFAULT '{}'::jsonb,
    indicator_keys TEXT[] NOT NULL,

    -- Versioning
    indicator_version INTEGER NOT NULL DEFAULT 1,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (time, symbol_id)
);

-- Recalculation jobs
CREATE TABLE IF NOT EXISTS recalculation_jobs (
    id BIGSERIAL PRIMARY KEY,
    indicator_name TEXT NOT NULL REFERENCES indicator_definitions(name),
    status TEXT NOT NULL DEFAULT 'pending',
    triggered_by TEXT NOT NULL DEFAULT 'auto',
    ticks_processed BIGINT NOT NULL DEFAULT 0,
    total_ticks BIGINT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTERVAL,
    last_error TEXT,
    progress_pct NUMERIC(5,2) DEFAULT 0
);

-- =============================================================================
-- DATA QUALITY TABLES
-- =============================================================================

-- Data quality issues
CREATE TABLE IF NOT EXISTS data_quality_issues (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    raw_data JSONB NOT NULL,
    detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved BOOLEAN NOT NULL DEFAULT false,
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);

-- Data quality metrics (hourly aggregation)
CREATE TABLE IF NOT EXISTS data_quality_metrics (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    date DATE NOT NULL,
    hour INTEGER NOT NULL,

    -- Counts
    ticks_received BIGINT NOT NULL DEFAULT 0,
    ticks_validated BIGINT NOT NULL DEFAULT 0,
    ticks_rejected BIGINT NOT NULL DEFAULT 0,
    anomalies_detected BIGINT NOT NULL DEFAULT 0,
    gaps_detected BIGINT NOT NULL DEFAULT 0,
    gaps_filled BIGINT NOT NULL DEFAULT 0,

    -- Quality score
    quality_score NUMERIC(5,2),
    quality_level TEXT,

    -- Latency (milliseconds)
    latency_avg_ms NUMERIC(10,2),
    latency_p50_ms NUMERIC(10,2),
    latency_p95_ms NUMERIC(10,2),
    latency_p99_ms NUMERIC(10,2),

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- CONFIGURATION TABLES
-- =============================================================================

-- System-wide configuration
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    is_sensitive BOOLEAN NOT NULL DEFAULT false,
    is_editable BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    version INTEGER NOT NULL DEFAULT 1
);

-- Per-symbol collection configuration
CREATE TABLE IF NOT EXISTS collection_config (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,

    -- Data collection flags
    collect_ticks BOOLEAN NOT NULL DEFAULT false,
    collect_24hr_ticker BOOLEAN NOT NULL DEFAULT true,
    collect_orderbook BOOLEAN NOT NULL DEFAULT false,

    -- Collection parameters
    tick_snapshot_interval_sec INTEGER DEFAULT 1,
    orderbook_levels INTEGER DEFAULT 10,
    orderbook_snapshot_interval_sec INTEGER DEFAULT 1,

    -- Retention (days)
    tick_retention_days INTEGER DEFAULT 30,
    orderbook_retention_days INTEGER DEFAULT 7,

    -- Quality thresholds
    max_price_move_pct NUMERIC(5,2) DEFAULT 10.0,
    max_gap_seconds INTEGER DEFAULT 5,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Configuration change log
CREATE TABLE IF NOT EXISTS config_change_log (
    id BIGSERIAL PRIMARY KEY,
    config_type TEXT NOT NULL,  -- 'system' or 'symbol'
    config_key TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by TEXT,
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    symbol_id INTEGER REFERENCES symbols(id)
);

-- Service status tracking
CREATE TABLE IF NOT EXISTS service_status (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL,
    details JSONB,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Symbols
CREATE INDEX IF NOT EXISTS idx_symbols_status ON symbols(status);
CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(is_active);
CREATE INDEX IF NOT EXISTS idx_symbols_allowed ON symbols(is_allowed);
CREATE INDEX IF NOT EXISTS idx_symbols_test ON symbols(is_test);

-- Trades
CREATE INDEX IF NOT EXISTS idx_trades_time_symbol ON trades(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades(symbol_id, time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_unique ON trades(trade_id, symbol_id);

-- Ticker 24hr stats
CREATE INDEX IF NOT EXISTS idx_ticker_time_symbol ON ticker_24hr_stats(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_ticker_symbol_time ON ticker_24hr_stats(symbol_id, time DESC);

-- Indicators
CREATE INDEX IF NOT EXISTS idx_indicator_definitions_category ON indicator_definitions(category);
CREATE INDEX IF NOT EXISTS idx_indicator_definitions_active ON indicator_definitions(is_active);
CREATE INDEX IF NOT EXISTS idx_candle_indicators_time_symbol ON candle_indicators(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_candle_indicators_symbol_time ON candle_indicators(symbol_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_candle_indicators_keys ON candle_indicators USING GIN (indicator_keys);
CREATE INDEX IF NOT EXISTS idx_candle_indicators_values ON candle_indicators USING GIN (values);

-- Recalculation jobs
CREATE INDEX IF NOT EXISTS idx_recalculation_jobs_status ON recalculation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_recalculation_jobs_created_at ON recalculation_jobs(created_at);

-- Data quality
CREATE INDEX IF NOT EXISTS idx_quality_issues_symbol ON data_quality_issues(symbol_id);
CREATE INDEX IF NOT EXISTS idx_quality_issues_unresolved ON data_quality_issues(resolved) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_date ON data_quality_metrics(symbol_id, date, hour);

-- =============================================================================
-- HELPER VIEWS
-- =============================================================================

-- Active symbols only
CREATE OR REPLACE VIEW active_symbols AS
SELECT id, symbol, base_asset, quote_asset
FROM symbols
WHERE is_active = true AND is_allowed = true;

-- Latest ticker stats per symbol
CREATE OR REPLACE VIEW latest_ticker_stats AS
SELECT DISTINCT ON (symbol_id)
    s.symbol,
    t.time,
    t.last_price,
    t.open_price,
    t.high_price,
    t.low_price,
    t.total_volume,
    t.total_quote_volume,
    t.price_change,
    t.price_change_pct,
    t.total_trades
FROM ticker_24hr_stats t
JOIN symbols s ON s.id = t.symbol_id
WHERE s.is_active = true AND s.is_allowed = true
ORDER BY symbol_id, t.time DESC;

-- Latest indicators per symbol
CREATE OR REPLACE VIEW latest_indicators AS
SELECT DISTINCT ON (symbol_id)
    s.symbol,
    ti.time,
    ti.price,
    ti.volume,
    ti.values,
    ti.indicator_keys
FROM candle_indicators ti
JOIN symbols s ON s.id = ti.symbol_id
WHERE s.is_active = true AND s.is_allowed = true
ORDER BY symbol_id, ti.time DESC;

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Get or create symbol
CREATE OR REPLACE FUNCTION get_or_create_symbol(
    p_symbol TEXT,
    p_base_asset TEXT,
    p_quote_asset TEXT,
    p_exchange TEXT DEFAULT 'binance'
) RETURNS INTEGER AS $$
DECLARE v_symbol_id INTEGER;
BEGIN
    SELECT id INTO v_symbol_id FROM symbols
    WHERE symbol = p_symbol;

    IF v_symbol_id IS NULL THEN
        INSERT INTO symbols (symbol, base_asset, quote_asset)
        VALUES (p_symbol, p_base_asset, p_quote_asset)
        RETURNING id INTO v_symbol_id;
    END IF;

    RETURN v_symbol_id;
END;
$$ LANGUAGE plpgsql;

-- Notify on new tick (for EnrichmentService)
CREATE OR REPLACE FUNCTION notify_new_tick()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('new_tick', json_build_object(
        'symbol_id', NEW.symbol_id,
        'time', NEW.time,
        'inserted_at', NEW.inserted_at
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Notify on config change
CREATE OR REPLACE FUNCTION notify_config_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'config_changed',
        json_build_object(
            'config_type', TG_TABLE_NAME,
            'key', NEW.key,
            'value', NEW.value
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Notify EnrichmentService on new ticker data
CREATE TRIGGER notify_new_tick_trigger
    AFTER INSERT ON ticker_24hr_stats
    FOR EACH ROW
    EXECUTE FUNCTION notify_new_tick();

-- Notify on config changes
CREATE TRIGGER system_config_change_trigger
    AFTER UPDATE ON system_config
    FOR EACH ROW
    EXECUTE FUNCTION notify_config_change();

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE symbols IS 'Symbol metadata from Binance exchange';
COMMENT ON TABLE trades IS 'Individual trade ticks';
COMMENT ON TABLE ticker_24hr_stats IS '24hr ticker statistics collected every 1 second';
COMMENT ON TABLE candle_indicators IS 'Calculated indicator values per tick';
COMMENT ON TABLE indicator_definitions IS 'Dynamic indicator definitions';
COMMENT ON TABLE data_quality_issues IS 'Data quality issues and anomalies';
COMMENT ON TABLE collection_config IS 'Per-symbol collection configuration';
COMMENT ON FUNCTION notify_new_tick() IS 'Notify EnrichmentService of new ticks (Python calculates indicators)';

-- =============================================================================
-- INITIALIZATION COMPLETE
-- =============================================================================
