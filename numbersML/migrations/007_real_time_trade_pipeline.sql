-- Migration: 007_real_time_trade_pipeline.sql
-- Description: Add tables for real-time 1-second trade aggregation pipeline
-- Date: 2026-03-28

-- ============================================================================
-- 1-SECOND CANDLES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS 1s_candles (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- OHLC
    open NUMERIC(20,10) NOT NULL,
    high NUMERIC(20,10) NOT NULL,
    low NUMERIC(20,10) NOT NULL,
    close NUMERIC(20,10) NOT NULL,
    
    -- Volume
    volume NUMERIC(30,10) NOT NULL DEFAULT 0,
    quote_volume NUMERIC(40,10) NOT NULL DEFAULT 0,
    
    -- Trade info
    trade_count INTEGER NOT NULL DEFAULT 0,
    first_trade_id BIGINT NOT NULL,
    last_trade_id BIGINT NOT NULL,
    
    -- Metadata
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (time, symbol_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_1s_candles_symbol_time 
    ON 1s_candles(symbol_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_1s_candles_time 
    ON 1s_candles(time DESC);

COMMENT ON TABLE 1s_candles IS '1-second aggregated candles from trade data';
COMMENT ON COLUMN 1s_candles.open IS 'Opening price (first trade)';
COMMENT ON COLUMN 1s_candles.high IS 'Highest price in 1s window';
COMMENT ON COLUMN 1s_candles.low IS 'Lowest price in 1s window';
COMMENT ON COLUMN 1s_candles.close IS 'Closing price (last trade)';
COMMENT ON COLUMN 1s_candles.volume IS 'Total base asset volume';
COMMENT ON COLUMN 1s_candles.quote_volume IS 'Total quote asset volume';
COMMENT ON COLUMN 1s_candles.trade_count IS 'Number of trades in 1s window';
COMMENT ON COLUMN 1s_candles.first_trade_id IS 'First aggregate trade ID';
COMMENT ON COLUMN 1s_candles.last_trade_id IS 'Last aggregate trade ID';

-- ============================================================================
-- PIPELINE STATE TABLE (for recovery)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pipeline_state (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- Last processed trade
    last_trade_id BIGINT NOT NULL DEFAULT 0,
    last_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Recovery state
    is_recovering BOOLEAN NOT NULL DEFAULT false,
    recovery_start_time TIMESTAMP,
    recovery_end_time TIMESTAMP,
    
    -- Statistics
    trades_processed BIGINT NOT NULL DEFAULT 0,
    gaps_detected INTEGER NOT NULL DEFAULT 0,
    last_gap_time TIMESTAMP,
    
    -- Metadata
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT chk_recovery_time CHECK (
        (is_recovering = false AND recovery_start_time IS NULL) OR
        (is_recovering = true AND recovery_start_time IS NOT NULL)
    )
);

-- Index for recovery queries
CREATE INDEX IF NOT EXISTS idx_pipeline_state_recovering 
    ON pipeline_state(is_recovering) WHERE is_recovering = true;

COMMENT ON TABLE pipeline_state IS 'Pipeline state for gap recovery and tracking';
COMMENT ON COLUMN pipeline_state.last_trade_id IS 'Last processed aggregate trade ID';
COMMENT ON COLUMN pipeline_state.is_recovering IS 'Currently recovering from gap';
COMMENT ON COLUMN pipeline_state.trades_processed IS 'Total trades processed since start';
COMMENT ON COLUMN pipeline_state.gaps_detected IS 'Total gaps detected and recovered';

-- ============================================================================
-- PIPELINE METRICS TABLE (for monitoring)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Performance
    trades_per_second NUMERIC(10,2),
    candles_written INTEGER,
    recovery_events INTEGER,
    
    -- Errors
    websocket_errors INTEGER DEFAULT 0,
    database_errors INTEGER DEFAULT 0,
    recovery_errors INTEGER DEFAULT 0,
    
    -- State
    active_symbols INTEGER,
    queue_size INTEGER,
    
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for time-series queries
CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_time 
    ON pipeline_metrics(timestamp DESC);

-- Retention: Keep last 24 hours of metrics
-- (Implement via cron job or application cleanup)

COMMENT ON TABLE pipeline_metrics IS 'Real-time pipeline performance metrics';

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_1s_candle_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_1s_candle_timestamp_trigger
    BEFORE UPDATE ON 1s_candles
    FOR EACH ROW
    EXECUTE FUNCTION update_1s_candle_timestamp();

-- Update pipeline state timestamp trigger
CREATE OR REPLACE FUNCTION update_pipeline_state_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_pipeline_state_timestamp_trigger
    BEFORE UPDATE ON pipeline_state
    FOR EACH ROW
    EXECUTE FUNCTION update_pipeline_state_timestamp();

-- ============================================================================
-- INITIALIZATION
-- ============================================================================

-- Initialize pipeline state for all active symbols
INSERT INTO pipeline_state (symbol_id, last_trade_id, last_timestamp)
SELECT id, 0, NOW()
FROM symbols
WHERE is_active = true
ON CONFLICT (symbol_id) DO NOTHING;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 007: Real-time trade pipeline tables created';
    RAISE NOTICE '  - 1s_candles: 1-second aggregated candles';
    RAISE NOTICE '  - pipeline_state: Recovery state tracking';
    RAISE NOTICE '  - pipeline_metrics: Performance monitoring';
END $$;
