# Quick Start - Data Collection

## Start Data Collection for Most Volatile Symbols

### Option 1: Automatic Script (Recommended)

```bash
# Make script executable
chmod +x scripts/start-collection.sh

# Run the script
./scripts/start-collection.sh
```

This will:
1. Find the 5 most volatile symbols on Binance
2. Start PostgreSQL and Redis
3. Register symbols in database
4. Start data collection

---

### Option 2: Manual Steps

#### Step 1: Find Volatile Symbols

```bash
# Run the volatility finder
python src/cli/find_volatile_symbols.py
```

Example output:
```
TOP 5 MOST VOLATILE SYMBOLS (24hr)
======================================================================
Rank  Symbol          Volatility   Price           Volume              
----------------------------------------------------------------------
1     PEPE/USDT          25.43%     $0.00000123    1234567890         
2     DOGE/USDT          18.92%     $0.08234       987654321          
3     SHIB/USDT          15.67%     $0.00000876    567890123          
4     SOL/USDT           12.34%     $102.45        234567890          
5     AVAX/USDT          11.89%     $35.67         123456789          
======================================================================

Symbols for configuration:
SYMBOLS = ['PEPE/USDT', 'DOGE/USDT', 'SHIB/USDT', 'SOL/USDT', 'AVAX/USDT']
```

#### Step 2: Start Infrastructure

```bash
cd docker

# Start PostgreSQL and Redis
docker-compose -f docker-compose-infra.yml up -d

# Wait for services
sleep 5

# Check health
docker-compose -f docker-compose-infra.yml ps
```

#### Step 3: Create Configuration

Create `config/symbols.txt`:
```
PEPE/USDT
DOGE/USDT
SHIB/USDT
SOL/USDT
AVAX/USDT
```

#### Step 4: Register Symbols in Database

```bash
# Connect to database
docker-compose -f docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading

# Insert symbols
INSERT INTO symbols (symbol, base_asset, quote_asset, exchange, tick_size, step_size, min_notional, is_allowed, is_active)
VALUES 
    ('PEPE/USDT', 'PEPE', 'USDT', 'binance', 0.00000001, 0.01, 10, true, true),
    ('DOGE/USDT', 'DOGE', 'USDT', 'binance', 0.00001, 1, 10, true, true),
    ('SHIB/USDT', 'SHIB', 'USDT', 'binance', 0.00000001, 1, 10, true, true),
    ('SOL/USDT', 'SOL', 'USDT', 'binance', 0.01, 0.01, 10, true, true),
    ('AVAX/USDT', 'AVAX', 'USDT', 'binance', 0.01, 0.01, 10, true, true)
ON CONFLICT (symbol) DO UPDATE SET is_active = true, is_allowed = true;
```

#### Step 5: Start Data Collection

```bash
# Set environment
export DATABASE_URL="postgresql://crypto:crypto@localhost:5432/crypto_trading"

# Start collector
python src/main.py
```

---

## Monitor Collection

### View Logs

```bash
# If running in Docker
docker logs crypto-data-collector -f

# If running locally
# Logs appear in terminal
```

### Check Database

```bash
# Connect to database
docker-compose -f docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading

# Count trades per symbol
SELECT 
    s.symbol,
    COUNT(*) as trade_count,
    MAX(t.time) as last_trade,
    MIN(t.time) as first_trade
FROM trades t
JOIN symbols s ON s.id = t.symbol_id
GROUP BY s.symbol
ORDER BY trade_count DESC;

# Recent trades
SELECT 
    s.symbol,
    t.time,
    t.price,
    t.quantity,
    t.side
FROM trades t
JOIN symbols s ON s.id = t.symbol_id
ORDER BY t.time DESC
LIMIT 20;

# Check data quality
SELECT 
    s.symbol,
    COUNT(*) as total_trades,
    COUNT(DISTINCT t.trade_id) as unique_trades
FROM trades t
JOIN symbols s ON s.id = t.symbol_id
GROUP BY s.symbol;
```

---

## Stop Collection

```bash
# Stop collector (Ctrl+C if running locally)

# Stop infrastructure
docker-compose -f docker/docker-compose-infra.yml down

# Or stop all services
docker-compose -f docker/docker-compose-infra.yml down -v
```

---

## Troubleshooting

### PostgreSQL Not Starting

```bash
# Check logs
docker-compose -f docker/docker-compose-infra.yml logs postgres

# Restart
docker-compose -f docker/docker-compose-infra.yml restart postgres
```

### Connection Refused

```bash
# Check if PostgreSQL is running
docker ps | grep crypto-postgres

# Check port
netstat -tlnp | grep 5432
```

### No Data Being Collected

```bash
# Check if symbols are active
docker-compose -f docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading -c \
    "SELECT symbol, is_active, is_allowed FROM symbols;"

# Check WebSocket connection in logs
docker logs crypto-data-collector | grep -i "connected\|error"
```

---

## Expected Output

```
2026-03-21 12:00:00 - INFO - Starting Binance WebSocket client for 5 symbols
2026-03-21 12:00:01 - INFO - Initialized 5 active symbols
2026-03-21 12:00:01 - INFO - Connecting to wss://stream.binance.com:9443/ws/...
2026-03-21 12:00:02 - INFO - WebSocket connected
2026-03-21 12:00:05 - DEBUG - Flushed 500 trades for symbol 1
2026-03-21 12:00:06 - DEBUG - Flushed 500 trades for symbol 2
...
```

---

## Data Storage Estimates

For 5 volatile symbols:

| Data Type | Per Day | Per Week | Per Month |
|-----------|---------|----------|-----------|
| **Trades** | ~500 MB | ~3.5 GB | ~15 GB |
| **24hr Ticker** | ~200 MB | ~1.4 GB | ~6 GB |

**Recommendation**: Run with at least 50 GB free disk space for 1 month of data.
