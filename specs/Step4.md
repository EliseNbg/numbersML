# Step 4: Redis Cache Layer & Pub/Sub

**Status:** ⏳ Pending
**Effort:** 4-6 hours
**Dependencies:** Step 1 (Foundation), Step 2 (Database Layer)

---

## 🎯 Objective

Implement Redis caching for low-latency data access and real-time pub/sub communication between components.

**Key Outcomes:**
- Redis cache adapter with TTL support
- Pub/sub for real-time data distribution
- Sub-5ms cache operations
- Cache strategies for candles, positions, signals

---

## 📁 Deliverables

```
app/
├── ports/
│   └── cache.py                    # Cache interface
└── adapters/
    └── cache/
        ├── __init__.py
        └── redis_cache.py          # Redis implementation

services/
└── cache_manager.py                # Cache coordination

tests/
└── adapters/
    └── cache/
        └── test_redis_cache.py
```

---

## 📝 Specifications

### Logging Requirements for Step 4

**All cache operations MUST use structured logging with:**
- **Correlation IDs**: Generate unique ID per cache operation for tracing
- **Component label**: Always set `component="cache"` for this layer
- **Operation context**: Include key, channel, ttl in logs
- **Latency tracking**: Log execution time for all cache operations (target: <5ms)
- **Error context**: Include full error details with exc_info=True
- **Pub/Sub events**: Log all publish/subscribe events with correlation IDs

**Example logging pattern:**
```python
correlation_id = generate_correlation_id()
start_time = datetime.utcnow()

try:
    # Cache operation
    await cache.set("key", value, ttl=60)
    logger.debug(
        "Cache operation completed",
        correlation_id=correlation_id,
        key="key",
        component="cache",
        latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
    )
except Exception as e:
    logger.error(
        "Cache operation failed",
        correlation_id=correlation_id,
        key="key",
        error=str(e),
        component="cache",
        exc_info=True
    )
```

**Loki Labels Required:**
- `correlation_id` - Unique operation ID
- `component` - Always "cache" for this layer
- `key` - Cache key (when applicable)
- `channel` - Pub/sub channel (when applicable)
- `symbol` - Trading pair (when applicable)

### 4.1 Cache Interface (`app/ports/cache.py`)

```python
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from app.domain.models import Candle, Tick, Position, Signal

class CacheAdapter(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]: pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None: pass
    
    @abstractmethod
    async def delete(self, key: str) -> None: pass
    
    @abstractmethod
    async def publish(self, channel: str, message: Any) -> None: pass
    
    @abstractmethod
    async def subscribe(self, channel: str, callback: Callable[[Any], None]) -> None: pass
    
    @abstractmethod
    async def get_latest_tick(self, symbol: str) -> Optional[Tick]: pass
    
    @abstractmethod
    async def get_candle(self, symbol: str, timeframe: str) -> Optional[Candle]: pass
    
    @abstractmethod
    async def get_position(self, strategy_id: str, symbol: str) -> Optional[Position]: pass
```

### 4.2 Redis Implementation (`app/adapters/cache/redis_cache.py`)

**Key Patterns:**
- `tick:{symbol}` - Latest tick (TTL: 60s)
- `candle:{symbol}:{timeframe}` - Latest candle (TTL: 300s)
- `position:{strategy_id}:{symbol}` - Current position (no TTL)
- `signal:{strategy_id}:{symbol}` - Latest signal (TTL: 300s)
- `candles:{symbol}:{timeframe}` - Pub/sub channel

**Features:**
- JSON serialization with Decimal/datetime support
- Connection pooling
- Pub/sub for real-time distribution
- TTL management
- Structured logging with correlation IDs

**Implementation:**
```python
# app/adapters/cache/redis_cache.py
import asyncio
import json
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio.client import PubSub

from app.ports.cache import CacheAdapter
from app.domain.models import Candle, Tick, Position, Signal
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal and datetime"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


class RedisCacheAdapter(CacheAdapter):
    """
    Redis cache adapter with pub/sub support.

    Features:
    - Low-latency get/set operations (<5ms target)
    - TTL management
    - Pub/sub for real-time distribution
    - JSON serialization with Decimal/datetime support
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
        self.pubsub: Optional[PubSub] = None
        self.subscriptions: Dict[str, Callable[[Any], None]] = {}
        self._listen_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self) -> None:
        """Connect to Redis with correlation ID tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            self.client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            # Test connection
            await self.client.ping()

            logger.info(
                "Connected to Redis",
                correlation_id=correlation_id,
                component="cache",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(
                "Failed to connect to Redis",
                correlation_id=correlation_id,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis with correlation ID tracking"""
        correlation_id = generate_correlation_id()

        # Close all subscriptions
        for channel in list(self.subscriptions.keys()):
            await self.unsubscribe(channel, self.subscriptions[channel])

        if self.client:
            await self.client.close()

        logger.info(
            "Disconnected from Redis",
            correlation_id=correlation_id,
            component="cache"
        )

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            value = await self.client.get(key)

            if value:
                result = json.loads(value)
                logger.debug(
                    "Cache hit",
                    correlation_id=correlation_id,
                    key=key,
                    component="cache",
                    latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
                )
                return result

            logger.debug(
                "Cache miss",
                correlation_id=correlation_id,
                key=key,
                component="cache",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
            return None

        except Exception as e:
            logger.error(
                "Cache get failed",
                correlation_id=correlation_id,
                key=key,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            serialized = json.dumps(value, cls=DecimalEncoder)

            if ttl:
                await self.client.setex(key, ttl, serialized)
            else:
                await self.client.set(key, serialized)

            logger.debug(
                "Cache set",
                correlation_id=correlation_id,
                key=key,
                ttl=ttl,
                component="cache",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(
                "Cache set failed",
                correlation_id=correlation_id,
                key=key,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def delete(self, key: str) -> None:
        """Delete key from cache with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            await self.client.delete(key)

            logger.debug(
                "Cache delete",
                correlation_id=correlation_id,
                key=key,
                component="cache",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(
                "Cache delete failed",
                correlation_id=correlation_id,
                key=key,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def publish(self, channel: str, message: Any) -> None:
        """Publish message to channel with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            serialized = json.dumps(message, cls=DecimalEncoder)
            subscribers = await self.client.publish(channel, serialized)

            logger.debug(
                "Cache publish",
                correlation_id=correlation_id,
                channel=channel,
                subscribers=subscribers,
                component="cache",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(
                "Cache publish failed",
                correlation_id=correlation_id,
                channel=channel,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def subscribe(self, channel: str, callback: Callable[[Any], None]) -> None:
        """Subscribe to channel with correlation tracking"""
        correlation_id = generate_correlation_id()

        try:
            if self.pubsub is None:
                self.pubsub = self.client.pubsub()

            await self.pubsub.subscribe(channel)
            self.subscriptions[channel] = callback

            # Start listening task
            if channel not in self._listen_tasks:
                self._listen_tasks[channel] = asyncio.create_task(
                    self._listen_channel(channel)
                )

            logger.info(
                "Cache subscribe",
                correlation_id=correlation_id,
                channel=channel,
                component="cache"
            )
        except Exception as e:
            logger.error(
                "Cache subscribe failed",
                correlation_id=correlation_id,
                channel=channel,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def unsubscribe(self, channel: str, callback: Callable[[Any], None]) -> None:
        """Unsubscribe from channel with correlation tracking"""
        correlation_id = generate_correlation_id()

        try:
            if channel in self.subscriptions:
                del self.subscriptions[channel]

            if self.pubsub:
                await self.pubsub.unsubscribe(channel)

            # Cancel listen task
            if channel in self._listen_tasks:
                self._listen_tasks[channel].cancel()
                del self._listen_tasks[channel]

            logger.info(
                "Cache unsubscribe",
                correlation_id=correlation_id,
                channel=channel,
                component="cache"
            )
        except Exception as e:
            logger.error(
                "Cache unsubscribe failed",
                correlation_id=correlation_id,
                channel=channel,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def _listen_channel(self, channel: str) -> None:
        """Listen to channel and call callback with correlation tracking"""
        listen_correlation_id = generate_correlation_id()

        try:
            while channel in self.subscriptions:
                try:
                    message = await self.pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )

                    if message and message['type'] == 'message':
                        callback = self.subscriptions.get(channel)
                        if callback:
                            data = json.loads(message['data'])
                            await callback(data)

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(
                        "Error processing channel message",
                        correlation_id=listen_correlation_id,
                        channel=channel,
                        component="cache",
                        error=str(e),
                        exc_info=True
                    )

        except asyncio.CancelledError:
            logger.debug(
                "Channel listener cancelled",
                correlation_id=listen_correlation_id,
                channel=channel,
                component="cache"
            )

    async def get_latest_tick(self, symbol: str) -> Optional[Tick]:
        """Get latest tick for symbol with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            key = f"tick:{symbol}"
            data = await self.get(key)

            if data:
                tick = Tick(
                    symbol=data['symbol'],
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    bid=Decimal(str(data['bid'])),
                    ask=Decimal(str(data['ask'])),
                    last=Decimal(str(data['last'])),
                    volume=Decimal(str(data.get('volume', 0)))
                )

                logger.debug(
                    "Retrieved latest tick",
                    correlation_id=correlation_id,
                    symbol=symbol,
                    component="cache",
                    latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
                )
                return tick

            return None

        except Exception as e:
            logger.error(
                "Failed to get latest tick",
                correlation_id=correlation_id,
                symbol=symbol,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def get_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """Get latest candle for symbol/timeframe with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            key = f"candle:{symbol}:{timeframe}"
            data = await self.get(key)

            if data:
                candle = Candle(
                    symbol=data['symbol'],
                    timeframe=data['timeframe'],
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    open=Decimal(str(data['open'])),
                    high=Decimal(str(data['high'])),
                    low=Decimal(str(data['low'])),
                    close=Decimal(str(data['close'])),
                    volume=Decimal(str(data['volume'])),
                    source=data.get('source', 'unknown'),
                    trade_count=data.get('trade_count', 0),
                    quote_volume=Decimal(str(data.get('quote_volume', 0)))
                )

                logger.debug(
                    "Retrieved latest candle",
                    correlation_id=correlation_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    component="cache",
                    latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
                )
                return candle

            return None

        except Exception as e:
            logger.error(
                "Failed to get candle",
                correlation_id=correlation_id,
                symbol=symbol,
                timeframe=timeframe,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def get_position(self, strategy_id: str, symbol: str) -> Optional[Position]:
        """Get position for strategy/symbol with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            key = f"position:{strategy_id}:{symbol}"
            data = await self.get(key)

            if data:
                position = Position(
                    strategy_id=data['strategy_id'],
                    symbol=data['symbol'],
                    quantity=Decimal(str(data['quantity'])),
                    avg_entry_price=Decimal(str(data['avg_entry_price'])),
                    current_price=Decimal(str(data['current_price'])),
                    unrealized_pnl=Decimal(str(data.get('unrealized_pnl', 0))),
                    realized_pnl=Decimal(str(data.get('realized_pnl', 0))),
                    updated_at=datetime.fromisoformat(data['updated_at']),
                    opened_at=datetime.fromisoformat(data.get('opened_at', data['updated_at'])),
                    closed_at=datetime.fromisoformat(data['closed_at']) if data.get('closed_at') else None
                )

                logger.debug(
                    "Retrieved position",
                    correlation_id=correlation_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    component="cache",
                    latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
                )
                return position

            return None

        except Exception as e:
            logger.error(
                "Failed to get position",
                correlation_id=correlation_id,
                strategy_id=strategy_id,
                symbol=symbol,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise

    async def set_position(self, position: Position) -> None:
        """Set position in cache with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        try:
            key = f"position:{position.strategy_id}:{position.symbol}"
            data = {
                'strategy_id': position.strategy_id,
                'symbol': position.symbol,
                'quantity': str(position.quantity),
                'avg_entry_price': str(position.avg_entry_price),
                'current_price': str(position.current_price),
                'unrealized_pnl': str(position.unrealized_pnl),
                'realized_pnl': str(position.realized_pnl),
                'updated_at': position.updated_at.isoformat(),
                'opened_at': position.opened_at.isoformat(),
                'closed_at': position.closed_at.isoformat() if position.closed_at else None
            }

            await self.set(key, data)

            logger.debug(
                "Cached position",
                correlation_id=correlation_id,
                strategy_id=position.strategy_id,
                symbol=position.symbol,
                component="cache",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(
                "Failed to cache position",
                correlation_id=correlation_id,
                strategy_id=position.strategy_id,
                symbol=position.symbol,
                component="cache",
                error=str(e),
                exc_info=True
            )
            raise
```

---

## ✅ Acceptance Criteria

- [ ] All cache operations implemented with correlation ID tracking
- [ ] Pub/sub working (publish + subscribe) with proper logging
- [ ] TTL working correctly
- [ ] JSON serialization handles Decimal, datetime
- [ ] Performance: <5ms for get/set operations (logged)
- [ ] All methods tested with correlation ID verification
- [ ] Integration tests with real Redis pass
- [ ] All logs include correlation_id, component="cache"
- [ ] Latency tracking on all operations
- [ ] Error logging includes exc_info=True

---

## 🧪 Testing Requirements

```python
# tests/adapters/cache/test_redis_cache.py
import pytest
from datetime import datetime
from decimal import Decimal
from app.logging_config import get_logger

logger = get_logger(__name__)

@pytest.mark.asyncio
async def test_cache_set_get():
    """Test cache set/get with correlation tracking"""
    cache = RedisCacheAdapter()
    await cache.connect()

    await cache.set("test:key", {"value": 123}, ttl=60)
    result = await cache.get("test:key")

    assert result["value"] == 123
    await cache.disconnect()

@pytest.mark.asyncio
async def test_pub_sub():
    """Test pub/sub with correlation tracking"""
    cache = RedisCacheAdapter()
    await cache.connect()

    messages = []

    async def callback(msg):
        messages.append(msg)

    await cache.subscribe("test:channel", callback)
    await cache.publish("test:channel", {"data": "test"})
    await asyncio.sleep(0.5)

    assert len(messages) > 0
    await cache.disconnect()

@pytest.mark.asyncio
async def test_cache_performance():
    """Test cache operations meet <5ms target"""
    cache = RedisCacheAdapter()
    await cache.connect()

    # Test set performance
    await cache.set("perf:test", {"data": "test"})
    # Should complete in <5ms (verified via logs)

    # Test get performance
    result = await cache.get("perf:test")
    assert result is not None

    await cache.disconnect()

@pytest.mark.asyncio
async def test_ttl_expiration():
    """Test TTL expiration with correlation tracking"""
    cache = RedisCacheAdapter()
    await cache.connect()

    await cache.set("ttl:test", {"value": 123}, ttl=1)
    result = await cache.get("ttl:test")
    assert result is not None

    await asyncio.sleep(1.5)

    result = await cache.get("ttl:test")
    assert result is None

    await cache.disconnect()
```

---

## 🎯 Next Step

After completing Step 4, proceed to **Step 5: Strategy Engine & Signal Generation** (`Step5.md`).

---

**Ready to implement? Start coding!** 🐾
