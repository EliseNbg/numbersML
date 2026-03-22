-- Migration: 004_add_is_test_field
-- Description: Add is_test field to symbols table for integration testing
-- Date: 2026-03-21

-- Add is_test column to symbols table
ALTER TABLE symbols
ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT false;

-- Add index for filtering test symbols
CREATE INDEX IF NOT EXISTS idx_symbols_is_test ON symbols(is_test);

-- Add comment
COMMENT ON COLUMN symbols.is_test IS 'Flag for test symbols used in integration tests';

-- Create 12 test symbols (ts1/USDC through ts12/USDC)
INSERT INTO symbols (symbol, base_asset, quote_asset, tick_size, step_size, min_notional, is_allowed, is_active, is_test)
VALUES
    ('ts1/USDC', 'ts1', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts2/USDC', 'ts2', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts3/USDC', 'ts3', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts4/USDC', 'ts4', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts5/USDC', 'ts5', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts6/USDC', 'ts6', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts7/USDC', 'ts7', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts8/USDC', 'ts8', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts9/USDC', 'ts9', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts10/USDC', 'ts10', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts11/USDC', 'ts11', 'USDC', 0.01, 0.01, 10, true, true, true),
    ('ts12/USDC', 'ts12', 'USDC', 0.01, 0.01, 10, true, true, true)
ON CONFLICT (symbol) DO UPDATE SET
    is_test = true,
    is_active = true,
    is_allowed = true,
    updated_at = NOW();

-- Verify test symbols were created
SELECT symbol, is_test, is_active, is_allowed
FROM symbols
WHERE is_test = true
ORDER BY symbol;
