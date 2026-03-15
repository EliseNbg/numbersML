# Step 3: Binance Data Ingest - WebSocket & REST

**Status:** ⏳ Pending  
**Effort:** 8-12 hours  
**Dependencies:** Step 1 (Foundation), Step 2 (Database Layer)

---

## 🎯 Objective

Implement Binance connectivity for real-time market data (1-second candles) and historical data fetch. **Critical: Finalize database schema based on actual Binance data structure.**

**Key Outcomes:**
- WebSocket connection to Binance (stable, auto-reconnect)
- 1-second candle streaming
- REST API client for historical data
- **Data exploration scripts → final DB schema**
- Redis pub/sub for candle distribution

---

## 📁 Deliverables

```
app/
└── adapters/
    └── exchanges/
        ├── __init__.py
        ├── binance_market_data.py    # WebSocket stream
        ├── binance_rest.py           # REST API client
        └── binance_schema.py         # Binance data structures

services/
└── data_ingest.py                    # Data ingestion coordinator

tests/
└── adapters/
    └── exchanges/
        ├── test_binance_websocket.py
        └── test_binance_rest.py

scripts/
├── fetch_binance_schema.py           # Explore Binance API
└── explore_binance_data.py           # Analyze structure

docs/
├── binance_api_schema.md             # Complete API schema
└── binance_data_analysis.md          # Data analysis findings
```

---

## 📝 Specifications

### 3.1 Binance WebSocket Market Data (`app/adapters/exchanges/binance_market_data.py`)

```python
# app/adapters/exchanges/binance_market_data.py
import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Optional

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from app.domain.models import Candle
from app.ports.exchanges import MarketDataStream
from app.logging_config import get_logger
from app.adapters.cache.redis_cache import RedisCacheAdapter

logger = get_logger(__name__)


class BinanceMarketData(MarketDataStream):
    """
    Binance WebSocket market data stream.
    
    Supports 1-second candle intervals for scalping.
    Auto-reconnects with exponential backoff.
    """
    
    def __init__(self, redis_cache: Optional[RedisCacheAdapter] = None):
        self.ws_url = "wss://stream.binance.com:9443/ws"
        self.rest_url = "https://api.binance.com"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.callbacks: Dict[str, Callable[[Candle], None]] = {}
        self.running = False
        self.redis_cache = redis_cache
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_delay = 60
    
    async def connect(self) -> None:
        """Connect to Binance WebSocket"""
        try:
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10
            )
            self.running = True
            logger.info("Connected to Binance WebSocket")
        except Exception as e:
            logger.error(f"Failed to connect to Binance WebSocket: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Binance WebSocket"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("Disconnected from Binance WebSocket")
    
    async def subscribe(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[Candle], None]
    ) -> None:
        """
        Subscribe to candle stream.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            timeframe: Candle interval (e.g., "1s", "1m")
            callback: Function to call with new candles
        """
        if not self.websocket:
            await self.connect()
        
        # Binance stream format: <symbol>@kline_<interval>
        stream = f"{symbol.lower()}@kline_{timeframe}"
        
        # Subscribe
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream],
            "id": 1
        }
        await self.websocket.send(json.dumps(subscribe_msg))
        
        # Store callback
        key = f"{symbol}:{timeframe}"
        self.callbacks[key] = callback
        logger.info(f"Subscribed to {stream}")
        
        # Start listening (if not already)
        if not hasattr(self, '_listen_task') or self._listen_task.done():
            self._listen_task = asyncio.create_task(self._listen())
    
    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from all streams for a symbol"""
        keys_to_remove = [k for k in self.callbacks if k.startswith(symbol)]
        for key in keys_to_remove:
            del self.callbacks[key]
        
        # Unsubscribe from Binance
        streams = [f"{symbol.lower()}@kline_{tf}" for tf in ["1s", "1m", "5m"]]
        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": 2
        }
        if self.websocket:
            await self.websocket.send(json.dumps(unsubscribe_msg))
    
    async def _listen(self) -> None:
        """Listen for WebSocket messages with auto-reconnect"""
        while self.running:
            try:
                async for message in self.websocket:
                    if not self.running:
                        break
                    
                    data = json.loads(message)
                    
                    # Handle candle updates
                    if 'k' in data:
                        candle = self._parse_candle(data['k'])
                        
                        # Call callback
                        key = f"{candle.symbol}:{candle.timeframe}"
                        if key in self.callbacks:
                            await self.callbacks[key](candle)
                        
                        # Publish to Redis
                        if self.redis_cache:
                            await self.redis_cache.publish(
                                f"candles:{candle.symbol}:{candle.timeframe}",
                                candle
                            )
                
            except ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                if self.running:
                    await self._reconnect()
            except Exception as e:
                logger.error(f"WebSocket error: {e}", exc_info=True)
                if self.running:
                    await self._reconnect()
    
    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff"""
        delay = min(self.reconnect_delay, self.max_reconnect_delay)
        logger.info(f"Reconnecting in {delay} seconds...")
        await asyncio.sleep(delay)
        
        try:
            await self.connect()
            
            # Resubscribe to all streams
            for key in self.callbacks.keys():
                symbol, timeframe = key.split(':')
                stream = f"{symbol.lower()}@kline_{timeframe}"
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": [stream],
                    "id": 1
                }
                if self.websocket:
                    await self.websocket.send(json.dumps(subscribe_msg))
            
            self.reconnect_delay = 5  # Reset delay
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            self.reconnect_delay *= 2  # Exponential backoff
    
    def _parse_candle(self, kline: dict) -> Candle:
        """Parse Binance kline to Candle object"""
        return Candle(
            symbol=kline['s'],
            timeframe=kline['i'],
            timestamp=datetime.fromtimestamp(kline['t'] / 1000),
            open=Decimal(kline['o']),
            high=Decimal(kline['h']),
            low=Decimal(kline['l']),
            close=Decimal(kline['c']),
            volume=Decimal(kline['v']),
            source="binance",
            trade_count=kline.get('n', 0),
            quote_volume=Decimal(kline.get('q', '0'))
        )
    
    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 1000
    ) -> List[Candle]:
        """
        Fetch historical candles via REST API.
        
        Args:
            symbol: Trading pair
            timeframe: Candle interval
            limit: Number of candles (max 1000)
        
        Returns:
            List of candles (oldest first)
        """
        url = f"{self.rest_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "limit": limit
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error = await response.text()
                    raise Exception(f"Binance API error: {error}")
                
                data = await response.json()
                
                candles = []
                for candle_data in data:
                    candle = Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=datetime.fromtimestamp(candle_data[0] / 1000),
                        open=Decimal(candle_data[1]),
                        high=Decimal(candle_data[2]),
                        low=Decimal(candle_data[3]),
                        close=Decimal(candle_data[4]),
                        volume=Decimal(candle_data[5]),
                        source="binance",
                        trade_count=candle_data[8],
                        quote_volume=Decimal(candle_data[7])
                    )
                    candles.append(candle)
                
                return candles
```

### 3.2 Data Exploration Scripts

**`scripts/fetch_binance_schema.py`:**
```python
#!/usr/bin/env python3
"""Fetch and document Binance API schema"""

import asyncio
import aiohttp

async def main():
    # Fetch kline data
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": "1s", "limit": 1}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            data = await response.json()
            print("Binance Kline Response:")
            print(f"Index 0: Open time ({data[0][0]})")
            print(f"Index 1: Open ({data[0][1]})")
            print(f"Index 2: High ({data[0][2]})")
            print(f"Index 3: Low ({data[0][3]})")
            print(f"Index 4: Close ({data[0][4]})")
            print(f"Index 5: Volume ({data[0][5]})")
            print(f"Index 6: Close time ({data[0][6]})")
            print(f"Index 7: Quote asset volume ({data[0][7]})")
            print(f"Index 8: Number of trades ({data[0][8]})")
            print(f"Index 9: Taker buy base asset volume ({data[0][9]})")
            print(f"Index 10: Taker buy quote asset volume ({data[0][10]})")
            print(f"Index 11: Ignore")

if __name__ == "__main__":
    asyncio.run(main())
```

**Output:** Use findings to update database schema with all Binance fields.

---

## ✅ Acceptance Criteria

- [ ] WebSocket connects successfully
- [ ] Auto-reconnect works (test by disconnecting network)
- [ ] 1-second candles stream correctly
- [ ] Candles parsed to domain objects with all fields
- [ ] Historical candles fetched via REST
- [ ] Redis pub/sub working
- [ ] PostgreSQL persistence working (batch inserts)
- [ ] Rate limiting respected
- [ ] Binance schema documented in `docs/binance_api_schema.md`
- [ ] Database schema updated with all Binance fields
- [ ] Performance: Handle 10+ symbols at 1-second intervals

---

## 🧪 Testing Requirements

### WebSocket Tests
```python
# tests/adapters/exchanges/test_binance_websocket.py
import pytest
from app.adapters.exchanges.binance_market_data import BinanceMarketData

@pytest.mark.asyncio
async def test_websocket_connect():
    """Test WebSocket connection"""
    binance = BinanceMarketData()
    await binance.connect()
    assert binance.websocket is not None
    await binance.disconnect()

@pytest.mark.asyncio
async def test_subscribe_1s_candle():
    """Test subscription to 1-second candles"""
    binance = BinanceMarketData()
    candles_received = []
    
    def callback(candle):
        candles_received.append(candle)
    
    await binance.subscribe("BTCUSDT", "1s", callback)
    
    # Wait for at least one candle
    await asyncio.sleep(2)
    
    assert len(candles_received) > 0
    assert candles_received[0].timeframe == "1s"
    
    await binance.disconnect()
```

---

## 📚 References

- Binance API Docs: https://binance-docs.github.io/apidocs/
- WebSocket Streams: https://binance-docs.github.io/apidocs/spot/en/#websocket-market-streams
- Kline/Candlestick Data: https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-streams

---

## 🎯 Next Step

After completing Step 3, proceed to **Step 4: Redis Cache Layer & Pub/Sub** (`Step4.md`).

---

**Ready to implement? Start coding!** 🐾
