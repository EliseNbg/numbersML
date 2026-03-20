# Architecture Updates - Ticker Statistics Collection

## Summary

Added **24hr ticker statistics collection** as a separate, lightweight service that complements the individual trades collector.

---

## 🎯 Key Changes

### 1. Hybrid Data Collection Strategy

**Before**:
- Collect individual trades for all symbols
- High storage (~3 TB for 6 months, 10 symbols)

**After**:
- **24hr ticker stats** for ALL symbols (low storage, 1-second resolution)
- **Individual trades** for KEY symbols only (BTC, ETH)
- **Total storage**: ~1.4 TB (53% savings!)

---

### 2. New Service: Ticker Collector

**File**: `docker/docker-compose-ticker.yml`

```yaml
services:
  ticker-collector:
    container_name: crypto-ticker-collector
    environment:
      TICKER_SYMBOLS: BTC/USDT,ETH/USDT,BNB/USDT,...  # ALL active symbols
      TICKER_SNAPSHOT_INTERVAL_SEC: 1
    resources:
      limits:
        cpus: '1.0'
        memory: 512M  # Very lightweight!
```

**Purpose**: Collect 24hr ticker statistics from Binance

**Stream**: `<symbol>@ticker`

**Frequency**: Every 1 second

**Storage**: ~43 MB/day/symbol (vs. 1.7 GB/day for trades)

---

### 3. New Database Table

```sql
CREATE TABLE ticker_24hr_stats (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    
    -- Prices
    last_price NUMERIC(20,10),
    open_price NUMERIC(20,10),
    high_price NUMERIC(20,10),
    low_price NUMERIC(20,10),
    
    -- Changes
    price_change NUMERIC(20,10),
    price_change_pct NUMERIC(10,6),
    
    -- Volumes
    total_volume NUMERIC(30,10),
    total_quote_volume NUMERIC(40,10),
    
    -- Trade info
    total_trades INTEGER,
    first_trade_id BIGINT,
    last_trade_id BIGINT,
    
    PRIMARY KEY (time, symbol_id)
);
```

---

### 4. Updated Configuration

Add to `collection_config` table:

```sql
ALTER TABLE collection_config ADD COLUMN
    -- Ticker statistics (for ALL symbols)
    collect_24hr_ticker BOOLEAN NOT NULL DEFAULT true,
    ticker_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    
    -- Individual trades (for KEY symbols only)
    collect_individual_trades BOOLEAN NOT NULL DEFAULT false,
    trade_retention_days INTEGER DEFAULT 30;
```

**Default Configuration**:

```yaml
# For ALL active symbols
BTC/USDT:
  collect_24hr_ticker: true          # ✅ Yes
  ticker_snapshot_interval_sec: 1    # Every second
  collect_individual_trades: true    # ✅ Yes (key symbol)
  trade_retention_days: 30           # Keep trades 30 days

ETH/USDT:
  collect_24hr_ticker: true          # ✅ Yes
  collect_individual_trades: true    # ✅ Yes (key symbol)
  trade_retention_days: 30

# For OTHER symbols (XRP, SOL, BNB, etc.)
XRP/USDT:
  collect_24hr_ticker: true          # ✅ Yes
  collect_individual_trades: false   # ❌ No (save storage)
  trade_retention_days: 0
```

---

## 📊 Storage Comparison

### Before (All Trades)

```
Individual trades (10 symbols, 6 months):
100 trades/sec × 200 bytes × 86,400 sec × 10 × 180 days = ~3 TB
```

### After (Hybrid Approach)

```
24hr ticker stats (10 symbols, 6 months):
1 update/sec × 500 bytes × 86,400 sec × 10 × 180 days = ~77 GB

Individual trades (2 symbols, 30 days):
100 trades/sec × 200 bytes × 86,400 sec × 2 × 30 days = ~100 GB

Indicators (10 symbols, 6 months):
~700 GB

Order Book (future, 10 symbols, 6 months):
~500 GB

Total: ~1.4 TB  ✅ 53% SAVINGS!
```

---

## 🚀 Implementation Files

### New Files to Create

1. **`docs/ticker-collector-design.md`** ✅ COMPLETE
   - Complete implementation guide
   - TickerStatsCollector class
   - Database schema
   - Docker Compose file
   - Usage examples

2. **`src/infrastructure/exchanges/ticker_collector.py`** (to implement)
   - TickerStatsCollector class
   - WebSocket connection to `@ticker` streams
   - Store in `ticker_24hr_stats` table

3. **`docker/docker-compose-ticker.yml`** (to implement)
   - Ticker collector service
   - Lightweight (1 CPU, 512MB RAM)

4. **`src/cli/commands/ticker.py`** (optional)
   - CLI commands for ticker management
   - Query ticker data
   - Configuration

---

## 🔧 Usage Examples

### Start Ticker Collector

```bash
# Start service
docker-compose -f docker-compose-ticker.yml up -d

# Check status
docker-compose -f docker-compose-ticker.yml ps

# View logs
docker logs crypto-ticker-collector -f
```

### Configure Per Symbol

```bash
# Enable ticker for all symbols (default)
crypto config set-symbol BTC/USDT collect_24hr_ticker true

# Change snapshot interval
crypto config set-symbol BTC/USDT ticker_snapshot_interval_sec 5

# Enable individual trades for key symbols only
crypto config set-symbol BTC/USDT collect_individual_trades true
crypto config set-symbol ETH/USDT collect_individual_trades true

# Disable for other symbols (save storage)
crypto config set-symbol XRP/USDT collect_individual_trades false
```

### Query Ticker Data

```sql
-- Get latest ticker for all symbols
SELECT DISTINCT ON (symbol_id)
    time, symbol, last_price, price_change, price_change_pct,
    total_volume, total_trades
FROM ticker_24hr_stats
ORDER BY symbol_id, time DESC;

-- Get 24hr price history for BTC
SELECT 
    time, last_price, high_price, low_price, total_volume
FROM ticker_24hr_stats
WHERE symbol = 'BTC/USDT'
  AND time > NOW() - INTERVAL '24 hours'
ORDER BY time DESC;

-- Derive 1-minute candles from ticker data
SELECT 
    date_trunc('minute', time) AS candle_time,
    first(last_price) AS open,
    max(high_price) AS high,
    min(low_price) AS low,
    last(last_price) AS close,
    sum(total_volume) AS volume
FROM ticker_24hr_stats
WHERE symbol = 'BTC/USDT'
  AND time > NOW() - INTERVAL '1 hour'
GROUP BY candle_time
ORDER BY candle_time;
```

---

## 📈 Benefits

### Storage Efficiency

| Data Type | Before | After | Savings |
|-----------|--------|-------|---------|
| Ticks/Trades | 3 TB | 100 GB | 97% |
| Ticker Stats | - | 77 GB | - |
| **Total** | **3 TB** | **~1.4 TB** | **53%** |

### Performance

- **Lower write load**: 1 update/sec vs. 100-1000 trades/sec
- **Faster queries**: Smaller tables, fewer rows
- **Less compression needed**: Can keep more data uncompressed

### Flexibility

- ✅ Enable/disable per symbol
- ✅ Change frequency without restart
- ✅ Derive candles from ticker data
- ✅ Add individual trades for specific symbols later

---

## 🎯 When to Use Each Data Type

### Use 24hr Ticker Stats For:

- ✅ Market monitoring
- ✅ Daily/weekly strategies
- ✅ Standard backtesting (1m+ timeframes)
- ✅ Portfolio tracking
- ✅ Price alerts
- ✅ Volume analysis

### Use Individual Trades For:

- ✅ High-frequency backtesting
- ✅ Order flow analysis
- ✅ Market microstructure research
- ✅ Precise entry/exit simulation
- ✅ Tick-level strategies

---

## 📝 Updated Service Architecture

```
┌────────────────────────────────────────────────────────────┐
│              DATA COLLECTION LAYER                          │
│                                                             │
│  ┌──────────────────┐         ┌──────────────────┐        │
│  │  Trade Collector │         │ Ticker Collector │        │
│  │  (Key symbols)   │         │ (All symbols)    │        │
│  │                  │         │                  │        │
│  │  @trade stream   │         │  @ticker stream  │        │
│  │  100-1000/sec    │         │  1/sec           │        │
│  │  High storage    │         │  Low storage     │        │
│  └────────┬─────────┘         └────────┬─────────┘        │
│           │                            │                   │
│           ▼                            ▼                   │
│  ┌──────────────────┐         ┌──────────────────┐        │
│  │  trades table    │         │ ticker_24hr_     │        │
│  │  (BTC, ETH only) │         │ stats table      │        │
│  │  ~100 GB         │         │  ~77 GB          │        │
│  └──────────────────┘         └──────────────────┘        │
│                                                             │
│           Both feed into:                                   │
│  ┌──────────────────────────────────────────────┐          │
│  │  tick_indicators table (calculated indicators)│          │
│  └──────────────────────────────────────────────┘          │
└────────────────────────────────────────────────────────────┘
```

---

## ✅ Implementation Checklist

### Phase 1 (Next Week)

- [ ] Create `ticker_24hr_stats` table
- [ ] Implement `TickerStatsCollector` class
- [ ] Create `docker-compose-ticker.yml`
- [ ] Update management scripts
- [ ] Test with all active symbols
- [ ] Monitor storage growth

### Phase 2 (Following Week)

- [ ] Update `DataCollectionService` to only collect for key symbols
- [ ] Configure per-symbol settings
- [ ] Test hybrid approach
- [ ] Verify storage savings
- [ ] Update documentation

### Phase 3 (Optional)

- [ ] Add candle derivation from ticker data
- [ ] Add ticker-based indicators
- [ ] Create dashboard for ticker metrics
- [ ] Add alerting on ticker thresholds

---

## 📚 Related Documents

- [ticker-collector-design.md](ticker-collector-design.md) - Complete implementation guide
- [modular-service-architecture.md](modular-service-architecture.md) - Updated service list
- [dynamic-configuration-design.md](dynamic-configuration-design.md) - Configuration management
- [data-flow-design.md](data-flow-design.md) - Overall data flow (updated)

---

## 🚀 Next Steps

1. **Review** [ticker-collector-design.md](ticker-collector-design.md)
2. **Implement** TickerStatsCollector class
3. **Create** docker-compose-ticker.yml
4. **Test** with all active symbols
5. **Monitor** storage and performance
6. **Adjust** configuration as needed

**Ready to implement the ticker collector!** 🎯
