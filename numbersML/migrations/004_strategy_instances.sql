--
-- Migration: Create strategy_instances table
-- Phase4 Step4
--

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--
-- Create strategy_instances table
--
CREATE TABLE strategy_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    config_set_id UUID NOT NULL REFERENCES configuration_sets(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('stopped', 'running', 'paused', 'error')),
    runtime_stats JSONB NOT NULL DEFAULT '{}',
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uk_strategy_config_set UNIQUE (strategy_id, config_set_id)
);

--
-- Indexes
--
CREATE INDEX idx_strategy_instances_status ON strategy_instances(status);
CREATE INDEX idx_strategy_instances_strategy_id ON strategy_instances(strategy_id);
CREATE INDEX idx_strategy_instances_config_set_id ON strategy_instances(config_set_id);
CREATE INDEX idx_strategy_instances_created_at ON strategy_instances(created_at DESC);

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
COMMENT ON TABLE strategy_instances IS 'Deployed strategy instances linking Strategy to ConfigurationSet';
COMMENT ON COLUMN strategy_instances.strategy_id IS 'UUID of the Strategy (from strategies table)';
COMMENT ON COLUMN strategy_instances.config_set_id IS 'UUID of the ConfigurationSet (from configuration_sets table)';
COMMENT ON COLUMN strategy_instances.status IS 'Lifecycle state: stopped, running, paused, error';
COMMENT ON COLUMN strategy_instances.runtime_stats IS 'JSONB with PnL, trades, uptime, etc.';
COMMENT ON COLUMN strategy_instances.started_at IS 'Timestamp when instance was last started';
COMMENT ON COLUMN strategy_instances.stopped_at IS 'Timestamp when instance was last stopped';
