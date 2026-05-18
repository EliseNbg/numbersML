-- Migration 012: Orders table
-- Stores executed orders from strategies

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID REFERENCES strategies(id),
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type VARCHAR(20) NOT NULL DEFAULT 'MARKET',
    quantity NUMERIC(20,10) NOT NULL,
    price NUMERIC(20,10),
    filled_quantity NUMERIC(20,10) DEFAULT 0,
    remaining_quantity NUMERIC(20,10),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'FILLED', 'CANCELED', 'REJECTED', 'PARTIAL')),
    execution_mode VARCHAR(20) NOT NULL DEFAULT 'paper',
    latency_ms INTEGER,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_strategy ON orders(strategy_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX idx_orders_symbol ON orders(symbol);
