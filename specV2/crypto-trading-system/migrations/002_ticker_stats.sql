-- Migration: 002_ticker_stats
-- Description: Create ticker statistics table
-- Date: 2026-03-20

-- 24hr ticker statistics table
CREATE TABLE IF NOT EXISTS ticker_24hr_stats (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    symbol TEXT NOT NULL,
    pair TEXT,
    
    -- Price changes
    price_change NUMERIC(20,10),
    price_change_pct NUMERIC(10,6),
    
    -- Prices
    last_price NUMERIC(20,10) NOT NULL,
    open_price NUMERIC(20,10),
    high_price NUMERIC(20,10),
    low_price NUMERIC(20,10),
    weighted_avg_price NUMERIC(20,10),
    
    -- Volumes
    last_quantity NUMERIC(20,10),
    total_volume NUMERIC(30,10),
    total_quote_volume NUMERIC(40,10),
    
    -- Trade IDs
    first_trade_id BIGINT,
    last_trade_id BIGINT,
    total_trades INTEGER,
    
    -- Times
    stats_open_time TIMESTAMP,
    stats_close_time TIMESTAMP,
    
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (time, symbol_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ticker_stats_time_symbol 
    ON ticker_24hr_stats(time DESC, symbol_id);

CREATE INDEX IF NOT EXISTS idx_ticker_stats_symbol_time 
    ON ticker_24hr_stats(symbol_id, time DESC);

-- Comments
COMMENT ON TABLE ticker_24hr_stats IS '24hr ticker statistics from Binance';
COMMENT ON COLUMN ticker_24hr_stats.price_change IS 'Price change in quote currency';
COMMENT ON COLUMN ticker_24hr_stats.price_change_pct IS 'Price change percentage';
COMMENT ON COLUMN ticker_24hr_stats.weighted_avg_price IS 'Volume-weighted average price';
