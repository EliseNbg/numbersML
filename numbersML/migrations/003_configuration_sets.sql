--
-- Migration: Create configuration_sets table
-- Phase 4 Step 2
--

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--
-- Create configuration_sets table
--
CREATE TABLE configuration_sets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1 NOT NULL,

    CONSTRAINT chk_version_positive CHECK (version > 0)
);

--
-- Indexes
--
CREATE INDEX idx_config_sets_active ON configuration_sets(is_active) WHERE is_active = true;
CREATE INDEX idx_config_sets_created_at ON configuration_sets(created_at DESC);

--
-- Auto-update updated_at trigger
--
CREATE OR REPLACE FUNCTION update_config_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_config_sets_updated_at
    BEFORE UPDATE ON configuration_sets
    FOR EACH ROW
    EXECUTE FUNCTION update_config_set_updated_at();

--
-- Comments
--
COMMENT ON TABLE configuration_sets IS 'Reusable configuration parameter sets for algorithms';
COMMENT ON COLUMN configuration_sets.name IS 'Human-readable name (unique)';
COMMENT ON COLUMN configuration_sets.config IS 'JSONB with symbols, thresholds, risk, execution params';
COMMENT ON COLUMN configuration_sets.is_active IS 'Whether available for new algorithm instances';
COMMENT ON COLUMN configuration_sets.version IS 'Incremented on each config update';
