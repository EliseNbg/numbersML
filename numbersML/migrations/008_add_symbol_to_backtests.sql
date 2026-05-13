-- Migration: Add symbol column to strategy_backtests table
-- This column stores the trading symbol used in the backtest (e.g., "DOGE/USDC")

ALTER TABLE strategy_backtests 
ADD COLUMN IF NOT EXISTS symbol TEXT;

-- Add index for efficient queries by symbol
CREATE INDEX IF NOT EXISTS idx_strategy_backtests_symbol ON strategy_backtests(symbol);

COMMENT ON COLUMN strategy_backtests.symbol IS 'Trading symbol used in the backtest (e.g., BTC/USDC, DOGE/USDC)';