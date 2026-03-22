-- Migration: 001_initial_schema
-- Description: Create core tables for crypto trading system
-- Date: 2026-03-20

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
CREATE TABLE IF NOT EXISTS tick_indicators (
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
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (symbol_id, date, hour)
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
    collect_candles BOOLEAN NOT NULL DEFAULT true,

    -- Collection frequency (seconds)
    tick_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    ticker_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    orderbook_snapshot_interval_sec INTEGER DEFAULT 1,
    candle_intervals TEXT[] NOT NULL DEFAULT '{"1m", "5m", "15m", "1h"}',

    -- Order book configuration (future)
    orderbook_levels INTEGER DEFAULT 10,
    orderbook_storage_mode TEXT DEFAULT 'arrays',

    -- Retention policies (days)
    tick_retention_days INTEGER NOT NULL DEFAULT 30,
    ticker_retention_days INTEGER NOT NULL DEFAULT 180,
    orderbook_retention_days INTEGER DEFAULT 30,
    candle_retention_days INTEGER NOT NULL DEFAULT 365,

    -- Quality thresholds
    max_price_move_pct NUMERIC(10,4) DEFAULT 10.0,
    max_quantity_move_pct NUMERIC(10,4) DEFAULT 50.0,
    max_gap_seconds INTEGER DEFAULT 5,

    -- Regional (EU compliance)
    is_allowed BOOLEAN NOT NULL DEFAULT true,
    last_region_check TIMESTAMP DEFAULT NOW(),

    -- Status
    is_collecting BOOLEAN NOT NULL DEFAULT false,
    last_config_change TIMESTAMP NOT NULL DEFAULT NOW(),
    config_version INTEGER NOT NULL DEFAULT 1,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_tick_interval CHECK (tick_snapshot_interval_sec >= 1),
    CONSTRAINT chk_ticker_interval CHECK (ticker_snapshot_interval_sec >= 1),
    CONSTRAINT chk_orderbook_levels CHECK (
        orderbook_levels IS NULL OR
        (orderbook_levels >= 5 AND orderbook_levels <= 20)
    ),
    CONSTRAINT chk_retention_days CHECK (tick_retention_days >= 0)
);

-- Audit trail for configuration changes
CREATE TABLE IF NOT EXISTS config_change_log (
    id BIGSERIAL PRIMARY KEY,
    config_type TEXT NOT NULL,
    config_key TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'system',
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'applied',
    reason TEXT
);

-- Service status tracking
CREATE TABLE IF NOT EXISTS service_status (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    pid INTEGER,
    host TEXT,
    port INTEGER,
    is_healthy BOOLEAN NOT NULL DEFAULT false,
    last_health_check TIMESTAMP,
    health_check_error TEXT,
    uptime_seconds BIGINT DEFAULT 0,
    records_processed BIGINT DEFAULT 0,
    errors_last_hour INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMP,
    config_version INTEGER DEFAULT 1,
    started_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- =============================================================================
-- MARKET DATA TABLES (ADDITIONAL)
-- =============================================================================

-- 24hr ticker statistics (low storage, all symbols)
CREATE TABLE IF NOT EXISTS ticker_24hr_stats (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    symbol TEXT NOT NULL,
    pair TEXT,

    -- Price changes
    price_change NUMERIC(20,10),
    price_change_pct NUMERIC(10,6),

    -- Prices
    last_price NUMERIC(20,10) NOT NULL,
    open_price NUMERIC(20,10),
    high_price NUMERIC(20,10),
    low_price NUMERIC(20,10),
    weighted_avg_price NUMERIC(20,10),

    -- Volumes
    last_quantity NUMERIC(20,10),
    total_volume NUMERIC(30,10),
    total_quote_volume NUMERIC(40,10),

    -- Trade IDs
    first_trade_id BIGINT,
    last_trade_id BIGINT,
    total_trades INTEGER,

    -- Times
    stats_open_time TIMESTAMP,
    stats_close_time TIMESTAMP,

    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (time, symbol_id)
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Domain table indexes
CREATE INDEX IF NOT EXISTS idx_symbols_status ON symbols(status);
CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_symbols_allowed ON symbols(is_allowed) WHERE is_allowed = true;
CREATE INDEX IF NOT EXISTS idx_trades_time_symbol ON trades(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades(symbol_id, time DESC);

-- Indicator indexes
CREATE INDEX IF NOT EXISTS idx_indicator_definitions_category ON indicator_definitions(category);
CREATE INDEX IF NOT EXISTS idx_indicator_definitions_active ON indicator_definitions(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_tick_indicators_time_symbol ON tick_indicators(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_tick_indicators_keys ON tick_indicators USING GIN (indicator_keys);

-- Job indexes
CREATE INDEX IF NOT EXISTS idx_recalculation_jobs_status ON recalculation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_recalculation_jobs_created_at ON recalculation_jobs(created_at DESC);

-- Quality indexes
CREATE INDEX IF NOT EXISTS idx_quality_issues_symbol ON data_quality_issues(symbol_id);
CREATE INDEX IF NOT EXISTS idx_quality_issues_detected_at ON data_quality_issues(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_quality_issues_resolved ON data_quality_issues(resolved) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_date ON data_quality_metrics(symbol_id, date DESC);

-- Configuration indexes
CREATE INDEX IF NOT EXISTS idx_system_config_key ON system_config(key);
CREATE INDEX IF NOT EXISTS idx_collection_config_collecting
    ON collection_config(is_collecting) WHERE is_collecting = true;
CREATE INDEX IF NOT EXISTS idx_config_change_log_type_key
    ON config_change_log(config_type, config_key);
CREATE INDEX IF NOT EXISTS idx_config_change_log_changed_at
    ON config_change_log(changed_at DESC);

-- Market data indexes
CREATE INDEX IF NOT EXISTS idx_ticker_stats_time_symbol
    ON ticker_24hr_stats(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_ticker_stats_symbol_time
    ON ticker_24hr_stats(symbol_id, time DESC);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables with updated_at
CREATE TRIGGER update_symbols_timestamp
    BEFORE UPDATE ON symbols
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_indicator_definitions_timestamp
    BEFORE UPDATE ON indicator_definitions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tick_indicators_timestamp
    BEFORE UPDATE ON tick_indicators
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_config_timestamp
    BEFORE UPDATE ON system_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_collection_config_timestamp
    BEFORE UPDATE ON collection_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_service_status_timestamp
    BEFORE UPDATE ON service_status
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Notify on config change
CREATE OR REPLACE FUNCTION notify_config_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'config_changed',
        json_build_object(
            'type', TG_TABLE_NAME,
            'key', NEW.key,
            'old_value', OLD.value,
            'new_value', NEW.value
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Notify on indicator change
CREATE OR REPLACE FUNCTION notify_indicator_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'indicator_changed',
        json_build_object(
            'indicator_name', NEW.name,
            'change_type', TG_OP,
            'version', NEW.version
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Notify on system_config changes
CREATE TRIGGER system_config_change_notification
    AFTER UPDATE ON system_config
    FOR EACH ROW
    WHEN (OLD.value IS DISTINCT FROM NEW.value)
    EXECUTE FUNCTION notify_config_change();

-- Notify on indicator_definitions changes
CREATE TRIGGER indicator_definitions_change_notification
    AFTER INSERT OR UPDATE OR DELETE ON indicator_definitions
    FOR EACH ROW
    EXECUTE FUNCTION notify_indicator_change();

-- =============================================================================
-- INITIAL DATA
-- =============================================================================

-- Insert default system configuration
INSERT INTO system_config (key, value, description) VALUES
('app.name', '{"value": "Crypto Trading System"}'::jsonb, 'Application name'),
('app.version', '{"value": "0.1.0"}'::jsonb, 'Application version'),
('app.environment', '{"value": "development"}'::jsonb, 'Environment'),
('app.region', '{"value": "EU"}'::jsonb, 'Operating region'),

-- Regional settings (EU compliance)
('region.allowed_quote_assets',
 '{"value": ["USDC", "BTC", "ETH"]}'::jsonb,
 'Allowed quote assets for EU region'),
('region.enable_auto_filter',
 '{"value": true}'::jsonb,
 'Enable auto-filtering by region'),

-- Data collection settings
('data_collection.enabled', '{"value": true}'::jsonb, 'Enable data collection'),
('data_collection.batch_size', '{"value": 500}'::jsonb, 'Batch size for inserts'),
('data_collection.batch_interval_ms', '{"value": 500}'::jsonb, 'Batch interval'),

-- Data quality settings
('data_quality.enabled', '{"value": true}'::jsonb, 'Enable quality validation'),
('data_quality.max_price_move_pct', '{"value": 10.0}'::jsonb, 'Max price move %'),
('data_quality.max_gap_seconds', '{"value": 5}'::jsonb, 'Max gap seconds'),

-- Enrichment settings
('enrichment.enabled', '{"value": true}'::jsonb, 'Enable enrichment'),
('enrichment.window_size', '{"value": 1000}'::jsonb, 'Window size'),
('enrichment.indicators',
 '{"value": ["rsi_14", "macd", "sma_20", "ema_20", "bollinger"]}'::jsonb,
 'Active indicators'),

-- Monitoring settings
('monitoring.enabled', '{"value": true}'::jsonb, 'Enable monitoring'),
('monitoring.log_level', '{"value": "INFO"}'::jsonb, 'Log level')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE symbols IS 'Trading pair symbols from Binance';
COMMENT ON TABLE trades IS 'Individual trade ticks';
COMMENT ON TABLE indicator_definitions IS 'Dynamic indicator definitions';
COMMENT ON TABLE tick_indicators IS 'Calculated indicator values per tick';
COMMENT ON TABLE recalculation_jobs IS 'Background jobs for indicator recalculation';

COMMENT ON TABLE data_quality_issues IS 'Detected data quality problems';
COMMENT ON TABLE data_quality_metrics IS 'Hourly data quality metrics';

COMMENT ON TABLE system_config IS 'Global system configuration';
COMMENT ON TABLE collection_config IS 'Per-symbol collection configuration';
COMMENT ON TABLE config_change_log IS 'Audit trail for configuration changes';
COMMENT ON TABLE service_status IS 'Real-time service status';
COMMENT ON TABLE ticker_24hr_stats IS '24hr ticker statistics';

COMMENT ON COLUMN symbols.is_allowed IS 'EU compliance - allowed for trading';
COMMENT ON COLUMN symbols.tick_size IS 'Minimum price increment';
COMMENT ON COLUMN symbols.step_size IS 'Minimum quantity increment';

COMMENT ON COLUMN collection_config.collect_ticks IS 'Collect individual trades';
COMMENT ON COLUMN collection_config.collect_24hr_ticker IS 'Collect 24hr ticker stats';
COMMENT ON COLUMN collection_config.is_allowed IS 'EU compliance flag';

COMMENT ON COLUMN tick_indicators.values IS 'JSONB with all indicator values';
COMMENT ON COLUMN tick_indicators.indicator_keys IS 'Array of indicator keys for fast lookup';

COMMENT ON COLUMN data_quality_issues.severity IS 'warning, error, or critical';
COMMENT ON COLUMN data_quality_metrics.quality_level IS 'excellent, good, fair, or poor';
