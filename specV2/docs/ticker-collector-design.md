# Ticker Statistics Collector - Implementation

## Overview

**Purpose**: Collect 24hr ticker statistics from Binance for ALL active symbols

**Why**: Much more storage-efficient than individual trades while providing sufficient data for most strategies

---

## Binance 24hr Ticker Stream

### WebSocket Stream

```
Stream Name: <symbol>@ticker
Example: btcusdt@ticker
URL: wss://stream.binance.com:9443/ws/btcusdt@ticker
Frequency: Every 1 second (or 3 seconds for some symbols)
```

### Message Format

```json
{
  "e": "24hrTicker",      // Event type
  "E": 123456789,         // Event time
  "s": "BTCUSDT",         // Symbol
  "p": "0.0015",          // Price change
  "P": "0.152",           // Price change percent
  "w": "0.00147974",      // Weighted average price
  "c": "0.0015",          // Last price
  "Q": "10",              // Last quantity
  "o": "0.0014",          // Open price
  "h": "0.0016",          // High price
  "l": "0.0013",          // Low price
  "v": "487850",          // Total traded volume
  "q": "32968676323.46",  // Total traded quote volume
  "O": 1591181820000,     // Statistics open time
  "C": 1591268262442,     // Statistics close time
  "F": 512014,            // First trade ID
  "L": 615289,            // Last trade ID
  "n": 103272             // Total number of trades
}
```

---

## Database Schema

```sql
-- 24hr ticker statistics
CREATE TABLE ticker_24hr_stats (
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

-- Indexes
CREATE INDEX idx_ticker_stats_time_symbol ON ticker_24hr_stats(time DESC, symbol_id);
CREATE INDEX idx_ticker_stats_symbol_time ON ticker_24hr_stats(symbol_id, time DESC);
```

---

## Implementation

**File**: `src/infrastructure/exchanges/ticker_collector.py`

```python
"""24hr ticker statistics collection."""

import asyncio
import asyncpg
import websockets
import json
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class TickerStatsCollector:
    """
    Collects 24hr ticker statistics from Binance.
    
    Stream: <symbol>@ticker
    Frequency: Every 1 second (or 3 seconds)
    Storage: ~43 MB/day/symbol (very efficient)
    
    Benefits:
    - Much lower storage than individual trades
    - Sufficient for most strategies
    - Includes OHLCV, volume, trade count
    - Can derive 1m candles from this data
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        symbols: List[str],
        snapshot_interval_sec: int = 1,
    ):
        self.db_pool = db_pool
        self.symbols = symbols
        self.snapshot_interval = snapshot_interval_sec
        
        self._symbol_ids: Dict[str, int] = {}
        self._last_ticker: Dict[int, Dict] = {}
        self._running = False
    
    async def start(self):
        """Start ticker collection."""
        logger.info("Starting 24hr ticker collector...")
        
        # Initialize symbol mappings
        await self._init_symbols()
        
        self._running = True
        
        # Start WebSocket connection
        await self._connect_websocket()
    
    async def stop(self):
        """Stop ticker collection."""
        logger.info("Stopping 24hr ticker collector...")
        self._running = False
    
    async def _init_symbols(self):
        """Initialize symbol mappings from database."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, symbol FROM symbols
                WHERE is_active = true AND symbol = ANY($1)
                """,
                self.symbols
            )
            
            for row in rows:
                self._symbol_ids[row['symbol']] = row['id']
                self._last_ticker[row['id']] = {}
        
        logger.info(f"Initialized {len(self._symbol_ids)} symbols for ticker collection")
    
    async def _connect_websocket(self):
        """Connect to Binance ticker WebSocket."""
        # Build stream names
        streams = [
            f"{s.lower().replace('/', '')}@ticker"
            for s in self.symbols
        ]
        
        ws_url = f"wss://stream.binance.com:9443/ws/{'/'.join(streams)}"
        
        logger.info(f"Connecting to ticker WebSocket: {ws_url}")
        
        while self._running:
            try:
                async with websockets.connect(ws_url) as ws:
                    logger.info("Ticker WebSocket connected")
                    
                    while self._running:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        await self._process_ticker_msg(msg)
                        
            except Exception as e:
                logger.error(f"Ticker WebSocket error: {e}")
                await asyncio.sleep(5)  # Backoff
    
    async def _process_ticker_msg(self, msg: str):
        """Process incoming ticker message."""
        data = json.loads(msg)
        
        # Validate event type
        if data.get('e') != '24hrTicker':
            return
        
        # Parse symbol (BTCUSDT → BTC/USDT)
        symbol = data.get('s', '')
        if symbol.endswith('USDT'):
            symbol = f"{symbol[:-4]}/USDT"
        elif symbol.endswith('BUSD'):
            symbol = f"{symbol[:-4]}/BUSD"
        # Add more quote asset handling as needed
        
        if symbol not in self._symbol_ids:
            return
        
        symbol_id = self._symbol_ids[symbol]
        
        # Parse ticker data
        ticker = {
            'time': datetime.utcnow(),
            'symbol_id': symbol_id,
            'symbol': symbol,
            'pair': data.get('ps', ''),
            'price_change': Decimal(data.get('p', '0')),
            'price_change_pct': Decimal(data.get('P', '0')),
            'last_price': Decimal(data.get('c', '0')),
            'open_price': Decimal(data.get('o', '0')),
            'high_price': Decimal(data.get('h', '0')),
            'low_price': Decimal(data.get('l', '0')),
            'weighted_avg_price': Decimal(data.get('w', '0')),
            'last_quantity': Decimal(data.get('Q', '0')),
            'total_volume': Decimal(data.get('v', '0')),
            'total_quote_volume': Decimal(data.get('q', '0')),
            'first_trade_id': int(data.get('F', 0)),
            'last_trade_id': int(data.get('L', 0)),
            'total_trades': int(data.get('n', 0)),
            'stats_open_time': datetime.fromtimestamp(
                data.get('O', 0) / 1000
            ) if data.get('O') else None,
            'stats_close_time': datetime.fromtimestamp(
                data.get('C', 0) / 1000
            ) if data.get('C') else None,
        }
        
        # Store ticker
        await self._store_ticker(ticker)
        
        # Keep last ticker in memory
        self._last_ticker[symbol_id] = ticker
    
    async def _store_ticker(self, ticker: Dict):
        """Store ticker statistics (upsert)."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ticker_24hr_stats (
                    time, symbol_id, symbol, pair,
                    price_change, price_change_pct,
                    last_price, open_price, high_price, low_price,
                    weighted_avg_price, last_quantity,
                    total_volume, total_quote_volume,
                    first_trade_id, last_trade_id, total_trades,
                    stats_open_time, stats_close_time
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19
                )
                ON CONFLICT (time, symbol_id) DO UPDATE SET
                    last_price = EXCLUDED.last_price,
                    total_volume = EXCLUDED.total_volume,
                    total_quote_volume = EXCLUDED.total_quote_volume,
                    total_trades = EXCLUDED.total_trades,
                    last_trade_id = EXCLUDED.last_trade_id,
                    inserted_at = NOW()
                """,
                ticker['time'],
                ticker['symbol_id'],
                ticker['symbol'],
                ticker['pair'],
                ticker['price_change'],
                ticker['price_change_pct'],
                ticker['last_price'],
                ticker['open_price'],
                ticker['high_price'],
                ticker['low_price'],
                ticker['weighted_avg_price'],
                ticker['last_quantity'],
                ticker['total_volume'],
                ticker['total_quote_volume'],
                ticker['first_trade_id'],
                ticker['last_trade_id'],
                ticker['total_trades'],
                ticker['stats_open_time'],
                ticker['stats_close_time'],
            )
    
    def get_last_ticker(self, symbol_id: int) -> Optional[Dict]:
        """Get last received ticker for a symbol."""
        return self._last_ticker.get(symbol_id)
    
    def get_all_last_tickers(self) -> Dict[int, Dict]:
        """Get last ticker for all symbols."""
        return self._last_ticker.copy()
```

---

## Docker Compose Integration

**File**: `docker/docker-compose-ticker.yml`

```yaml
version: '3.8'

services:
  ticker-collector:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-ticker-collector
    restart: unless-stopped
    environment:
      # Application
      APP_SERVICE: ticker_collector
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Collector config
      TICKER_SYMBOLS: ${TICKER_SYMBOLS:-BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT,XRP/USDT}
      TICKER_SNAPSHOT_INTERVAL_SEC: ${TICKER_SNAPSHOT_INTERVAL_SEC:-1}
      
      # Feature flags
      TICKER_ENABLED: ${TICKER_ENABLED:-true}
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ticker_logs:/app/logs
      - ../config:/app/config:ro
    networks:
      - crypto_network
    healthcheck:
      test: ["CMD", "python", "-m", "src.cli.health_check"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M

volumes:
  ticker_logs:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

---

## Configuration

Add to `collection_config` table:

```sql
ALTER TABLE collection_config ADD COLUMN 
    -- Ticker statistics
    collect_24hr_ticker BOOLEAN NOT NULL DEFAULT true,
    ticker_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    
    -- Individual trades (high storage)
    collect_individual_trades BOOLEAN NOT NULL DEFAULT false,
    trade_retention_days INTEGER DEFAULT 30;
```

**Default Settings**:

```yaml
# For ALL active symbols
collect_24hr_ticker: true
ticker_snapshot_interval_sec: 1

# For KEY symbols only (BTC, ETH)
collect_individual_trades: true
trade_retention_days: 30

# For OTHER symbols
collect_individual_trades: false
trade_retention_days: 0
```

---

## Usage Examples

### Start Ticker Collector

```bash
# Start service
docker-compose -f docker-compose-ticker.yml up -d

# Check status
docker-compose -f docker-compose-ticker.yml ps

# View logs
docker logs crypto-ticker-collector -f
```

### Query Ticker Data

```sql
-- Get latest ticker for all symbols
SELECT DISTINCT ON (symbol_id)
    time,
    symbol,
    last_price,
    price_change,
    price_change_pct,
    total_volume,
    total_trades
FROM ticker_24hr_stats
ORDER BY symbol_id, time DESC;

-- Get price history for a symbol
SELECT 
    time,
    last_price,
    high_price,
    low_price,
    total_volume
FROM ticker_24hr_stats
WHERE symbol = 'BTC/USDT'
  AND time > NOW() - INTERVAL '24 hours'
ORDER BY time DESC;

-- Calculate 1-minute candles from ticker data
SELECT 
    date_trunc('minute', time) AS minute,
    first(last_price) AS open,
    max(high_price) AS high,
    min(low_price) AS low,
    last(last_price) AS close,
    sum(total_volume) AS volume
FROM ticker_24hr_stats
WHERE symbol = 'BTC/USDT'
  AND time > NOW() - INTERVAL '1 hour'
GROUP BY minute
ORDER BY minute;
```

### Configure Per-Symbol

```bash
# Enable ticker for all active symbols (default)
crypto config set-symbol BTC/USDT collect_24hr_ticker true

# Change snapshot interval
crypto config set-symbol BTC/USDT ticker_snapshot_interval_sec 5

# Enable individual trades for key symbols only
crypto config set-symbol BTC/USDT collect_individual_trades true
crypto config set-symbol ETH/USDT collect_individual_trades true

# Disable individual trades for other symbols (save storage)
crypto config set-symbol XRP/USDT collect_individual_trades false
```

---

## Storage Comparison

### 24hr Ticker Stats (Recommended)

```
1 update/sec × 500 bytes × 86,400 sec = 43 MB/day/symbol
43 MB × 10 symbols × 180 days = ~77 GB for 6 months ✅
```

### Individual Trades (Key Symbols Only)

```
100 trades/sec × 200 bytes × 86,400 sec = 1.7 GB/day/symbol
1.7 GB × 2 symbols × 30 days = ~100 GB for 30 days ✅
```

### Total Storage (Hybrid Approach)

```
Ticker (10 symbols, 6 months):    ~77 GB
Trades (2 symbols, 30 days):      ~100 GB
Indicators (10 symbols, 6mo):     ~700 GB
Order Book (future, 10 sym, 6mo): ~500 GB
────────────────────────────────────────────
Total:                            ~1.4 TB ✅
```

vs. **3+ TB** if collecting all trades for all symbols

**Savings: 53% less storage!**

---

## Benefits

✅ **Low Storage**: 77 GB vs. 3 TB for 6 months  
✅ **Sufficient for Most Strategies**: 1-second resolution  
✅ **Includes OHLCV**: Can derive candles  
✅ **Volume Data**: Total traded volume  
✅ **Trade Count**: Number of trades in 24hr window  
✅ **Scalable**: Easy to add more symbols  
✅ **Configurable**: Per-symbol settings  

---

## When to Use Individual Trades Instead

Use **individual trades** when you need:

- ✅ Precise entry/exit simulation
- ✅ Order flow analysis
- ✅ Market microstructure research
- ✅ High-frequency backtesting
- ✅ Trade-by-trade reconstruction

Use **24hr ticker** when you need:

- ✅ Market monitoring
- ✅ Daily/weekly strategies
- ✅ Standard backtesting (1m+ timeframes)
- ✅ Portfolio tracking
- ✅ Low storage footprint

**Recommendation**: Start with ticker for all, add trades for 2-3 key symbols.

---

## Next Steps

1. **Create ticker_24hr_stats table**
2. **Implement TickerStatsCollector class**
3. **Add docker-compose-ticker.yml**
4. **Update management scripts**
5. **Test with all active symbols**
6. **Monitor storage growth**
7. **Adjust configuration as needed**

---

## Integration with Data Collection

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
│  └────────┬─────────┘         └────────┬─────────┘        │
│           │                            │                   │
│           ▼                            ▼                   │
│  ┌──────────────────┐         ┌──────────────────┐        │
│  │  trades table    │         │ ticker_24hr_     │        │
│  │  (High storage)  │         │ stats table      │        │
│  │  ~100 GB (30d)   │         │  ~77 GB (6mo)    │        │
│  └──────────────────┘         └──────────────────┘        │
└────────────────────────────────────────────────────────────┘
```

Both services run independently, store in separate tables, can be enabled/disabled per symbol.

---

**Ready to implement!**
