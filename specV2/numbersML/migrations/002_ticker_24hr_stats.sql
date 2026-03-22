-- Migration: 002_ticker_24hr_stats
-- Description: Create table for 24hr ticker statistics
-- Date: 2026-03-21

-- =============================================================================
-- 24HR TICKER STATISTICS TABLE
-- =============================================================================

-- Store 24hr ticker statistics (updated every 1 second)
CREATE TABLE IF NOT EXISTS ticker_24hr_stats (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),

    -- Price data
    last_price NUMERIC(20,10) NOT NULL,
    open_price NUMERIC(20,10) NOT NULL,
    high_price NUMERIC(20,10) NOT NULL,
    low_price NUMERIC(20,10) NOT NULL,

    -- Volume data
    volume NUMERIC(30,10) NOT NULL,
    quote_volume NUMERIC(30,10) NOT NULL,

    -- Price change
    price_change NUMERIC(20,10),
    price_change_pct NUMERIC(10,4),

    -- Trade count
    trade_count BIGINT,

    -- Best bid/ask
    best_bid NUMERIC(20,10),
    best_ask NUMERIC(20,10),

    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (time, symbol_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ticker_time_symbol ON ticker_24hr_stats(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_ticker_symbol_time ON ticker_24hr_stats(symbol_id, time DESC);

-- Comment
COMMENT ON TABLE ticker_24hr_stats IS '24hr ticker statistics collected every 1 second';
COMMENT ON COLUMN ticker_24hr_stats.time IS 'Snapshot time';
COMMENT ON COLUMN ticker_24hr_stats.symbol_id IS 'Reference to symbols table';
COMMENT ON COLUMN ticker_24hr_stats.last_price IS 'Last traded price';
COMMENT ON COLUMN ticker_24hr_stats.volume IS '24hr trading volume';
COMMENT ON COLUMN ticker_24hr_stats.quote_volume IS '24hr quote currency volume';
COMMENT ON COLUMN ticker_24hr_stats.price_change IS 'Price change (24hr)';
COMMENT ON COLUMN ticker_24hr_stats.price_change_pct IS 'Price change percent (24hr)';
COMMENT ON COLUMN ticker_24hr_stats.trade_count IS 'Number of trades (24hr)';

-- =============================================================================
-- HELPER VIEWS
-- =============================================================================

-- Latest ticker stats per symbol
CREATE OR REPLACE VIEW latest_ticker_stats AS
SELECT DISTINCT ON (symbol_id)
    s.symbol,
    t.time,
    t.last_price,
    t.open_price,
    t.high_price,
    t.low_price,
    t.volume,
    t.quote_volume,
    t.price_change,
    t.price_change_pct,
    t.trade_count,
    t.best_bid,
    t.best_ask
FROM ticker_24hr_stats t
JOIN symbols s ON s.id = t.symbol_id
ORDER BY symbol_id, time DESC;

-- =============================================================================
-- SAMPLE DATA INSERT (for testing)
-- =============================================================================

-- Uncomment to insert sample data
-- INSERT INTO ticker_24hr_stats (time, symbol_id, last_price, open_price, high_price, low_price, volume, quote_volume, price_change, price_change_pct, trade_count)
-- VALUES (NOW(), 1, 50000.00, 49500.00, 50500.00, 49000.00, 1000000, 50000000, 500, 1.01, 100000);
