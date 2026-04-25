-- Phase 3 strategy lifecycle foundation.
-- Adds versioned strategy configuration, runtime tracking, backtests, and audit events.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS strategies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT,
    mode TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper', 'live')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'validated', 'active', 'paused', 'archived')),
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_strategies_name ON strategies (name);
CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies (status);
CREATE INDEX IF NOT EXISTS idx_strategies_mode ON strategies (mode);

CREATE TABLE IF NOT EXISTS strategy_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    config JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(strategy_id, version)
);

CREATE INDEX IF NOT EXISTS idx_strategy_versions_strategy_id
    ON strategy_versions (strategy_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_versions_active
    ON strategy_versions (strategy_id)
    WHERE is_active = true;

CREATE TABLE IF NOT EXISTS strategy_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    strategy_version_id UUID NOT NULL REFERENCES strategy_versions(id) ON DELETE RESTRICT,
    run_mode TEXT NOT NULL CHECK (run_mode IN ('paper', 'live')),
    state TEXT NOT NULL DEFAULT 'running' CHECK (state IN ('running', 'stopped', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_strategy_runs_strategy_id ON strategy_runs (strategy_id, started_at DESC);

CREATE TABLE IF NOT EXISTS strategy_backtests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    strategy_version_id UUID NOT NULL REFERENCES strategy_versions(id) ON DELETE RESTRICT,
    time_range_start TIMESTAMPTZ NOT NULL,
    time_range_end TIMESTAMPTZ NOT NULL,
    initial_balance NUMERIC(20, 10) NOT NULL,
    final_balance NUMERIC(20, 10),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    trades JSONB NOT NULL DEFAULT '[]'::jsonb,
    equity_curve JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (time_range_start < time_range_end)
);

CREATE INDEX IF NOT EXISTS idx_strategy_backtests_strategy_id
    ON strategy_backtests (strategy_id, created_at DESC);

CREATE TABLE IF NOT EXISTS strategy_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    strategy_version_id UUID REFERENCES strategy_versions(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategy_events_strategy_id
    ON strategy_events (strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_events_event_type
    ON strategy_events (event_type, created_at DESC);
