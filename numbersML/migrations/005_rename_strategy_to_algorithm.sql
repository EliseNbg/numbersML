-- Migration: Rename algorithm tables to algorithm
-- Date: 2026-05-05
-- Description: Rename all algorithm-related tables to algorithm for consistency

-- Rename main tables
ALTER TABLE IF EXISTS algorithms RENAME TO algorithms;
ALTER TABLE IF EXISTS algorithm_backtests RENAME TO algorithm_backtests;
ALTER TABLE IF EXISTS algorithm_instances RENAME TO algorithm_instances;
ALTER TABLE IF EXISTS algorithm_runtime_states RENAME TO algorithm_runtime_states;

-- Rename indexes (PostgreSQL automatically renames indexes with the table, but let's be explicit for clarity)
-- Indexes will be automatically renamed by PostgreSQL

-- Update foreign key references in other tables if needed
-- (Foreign key constraint names will still reference old table names but will work correctly)

-- Rename sequence if exists
ALTER SEQUENCE IF EXISTS algorithms_id_seq RENAME TO algorithms_id_seq;

-- Update any column comments that reference the old name
COMMENT ON TABLE algorithms IS 'Algorithm definitions (formerly algorithms)';
COMMENT ON TABLE algorithm_backtests IS 'Backtest jobs for algorithms (formerly algorithm_backtests)';
COMMENT ON TABLE algorithm_instances IS 'Running instances of algorithms (formerly algorithm_instances)';
COMMENT ON TABLE algorithm_runtime_states IS 'Runtime state of algorithm instances (formerly algorithm_runtime_states)';
