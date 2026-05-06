-- Migration: Revert instance table renames
-- Date: 2026-05-06
-- Description: Rename algorithm_instances back to strategy_instances to match code naming.

-- Rename instance tables back
ALTER TABLE IF EXISTS algorithm_instances RENAME TO strategy_instances;
ALTER TABLE IF EXISTS algorithm_runtime_states RENAME TO strategy_runtime_states;

-- Update comments
COMMENT ON TABLE strategy_instances IS 'Running instances of algorithms (formerly algorithm_instances)';
COMMENT ON TABLE strategy_runtime_states IS 'Runtime state of algorithm instances (formerly algorithm_runtime_states)';
