# 🚀 Start Data Collection - Quick Guide

## Current Top 5 Volatile Symbols (Live from Binance)

```
===========================================================================
TOP 5 MOST VOLATILE SYMBOLS (24hr) - Binance
===========================================================================
Rank  Symbol          Volatility   Price           Volume              
---------------------------------------------------------------------------
1     TROY/USDC         114.29%     $0.00006500     3339535203.00000000 
2     DF/USDT            98.11%     $0.00164000     302888381.00000000  
3     SLF/USDC           97.32%     $0.02010000     18522191.70000000   
4     DF/USDC            90.46%     $0.00151000     15164880.00000000   
5     VIB/USDT           85.67%     $0.00223000     85327486.00000000   
===========================================================================
```

**Note**: Volatility changes frequently. Run the script to get current data.

---

## Option 1: Quick Start (Recommended)

### Step 1: Start Infrastructure

```bash
cd /home/andy/projects/numbers/specV2/crypto-trading-system

# Start PostgreSQL and Redis
docker-compose -f docker/docker-compose-infra.yml up -d

# Wait for services to be ready
sleep 10

# Check health
docker-compose -f docker/docker-compose-infra.yml ps
```

### Step 2: Run Data Collection

```bash
# Start collection for volatile symbols
.venv/bin/python src/cli/collect_volatile.py
```

That's it! Data will be collected in real-time.

---

## Option 2: Full Setup Script

```bash
# Run the automated setup
chmod +x scripts/start-collection.sh
./scripts/start-collection.sh
```

---

## Monitor Collection

### View Live Stats

The collector shows output like:
```
2026-03-21 12:00:00 - INFO - Starting collection for 5 symbols: ['TROY/USDC', 'DF/USDT', ...]
2026-03-21 12:00:01 - INFO - Registered symbol: TROY/USDC (ID: 1)
2026-03-21 12:00:02 - INFO - WebSocket connected - collecting data...
2026-03-21 12:00:05 - INFO - Stored 100 trades (total: 100)
2026-03-21 12:00:08 - INFO - Stored 100 trades (total: 200)
...
```

### Check Database

```bash
# Connect to database
docker-compose -f docker/docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading

# Count trades per symbol
SELECT 
    s.symbol,
    COUNT(*) as trade_count,
    MAX(t.time) as last_trade
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
LIMIT 10;

# Exit
\q
```

### Check Storage

```bash
# Check database size
docker-compose -f docker/docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading -c \
    "SELECT pg_size_pretty(pg_database_size('crypto_trading'));"
```

---

## Stop Collection

```bash
# Press Ctrl+C in the terminal running the collector

# Or stop infrastructure
docker-compose -f docker/docker-compose-infra.yml down
```

---

## Refresh Volatile Symbols

Volatility changes frequently. To get updated symbols:

```bash
# Run the volatility finder
.venv/bin/python src/cli/find_volatile_symbols.py

# Then restart collection with new symbols
.venv/bin/python src/cli/collect_volatile.py
```

---

## Troubleshooting

### PostgreSQL Not Starting

```bash
# Check if port 5432 is in use
netstat -tlnp | grep 5432

# Check Docker logs
docker-compose -f docker/docker-compose-infra.yml logs postgres
```

### Connection Refused

```bash
# Make sure Docker containers are running
docker ps | grep crypto

# Restart infrastructure
docker-compose -f docker/docker-compose-infra.yml down
docker-compose -f docker/docker-compose-infra.yml up -d
```

### No Trades Being Collected

```bash
# Check WebSocket connection
# Look for "WebSocket connected" in logs

# Check if symbols are active in database
docker-compose -f docker/docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading -c \
    "SELECT symbol, is_active FROM symbols;"
```

---

## Expected Data Volume

For 5 volatile symbols:

| Time Period | Estimated Trades | Database Size |
|-------------|-----------------|---------------|
| 1 hour | ~5,000-20,000 | ~10-50 MB |
| 1 day | ~100,000-500,000 | ~200-500 MB |
| 1 week | ~1-3 million | ~2-5 GB |

---

## Next Steps

After collecting data:

1. **Run Asset Sync** (optional - for complete metadata)
   ```bash
   .venv/bin/python src/cli/sync_assets.py
   ```

2. **Check Data Quality**
   ```bash
   docker-compose -f docker/docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading
   SELECT symbol, COUNT(*) as trades, COUNT(DISTINCT trade_id) as unique_trades
   FROM trades t JOIN symbols s ON s.id = t.symbol_id
   GROUP BY symbol;
   ```

3. **Fill Gaps** (if any)
   ```bash
   .venv/bin/python src/cli/gap_fill --detect
   ```

---

**Happy collecting! 📊**
