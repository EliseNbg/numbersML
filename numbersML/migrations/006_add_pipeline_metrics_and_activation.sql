-- Migration: 006_add_pipeline_metrics_and_activation.sql
-- Description: Add pipeline performance monitoring and activation controls
-- Date: 2026-03-23
-- Author: Senior Software Architect

-- ============================================================================
-- PART 1: Pipeline Metrics Table for Performance Monitoring
-- ============================================================================

-- Create pipeline_metrics table for tracking 1-second SLA compliance
CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    symbol_id INTEGER REFERENCES symbols(id),
    symbol TEXT NOT NULL,
    
    -- Pipeline stage timings (milliseconds)
    collection_time_ms INTEGER,
    enrichment_time_ms INTEGER,
    ml_inference_time_ms INTEGER,
    trade_execution_time_ms INTEGER,
    total_time_ms INTEGER NOT NULL,
    
    -- Context for capacity planning
    active_symbols_count INTEGER,
    active_indicators_count INTEGER,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'success',  -- success, slow, failed
    error_message TEXT,
    
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for dashboard queries
CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_timestamp 
    ON pipeline_metrics(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_symbol 
    ON pipeline_metrics(symbol_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_status 
    ON pipeline_metrics(status);

-- Index for SLA violation queries
CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_sla 
    ON pipeline_metrics(total_time_ms DESC) 
    WHERE total_time_ms > 1000;

-- Comment
COMMENT ON TABLE pipeline_metrics IS 'Real-time pipeline performance metrics for 1-second SLA monitoring';
COMMENT ON COLUMN pipeline_metrics.collection_time_ms IS 'Time to collect ticker from Binance (ms)';
COMMENT ON COLUMN pipeline_metrics.enrichment_time_ms IS 'Time to calculate indicators (ms)';
COMMENT ON COLUMN pipeline_metrics.ml_inference_time_ms IS 'Time for ML/LLM inference (ms) - future';
COMMENT ON COLUMN pipeline_metrics.trade_execution_time_ms IS 'Time to execute trade (ms) - future';
COMMENT ON COLUMN pipeline_metrics.total_time_ms IS 'Total pipeline time (ms)';
COMMENT ON COLUMN pipeline_metrics.active_symbols_count IS 'Number of active symbols at time of processing';
COMMENT ON COLUMN pipeline_metrics.active_indicators_count IS 'Number of active indicators at time of processing';
COMMENT ON COLUMN pipeline_metrics.status IS 'success (<1000ms), slow (>1000ms), or failed';


-- ============================================================================
-- PART 2: Dashboard Views
-- ============================================================================

-- View: Pipeline performance summary (last hour, by minute)
CREATE OR REPLACE VIEW v_pipeline_performance AS
SELECT 
    DATE_TRUNC('minute', timestamp) as minute,
    COUNT(*) as ticks_processed,
    ROUND(AVG(total_time_ms)::numeric, 2) as avg_total_time_ms,
    MAX(total_time_ms) as max_total_time_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p95_time_ms,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p99_time_ms,
    ROUND(AVG(enrichment_time_ms)::numeric, 2) as avg_enrichment_time_ms,
    ROUND(AVG(collection_time_ms)::numeric, 2) as avg_collection_time_ms,
    ROUND(AVG(active_symbols_count)::numeric, 0) as avg_active_symbols,
    ROUND(AVG(active_indicators_count)::numeric, 0) as avg_active_indicators,
    COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations,
    ROUND((COUNT(*) FILTER (WHERE total_time_ms > 1000)::numeric / COUNT(*) * 100), 2) as sla_violation_pct
FROM pipeline_metrics
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY DATE_TRUNC('minute', timestamp)
ORDER BY minute DESC;

COMMENT ON VIEW v_pipeline_performance IS 'Real-time pipeline performance dashboard (last hour, by minute)';


-- View: Active configuration summary
CREATE OR REPLACE VIEW v_active_configuration AS
SELECT 
    (SELECT COUNT(*) FROM symbols WHERE is_active = true AND is_allowed = true) as active_symbols,
    (SELECT COUNT(*) FROM indicator_definitions WHERE is_active = true) as active_indicators,
    (SELECT ARRAY_AGG(symbol ORDER BY symbol) FROM symbols WHERE is_active = true AND is_allowed = true) as symbol_list,
    (SELECT ARRAY_AGG(name ORDER BY name) FROM indicator_definitions WHERE is_active = true) as indicator_list,
    (SELECT COUNT(*) FROM symbols) as total_symbols,
    (SELECT COUNT(*) FROM indicator_definitions) as total_indicators;

COMMENT ON VIEW v_active_configuration IS 'Current active symbols and indicators configuration';


-- View: SLA compliance summary (last 24 hours)
CREATE OR REPLACE VIEW v_sla_compliance AS
SELECT 
    DATE_TRUNC('hour', timestamp) as hour,
    COUNT(*) as total_ticks,
    COUNT(*) FILTER (WHERE total_time_ms <= 1000) as sla_compliant,
    COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations,
    ROUND((COUNT(*) FILTER (WHERE total_time_ms <= 1000)::numeric / COUNT(*) * 100), 2) as compliance_pct,
    ROUND(AVG(total_time_ms)::numeric, 2) as avg_time_ms,
    MAX(total_time_ms) as max_time_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p95_time_ms,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p99_time_ms
FROM pipeline_metrics
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', timestamp)
ORDER BY hour DESC;

COMMENT ON VIEW v_sla_compliance IS 'SLA compliance report (1-second target, last 24 hours)';


-- View: Top slowest symbols (for capacity planning)
CREATE OR REPLACE VIEW v_slowest_symbols AS
SELECT 
    s.symbol,
    s.is_active,
    COUNT(*) as ticks_processed,
    ROUND(AVG(pm.total_time_ms)::numeric, 2) as avg_time_ms,
    MAX(pm.total_time_ms) as max_time_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY pm.total_time_ms)::numeric, 2) as p95_time_ms,
    COUNT(*) FILTER (WHERE pm.total_time_ms > 1000) as sla_violations,
    ROUND(AVG(pm.enrichment_time_ms)::numeric, 2) as avg_enrichment_ms,
    ROUND(AVG(pm.active_indicators_count)::numeric, 0) as avg_indicators
FROM pipeline_metrics pm
JOIN symbols s ON s.id = pm.symbol_id
WHERE pm.timestamp > NOW() - INTERVAL '1 hour'
GROUP BY s.symbol, s.is_active
ORDER BY avg_time_ms DESC
LIMIT 20;

COMMENT ON VIEW v_slowest_symbols IS 'Top 20 slowest symbols for capacity planning (last hour)';


-- ============================================================================
-- PART 3: Verify is_active field exists in symbols table
-- ============================================================================

-- Add is_active to symbols if not exists (should already exist)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'symbols' AND column_name = 'is_active'
    ) THEN
        ALTER TABLE symbols ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
        CREATE INDEX idx_symbols_active ON symbols(is_active) WHERE is_active = true;
    END IF;
END $$;

-- Ensure index exists for fast active symbol lookup
CREATE INDEX IF NOT EXISTS idx_symbols_active 
    ON symbols(is_active) WHERE is_active = true AND is_allowed = true;


-- ============================================================================
-- PART 4: Verify is_active field exists in indicator_definitions table
-- ============================================================================

-- Add is_active to indicator_definitions if not exists (should already exist)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'indicator_definitions' AND column_name = 'is_active'
    ) THEN
        ALTER TABLE indicator_definitions ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
        CREATE INDEX idx_indicator_definitions_active 
            ON indicator_definitions(is_active) WHERE is_active = true;
    END IF;
END $$;

-- Ensure index exists for fast active indicator lookup
CREATE INDEX IF NOT EXISTS idx_indicator_definitions_active 
    ON indicator_definitions(is_active) WHERE is_active = true;


-- ============================================================================
-- PART 5: Helper Functions
-- ============================================================================

-- Function: Get current pipeline performance
CREATE OR REPLACE FUNCTION get_pipeline_performance(
    p_minutes INTEGER DEFAULT 5
) RETURNS TABLE (
    avg_time_ms NUMERIC,
    max_time_ms INTEGER,
    p95_time_ms NUMERIC,
    p99_time_ms NUMERIC,
    ticks_processed BIGINT,
    sla_violations BIGINT,
    compliance_pct NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ROUND(AVG(total_time_ms)::numeric, 2) as avg_time_ms,
        MAX(total_time_ms) as max_time_ms,
        ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p95_time_ms,
        ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_time_ms)::numeric, 2) as p99_time_ms,
        COUNT(*) as ticks_processed,
        COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations,
        ROUND((COUNT(*) FILTER (WHERE total_time_ms <= 1000)::numeric / COUNT(*) * 100), 2) as compliance_pct
    FROM pipeline_metrics
    WHERE timestamp > NOW() - (p_minutes || ' minutes')::INTERVAL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_pipeline_performance IS 'Get current pipeline performance for last N minutes';


-- Function: Check if we can handle more symbols (capacity planning)
CREATE OR REPLACE FUNCTION can_handle_more_symbols(
    p_target_time_ms INTEGER DEFAULT 800,
    p_safety_margin NUMERIC DEFAULT 0.2
) RETURNS TABLE (
    can_add BOOLEAN,
    current_avg_time_ms NUMERIC,
    available_capacity_ms NUMERIC,
    recommendation TEXT
) AS $$
DECLARE
    v_current_avg NUMERIC;
    v_available NUMERIC;
BEGIN
    -- Get current average processing time
    SELECT AVG(total_time_ms) INTO v_current_avg
    FROM pipeline_metrics
    WHERE timestamp > NOW() - INTERVAL '5 minutes';
    
    v_current_avg := COALESCE(v_current_avg, 0);
    v_available := p_target_time_ms - v_current_avg;
    
    RETURN QUERY
    SELECT 
        (v_available > (p_target_time_ms * p_safety_margin)) as can_add,
        ROUND(v_current_avg, 2) as current_avg_time_ms,
        ROUND(v_available, 2) as available_capacity_ms,
        CASE 
            WHEN v_available > (p_target_time_ms * 0.5) THEN 'Can add more symbols/indicators'
            WHEN v_available > (p_target_time_ms * 0.2) THEN 'Approaching capacity limit'
            ELSE 'At capacity - reduce symbols/indicators'
        END as recommendation;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION can_handle_more_symbols IS 'Capacity planning: check if pipeline can handle more load';


-- ============================================================================
-- PART 6: Sample Data for Testing (Optional - Comment out in production)
-- ============================================================================

-- Insert sample metrics for testing (remove in production)
-- INSERT INTO pipeline_metrics (symbol_id, symbol, collection_time_ms, enrichment_time_ms, total_time_ms, active_symbols_count, active_indicators_count, status)
-- SELECT 
--     1,
--     'BTC/USDC',
--     (random() * 50 + 10)::int,
--     (random() * 200 + 50)::int,
--     (random() * 300 + 100)::int,
--     20,
--     12,
--     CASE WHEN random() > 0.95 THEN 'slow' ELSE 'success' END
-- FROM generate_series(NOW() - INTERVAL '1 hour', NOW(), INTERVAL '1 second');


-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Verify tables created
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pipeline_metrics') THEN
        RAISE NOTICE '✅ Migration 006 completed successfully';
        RAISE NOTICE '✅ pipeline_metrics table created';
        RAISE NOTICE '✅ Dashboard views created: v_pipeline_performance, v_active_configuration, v_sla_compliance, v_slowest_symbols';
        RAISE NOTICE '✅ Helper functions created: get_pipeline_performance(), can_handle_more_symbols()';
    ELSE
        RAISE EXCEPTION '❌ Migration 006 failed: pipeline_metrics table not created';
    END IF;
END $$;
