# Order Book Data Collection Design

## Problem Statement

**Goal**: Collect and store top 10 bid/ask levels from Binance

**Challenges**:
- Order book updates **very frequently** (100s per second)
- Full order book = **20 data points per update** (10 bids × 2 + 10 asks × 2)
- Storage can explode quickly
- Need to balance detail vs. practicality

---

## Data Requirements Analysis

### Order Book Update Frequency

```
Binance WebSocket Streams:

@depth@100ms   → Updates every 100ms (10 times/sec)
@depth@1000ms  → Updates every 1000ms (1 time/sec)
@depth5@100ms  → Top 5 levels, 100ms updates
@depth10@100ms → Top 10 levels, 100ms updates
@depth20@100ms → Top 20 levels, 100ms updates
```

### Storage Calculation

**Assumptions**:
- 10 symbols
- Top 10 bid/ask levels
- Each level: price (8 bytes) + quantity (8 bytes) = 16 bytes
- 20 levels × 16 bytes = 320 bytes per snapshot

**Scenario A: Store Every Update (100ms)**
```
10 updates/sec × 320 bytes × 10 symbols = 32 KB/sec
32 KB × 86,400 sec × 10 symbols = 27.6 GB/day
27.6 GB × 180 days = 5 TB for 6 months ❌ TOO MUCH
```

**Scenario B: Store Every Second**
```
1 update/sec × 320 bytes × 10 symbols = 3.2 KB/sec
3.2 KB × 86,400 sec × 10 symbols = 2.76 GB/day
2.76 GB × 180 days = 500 GB for 6 months ✅ ACCEPTABLE
```

**Scenario C: Store Every 5 Seconds**
```
0.2 updates/sec × 320 bytes × 10 symbols = 640 bytes/sec
640 bytes × 86,400 sec × 10 symbols = 550 MB/day
550 MB × 180 days = 100 GB for 6 months ✅ VERY ACCEPTABLE
```

---

## Design Decision

### Recommendation: **Store Every 1 Second**

**Rationale**:
- Good balance of detail vs. storage
- Matches tick data resolution
- Sufficient for most strategies
- 500 GB for 6 months is manageable

**For HFT Strategies** (if needed later):
- Store 100ms snapshots for last 24 hours only
- Aggregate to 1-second for older data
- Or store only when order book changes significantly

---

## Implementation Design

### Option 1: Store as Arrays (RECOMMENDED)

**Schema**:

```sql
CREATE TABLE orderbook_snapshots (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    
    -- Bids (sorted desc: best bid first)
    bids_price NUMERIC(20,10)[],    -- Array of 10 prices
    bids_qty NUMERIC(20,10)[],      -- Array of 10 quantities
    
    -- Asks (sorted asc: best ask first)
    asks_price NUMERIC(20,10)[],    -- Array of 10 prices
    asks_qty NUMERIC(20,10)[],      -- Array of 10 quantities
    
    -- Derived fields (for easy querying)
    best_bid NUMERIC(20,10) NOT NULL,
    best_ask NUMERIC(20,10) NOT NULL,
    bid_qty_total NUMERIC(20,10) NOT NULL,
    ask_qty_total NUMERIC(20,10) NOT NULL,
    spread NUMERIC(20,10) NOT NULL,
    spread_pct NUMERIC(10,6) NOT NULL,
    mid_price NUMERIC(20,10) NOT NULL,
    
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (time, symbol_id)
);

-- Indexes
CREATE INDEX idx_orderbook_time_symbol ON orderbook_snapshots(time DESC, symbol_id);
CREATE INDEX idx_orderbook_symbol_time ON orderbook_snapshots(symbol_id, time DESC);
```

**Example Row**:

```sql
INSERT INTO orderbook_snapshots (
    time, symbol_id,
    bids_price, bids_qty,
    asks_price, asks_qty,
    best_bid, best_ask, spread, spread_pct, mid_price,
    bid_qty_total, ask_qty_total
) VALUES (
    '2024-03-18 12:00:01',
    1,  -- BTC/USDT
    -- Bids: [50000.00, 49999.50, 49999.00, ...]
    ARRAY[50000.00, 49999.50, 49999.00, 49998.50, 49998.00, 
          49997.50, 49997.00, 49996.50, 49996.00, 49995.50],
    ARRAY[1.5, 2.3, 0.8, 1.2, 3.1, 0.5, 2.0, 1.8, 0.9, 1.1],
    
    -- Asks: [50000.50, 50001.00, 50001.50, ...]
    ARRAY[50000.50, 50001.00, 50001.50, 50002.00, 50002.50,
          50003.00, 50003.50, 50004.00, 50004.50, 50005.00],
    ARRAY[2.1, 1.8, 0.9, 1.5, 2.5, 1.2, 0.7, 1.9, 1.3, 2.2],
    
    -- Derived fields
    50000.00,  -- best_bid
    50000.50,  -- best_ask
    0.50,      -- spread
    0.001,     -- spread_pct (0.1%)
    50000.25,  -- mid_price
    15.2,      -- bid_qty_total
    16.1       -- ask_qty_total
);
```

**Pros**:
- ✅ Compact storage (1 row per second)
- ✅ Fast retrieval (single row read)
- ✅ Easy to get latest snapshot
- ✅ PostgreSQL arrays are efficient

**Cons**:
- ❌ Can't query individual levels easily (but you rarely need to)
- ❌ Fixed to 10 levels (but you can change schema)

---

### Option 2: Normalized Table (NOT RECOMMENDED)

**Schema**:

```sql
CREATE TABLE orderbook_levels (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL,
    side TEXT NOT NULL,  -- 'BID' or 'ASK'
    level INTEGER NOT NULL,  -- 1-10 (1 = best)
    price NUMERIC(20,10) NOT NULL,
    quantity NUMERIC(20,10) NOT NULL,
    
    PRIMARY KEY (time, symbol_id, side, level)
);
```

**Storage**:
- 20 rows per snapshot (10 bids + 10 asks)
- 20× more rows than Option 1
- Much slower queries

**Verdict**: ❌ Don't use this for high-frequency order book data

---

### Option 3: Hybrid Approach (FOR ADVANCED USE)

Store:
- **Latest snapshot**: As arrays (fast access)
- **Changes (deltas)**: Only what changed (storage efficient)
- **Aggregated**: 1-minute OHLCV of order book metrics

**Schema**:

```sql
-- Latest snapshot (in-memory or Redis)
-- Stored in Redis for fast access

-- Deltas (for replay)
CREATE TABLE orderbook_deltas (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL,
    side TEXT NOT NULL,
    level INTEGER NOT NULL,
    price NUMERIC(20,10),  -- NULL if unchanged
    quantity NUMERIC(20,10),  -- NULL if removed
    operation TEXT NOT NULL  -- 'UPDATE', 'INSERT', 'DELETE'
);

-- 1-minute aggregated metrics
CREATE TABLE orderbook_metrics_1m (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL,
    
    -- Average spread
    avg_spread NUMERIC(20,10),
    avg_spread_pct NUMERIC(10,6),
    
    -- Min/Max spread
    min_spread NUMERIC(20,10),
    max_spread NUMERIC(20,10),
    
    -- Average depth
    avg_bid_depth NUMERIC(20,10),
    avg_ask_depth NUMERIC(20,10),
    
    -- Volatility indicators
    bid_price_stddev NUMERIC(20,10),
    ask_price_stddev NUMERIC(20,10),
    
    PRIMARY KEY (time, symbol_id)
);
```

**Verdict**: ✅ Use this if you need order book analytics

---

## Collection Implementation

### WebSocket Stream Selection

```python
# Binance WebSocket stream names
STREAM_DEPTH_10 = "btcusdt@depth10@1000ms"  # Top 10, 1 second updates
STREAM_DEPTH_10_100MS = "btcusdt@depth10@100ms"  # Top 10, 100ms updates

# Recommendation: Use 1000ms for storage
# You can always downsample, but can't upsample
```

### Collection Service

**File**: `src/infrastructure/exchanges/orderbook_collector.py`

```python
"""Order book data collection."""

import asyncio
import asyncpg
import websockets
import json
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class OrderBookCollector:
    """
    Collects order book snapshots from Binance.
    
    Strategy:
    - Subscribe to depth10@1000ms streams (1 second updates)
    - Store snapshot every 1 second
    - Calculate derived metrics (spread, mid_price, etc.)
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        symbols: List[str],
        storage_interval_sec: int = 1,
    ):
        self.db_pool = db_pool
        self.symbols = symbols
        self.storage_interval = storage_interval_sec
        
        self._symbol_ids: Dict[str, int] = {}
        self._current_book: Dict[int] = {}  # symbol_id -> order book
        self._running = False
    
    async def start(self):
        """Start order book collection."""
        logger.info("Starting order book collector...")
        
        # Initialize symbol mappings
        await self._init_symbols()
        
        self._running = True
        
        # Start WebSocket connection
        await self._connect_websocket()
    
    async def stop(self):
        """Stop order book collection."""
        logger.info("Stopping order book collector...")
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
                self._current_book[row['id']] = {
                    'bids': [],
                    'asks': [],
                }
        
        logger.info(f"Initialized {len(self._symbol_ids)} symbols for order book")
    
    async def _connect_websocket(self):
        """Connect to Binance order book WebSocket."""
        # Build stream names
        streams = [
            f"{s.lower().replace('/', '')}@depth10@1000ms"
            for s in self.symbols
        ]
        
        ws_url = f"wss://stream.binance.com:9443/ws/{'/'.join(streams)}"
        
        logger.info(f"Connecting to {ws_url}")
        
        while self._running:
            try:
                async with websockets.connect(ws_url) as ws:
                    logger.info("Order book WebSocket connected")
                    
                    while self._running:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        await self._process_orderbook_msg(msg)
                        
            except Exception as e:
                logger.error(f"Order book WebSocket error: {e}")
                await asyncio.sleep(5)  # Backoff
    
    async def _process_orderbook_msg(self, msg: str):
        """Process incoming order book message."""
        data = json.loads(msg)
        
        # Parse symbol
        symbol = data.get('s', '').upper()
        symbol = f"{symbol[:3]}/{symbol[3:]}"  # BTCUSDT → BTC/USDT
        
        if symbol not in self._symbol_ids:
            return
        
        symbol_id = self._symbol_ids[symbol]
        
        # Parse order book
        bids = data.get('bids', [])  # [[price, qty], ...]
        asks = data.get('asks', [])  # [[price, qty], ...]
        
        # Ensure we have exactly 10 levels (pad if needed)
        bids = self._pad_levels(bids, 10)
        asks = self._pad_levels(asks, 10)
        
        # Update current book
        self._current_book[symbol_id] = {
            'bids': bids,
            'asks': asks,
            'time': datetime.utcnow(),
        }
    
    def _pad_levels(self, levels: List, target: int) -> List:
        """Pad levels to target count."""
        while len(levels) < target:
            levels.append(['0', '0'])  # Pad with zeros
        return levels[:target]  # Truncate if too many
    
    async def _store_snapshots(self):
        """Periodically store order book snapshots."""
        while self._running:
            await asyncio.sleep(self.storage_interval)
            
            try:
                async with self.db_pool.acquire() as conn:
                    async with conn.transaction():
                        for symbol_id, book in self._current_book.items():
                            if not book.get('bids'):
                                continue
                            
                            await self._store_snapshot(conn, symbol_id, book)
            
            except Exception as e:
                logger.error(f"Error storing order book snapshots: {e}")
    
    async def _store_snapshot(
        self, 
        conn: asyncpg.Connection, 
        symbol_id: int, 
        book: Dict
    ):
        """Store single order book snapshot."""
        bids = book['bids']
        asks = book['asks']
        time = book.get('time', datetime.utcnow())
        
        # Extract arrays
        bids_price = [Decimal(b[0]) for b in bids]
        bids_qty = [Decimal(b[1]) for b in bids]
        asks_price = [Decimal(a[0]) for a in asks]
        asks_qty = [Decimal(a[1]) for a in asks]
        
        # Calculate derived metrics
        best_bid = bids_price[0] if bids_price[0] > 0 else None
        best_ask = asks_price[0] if asks_price[0] > 0 else None
        
        if best_bid and best_ask:
            spread = best_ask - best_bid
            spread_pct = (spread / best_bid) * 100
            mid_price = (best_bid + best_ask) / 2
        else:
            spread = spread_pct = mid_price = None
        
        bid_qty_total = sum(bids_qty)
        ask_qty_total = sum(asks_qty)
        
        # Store
        await conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                time, symbol_id,
                bids_price, bids_qty,
                asks_price, asks_qty,
                best_bid, best_ask,
                spread, spread_pct, mid_price,
                bid_qty_total, ask_qty_total
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            )
            ON CONFLICT (time, symbol_id) DO UPDATE SET
                bids_price = EXCLUDED.bids_price,
                bids_qty = EXCLUDED.bids_qty,
                asks_price = EXCLUDED.asks_price,
                asks_qty = EXCLUDED.asks_qty,
                best_bid = EXCLUDED.best_bid,
                best_ask = EXCLUDED.best_ask,
                spread = EXCLUDED.spread,
                spread_pct = EXCLUDED.spread_pct,
                mid_price = EXCLUDED.mid_price,
                bid_qty_total = EXCLUDED.bid_qty_total,
                ask_qty_total = EXCLUDED.ask_qty_total
            """,
            time, symbol_id,
            bids_price, bids_qty,
            asks_price, asks_qty,
            best_bid, best_ask,
            spread, spread_pct, mid_price,
            bid_qty_total, ask_qty_total
        )
```

---

## Storage Optimization

### Compression for Old Data

```sql
-- After 30 days, compress to 5-second snapshots
CREATE OR REPLACE FUNCTION compress_orderbook_old_data()
RETURNS VOID AS $$
BEGIN
    -- Delete high-frequency data older than 30 days
    -- Keep only 5-second snapshots
    
    -- Step 1: Create compressed snapshots (5-second intervals)
    INSERT INTO orderbook_snapshots_compressed (
        time, symbol_id,
        bids_price, bids_qty,
        asks_price, asks_qty,
        best_bid, best_ask, spread, spread_pct, mid_price,
        bid_qty_total, ask_qty_total
    )
    SELECT 
        date_trunc('second', time) + 
            (EXTRACT(EPOCH FROM time)::int % 5) * INTERVAL '1 second' AS time,
        symbol_id,
        -- Average of arrays (simplified, just take first snapshot)
        (ARRAY_AGG(bids_price ORDER BY time))[1],
        (ARRAY_AGG(bids_qty ORDER BY time))[1],
        (ARRAY_AGG(asks_price ORDER BY time))[1],
        (ARRAY_AGG(asks_qty ORDER BY time))[1],
        AVG(best_bid),
        AVG(best_ask),
        AVG(spread),
        AVG(spread_pct),
        AVG(mid_price),
        AVG(bid_qty_total),
        AVG(ask_qty_total)
    FROM orderbook_snapshots
    WHERE time < NOW() - INTERVAL '30 days'
      AND time >= NOW() - INTERVAL '60 days'
    GROUP BY date_trunc('second', time) + 
             (EXTRACT(EPOCH FROM time)::int % 5) * INTERVAL '1 second',
             symbol_id
    ON CONFLICT (time, symbol_id) DO NOTHING;
    
    -- Step 2: Delete uncompressed data older than 30 days
    DELETE FROM orderbook_snapshots
    WHERE time < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;
```

### Partitioning

```sql
-- Partition by month for better performance
CREATE TABLE orderbook_snapshots (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL,
    -- ... other columns ...
    PRIMARY KEY (time, symbol_id)
) PARTITION BY RANGE (time);

-- Create monthly partitions
CREATE TABLE orderbook_snapshots_2024_01 
    PARTITION OF orderbook_snapshots
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE orderbook_snapshots_2024_02 
    PARTITION OF orderbook_snapshots
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- Drop old partitions easily
DROP TABLE orderbook_snapshots_2023_01;  -- Instant, no vacuum needed
```

---

## Query Examples

### Get Latest Order Book

```sql
SELECT DISTINCT ON (symbol_id)
    o.time,
    s.symbol,
    o.bids_price[1] AS best_bid,
    o.asks_price[1] AS best_ask,
    o.spread,
    o.spread_pct,
    o.mid_price,
    o.bid_qty_total,
    o.ask_qty_total
FROM orderbook_snapshots o
JOIN symbols s ON s.id = o.symbol_id
WHERE s.is_active = true
ORDER BY symbol_id, time DESC;
```

### Get Order Book History

```sql
SELECT 
    time,
    bids_price[1] AS best_bid,
    asks_price[1] AS best_ask,
    spread,
    spread_pct
FROM orderbook_snapshots
WHERE symbol_id = 1  -- BTC/USDT
  AND time BETWEEN '2024-03-18 12:00:00' AND '2024-03-18 12:05:00'
ORDER BY time;
```

### Calculate Order Book Imbalance

```sql
SELECT 
    time,
    symbol_id,
    bid_qty_total / (bid_qty_total + ask_qty_total) AS bid_imbalance
FROM orderbook_snapshots
WHERE symbol_id = 1
  AND time > NOW() - INTERVAL '1 hour'
ORDER BY time DESC;
```

---

## Summary & Recommendation

### Recommended Approach

```yaml
Storage Strategy:
  frequency: 1 second
  levels: 10 bid + 10 ask
  format: PostgreSQL arrays
  table: orderbook_snapshots

Schema:
  - bids_price NUMERIC[]
  - bids_qty NUMERIC[]
  - asks_price NUMERIC[]
  - asks_qty NUMERIC[]
  - Derived fields: best_bid, best_ask, spread, mid_price

Optimization:
  - Partition by month
  - Compress to 5-second after 30 days
  - Delete after 180 days (or archive)

Storage Estimate:
  - 10 symbols
  - 1 second frequency
  - 6 months retention
  - Total: ~500 GB
```

### Implementation Steps

1. **Create schema** (orderbook_snapshots table)
2. **Implement OrderBookCollector** service
3. **Add to docker-compose** (separate or with collector)
4. **Test with 1-2 symbols**
5. **Monitor storage growth**
6. **Adjust frequency if needed**

---

## Alternative: Don't Store Order Book (Yet)

**Consider**: Do you really need order book data for Phase 1?

**Phase 1 Goal**: Data gathering for backtesting

**Question**: Will you use order book data in backtesting?
- If **NO**: Don't collect it yet (save storage, complexity)
- If **YES** (market making, order book strategies): Collect it
- If **MAYBE**: Collect for 1-2 symbols only, evaluate later

**Recommendation for Phase 1**:
- Start with **tick data (trades)** only
- Add order book for **1-2 symbols** as experiment
- Evaluate storage vs. value after 1 month
- Scale up or down based on actual usage

---

## Questions?

1. **Do you need order book for your strategies?**
   - Market making → YES
   - Trend following → Maybe not
   - Swing trading → NO

2. **What resolution do you need?**
   - 100ms → HFT (consider specialized infrastructure)
   - 1 second → Most strategies
   - 5+ seconds → Long-term strategies

3. **How much history?**
   - 24 hours → Testing, debugging
   - 30 days → Strategy development
   - 6 months → Serious backtesting

**My recommendation**: Start simple, measure actual usage, then scale.
