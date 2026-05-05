--
-- Migration: Create algorithm_instances table
-- Phase 4 Step 5
--

-- Enable UUID extension if not exists (idempotent)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--
-- Create algorithm_instances table
--
CREATE TABLE algorithm_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    algorithm_id UUID NOT NULL REFERENCES algorithms(id) ON DELETE CASCADE,
    config_set_id UUID NOT NULL REFERENCES configuration_sets(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (
        status IN ('stopped', 'running', 'paused', 'error')
    ),
    runtime_stats JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_algorithm_config UNIQUE(algorithm_id, config_set_id),
    CONSTRAINT chk_runtime_stats_json CHECK (jsonb_typeof(runtime_stats) = 'object')
);

--
-- Indexes
--
CREATE INDEX idx_algorithm_instances_status ON algorithm_instances(status);
CREATE INDEX idx_algorithm_instances_algorithm ON algorithm_instances(algorithm_id);
CREATE INDEX idx_algorithm_instances_config ON algorithm_instances(config_set_id);

--
-- Auto-update updated_at trigger
--
CREATE OR REPLACE FUNCTION update_algorithm_instance_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_algorithm_instances_updated_at
    BEFORE UPDATE ON algorithm_instances
    FOR EACH ROW
    EXECUTE FUNCTION update_algorithm_instance_updated_at();

--
-- Comments
--
COMMENT ON TABLE algorithm_instances IS 'Links Algorithm with ConfigurationSet for deployment';
COMMENT ON COLUMN algorithm_instances.runtime_stats IS 'JSONB with PnL, trades, uptime, etc.';
