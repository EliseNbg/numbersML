-- Migration: 010_symbol_filters.sql
-- Add extended Binance filter columns to symbols table

ALTER TABLE symbols ADD COLUMN IF NOT EXISTS market_min_qty NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS market_max_qty NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS market_step_size NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS bid_multiplier_up NUMERIC(10,6) DEFAULT 1.3;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS bid_multiplier_down NUMERIC(10,6) DEFAULT 0.7;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS ask_multiplier_up NUMERIC(10,6) DEFAULT 5.0;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS ask_multiplier_down NUMERIC(10,6) DEFAULT 0.8;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS max_num_orders INTEGER DEFAULT 200;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS max_position NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS filters_last_synced TIMESTAMPTZ;
