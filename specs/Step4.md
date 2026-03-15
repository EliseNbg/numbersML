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

---

## ✅ Acceptance Criteria

- [ ] All cache operations implemented
- [ ] Pub/sub working (publish + subscribe)
- [ ] TTL working correctly
- [ ] JSON serialization handles Decimal, datetime
- [ ] Performance: <5ms for get/set operations
- [ ] All methods tested
- [ ] Integration tests with real Redis pass

---

## 🧪 Testing Requirements

```python
# tests/adapters/cache/test_redis_cache.py
@pytest.mark.asyncio
async def test_cache_set_get():
    cache = RedisCacheAdapter()
    await cache.set("test:key", {"value": 123}, ttl=60)
    result = await cache.get("test:key")
    assert result["value"] == 123

@pytest.mark.asyncio
async def test_pub_sub():
    cache = RedisCacheAdapter()
    messages = []
    
    async def callback(msg):
        messages.append(msg)
    
    await cache.subscribe("test:channel", callback)
    await cache.publish("test:channel", {"data": "test"})
    await asyncio.sleep(0.5)
    
    assert len(messages) > 0
```

---

## 🎯 Next Step

After completing Step 4, proceed to **Step 5: Strategy Engine & Signal Generation** (`Step5.md`).

---

**Ready to implement? Start coding!** 🐾
