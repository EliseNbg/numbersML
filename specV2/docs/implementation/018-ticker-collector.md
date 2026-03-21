# Step 018: Ticker Collector - Implementation Guide

**Phase**: 3 - Data Quality  
**Effort**: 6 hours  
**Dependencies**: Step 004 (Data Collection), Step 017 (Data Quality) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements the 24hr ticker statistics collector with:
- Real-time ticker stream from Binance
- Low-storage statistics collection
- Integration with anomaly detection
- Quality metrics tracking
- Comprehensive tests (85%+ coverage)

---

## Implementation Tasks

### Task 1: Ticker Collector Service

**File**: `src/infrastructure/exchanges/ticker_collector.py`

```python
"""
24hr ticker statistics collector.

Collects ticker statistics from Binance WebSocket streams.
Low-storage alternative to individual trade collection.
"""

import asyncio
import asyncpg
import websockets
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from src.domain.services.anomaly_detector import AnomalyDetector, AnomalyResult
from src.domain.services.gap_detector import GapDetector, DataGap
from src.domain.services.quality_metrics import QualityMetricsTracker

logger = logging.getLogger(__name__)


class TickerCollector:
    """
    Collects 24hr ticker statistics from Binance.
    
    Stream: <symbol>@ticker
    Frequency: Every 1 second
    Storage: ~43 MB/day/symbol (very efficient)
    
    Attributes:
        db_pool: PostgreSQL connection pool
        symbols: List of symbols to collect
        anomaly_detectors: Per-symbol anomaly detectors
        gap_detectors: Per-symbol gap detectors
        metrics_tracker: Quality metrics tracker
    
    Example:
        >>> collector = TickerCollector(db_pool, ['BTC/USDT', 'ETH/USDT'])
        >>> await collector.start()
    """
    
    BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        symbols: List[str],
        anomaly_threshold: Decimal = Decimal("5.0"),
        max_gap_seconds: int = 5,
    ) -> None:
        """
        Initialize ticker collector.
        
        Args:
            db_pool: PostgreSQL connection pool
            symbols: List of symbols to collect
            anomaly_threshold: Price move % for anomaly detection
            max_gap_seconds: Maximum allowed time gap
        """
        self.db_pool: asyncpg.Pool = db_pool
        self.symbols: List[str] = symbols
        self.anomaly_threshold: Decimal = anomaly_threshold
        self.max_gap_seconds: int = max_gap_seconds
        
        # Services (initialized per symbol)
        self._anomaly_detectors: Dict[int, AnomalyDetector] = {}
        self._gap_detectors: Dict[int, GapDetector] = {}
        self._metrics_tracker: Optional[QualityMetricsTracker] = None
        
        # State
        self._symbol_ids: Dict[str, int] = {}
        self._running: bool = False
        self._stats: Dict[str, int] = {'processed': 0, 'anomalies': 0, 'gaps': 0}
    
    async def start(self) -> None:
        """Start ticker collection."""
        logger.info(f"Starting Ticker Collector for {len(self.symbols)} symbols")
        
        await self._init_symbols()
        self._running = True
        
        await self._connect_websocket()
    
    async def stop(self) -> None:
        """Stop ticker collection."""
        logger.info("Stopping Ticker Collector...")
        self._running = False
    
    async def _init_symbols(self) -> None:
        """Initialize symbol mappings and services."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, symbol, tick_size, step_size, min_notional
                FROM symbols
                WHERE symbol = ANY($1) AND is_active = true AND is_allowed = true
                """,
                self.symbols
            )
            
            for row in rows:
                symbol = row['symbol']
                symbol_id = row['id']
                
                self._symbol_ids[symbol] = symbol_id
                
                # Initialize services per symbol
                from src.domain.models.symbol import Symbol
                
                symbol_entity = Symbol(
                    id=symbol_id,
                    symbol=symbol,
                    tick_size=row['tick_size'],
                    step_size=row['step_size'],
                    min_notional=row['min_notional'],
                )
                
                self._anomaly_detectors[symbol_id] = AnomalyDetector(
                    symbol=symbol_entity,
                    price_spike_threshold=self.anomaly_threshold,
                )
                
                self._gap_detectors[symbol_id] = GapDetector(
                    max_gap_seconds=self.max_gap_seconds,
                )
                
                self._gap_detectors[symbol_id].start_monitoring(
                    symbol_id, symbol
                )
        
        # Initialize metrics tracker
        self._metrics_tracker = QualityMetricsTracker(self.db_pool)
        
        logger.info(f"Initialized {len(self._symbol_ids)} symbols with quality services")
    
    async def _connect_websocket(self) -> None:
        """Connect to Binance WebSocket with auto-reconnect."""
        while self._running:
            try:
                # Build stream URLs
                streams = [
                    f"{s.lower().replace('/', '')}@ticker"
                    for s in self._symbol_ids.keys()
                ]
                ws_url = f"{self.BINANCE_WS_URL}/{'/'.join(streams)}"
                
                logger.info(f"Connecting to ticker WebSocket: {ws_url}")
                
                async with websockets.connect(ws_url) as ws:
                    logger.info("Ticker WebSocket connected")
                    
                    while self._running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=60)
                            await self._process_ticker_msg(msg)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=10)
                
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                
                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
    
    async def _process_ticker_msg(self, msg: str) -> None:
        """
        Process incoming ticker message.
        
        Args:
            msg: WebSocket message (JSON string)
        """
        try:
            data = json.loads(msg)
            
            # Validate message type
            if data.get('e') != '24hrTicker':
                return
            
            # Parse symbol
            raw_symbol = data.get('s', '')
            symbol = self._parse_symbol(raw_symbol)
            
            if symbol not in self._symbol_ids:
                return
            
            symbol_id = self._symbol_ids[symbol]
            
            # Parse ticker data
            ticker_data = {
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
            }
            
            # Check for gaps
            gap = self._gap_detectors[symbol_id].check_tick(
                symbol_id, ticker_data['time']
            )
            
            if gap:
                self._stats['gaps'] += 1
                self._metrics_tracker.record_gap(symbol_id, is_filled=False)
                logger.warning(f"Gap detected for {symbol}: {gap.gap_seconds}s")
            
            # Create mock trade for anomaly detection
            from src.domain.models.trade import Trade
            
            mock_trade = Trade(
                time=ticker_data['time'],
                symbol_id=symbol_id,
                trade_id=str(ticker_data['last_trade_id']),
                price=ticker_data['last_price'],
                quantity=ticker_data['last_quantity'],
                side='BUY',
            )
            
            # Detect anomalies
            anomaly_result = self._anomaly_detectors[symbol_id].detect(mock_trade)
            
            if anomaly_result.is_anomaly:
                self._stats['anomalies'] += 1
                self._metrics_tracker.record_anomaly(symbol_id)
                
                if anomaly_result.should_reject:
                    logger.error(
                        f"Rejecting ticker for {symbol}: "
                        f"{anomaly_result.anomalies[0].message}"
                    )
                    return
                elif anomaly_result.should_flag:
                    logger.warning(
                        f"Flagging ticker for {symbol}: "
                        f"{anomaly_result.anomalies[0].message}"
                    )
            
            # Store ticker
            await self._store_ticker(ticker_data)
            
            # Record metrics
            self._stats['processed'] += 1
            self._metrics_tracker.record_tick(
                symbol_id, is_valid=True, latency_ms=0.0
            )
        
        except Exception as e:
            logger.error(f"Error processing ticker message: {e}")
    
    def _parse_symbol(self, raw_symbol: str) -> str:
        """Parse symbol from Binance format."""
        if raw_symbol.endswith('USDT'):
            return f"{raw_symbol[:-4]}/USDT"
        elif raw_symbol.endswith('BTC'):
            return f"{raw_symbol[:-3]}/BTC"
        elif raw_symbol.endswith('ETH'):
            return f"{raw_symbol[:-3]}/ETH"
        return raw_symbol
    
    async def _store_ticker(self, ticker_data: Dict) -> None:
        """Store ticker data in database."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ticker_24hr_stats (
                    time, symbol_id, symbol, pair,
                    price_change, price_change_pct,
                    last_price, open_price, high_price, low_price,
                    weighted_avg_price, last_quantity,
                    total_volume, total_quote_volume,
                    first_trade_id, last_trade_id, total_trades
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17
                )
                ON CONFLICT (time, symbol_id) DO UPDATE SET
                    last_price = EXCLUDED.last_price,
                    total_volume = EXCLUDED.total_volume,
                    total_quote_volume = EXCLUDED.total_quote_volume,
                    total_trades = EXCLUDED.total_trades,
                    last_trade_id = EXCLUDED.last_trade_id
                """,
                ticker_data['time'],
                ticker_data['symbol_id'],
                ticker_data['symbol'],
                ticker_data['pair'],
                ticker_data['price_change'],
                ticker_data['price_change_pct'],
                ticker_data['last_price'],
                ticker_data['open_price'],
                ticker_data['high_price'],
                ticker_data['low_price'],
                ticker_data['weighted_avg_price'],
                ticker_data['last_quantity'],
                ticker_data['total_volume'],
                ticker_data['total_quote_volume'],
                ticker_data['first_trade_id'],
                ticker_data['last_trade_id'],
                ticker_data['total_trades'],
            )
    
    def get_stats(self) -> Dict[str, int]:
        """Get collection statistics."""
        return self._stats.copy()

```

### Task 2: Database Schema for Ticker Stats

**File**: `migrations/002_ticker_stats.sql`

```sql
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
```

---

## Acceptance Criteria

- [ ] TickerCollector service implemented
- [ ] Anomaly detection integrated
- [ ] Gap detection integrated
- [ ] Quality metrics tracking integrated
- [ ] Database migration created
- [ ] Unit tests (80%+ coverage)
- [ ] Integration test with quality services

---

## Next Steps

After completing this step, proceed to **Integration Test & Pipeline Integration**
