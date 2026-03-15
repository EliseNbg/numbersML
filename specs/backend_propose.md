# Trading Backend Architecture Proposal

**Version:** 1.0  
**Date:** 2026-03-15  
**Author:** Claw (Senior Software Architect)  
**Status:** Proposed

---

## Executive Summary

This document proposes a scalable, flexible trading backend architecture for multi-strategy cryptocurrency and stock trading. The design prioritizes:

- **Low latency** (<40ms target)
- **Parallel strategy execution** (training & testing)
- **Clean separation of concerns** (hexagonal architecture)
- **Simple deployment** (Docker Compose)
- **Technology stack**: Python, PostgreSQL, Redis

---

# Part 1: Architecture Decision Records (ADRs)

## ADR-001: Modular Monolith Architecture

**Status:** Proposed  
**Date:** 2026-03-15

### Context
We need an architecture that supports:
- Multiple parallel trading strategies
- Backtesting and live trading modes
- Low latency (<40ms)
- Easy local development on a notebook
- Future scalability to microservices if needed

### Decision
Start with a **Modular Monolith** architecture, organized by domain boundaries with clear interfaces. This can be split into microservices later if scaling demands it.

**Rationale:**
- Lower complexity for single-developer setup
- No network overhead between components (critical for <40ms latency)
- Easier debugging and testing
- Can deploy as single Docker container
- Domain boundaries are clear, so extraction to services is straightforward later

**Consequences:**
- ✅ Faster development velocity
- ✅ Simpler deployment (single container)
- ✅ Lower latency (in-process communication)
- ⚠️ Must enforce module boundaries strictly
- ⚠️ Scaling requires replicating entire app (not individual services)

### Implementation
- Hexagonal architecture (ports & adapters)
- Domain-driven design for module boundaries
- Event-driven internal communication (asyncio + Redis pub/sub)

---

## ADR-002: PostgreSQL as Primary Database

**Status:** Proposed  
**Date:** 2026-03-15

### Context
We need persistent storage for:
- Orders, trades, positions
- Historical market data (OHLCV candles)
- Strategy configurations
- Performance metrics

Requirements: ACID compliance, SQL familiarity, sufficient performance for <40ms target.

### Decision
Use **PostgreSQL** as the primary database without TimescaleDB extension.

**Rationale:**
- ACID-compliant for financial transactions
- Mature, stable, excellent Python support (asyncpg, SQLAlchemy)
- Sufficient performance for 40ms latency target
- JSONB support for flexible strategy configs
- TimescaleDB adds complexity without benefit at this scale
- Standard PostgreSQL partitioning can handle time-series data if needed

**Consequences:**
- ✅ Simpler setup and maintenance
- ✅ Full SQL capability
- ✅ JSONB for flexible configs
- ⚠️ Manual partitioning if data grows very large
- ⚠️ Slightly less optimized for time-series vs. TimescaleDB

### Schema Design
See Appendix A: Database Schema

---

## ADR-003: Redis Caching Layer

**Status:** Proposed  
**Date:** 2026-03-15

### Context
We need ultra-low latency access to:
- Real-time order books
- Latest market ticks
- Active positions
- Strategy signals
- Rate limiting

### Decision
Use **Redis** as in-memory caching and pub/sub layer between application and PostgreSQL.

**Rationale:**
- Sub-millisecond read/write latency
- Pub/sub for real-time data distribution
- Atomic operations for rate limiting
- Simple key-value + data structures (hashes, sorted sets)
- Mature Python clients (redis-py, aioredis)

**Consequences:**
- ✅ Critical path data is in-memory
- ✅ Real-time pub/sub for strategy threads
- ✅ Natural rate limiting with Redis INCR/EXPIRE
- ⚠️ Data volatility (must persist critical data to PostgreSQL)
- ⚠️ Additional infrastructure component

### Cache Strategy
| Data Type | Storage | TTL |
|-----------|---------|-----|
| Order book | Redis | None (updated live) |
| Latest tick | Redis | 1 minute |
| Active positions | Redis + PostgreSQL | None |
| Strategy signals | Redis | 5 minutes |
| Historical candles | PostgreSQL | N/A |
| Orders/Trades | PostgreSQL | N/A |

---

## ADR-004: Python as Primary Language

**Status:** Proposed  
**Date:** 2026-03-15

### Context
We need a language that supports:
- Rapid development and iteration
- Async I/O for WebSocket connections
- Rich ecosystem for trading/data analysis
- Easy integration with PostgreSQL and Redis

### Decision
Use **Python 3.11+** as the primary language for all components.

**Rationale:**
- Excellent async support (asyncio)
- Rich trading libraries (ccxt, pandas, numpy)
- Fast development velocity
- Strong PostgreSQL (asyncpg) and Redis (aioredis) support
- Easy to write and test strategies
- Good enough performance for 40ms target (not HFT)

**Consequences:**
- ✅ Fast iteration on strategies
- ✅ Huge ecosystem (data, ML, analysis)
- ✅ Easy to hire/find help if needed
- ⚠️ Not suitable for microsecond-level HFT
- ⚠️ GIL limits true multi-threading (use asyncio + multiprocessing)

### Key Libraries
- `asyncio` - Async I/O
- `asyncpg` - PostgreSQL async driver
- `aioredis` - Redis async client
- `ccxt` - Crypto exchange connectivity
- `yfinance` / `yahooquery` - Yahoo Finance data
- `websockets` - WebSocket client
- `pydantic` - Data validation
- `SQLAlchemy 2.0` - ORM (optional, for complex queries)

---

## ADR-005: Docker Compose Deployment

**Status:** Proposed  
**Date:** 2026-03-15

### Context
We need simple, reproducible deployment that:
- Runs on a local notebook
- Spins up all dependencies (DB, Redis, app)
- Is easy to backup and restore
- Can be deployed to cloud later if needed

### Decision
Use **Docker Compose** for local development and deployment.

**Rationale:**
- Single command to start entire stack
- Isolated, reproducible environments
- Easy to version control (docker-compose.yml)
- Simple backup (docker volumes)
- Can deploy to cloud (AWS ECS, DigitalOcean, etc.) with minimal changes

**Consequences:**
- ✅ One-command deployment
- ✅ Consistent across environments
- ✅ Easy backup/restore
- ⚠️ Slight overhead vs. native deployment
- ⚠️ Learning curve if unfamiliar with Docker

---

## ADR-006: Hexagonal Architecture (Ports & Adapters)

**Status:** Proposed  
**Date:** 2026-03-15

### Context
We need an architecture that:
- Isolates business logic from external concerns
- Makes testing easy (mock adapters)
- Allows swapping implementations (e.g., exchange APIs)
- Supports parallel strategy development

### Decision
Implement **Hexagonal Architecture** with clear ports and adapters.

**Rationale:**
- Core domain logic has no external dependencies
- Easy to test (inject mock adapters)
- Swap exchanges, databases, caches without changing core
- Clear boundaries for parallel development

**Consequences:**
- ✅ Testable core logic
- ✅ Flexible adapter implementations
- ✅ Clear separation of concerns
- ⚠️ More boilerplate code
- ⚠️ Requires discipline to maintain boundaries

---

# Part 2: Docker Compose Setup

## Proposed docker-compose.yml

```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:16-alpine
    container_name: trading-db
    environment:
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: ${DB_PASSWORD:-trading_secret}
      POSTGRES_DB: trading
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-db:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trading"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - trading-network
    restart: unless-stopped

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: trading-cache
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - trading-network
    restart: unless-stopped

  # Trading Application
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: trading-app
    environment:
      - DATABASE_URL=postgresql://trading:${DB_PASSWORD:-trading_secret}@postgres:5432/trading
      - REDIS_URL=redis://redis:6379/0
      - ENVIRONMENT=${ENVIRONMENT:-development}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_SECRET_KEY=${BINANCE_SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app
      - ./logs:/app/logs
      - ./strategies:/app/strategies
    networks:
      - trading-network
    restart: unless-stopped

  # Optional: Adminer for DB management (dev only)
  adminer:
    image: adminer:latest
    container_name: trading-adminer
    ports:
      - "8080:8080"
    environment:
      ADMINER_DEFAULT_SERVER: postgres
    depends_on:
      - postgres
    networks:
      - trading-network
    profiles:
      - dev

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local

networks:
  trading-network:
    driver: bridge
```

## Environment Variables (.env template)

```bash
# Database
DB_PASSWORD=your_secure_password_here

# Binance API (optional - for live trading)
BINANCE_API_KEY=
BINANCE_SECRET_KEY=

# Environment
ENVIRONMENT=development  # development | staging | production

# Application
LOG_LEVEL=INFO
MAX_STRATEGIES=10
```

## Dockerfile (Application)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY strategies/ ./strategies/

# Run as non-root user
RUN useradd -m -u 1000 trader && chown -R trader:trader /app
USER trader

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; import asyncpg; import redis" || exit 1

CMD ["python", "-m", "app.main"]
```

## requirements.txt

```txt
# Async
asyncio-mqtt==0.16.1

# Database
asyncpg==0.29.0
SQLAlchemy==2.0.23
alembic==1.13.1

# Redis
redis==5.0.1
aioredis==2.0.1

# Trading
ccxt==4.2.24
yfinance==0.2.36
yahooquery==2.3.2
websockets==12.0

# Data & Analysis
pandas==2.1.4
numpy==1.26.3
ta-lib==0.4.28  # Technical analysis

# Validation
pydantic==2.5.3
pydantic-settings==2.1.0

# Logging & Monitoring
structlog==23.2.0
prometheus-client==0.19.0

# Utilities
python-dotenv==1.0.0
aiohttp==3.9.1
```

---

# Part 3: Python Service Structure (Hexagonal Architecture)

## Directory Structure

```
trading-backend/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md
│
├── app/                          # Application core
│   ├── __init__.py
│   ├── main.py                   # Entry point
│   ├── config.py                 # Configuration management
│   │
│   ├── domain/                   # Domain layer (business logic)
│   │   ├── __init__.py
│   │   ├── models.py             # Domain entities
│   │   ├── services.py           # Domain services
│   │   ├── events.py             # Domain events
│   │   └── exceptions.py         # Domain exceptions
│   │
│   ├── ports/                    # Ports (interfaces)
│   │   ├── __init__.py
│   │   ├── repositories.py       # Repository interfaces
│   │   ├── exchanges.py          # Exchange interfaces
│   │   ├── cache.py              # Cache interfaces
│   │   └── strategies.py         # Strategy interface
│   │
│   └── adapters/                 # Adapters (implementations)
│       ├── __init__.py
│       ├── repositories/
│       │   ├── __init__.py
│       │   ├── postgres_orders.py
│       │   ├── postgres_trades.py
│       │   ├── postgres_positions.py
│       │   └── postgres_market_data.py
│       ├── exchanges/
│       │   ├── __init__.py
│       │   ├── binance_adapter.py
│       │   └── yahoo_adapter.py
│       ├── cache/
│       │   ├── __init__.py
│       │   └── redis_cache.py
│       └── strategies/
│           ├── __init__.py
│           └── base_strategy.py
│
├── services/                     # Application services
│   ├── __init__.py
│   ├── data_ingest.py            # Market data ingestion
│   ├── order_manager.py          # Order management
│   ├── position_tracker.py       # Position tracking
│   ├── strategy_runner.py        # Strategy execution
│   └── risk_manager.py           # Risk management
│
├── api/                          # API layer (if needed)
│   ├── __init__.py
│   ├── routes.py
│   └── schemas.py
│
├── strategies/                   # User-defined strategies
│   ├── __init__.py
│   ├── base.py                   # Base strategy class
│   ├── example_moving_avg.py     # Example strategy
│   └── README.md
│
├── tests/                        # Tests
│   ├── __init__.py
│   ├── conftest.py
│   ├── domain/
│   ├── adapters/
│   └── services/
│
└── logs/                         # Log files (gitignored)
```

## Core Domain Models (app/domain/models.py)

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
from uuid import uuid4


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Candle:
    """OHLCV candle data"""
    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str = "unknown"


@dataclass
class Tick:
    """Real-time price tick"""
    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal


@dataclass
class Order:
    """Order entity"""
    order_id: str = field(default_factory=lambda: str(uuid4()))
    strategy_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    type: OrderType = OrderType.MARKET
    price: Optional[Decimal] = None
    quantity: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    exchange: str = ""
    
    def fill(self, price: Decimal, quantity: Decimal, timestamp: datetime):
        """Mark order as filled"""
        self.status = OrderStatus.FILLED
        self.filled_at = timestamp


@dataclass
class Trade:
    """Executed trade"""
    trade_id: str = field(default_factory=lambda: str(uuid4()))
    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    pnl: Optional[Decimal] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Position:
    """Current position"""
    strategy_id: str = ""
    symbol: str = ""
    quantity: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def update_pnl(self, current_price: Decimal):
        """Calculate unrealized PnL"""
        self.current_price = current_price
        if self.quantity != 0:
            self.unrealized_pnl = (current_price - self.avg_entry_price) * self.quantity
        self.updated_at = datetime.utcnow()


@dataclass
class StrategyConfig:
    """Strategy configuration"""
    strategy_id: str
    name: str
    symbol: str
    timeframe: str
    is_active: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
```

## Port Interfaces (app/ports/)

```python
# app/ports/repositories.py
from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.models import Order, Trade, Position, Candle, StrategyConfig


class OrderRepository(ABC):
    @abstractmethod
    async def save(self, order: Order) -> None:
        pass
    
    @abstractmethod
    async def get_by_id(self, order_id: str) -> Optional[Order]:
        pass
    
    @abstractmethod
    async def get_by_strategy(self, strategy_id: str) -> List[Order]:
        pass
    
    @abstractmethod
    async def get_pending_orders(self) -> List[Order]:
        pass


class TradeRepository(ABC):
    @abstractmethod
    async def save(self, trade: Trade) -> None:
        pass
    
    @abstractmethod
    async def get_by_strategy(self, strategy_id: str) -> List[Trade]:
        pass


class PositionRepository(ABC):
    @abstractmethod
    async def save(self, position: Position) -> None:
        pass
    
    @abstractmethod
    async def get_by_strategy(self, strategy_id: str) -> List[Position]:
        pass
    
    @abstractmethod
    async def get_by_symbol(self, symbol: str) -> List[Position]:
        pass


class MarketDataRepository(ABC):
    @abstractmethod
    async def save_candle(self, candle: Candle) -> None:
        pass
    
    @abstractmethod
    async def get_candles(
        self, 
        symbol: str, 
        timeframe: str, 
        start: datetime, 
        end: datetime
    ) -> List[Candle]:
        pass
    
    @abstractmethod
    async def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        pass


class StrategyRepository(ABC):
    @abstractmethod
    async def save(self, config: StrategyConfig) -> None:
        pass
    
    @abstractmethod
    async def get_all(self) -> List[StrategyConfig]:
        pass
    
    @abstractmethod
    async def get_by_id(self, strategy_id: str) -> Optional[StrategyConfig]:
        pass
    
    @abstractmethod
    async def get_active(self) -> List[StrategyConfig]:
        pass
```

```python
# app/ports/exchanges.py
from abc import ABC, abstractmethod
from typing import Optional, Callable
from app.domain.models import Order, Tick, Candle


class ExchangeAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        pass
    
    @abstractmethod
    async def get_balance(self, symbol: str) -> Decimal:
        pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> None:
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        pass


class MarketDataStream(ABC):
    @abstractmethod
    async def subscribe(self, symbol: str, callback: Callable[[Tick], None]) -> None:
        pass
    
    @abstractmethod
    async def unsubscribe(self, symbol: str) -> None:
        pass
    
    @abstractmethod
    async def get_historical_candles(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int
    ) -> list[Candle]:
        pass
```

```python
# app/ports/cache.py
from abc import ABC, abstractmethod
from typing import Optional, Any
from app.domain.models import Tick, Position, Order


class CacheAdapter(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        pass
    
    @abstractmethod
    async def publish(self, channel: str, message: Any) -> None:
        pass
    
    @abstractmethod
    async def subscribe(self, channel: str, callback: Callable[[Any], None]) -> None:
        pass
    
    @abstractmethod
    async def get_latest_tick(self, symbol: str) -> Optional[Tick]:
        pass
    
    @abstractmethod
    async def set_latest_tick(self, tick: Tick) -> None:
        pass
    
    @abstractmethod
    async def get_position(self, strategy_id: str, symbol: str) -> Optional[Position]:
        pass
    
    @abstractmethod
    async def set_position(self, position: Position) -> None:
        pass
```

## Strategy Interface (strategies/base.py)

```python
from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


class BaseStrategy(ABC):
    """
    Base class for all trading strategies.
    Inherit from this and implement on_candle() and/or on_tick().
    """
    
    def __init__(self, strategy_id: str, config: dict):
        self.strategy_id = strategy_id
        self.config = config
        self.symbol = config.get("symbol", "BTCUSDT")
        self.timeframe = config.get("timeframe", "1m")
        self.is_active = False
        
    @abstractmethod
    async def on_candle(self, candle: dict) -> Optional[dict]:
        """
        Called when a new candle is available.
        Return signal dict: {"action": "BUY"|"SELL"|"HOLD", "quantity": Decimal, "price": Optional[Decimal]}
        """
        pass
    
    async def on_tick(self, tick: dict) -> Optional[dict]:
        """
        Called on real-time tick (optional, for scalping).
        Return signal dict: {"action": "BUY"|"SELL"|"HOLD", "quantity": Decimal, "price": Optional[Decimal]}
        """
        return None
    
    async def start(self):
        """Called when strategy is activated"""
        self.is_active = True
    
    async def stop(self):
        """Called when strategy is deactivated"""
        self.is_active = False
```

---

# Part 4: MVP Data Ingest Modules

## Data Ingest Service (services/data_ingest.py)

```python
import asyncio
import logging
from typing import Dict, Callable, Optional
from datetime import datetime
from decimal import Decimal

from app.domain.models import Candle, Tick
from app.adapters.exchanges.binance_adapter import BinanceMarketData
from app.adapters.exchanges.yahoo_adapter import YahooMarketData
from app.ports.cache import CacheAdapter
from app.ports.repositories import MarketDataRepository

logger = logging.getLogger(__name__)


class DataIngestService:
    """
    Central service for ingesting market data from multiple sources.
    Handles WebSocket streams and REST polling.
    """
    
    def __init__(
        self,
        cache: CacheAdapter,
        repository: MarketDataRepository,
    ):
        self.cache = cache
        self.repository = repository
        self.binance = BinanceMarketData()
        self.yahoo = YahooMarketData()
        self.running = False
        self.subscriptions: Dict[str, Callable] = {}
        
    async def start(self):
        """Start all data ingestion"""
        self.running = True
        logger.info("Data ingest service started")
        
    async def stop(self):
        """Stop all data ingestion"""
        self.running = False
        await self.binance.disconnect()
        logger.info("Data ingest service stopped")
    
    async def subscribe_crypto(
        self, 
        symbol: str, 
        timeframe: str,
        callback: Callable[[Candle], None]
    ):
        """Subscribe to crypto market data (Binance)"""
        self.subscriptions[f"crypto:{symbol}:{timeframe}"] = callback
        
        # Start WebSocket stream
        await self.binance.subscribe(symbol, timeframe, self._handle_crypto_data)
        logger.info(f"Subscribed to {symbol} {timeframe}")
    
    async def subscribe_stock(
        self, 
        symbol: str, 
        timeframe: str,
        callback: Callable[[Candle], None]
    ):
        """Subscribe to stock market data (Yahoo Finance)"""
        self.subscriptions[f"stock:{symbol}:{timeframe}"] = callback
        
        # Start polling (Yahoo doesn't have WebSocket)
        asyncio.create_task(self._poll_stock_data(symbol, timeframe))
        logger.info(f"Subscribed to {symbol} {timeframe}")
    
    async def _handle_crypto_data(self, candle: Candle):
        """Handle incoming crypto candle data"""
        # Cache latest tick
        await self.cache.set_latest_tick(
            Tick(
                symbol=candle.symbol,
                timestamp=candle.timestamp,
                bid=candle.open,
                ask=candle.close,
                last=candle.close,
                volume=candle.volume
            )
        )
        
        # Persist to database
        await self.repository.save_candle(candle)
        
        # Notify subscribers
        key = f"crypto:{candle.symbol}:{candle.timeframe}"
        if key in self.subscriptions:
            await self.subscriptions[key](candle)
    
    async def _poll_stock_data(self, symbol: str, timeframe: str):
        """Poll stock data from Yahoo Finance"""
        while self.running:
            try:
                candles = await self.yahoo.get_candles(symbol, timeframe, limit=1)
                
                if candles:
                    candle = candles[0]
                    
                    # Cache latest tick
                    await self.cache.set_latest_tick(
                        Tick(
                            symbol=candle.symbol,
                            timestamp=candle.timestamp,
                            bid=candle.open,
                            ask=candle.close,
                            last=candle.close,
                            volume=candle.volume
                        )
                    )
                    
                    # Persist to database
                    await self.repository.save_candle(candle)
                    
                    # Notify subscribers
                    key = f"stock:{candle.symbol}:{candle.timeframe}"
                    if key in self.subscriptions:
                        await self.subscriptions[key](candle)
                
                # Poll interval based on timeframe
                poll_interval = self._get_poll_interval(timeframe)
                await asyncio.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error polling {symbol}: {e}")
                await asyncio.sleep(5)
    
    def _get_poll_interval(self, timeframe: str) -> int:
        """Get polling interval based on timeframe"""
        intervals = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return intervals.get(timeframe, 60)
    
    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        source: str = "binance"
    ) -> list[Candle]:
        """Fetch historical candles from database or exchange"""
        # Try database first
        candles = await self.repository.get_candles(symbol, timeframe, start, end)
        
        if not candles and source == "binance":
            # Fetch from exchange if not in DB
            candles = await self.binance.get_historical_candles(symbol, timeframe, limit=1000)
            
            # Persist to DB
            for candle in candles:
                await self.repository.save_candle(candle)
        
        return candles
```

## Binance Adapter (app/adapters/exchanges/binance_adapter.py)

```python
import asyncio
import logging
import websockets
import json
from typing import Callable, Optional, List
from datetime import datetime
from decimal import Decimal

from app.domain.models import Candle, Order, OrderSide, OrderType, OrderStatus
from app.ports.exchanges import ExchangeAdapter, MarketDataStream

logger = logging.getLogger(__name__)


class BinanceMarketData(MarketDataStream):
    """Binance WebSocket market data stream"""
    
    def __init__(self):
        self.ws_url = "wss://stream.binance.com:9443/ws"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.callbacks: dict = {}
        self.running = False
        
    async def connect(self):
        """Connect to Binance WebSocket"""
        self.websocket = await websockets.connect(self.ws_url)
        self.running = True
        logger.info("Connected to Binance WebSocket")
        
    async def disconnect(self):
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
    ):
        """Subscribe to candle stream"""
        if not self.websocket:
            await self.connect()
        
        # Binance candle stream format: <symbol>@kline_<interval>
        stream = f"{symbol.lower()}@kline_{timeframe}"
        
        # Subscribe to stream
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream],
            "id": 1
        }
        await self.websocket.send(json.dumps(subscribe_msg))
        
        # Store callback
        self.callbacks[f"{symbol}:{timeframe}"] = callback
        
        # Start listening (if not already)
        if not hasattr(self, '_listen_task') or self._listen_task.done():
            self._listen_task = asyncio.create_task(self._listen())
    
    async def unsubscribe(self, symbol: str):
        """Unsubscribe from symbol"""
        # Remove callback
        keys_to_remove = [k for k in self.callbacks if k.startswith(symbol)]
        for key in keys_to_remove:
            del self.callbacks[key]
    
    async def _listen(self):
        """Listen for WebSocket messages"""
        try:
            async for message in self.websocket:
                if not self.running:
                    break
                    
                data = json.loads(message)
                
                # Handle candle updates
                if 'k' in data:
                    kline = data['k']
                    candle = Candle(
                        symbol=data['s'],
                        timeframe=kline['i'],
                        timestamp=datetime.fromtimestamp(kline['t'] / 1000),
                        open=Decimal(kline['o']),
                        high=Decimal(kline['h']),
                        low=Decimal(kline['l']),
                        close=Decimal(kline['c']),
                        volume=Decimal(kline['v']),
                        source="binance"
                    )
                    
                    # Call callback
                    key = f"{candle.symbol}:{candle.timeframe}"
                    if key in self.callbacks:
                        await self.callbacks[key](candle)
                        
        except Exception as e:
            logger.error(f"Binance WebSocket error: {e}")
            if self.running:
                await asyncio.sleep(5)
                await self._listen()
    
    async def get_historical_candles(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int = 1000
    ) -> List[Candle]:
        """Fetch historical candles via REST API"""
        import aiohttp
        
        url = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "limit": limit
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
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
                        source="binance"
                    )
                    candles.append(candle)
                
                return candles


class BinanceExchange(ExchangeAdapter):
    """Binance exchange adapter for trading"""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.binance.com"
        
    async def connect(self):
        logger.info("Binance exchange connected")
        
    async def disconnect(self):
        logger.info("Binance exchange disconnected")
        
    async def get_balance(self, symbol: str) -> Decimal:
        # Implement balance fetch
        return Decimal("0")
    
    async def place_order(self, order: Order) -> Order:
        # Implement order placement
        order.status = OrderStatus.SUBMITTED
        return order
    
    async def cancel_order(self, order_id: str) -> None:
        # Implement order cancellation
        pass
    
    async def get_order_status(self, order_id: str) -> Order:
        # Implement order status check
        return Order(order_id=order_id)
```

## Yahoo Finance Adapter (app/adapters/exchanges/yahoo_adapter.py)

```python
import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

import yfinance as yf
from app.domain.models import Candle
from app.ports.exchanges import MarketDataStream

logger = logging.getLogger(__name__)


class YahooMarketData(MarketDataStream):
    """Yahoo Finance market data (REST-based, no WebSocket)"""
    
    def __init__(self):
        self.cache = {}
        
    async def connect(self):
        logger.info("Yahoo Finance adapter initialized")
        
    async def disconnect(self):
        logger.info("Yahoo Finance adapter disconnected")
    
    async def subscribe(
        self, 
        symbol: str, 
        timeframe: str, 
        callback: callable
    ):
        """
        Yahoo doesn't support WebSocket, so this is a no-op.
        Use polling via get_candles() instead.
        """
        logger.warning("Yahoo Finance doesn't support WebSocket subscriptions. Use polling.")
    
    async def unsubscribe(self, symbol: str):
        pass
    
    async def get_candles(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> List[Candle]:
        """Fetch candles from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            
            # Map timeframe to Yahoo interval
            interval_map = {
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "1h": "1h",
                "1d": "1d",
                "1wk": "1wk",
                "1mo": "1mo",
            }
            
            interval = interval_map.get(timeframe, "1d")
            
            # Get historical data
            data = ticker.history(period=f"{limit}{timeframe[-1]}", interval=interval)
            
            candles = []
            for idx, row in data.iterrows():
                candle = Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=row.name.to_pydatetime(),
                    open=Decimal(str(row['Open'])),
                    high=Decimal(str(row['High'])),
                    low=Decimal(str(row['Low'])),
                    close=Decimal(str(row['Close'])),
                    volume=Decimal(str(row['Volume'])),
                    source="yahoo"
                )
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            logger.error(f"Error fetching Yahoo data for {symbol}: {e}")
            return []
    
    async def get_historical_candles(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int = 1000
    ) -> List[Candle]:
        """Alias for get_candles"""
        return await self.get_candles(symbol, timeframe, limit)
```

## PostgreSQL Repository Implementation (app/adapters/repositories/postgres_market_data.py)

```python
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

import asyncpg
from app.domain.models import Candle
from app.ports.repositories import MarketDataRepository

logger = logging.getLogger(__name__)


class PostgresMarketDataRepository(MarketDataRepository):
    """PostgreSQL implementation for market data"""
    
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
    
    async def save_candle(self, candle: Candle) -> None:
        """Save candle to database"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO candles (symbol, timeframe, timestamp, open, high, low, close, volume, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING
                """,
                candle.symbol,
                candle.timeframe,
                candle.timestamp,
                float(candle.open),
                float(candle.high),
                float(candle.low),
                float(candle.close),
                float(candle.volume),
                candle.source
            )
    
    async def get_candles(
        self, 
        symbol: str, 
        timeframe: str, 
        start: datetime, 
        end: datetime
    ) -> List[Candle]:
        """Fetch candles from database"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT symbol, timeframe, timestamp, open, high, low, close, volume, source
                FROM candles
                WHERE symbol = $1 
                  AND timeframe = $2 
                  AND timestamp BETWEEN $3 AND $4
                ORDER BY timestamp ASC
                """,
                symbol, timeframe, start, end
            )
            
            candles = []
            for row in rows:
                candle = Candle(
                    symbol=row['symbol'],
                    timeframe=row['timeframe'],
                    timestamp=row['timestamp'],
                    open=Decimal(str(row['open'])),
                    high=Decimal(str(row['high'])),
                    low=Decimal(str(row['low'])),
                    close=Decimal(str(row['close'])),
                    volume=Decimal(str(row['volume'])),
                    source=row['source']
                )
                candles.append(candle)
            
            return candles
    
    async def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """Get most recent candle"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT symbol, timeframe, timestamp, open, high, low, close, volume, source
                FROM candles
                WHERE symbol = $1 AND timeframe = $2
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                symbol, timeframe
            )
            
            if row:
                return Candle(
                    symbol=row['symbol'],
                    timeframe=row['timeframe'],
                    timestamp=row['timestamp'],
                    open=Decimal(str(row['open'])),
                    high=Decimal(str(row['high'])),
                    low=Decimal(str(row['low'])),
                    close=Decimal(str(row['close'])),
                    volume=Decimal(str(row['volume'])),
                    source=row['source']
                )
            return None
```

## Redis Cache Implementation (app/adapters/cache/redis_cache.py)

```python
import json
import logging
from typing import Optional, Any, Callable
from datetime import datetime
from decimal import Decimal

import aioredis
from app.domain.models import Tick, Position
from app.ports.cache import CacheAdapter

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class RedisCacheAdapter(CacheAdapter):
    """Redis cache implementation"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
    
    async def connect(self):
        self.redis = await aioredis.from_url(self.redis_url)
        logger.info("Connected to Redis")
    
    async def disconnect(self):
        if self.redis:
            await self.redis.close()
        logger.info("Disconnected from Redis")
    
    async def get(self, key: str) -> Optional[Any]:
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        serialized = json.dumps(value, cls=DecimalEncoder)
        if ttl:
            await self.redis.setex(key, ttl, serialized)
        else:
            await self.redis.set(key, serialized)
    
    async def delete(self, key: str) -> None:
        await self.redis.delete(key)
    
    async def publish(self, channel: str, message: Any) -> None:
        serialized = json.dumps(message, cls=DecimalEncoder)
        await self.redis.publish(channel, serialized)
    
    async def subscribe(self, channel: str, callback: Callable[[Any], None]) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        
        async def listen():
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    await callback(data)
        
        asyncio.create_task(listen())
    
    async def get_latest_tick(self, symbol: str) -> Optional[Tick]:
        key = f"tick:{symbol}"
        data = await self.get(key)
        if data:
            return Tick(
                symbol=data['symbol'],
                timestamp=datetime.fromisoformat(data['timestamp']),
                bid=Decimal(data['bid']),
                ask=Decimal(data['ask']),
                last=Decimal(data['last']),
                volume=Decimal(data['volume'])
            )
        return None
    
    async def set_latest_tick(self, tick: Tick) -> None:
        key = f"tick:{tick.symbol}"
        await self.set(key, {
            'symbol': tick.symbol,
            'timestamp': tick.timestamp.isoformat(),
            'bid': str(tick.bid),
            'ask': str(tick.ask),
            'last': str(tick.last),
            'volume': str(tick.volume)
        }, ttl=60)  # 1 minute TTL
    
    async def get_position(self, strategy_id: str, symbol: str) -> Optional[Position]:
        key = f"position:{strategy_id}:{symbol}"
        data = await self.get(key)
        if data:
            return Position(
                strategy_id=data['strategy_id'],
                symbol=data['symbol'],
                quantity=Decimal(data['quantity']),
                avg_entry_price=Decimal(data['avg_entry_price']),
                current_price=Decimal(data['current_price']),
                unrealized_pnl=Decimal(data['unrealized_pnl']),
                updated_at=datetime.fromisoformat(data['updated_at'])
            )
        return None
    
    async def set_position(self, position: Position) -> None:
        key = f"position:{position.strategy_id}:{position.symbol}"
        await self.set(key, {
            'strategy_id': position.strategy_id,
            'symbol': position.symbol,
            'quantity': str(position.quantity),
            'avg_entry_price': str(position.avg_entry_price),
            'current_price': str(position.current_price),
            'unrealized_pnl': str(position.unrealized_pnl),
            'updated_at': position.updated_at.isoformat()
        })
```

---

# Appendix A: Database Schema

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Market data (OHLCV candles)
CREATE TABLE candles (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC(20, 8),
    high NUMERIC(20, 8),
    low NUMERIC(20, 8),
    close NUMERIC(20, 8),
    volume NUMERIC(20, 8),
    source TEXT DEFAULT 'unknown',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint to prevent duplicates
CREATE UNIQUE INDEX idx_candles_unique 
ON candles(symbol, timeframe, timestamp);

-- Index for fast queries
CREATE INDEX idx_candles_symbol_time ON candles(symbol, timestamp DESC);

-- Orders
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    type TEXT NOT NULL,
    price NUMERIC(20, 8),
    quantity NUMERIC(20, 8) NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    filled_at TIMESTAMPTZ,
    exchange TEXT NOT NULL
);

CREATE INDEX idx_orders_strategy ON orders(strategy_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at DESC);

-- Trades (executed orders)
CREATE TABLE trades (
    trade_id TEXT PRIMARY KEY,
    order_id TEXT REFERENCES orders(order_id),
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    fee NUMERIC(20, 8) DEFAULT 0,
    pnl NUMERIC(20, 8),
    executed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trades_strategy ON trades(strategy_id, executed_at DESC);
CREATE INDEX idx_trades_order ON trades(order_id);

-- Positions (current holdings)
CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    avg_entry_price NUMERIC(20, 8),
    current_price NUMERIC(20, 8),
    unrealized_pnl NUMERIC(20, 8),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy_id, symbol)
);

CREATE INDEX idx_positions_strategy ON positions(strategy_id);

-- Strategies (metadata for parallel testing)
CREATE TABLE strategies (
    strategy_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    config JSONB,
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_strategies_active ON strategies(is_active);

-- Performance metrics (per strategy)
CREATE TABLE strategy_performance (
    id BIGSERIAL PRIMARY KEY,
    strategy_id TEXT REFERENCES strategies(strategy_id),
    date DATE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    total_pnl NUMERIC(20, 8),
    sharpe_ratio NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy_id, date)
);

CREATE INDEX idx_performance_strategy ON strategy_performance(strategy_id, date DESC);

-- Audit log (optional but recommended)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
```

---

# Next Steps

1. **Review this proposal** - Does this architecture match your vision?
2. **Create the project structure** - I can generate all the files
3. **Implement MVP** - Start with data ingest + basic strategy runner
4. **Test locally** - Run with Docker Compose on your notebook
5. **Iterate** - Add features based on real usage

Want me to start creating the actual files, or do you want to discuss any changes first? 🐾
