-- Migration: Fix algorithm_backtests table to reference strategy_instances
-- Date: 2026-05-06
-- Description: Rename columns to be consistent with the domain model.
-- StrategyInstance = Algorithm + ConfigurationSet, and backtests run on StrategyInstances.

-- Drop the old table and recreate with correct schema
DROP TABLE IF EXISTS algorithm_backtests CASCADE;

CREATE TABLE algorithm_backtests (
    id UUID DEFAULT public.uuid_generate_v4() NOT NULL,
    strategy_instance_id UUID NOT NULL,
    algorithm_version_id UUID NOT NULL,
    time_range_start TIMESTAMPTZ NOT NULL,
    time_range_end TIMESTAMPTZ NOT NULL,
    initial_balance NUMERIC(20,10) NOT NULL,
    final_balance NUMERIC(20,10),
    metrics JSONB DEFAULT '{}'::JSONB NOT NULL,
    trades JSONB DEFAULT '[]'::JSONB NOT NULL,
    equity_curve JSONB DEFAULT '[]'::JSONB NOT NULL,
    created_by TEXT DEFAULT 'system'::TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT algorithm_backtests_pkey PRIMARY KEY (id),
    CONSTRAINT algorithm_backtests_strategy_instance_id_fkey 
        FOREIGN KEY (strategy_instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE,
    CONSTRAINT algorithm_backtests_algorithm_version_id_fkey 
        FOREIGN KEY (algorithm_version_id) REFERENCES algorithm_versions(id) ON DELETE RESTRICT,
    CONSTRAINT algorithm_backtests_check CHECK (time_range_start < time_range_end)
);

CREATE INDEX idx_algorithm_backtests_strategy_instance 
ON algorithm_backtests (strategy_instance_id, created_at DESC);

COMMENT ON TABLE algorithm_backtests IS 'Backtest results for StrategyInstances (Algorithm + ConfigurationSet)';
COMMENT ON COLUMN algorithm_backtests.strategy_instance_id IS 'References the strategy_instances table (Algorithm + ConfigSet combination)';
COMMENT ON COLUMN algorithm_backtests.algorithm_version_id IS 'Algorithm version used for the backtest';
