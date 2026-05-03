--
-- Migration: Create strategy_instances table
-- Phase 4 Step 5
--

-- Enable UUID extension if not exists (idempotent)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--
-- Create strategy_instances table
--
CREATE TABLE strategy_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    config_set_id UUID NOT NULL REFERENCES configuration_sets(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (
        status IN ('stopped', 'running', 'paused', 'error')
    ),
    runtime_stats JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_strategy_config UNIQUE(strategy_id, config_set_id),
    CONSTRAINT chk_runtime_stats_json CHECK (jsonb_typeof(runtime_stats) = 'object')
);

--
-- Indexes
--
CREATE INDEX idx_strategy_instances_status ON strategy_instances(status);
CREATE INDEX idx_strategy_instances_strategy ON strategy_instances(strategy_id);
CREATE INDEX idx_strategy_instances_config ON strategy_instances(config_set_id);

--
-- Auto-update updated_at trigger
--
CREATE OR REPLACE FUNCTION update_strategy_instance_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_strategy_instances_updated_at
    BEFORE UPDATE ON strategy_instances
    FOR EACH ROW
    EXECUTE FUNCTION update_strategy_instance_updated_at();

--
-- Comments
--
COMMENT ON TABLE strategy_instances IS 'Links Algorithm with ConfigurationSet for deployment';
COMMENT ON COLUMN strategy_instances.runtime_stats IS 'JSONB with PnL, trades, uptime, etc.';
