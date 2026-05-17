-- Migration 009: Strategy Signals Table
-- Stores all trade signals emitted by strategies during pipeline execution.

CREATE TABLE IF NOT EXISTS strategy_signals (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    strategy_id UUID NOT NULL REFERENCES strategies(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
    quantity NUMERIC(20,10) NOT NULL,
    price NUMERIC(20,10),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'EXECUTED', 'REJECTED', 'FAILED')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_strategy_signals_strategy ON strategy_signals(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_signals_symbol ON strategy_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_strategy_signals_status ON strategy_signals(status);
CREATE INDEX IF NOT EXISTS idx_strategy_signals_created ON strategy_signals(created_at DESC);

COMMENT ON TABLE strategy_signals IS 'Trade signals emitted by strategies during pipeline execution';
COMMENT ON COLUMN strategy_signals.metadata IS 'Additional context: expected_profit_price, reason, indicators_used, etc.';
