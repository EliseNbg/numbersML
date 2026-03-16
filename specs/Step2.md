# Step 2: Database Layer - Schema & Repositories

**Status:** ⏳ Pending  
**Effort:** 6-8 hours  
**Dependencies:** Step 1 (Project Foundation)

---

## 🎯 Objective

Implement the database layer with PostgreSQL schema, domain models, and repository pattern for data persistence. This layer provides clean abstraction over database operations.

**Key Outcomes:**
- Domain models defined (Candle, Order, Trade, Position, etc.)
- PostgreSQL schema created
- Repository interfaces (ports)
- Repository implementations (adapters)
- Connection pooling configured
- Batch insert support for performance

---

## 📁 Deliverables

Create the following file structure:

```
app/
├── domain/
│   ├── __init__.py
│   ├── models.py                 # Domain entities
│   ├── services.py               # Domain services (optional)
│   └── exceptions.py             # Domain exceptions
├── ports/
│   ├── __init__.py
│   └── repositories.py           # Repository interfaces
└── adapters/
    └── repositories/
        ├── __init__.py
        ├── postgres_pool.py      # Connection pool management
        ├── candles.py            # Candle repository
        ├── orders.py             # Order repository
        ├── trades.py             # Trade repository
        └── positions.py          # Position repository

tests/
├── domain/
│   └── test_models.py
└── adapters/
    └── repositories/
        ├── test_candles.py
        ├── test_orders.py
        └── test_positions.py

scripts/
└── init_db.sql                   # Database initialization
```

---

## 📝 Specifications

### Logging Requirements for Step 2

**All database operations MUST use structured logging with:**
- **Correlation IDs**: Generate unique ID per operation for tracing
- **Component label**: Always set `component="database"`
- **Operation context**: Include symbol, timeframe, strategy_id where applicable
- **Latency tracking**: Log execution time for all database operations
- **Error context**: Include full error details with exc_info=True

**Example logging pattern:**
```python
correlation_id = generate_correlation_id()
start_time = datetime.utcnow()

try:
    # Database operation
    logger.debug(
        "Operation description",
        correlation_id=correlation_id,
        symbol="BTCUSDT",
        strategy_id="sma_1",
        component="database",
        latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
    )
except Exception as e:
    logger.error(
        "Operation failed",
        correlation_id=correlation_id,
        error=str(e),
        component="database",
        exc_info=True
    )
```

**Loki Labels Required:**
- `correlation_id` - Unique operation ID
- `component` - Always "database" for this layer
- `symbol` - Trading pair (when applicable)
- `strategy_id` - Strategy identifier (when applicable)

### 2.1 Domain Models (`app/domain/models.py`)

**Requirements:**
- Use Python dataclasses for domain entities
- Include all necessary fields for trading
- Use `Decimal` for financial values (never float!)
- Include validation where appropriate

**Implementation:**

```python
# app/domain/models.py
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4


# === Enums ===

class OrderSide(str, Enum):
    """Order side"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(str, Enum):
    """Order status"""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


# === Market Data ===

@dataclass
class Candle:
    """
    OHLCV candle for scalping (1-second intervals supported).
    
    Attributes:
        symbol: Trading pair (e.g., "BTCUSDT")
        timeframe: Candle interval (e.g., "1s", "1m", "5m")
        timestamp: Candle open time
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Base asset volume
        source: Data source ("binance", "yahoo", etc.)
        trade_count: Number of trades in candle
        quote_volume: Quote asset volume
    """
    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str = "unknown"
    trade_count: int = 0
    quote_volume: Decimal = Decimal("0")
    
    def __post_init__(self):
        """Validate candle data"""
        if self.high < self.low:
            raise ValueError("High cannot be lower than low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("High must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("Low must be <= open and close")


@dataclass
class Tick:
    """
    Real-time price tick.
    
    Attributes:
        symbol: Trading pair
        timestamp: Tick time
        bid: Best bid price
        ask: Best ask price
        last: Last trade price
        volume: Trade volume
    """
    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal = Decimal("0")


# === Orders & Trades ===

@dataclass
class Order:
    """
    Trading order.
    
    Attributes:
        order_id: Unique order ID (UUID)
        strategy_id: Strategy that created this order
        symbol: Trading pair
        side: BUY or SELL
        type: Order type (MARKET, LIMIT, etc.)
        price: Limit price (None for market orders)
        quantity: Order quantity
        status: Current status
        created_at: Creation timestamp
        filled_at: Fill timestamp (when completed)
        exchange: Exchange name
        client_order_id: Exchange-specific order ID
        avg_fill_price: Average fill price
        total_filled: Total quantity filled
    """
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
    client_order_id: Optional[str] = None
    avg_fill_price: Optional[Decimal] = None
    total_filled: Decimal = Decimal("0")
    
    def fill(self, price: Decimal, quantity: Decimal, timestamp: datetime) -> None:
        """
        Mark order as filled.
        
        Args:
            price: Fill price
            quantity: Filled quantity
            timestamp: Fill time
        """
        if self.total_filled == 0:
            self.avg_fill_price = price
        else:
            # Calculate weighted average
            total_value = (self.avg_fill_price * self.total_filled) + (price * quantity)
            self.total_filled += quantity
            self.avg_fill_price = total_value / self.total_filled
        
        if self.total_filled >= self.quantity:
            self.status = OrderStatus.FILLED
            self.filled_at = timestamp
    
    def cancel(self) -> None:
        """Cancel the order"""
        if self.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
            self.status = OrderStatus.CANCELLED


@dataclass
class Trade:
    """
    Executed trade (fill).
    
    Attributes:
        trade_id: Unique trade ID
        order_id: Parent order ID
        strategy_id: Strategy that created the trade
        symbol: Trading pair
        side: BUY or SELL
        price: Execution price
        quantity: Executed quantity
        fee: Transaction fee
        fee_currency: Fee currency (e.g., "BNB", "USDT")
        pnl: Profit/loss (calculated on close)
        executed_at: Execution timestamp
        is_maker: True if maker order (false if taker)
    """
    trade_id: str = field(default_factory=lambda: str(uuid4()))
    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    fee_currency: str = "USDT"
    pnl: Optional[Decimal] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)
    is_maker: bool = False


# === Positions ===

@dataclass
class Position:
    """
    Current trading position.
    
    Attributes:
        strategy_id: Strategy that owns this position
        symbol: Trading pair
        quantity: Position size (positive=long, negative=short)
        avg_entry_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        realized_pnl: Realized profit/loss from closed trades
        updated_at: Last update timestamp
        opened_at: Position open time
        closed_at: Position close time (None if open)
    """
    strategy_id: str = ""
    symbol: str = ""
    quantity: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    updated_at: datetime = field(default_factory=datetime.utcnow)
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    
    @property
    def is_open(self) -> bool:
        """Check if position is still open"""
        return self.closed_at is None
    
    @property
    def side(self) -> Optional[str]:
        """Get position side"""
        if self.quantity > 0:
            return "LONG"
        elif self.quantity < 0:
            return "SHORT"
        return None
    
    def update_pnl(self, current_price: Decimal) -> None:
        """
        Update unrealized PnL based on current price.
        
        Args:
            current_price: Current market price
        """
        self.current_price = current_price
        if self.quantity != 0:
            self.unrealized_pnl = (current_price - self.avg_entry_price) * self.quantity
        self.updated_at = datetime.utcnow()
    
    def close(self, close_price: Decimal, close_time: datetime) -> Decimal:
        """
        Close the position and calculate realized PnL.
        
        Args:
            close_price: Close price
            close_time: Close timestamp
        
        Returns:
            Realized PnL
        """
        realized = (close_price - self.avg_entry_price) * self.quantity
        self.realized_pnl += realized
        self.quantity = Decimal("0")
        self.unrealized_pnl = Decimal("0")
        self.closed_at = close_time
        self.updated_at = close_time
        return realized


# === Strategy ===

@dataclass
class StrategyConfig:
    """
    Strategy configuration.
    
    Attributes:
        strategy_id: Unique strategy ID
        name: Strategy name
        symbol: Trading pair
        timeframe: Candle timeframe
        is_active: Whether strategy is active
        config: Strategy-specific parameters (JSON)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    strategy_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    symbol: str = "BTCUSDT"
    timeframe: str = "1s"
    is_active: bool = False
    config: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

---

### 2.2 Domain Exceptions (`app/domain/exceptions.py`)

```python
# app/domain/exceptions.py
class DomainException(Exception):
    """Base exception for domain errors"""
    pass


class InvalidCandleError(DomainException):
    """Raised when candle data is invalid"""
    pass


class OrderNotFoundError(DomainException):
    """Raised when order is not found"""
    pass


class OrderValidationError(DomainException):
    """Raised when order validation fails"""
    pass


class PositionNotFoundError(DomainException):
    """Raised when position is not found"""
    pass


class InsufficientBalanceError(DomainException):
    """Raised when account has insufficient balance"""
    pass


class DuplicateCandleError(DomainException):
    """Raised when trying to insert duplicate candle"""
    pass
```

---

### 2.3 Repository Interfaces (`app/ports/repositories.py`)

**Requirements:**
- Define abstract interfaces for all repositories
- Use async methods throughout
- Type hints for all parameters and return values

**Implementation:**

```python
# app/ports/repositories.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from app.domain.models import Candle, Order, Trade, Position, StrategyConfig


class CandleRepository(ABC):
    """Repository for candle (market data) operations"""
    
    @abstractmethod
    async def save(self, candle: Candle) -> None:
        """Save a single candle"""
        pass
    
    @abstractmethod
    async def save_batch(self, candles: List[Candle]) -> None:
        """Save multiple candles in batch (performance critical)"""
        pass
    
    @abstractmethod
    async def get_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime
    ) -> List[Candle]:
        """Get candles in time range"""
        pass
    
    @abstractmethod
    async def get_latest(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """Get most recent candle"""
        pass
    
    @abstractmethod
    async def get_last_n(
        self,
        symbol: str,
        timeframe: str,
        count: int
    ) -> List[Candle]:
        """Get last N candles"""
        pass


class OrderRepository(ABC):
    """Repository for order operations"""
    
    @abstractmethod
    async def save(self, order: Order) -> None:
        """Save order"""
        pass
    
    @abstractmethod
    async def get_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        pass
    
    @abstractmethod
    async def get_by_strategy(self, strategy_id: str) -> List[Order]:
        """Get all orders for a strategy"""
        pass
    
    @abstractmethod
    async def get_pending(self) -> List[Order]:
        """Get all pending orders"""
        pass
    
    @abstractmethod
    async def update_status(self, order_id: str, status: str) -> None:
        """Update order status"""
        pass
    
    @abstractmethod
    async def update_fill(
        self,
        order_id: str,
        avg_fill_price: float,
        total_filled: float,
        filled_at: datetime
    ) -> None:
        """Update order fill information"""
        pass


class TradeRepository(ABC):
    """Repository for trade operations"""
    
    @abstractmethod
    async def save(self, trade: Trade) -> None:
        """Save trade"""
        pass
    
    @abstractmethod
    async def get_by_id(self, trade_id: str) -> Optional[Trade]:
        """Get trade by ID"""
        pass
    
    @abstractmethod
    async def get_by_order(self, order_id: str) -> List[Trade]:
        """Get all trades for an order"""
        pass
    
    @abstractmethod
    async def get_by_strategy(self, strategy_id: str) -> List[Trade]:
        """Get all trades for a strategy"""
        pass
    
    @abstractmethod
    async def get_recent(self, limit: int = 100) -> List[Trade]:
        """Get recent trades"""
        pass


class PositionRepository(ABC):
    """Repository for position operations"""
    
    @abstractmethod
    async def save(self, position: Position) -> None:
        """Save position (upsert)"""
        pass
    
    @abstractmethod
    async def get_by_id(self, strategy_id: str, symbol: str) -> Optional[Position]:
        """Get position by strategy and symbol"""
        pass
    
    @abstractmethod
    async def get_by_strategy(self, strategy_id: str) -> List[Position]:
        """Get all positions for a strategy"""
        pass
    
    @abstractmethod
    async def get_by_symbol(self, symbol: str) -> List[Position]:
        """Get all positions for a symbol"""
        pass
    
    @abstractmethod
    async def get_all_open(self) -> List[Position]:
        """Get all open positions"""
        pass


class StrategyRepository(ABC):
    """Repository for strategy configuration"""
    
    @abstractmethod
    async def save(self, config: StrategyConfig) -> None:
        """Save strategy config"""
        pass
    
    @abstractmethod
    async def get_by_id(self, strategy_id: str) -> Optional[StrategyConfig]:
        """Get strategy by ID"""
        pass
    
    @abstractmethod
    async def get_all(self) -> List[StrategyConfig]:
        """Get all strategies"""
        pass
    
    @abstractmethod
    async def get_active(self) -> List[StrategyConfig]:
        """Get all active strategies"""
        pass
    
    @abstractmethod
    async def update_status(self, strategy_id: str, is_active: bool) -> None:
        """Update strategy active status"""
        pass
```

---

### 2.4 Connection Pool (`app/adapters/repositories/postgres_pool.py`)

```python
# app/adapters/repositories/postgres_pool.py
import asyncio
import logging
from typing import Optional

import asyncpg
from asyncpg import Pool

from app.config import Settings, get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class DatabasePool:
    """
    PostgreSQL connection pool manager.
    
    Singleton pattern for shared pool access.
    """
    
    _instance: Optional["DatabasePool"] = None
    _pool: Optional[Pool] = None
    _lock: asyncio.Lock = asyncio.Lock()
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
    
    @classmethod
    async def get_instance(cls) -> "DatabasePool":
        """Get singleton instance"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance.initialize()
        return cls._instance
    
    async def initialize(self) -> None:
        """Initialize connection pool"""
        if self._pool is not None:
            logger.warning("Database pool already initialized")
            return
        
        try:
            logger.info(
                "Creating database connection pool",
                url=self.settings.database_url,
                min_size=self.settings.database_pool_min_size,
                max_size=self.settings.database_pool_size
            )
            
            self._pool = await asyncpg.create_pool(
                dsn=self.settings.database_url,
                min_size=self.settings.database_pool_min_size,
                max_size=self.settings.database_pool_size,
                command_timeout=60,
            )
            
            # Test connection
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            logger.info("Database pool initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize database pool", error=str(e))
            raise
    
    async def close(self) -> None:
        """Close connection pool"""
        if self._pool:
            logger.info("Closing database connection pool")
            await self._pool.close()
            self._pool = None
    
    @property
    def pool(self) -> Pool:
        """Get connection pool"""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized")
        return self._pool
    
    async def acquire(self):
        """Acquire connection from pool"""
        return self._pool.acquire()
    
    async def execute(self, query: str, *args) -> None:
        """Execute query without returning results"""
        async with self._pool.acquire() as conn:
            await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> list:
        """Fetch all rows"""
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchone(self, query: str, *args) -> Optional[dict]:
        """Fetch single row"""
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Optional[any]:
        """Fetch single value"""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)


# Convenience functions
async def get_db_pool() -> DatabasePool:
    """Get database pool instance"""
    return await DatabasePool.get_instance()


async def close_db_pool() -> None:
    """Close database pool"""
    pool = await DatabasePool.get_instance()
    await pool.close()
```

---

### 2.5 Candle Repository (`app/adapters/repositories/candles.py`)

```python
# app/adapters/repositories/candles.py
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from app.domain.models import Candle
from app.ports.repositories import CandleRepository
from app.adapters.repositories.postgres_pool import DatabasePool
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class PostgresCandleRepository(CandleRepository):
    """PostgreSQL implementation of candle repository"""
    
    def __init__(self, pool: DatabasePool):
        self.pool = pool
    
    async def save(self, candle: Candle) -> None:
        """Save a single candle with correlation ID tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()
        
        query = """
            INSERT INTO candles (
                symbol, timeframe, timestamp, open, high, low, close,
                volume, source, trade_count, quote_volume
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING
        """
        
        try:
            async with self.pool.pool.acquire() as conn:
                await conn.execute(
                    query,
                    candle.symbol,
                    candle.timeframe,
                    candle.timestamp,
                    float(candle.open),
                    float(candle.high),
                    float(candle.low),
                    float(candle.close),
                    float(candle.volume),
                    candle.source,
                    candle.trade_count,
                    float(candle.quote_volume)
                )
                
                logger.debug(
                    "Saved candle",
                    correlation_id=correlation_id,
                    symbol=candle.symbol,
                    timeframe=candle.timeframe,
                    timestamp=candle.timestamp.isoformat(),
                    component="database",
                    latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
                )
        except Exception as e:
            logger.error(
                "Failed to save candle",
                correlation_id=correlation_id,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                error=str(e),
                component="database",
                exc_info=True
            )
            raise
    
    async def save_batch(self, candles: List[Candle]) -> None:
        """Save multiple candles in batch with correlation ID tracking"""
        if not candles:
            return
        
        # Generate correlation ID for this batch operation
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()
        
        query = """
            INSERT INTO candles (
                symbol, timeframe, timestamp, open, high, low, close,
                volume, source, trade_count, quote_volume
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING
        """
        
        try:
            async with self.pool.pool.acquire() as conn:
                # Use copy_records_to_table for better performance with large batches
                if len(candles) > 100:
                    records = [
                        (
                            c.symbol, c.timeframe, c.timestamp,
                            float(c.open), float(c.high), float(c.low),
                            float(c.close), float(c.volume),
                            c.source, c.trade_count, float(c.quote_volume)
                        )
                        for c in candles
                    ]
                    await conn.copy_records_to_table(
                        'candles',
                        records=records,
                        columns=[
                            'symbol', 'timeframe', 'timestamp', 'open', 'high',
                            'low', 'close', 'volume', 'source', 'trade_count', 'quote_volume'
                        ]
                    )
                else:
                    # Regular batch insert for smaller batches
                    await conn.executemany(
                        query,
                        [
                            (
                                c.symbol, c.timeframe, c.timestamp,
                                float(c.open), float(c.high), float(c.low),
                                float(c.close), float(c.volume),
                                c.source, c.trade_count, float(c.quote_volume)
                            )
                            for c in candles
                        ]
                    )
            
            logger.debug(
                "Saved candles batch",
                correlation_id=correlation_id,
                count=len(candles),
                symbol=candles[0].symbol if candles else "",
                timeframe=candles[0].timeframe if candles else "",
                component="database",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
            
        except Exception as e:
            logger.error(
                "Failed to save batch candles",
                correlation_id=correlation_id,
                count=len(candles),
                error=str(e),
                component="database",
                exc_info=True
            )
            raise
    
    async def get_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime
    ) -> List[Candle]:
        """Get candles in time range"""
        query = """
            SELECT symbol, timeframe, timestamp, open, high, low, close,
                   volume, source, trade_count, quote_volume
            FROM candles
            WHERE symbol = $1
              AND timeframe = $2
              AND timestamp BETWEEN $3 AND $4
            ORDER BY timestamp ASC
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol, timeframe, start, end)
            
            return [
                Candle(
                    symbol=row['symbol'],
                    timeframe=row['timeframe'],
                    timestamp=row['timestamp'],
                    open=Decimal(str(row['open'])),
                    high=Decimal(str(row['high'])),
                    low=Decimal(str(row['low'])),
                    close=Decimal(str(row['close'])),
                    volume=Decimal(str(row['volume'])),
                    source=row['source'],
                    trade_count=row['trade_count'],
                    quote_volume=Decimal(str(row['quote_volume']))
                )
                for row in rows
            ]
    
    async def get_latest(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """Get most recent candle"""
        query = """
            SELECT symbol, timeframe, timestamp, open, high, low, close,
                   volume, source, trade_count, quote_volume
            FROM candles
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        async with self.pool.pool.acquire() as conn:
            row = await conn.fetchrow(query, symbol, timeframe)
            
            if row is None:
                return None
            
            return Candle(
                symbol=row['symbol'],
                timeframe=row['timeframe'],
                timestamp=row['timestamp'],
                open=Decimal(str(row['open'])),
                high=Decimal(str(row['high'])),
                low=Decimal(str(row['low'])),
                close=Decimal(str(row['close'])),
                volume=Decimal(str(row['volume'])),
                source=row['source'],
                trade_count=row['trade_count'],
                quote_volume=Decimal(str(row['quote_volume']))
            )
    
    async def get_last_n(
        self,
        symbol: str,
        timeframe: str,
        count: int
    ) -> List[Candle]:
        """Get last N candles"""
        query = """
            SELECT symbol, timeframe, timestamp, open, high, low, close,
                   volume, source, trade_count, quote_volume
            FROM candles
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY timestamp DESC
            LIMIT $3
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol, timeframe, count)
            
            candles = [
                Candle(
                    symbol=row['symbol'],
                    timeframe=row['timeframe'],
                    timestamp=row['timestamp'],
                    open=Decimal(str(row['open'])),
                    high=Decimal(str(row['high'])),
                    low=Decimal(str(row['low'])),
                    close=Decimal(str(row['close'])),
                    volume=Decimal(str(row['volume'])),
                    source=row['source'],
                    trade_count=row['trade_count'],
                    quote_volume=Decimal(str(row['quote_volume']))
                )
                for row in rows
            ]
            
            # Return in ascending order
            return list(reversed(candles))
```

---

### 2.6 Order Repository (`app/adapters/repositories/orders.py`)

```python
# app/adapters/repositories/orders.py
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from app.domain.models import Order, OrderSide, OrderType, OrderStatus
from app.ports.repositories import OrderRepository
from app.adapters.repositories.postgres_pool import DatabasePool
from app.logging_config import get_logger

logger = get_logger(__name__)


class PostgresOrderRepository(OrderRepository):
    """PostgreSQL implementation of order repository"""
    
    def __init__(self, pool: DatabasePool):
        self.pool = pool
    
    async def save(self, order: Order) -> None:
        """Save order"""
        query = """
            INSERT INTO orders (
                order_id, strategy_id, symbol, side, type, price, quantity,
                status, created_at, filled_at, exchange, client_order_id,
                avg_fill_price, total_filled
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (order_id) DO UPDATE SET
                status = EXCLUDED.status,
                avg_fill_price = EXCLUDED.avg_fill_price,
                total_filled = EXCLUDED.total_filled,
                filled_at = EXCLUDED.filled_at,
                updated_at = NOW()
        """
        
        try:
            async with self.pool.pool.acquire() as conn:
                await conn.execute(
                    query,
                    order.order_id,
                    order.strategy_id,
                    order.symbol,
                    order.side.value,
                    order.type.value,
                    float(order.price) if order.price else None,
                    float(order.quantity),
                    order.status.value,
                    order.created_at,
                    order.filled_at,
                    order.exchange,
                    order.client_order_id,
                    float(order.avg_fill_price) if order.avg_fill_price else None,
                    float(order.total_filled)
                )
        except Exception as e:
            logger.error(
                "Failed to save order",
                order_id=order.order_id,
                error=str(e)
            )
            raise
    
    async def get_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        query = """
            SELECT order_id, strategy_id, symbol, side, type, price, quantity,
                   status, created_at, filled_at, exchange, client_order_id,
                   avg_fill_price, total_filled
            FROM orders
            WHERE order_id = $1
        """
        
        async with self.pool.pool.acquire() as conn:
            row = await conn.fetchrow(query, order_id)
            
            if row is None:
                return None
            
            return Order(
                order_id=row['order_id'],
                strategy_id=row['strategy_id'],
                symbol=row['symbol'],
                side=OrderSide(row['side']),
                type=OrderType(row['type']),
                price=Decimal(str(row['price'])) if row['price'] else None,
                quantity=Decimal(str(row['quantity'])),
                status=OrderStatus(row['status']),
                created_at=row['created_at'],
                filled_at=row['filled_at'],
                exchange=row['exchange'],
                client_order_id=row['client_order_id'],
                avg_fill_price=Decimal(str(row['avg_fill_price'])) if row['avg_fill_price'] else None,
                total_filled=Decimal(str(row['total_filled']))
            )
    
    async def get_by_strategy(self, strategy_id: str) -> List[Order]:
        """Get all orders for a strategy"""
        query = """
            SELECT order_id, strategy_id, symbol, side, type, price, quantity,
                   status, created_at, filled_at, exchange, client_order_id,
                   avg_fill_price, total_filled
            FROM orders
            WHERE strategy_id = $1
            ORDER BY created_at DESC
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, strategy_id)
            return [self._row_to_order(row) for row in rows]
    
    async def get_pending(self) -> List[Order]:
        """Get all pending orders"""
        query = """
            SELECT order_id, strategy_id, symbol, side, type, price, quantity,
                   status, created_at, filled_at, exchange, client_order_id,
                   avg_fill_price, total_filled
            FROM orders
            WHERE status IN ('PENDING', 'SUBMITTED', 'PARTIALLY_FILLED')
            ORDER BY created_at ASC
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [self._row_to_order(row) for row in rows]
    
    async def update_status(self, order_id: str, status: str) -> None:
        """Update order status"""
        query = """
            UPDATE orders
            SET status = $1, updated_at = NOW()
            WHERE order_id = $2
        """
        
        async with self.pool.pool.acquire() as conn:
            await conn.execute(query, status, order_id)
    
    async def update_fill(
        self,
        order_id: str,
        avg_fill_price: float,
        total_filled: float,
        filled_at: datetime
    ) -> None:
        """Update order fill information"""
        query = """
            UPDATE orders
            SET avg_fill_price = $1,
                total_filled = $2,
                filled_at = $3,
                status = CASE
                    WHEN $2 >= quantity THEN 'FILLED'
                    ELSE 'PARTIALLY_FILLED'
                END,
                updated_at = NOW()
            WHERE order_id = $4
        """
        
        async with self.pool.pool.acquire() as conn:
            await conn.execute(query, avg_fill_price, total_filled, filled_at, order_id)
    
    def _row_to_order(self, row) -> Order:
        """Convert database row to Order object"""
        return Order(
            order_id=row['order_id'],
            strategy_id=row['strategy_id'],
            symbol=row['symbol'],
            side=OrderSide(row['side']),
            type=OrderType(row['type']),
            price=Decimal(str(row['price'])) if row['price'] else None,
            quantity=Decimal(str(row['quantity'])),
            status=OrderStatus(row['status']),
            created_at=row['created_at'],
            filled_at=row['filled_at'],
            exchange=row['exchange'],
            client_order_id=row['client_order_id'],
            avg_fill_price=Decimal(str(row['avg_fill_price'])) if row['avg_fill_price'] else None,
            total_filled=Decimal(str(row['total_filled']))
        )
```

---

### 2.7 Position Repository (`app/adapters/repositories/positions.py`)

```python
# app/adapters/repositories/positions.py
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from app.domain.models import Position
from app.ports.repositories import PositionRepository
from app.adapters.repositories.postgres_pool import DatabasePool
from app.logging_config import get_logger

logger = get_logger(__name__)


class PostgresPositionRepository(PositionRepository):
    """PostgreSQL implementation of position repository"""
    
    def __init__(self, pool: DatabasePool):
        self.pool = pool
    
    async def save(self, position: Position) -> None:
        """Save position (upsert)"""
        query = """
            INSERT INTO positions (
                strategy_id, symbol, quantity, avg_entry_price, current_price,
                unrealized_pnl, realized_pnl, opened_at, closed_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (strategy_id, symbol) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                avg_entry_price = EXCLUDED.avg_entry_price,
                current_price = EXCLUDED.current_price,
                unrealized_pnl = EXCLUDED.unrealized_pnl,
                realized_pnl = EXCLUDED.realized_pnl,
                closed_at = EXCLUDED.closed_at,
                updated_at = NOW()
        """
        
        try:
            async with self.pool.pool.acquire() as conn:
                await conn.execute(
                    query,
                    position.strategy_id,
                    position.symbol,
                    float(position.quantity),
                    float(position.avg_entry_price),
                    float(position.current_price),
                    float(position.unrealized_pnl),
                    float(position.realized_pnl),
                    position.opened_at,
                    position.closed_at,
                    position.updated_at
                )
        except Exception as e:
            logger.error(
                "Failed to save position",
                strategy_id=position.strategy_id,
                symbol=position.symbol,
                error=str(e)
            )
            raise
    
    async def get_by_id(self, strategy_id: str, symbol: str) -> Optional[Position]:
        """Get position by strategy and symbol"""
        query = """
            SELECT strategy_id, symbol, quantity, avg_entry_price, current_price,
                   unrealized_pnl, realized_pnl, opened_at, closed_at, updated_at
            FROM positions
            WHERE strategy_id = $1 AND symbol = $2
        """
        
        async with self.pool.pool.acquire() as conn:
            row = await conn.fetchrow(query, strategy_id, symbol)
            
            if row is None:
                return None
            
            return self._row_to_position(row)
    
    async def get_by_strategy(self, strategy_id: str) -> List[Position]:
        """Get all positions for a strategy"""
        query = """
            SELECT strategy_id, symbol, quantity, avg_entry_price, current_price,
                   unrealized_pnl, realized_pnl, opened_at, closed_at, updated_at
            FROM positions
            WHERE strategy_id = $1
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, strategy_id)
            return [self._row_to_position(row) for row in rows]
    
    async def get_by_symbol(self, symbol: str) -> List[Position]:
        """Get all positions for a symbol"""
        query = """
            SELECT strategy_id, symbol, quantity, avg_entry_price, current_price,
                   unrealized_pnl, realized_pnl, opened_at, closed_at, updated_at
            FROM positions
            WHERE symbol = $1
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, symbol)
            return [self._row_to_position(row) for row in rows]
    
    async def get_all_open(self) -> List[Position]:
        """Get all open positions"""
        query = """
            SELECT strategy_id, symbol, quantity, avg_entry_price, current_price,
                   unrealized_pnl, realized_pnl, opened_at, closed_at, updated_at
            FROM positions
            WHERE closed_at IS NULL AND quantity != 0
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [self._row_to_position(row) for row in rows]
    
    def _row_to_position(self, row) -> Position:
        """Convert database row to Position object"""
        return Position(
            strategy_id=row['strategy_id'],
            symbol=row['symbol'],
            quantity=Decimal(str(row['quantity'])),
            avg_entry_price=Decimal(str(row['avg_entry_price'])),
            current_price=Decimal(str(row['current_price'])),
            unrealized_pnl=Decimal(str(row['unrealized_pnl'])),
            realized_pnl=Decimal(str(row['realized_pnl'])),
            opened_at=row['opened_at'],
            closed_at=row['closed_at'],
            updated_at=row['updated_at']
        )
```

---

### 2.8 Trade Repository (`app/adapters/repositories/trades.py`)

```python
# app/adapters/repositories/trades.py
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from app.domain.models import Trade, OrderSide
from app.ports.repositories import TradeRepository
from app.adapters.repositories.postgres_pool import DatabasePool
from app.logging_config import get_logger

logger = get_logger(__name__)


class PostgresTradeRepository(TradeRepository):
    """PostgreSQL implementation of trade repository"""
    
    def __init__(self, pool: DatabasePool):
        self.pool = pool
    
    async def save(self, trade: Trade) -> None:
        """Save trade"""
        query = """
            INSERT INTO trades (
                trade_id, order_id, strategy_id, symbol, side, price, quantity,
                fee, fee_currency, pnl, executed_at, is_maker
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """
        
        try:
            async with self.pool.pool.acquire() as conn:
                await conn.execute(
                    query,
                    trade.trade_id,
                    trade.order_id,
                    trade.strategy_id,
                    trade.symbol,
                    trade.side.value,
                    float(trade.price),
                    float(trade.quantity),
                    float(trade.fee),
                    trade.fee_currency,
                    float(trade.pnl) if trade.pnl else None,
                    trade.executed_at,
                    trade.is_maker
                )
        except Exception as e:
            logger.error(
                "Failed to save trade",
                trade_id=trade.trade_id,
                error=str(e)
            )
            raise
    
    async def get_by_id(self, trade_id: str) -> Optional[Trade]:
        """Get trade by ID"""
        query = """
            SELECT trade_id, order_id, strategy_id, symbol, side, price, quantity,
                   fee, fee_currency, pnl, executed_at, is_maker
            FROM trades
            WHERE trade_id = $1
        """
        
        async with self.pool.pool.acquire() as conn:
            row = await conn.fetchrow(query, trade_id)
            
            if row is None:
                return None
            
            return self._row_to_trade(row)
    
    async def get_by_order(self, order_id: str) -> List[Trade]:
        """Get all trades for an order"""
        query = """
            SELECT trade_id, order_id, strategy_id, symbol, side, price, quantity,
                   fee, fee_currency, pnl, executed_at, is_maker
            FROM trades
            WHERE order_id = $1
            ORDER BY executed_at ASC
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, order_id)
            return [self._row_to_trade(row) for row in rows]
    
    async def get_by_strategy(self, strategy_id: str) -> List[Trade]:
        """Get all trades for a strategy"""
        query = """
            SELECT trade_id, order_id, strategy_id, symbol, side, price, quantity,
                   fee, fee_currency, pnl, executed_at, is_maker
            FROM trades
            WHERE strategy_id = $1
            ORDER BY executed_at DESC
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, strategy_id)
            return [self._row_to_trade(row) for row in rows]
    
    async def get_recent(self, limit: int = 100) -> List[Trade]:
        """Get recent trades"""
        query = """
            SELECT trade_id, order_id, strategy_id, symbol, side, price, quantity,
                   fee, fee_currency, pnl, executed_at, is_maker
            FROM trades
            ORDER BY executed_at DESC
            LIMIT $1
        """
        
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [self._row_to_trade(row) for row in rows]
    
    def _row_to_trade(self, row) -> Trade:
        """Convert database row to Trade object"""
        return Trade(
            trade_id=row['trade_id'],
            order_id=row['order_id'],
            strategy_id=row['strategy_id'],
            symbol=row['symbol'],
            side=OrderSide(row['side']),
            price=Decimal(str(row['price'])),
            quantity=Decimal(str(row['quantity'])),
            fee=Decimal(str(row['fee'])),
            fee_currency=row['fee_currency'],
            pnl=Decimal(str(row['pnl'])) if row['pnl'] else None,
            executed_at=row['executed_at'],
            is_maker=row['is_maker']
        )
```

---

### 2.9 Database Schema (`scripts/init_db.sql`)

```sql
-- scripts/init_db.sql
-- Trading Backend Database Schema
-- Run: psql -U trading -d trading -f scripts/init_db.sql

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- === Market Data ===

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
    trade_count INTEGER DEFAULT 0,
    quote_volume NUMERIC(20, 8),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint to prevent duplicates
CREATE UNIQUE INDEX idx_candles_unique 
ON candles(symbol, timeframe, timestamp);

-- Index for fast queries
CREATE INDEX idx_candles_symbol_time ON candles(symbol, timestamp DESC);
CREATE INDEX idx_candles_symbol_timeframe ON candles(symbol, timeframe);

-- === Orders ===

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
    exchange TEXT NOT NULL,
    client_order_id TEXT,
    avg_fill_price NUMERIC(20, 8),
    total_filled NUMERIC(20, 8) DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_strategy ON orders(strategy_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at DESC);
CREATE INDEX idx_orders_symbol ON orders(symbol);

-- === Trades ===

CREATE TABLE trades (
    trade_id TEXT PRIMARY KEY,
    order_id TEXT REFERENCES orders(order_id),
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    fee NUMERIC(20, 8) DEFAULT 0,
    fee_currency TEXT DEFAULT 'USDT',
    pnl NUMERIC(20, 8),
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    is_maker BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_trades_strategy ON trades(strategy_id, executed_at DESC);
CREATE INDEX idx_trades_order ON trades(order_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);

-- === Positions ===

CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    avg_entry_price NUMERIC(20, 8),
    current_price NUMERIC(20, 8),
    unrealized_pnl NUMERIC(20, 8),
    realized_pnl NUMERIC(20, 8) DEFAULT 0,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy_id, symbol)
);

CREATE INDEX idx_positions_strategy ON positions(strategy_id);
CREATE INDEX idx_positions_symbol ON positions(symbol);

-- === Strategies ===

CREATE TABLE strategies (
    strategy_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    config JSONB,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_strategies_active ON strategies(is_active);

-- === Performance Metrics ===

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

-- === Audit Log ===

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

-- === Comments ===

COMMENT ON TABLE candles IS 'OHLCV candle data (1-second intervals supported)';
COMMENT ON TABLE orders IS 'Trading orders with lifecycle tracking';
COMMENT ON TABLE trades IS 'Executed trades (fills)';
COMMENT ON TABLE positions IS 'Current trading positions';
COMMENT ON TABLE strategies IS 'Strategy configurations';
COMMENT ON TABLE strategy_performance IS 'Daily strategy performance metrics';
COMMENT ON TABLE audit_log IS 'Audit trail for all changes';
```

---

## ✅ Acceptance Criteria

Complete this step when all criteria are met:

- [ ] **Domain models defined** - All entities (Candle, Order, Trade, Position) implemented
- [ ] **Repository interfaces defined** - All ports in `app/ports/repositories.py`
- [ ] **PostgreSQL repositories implemented** - All adapters working
- [ ] **Connection pooling works** - DatabasePool singleton functional
- [ ] **Batch insert performance** - 1000 candles in <100ms
- [ ] **Schema created** - All tables, indexes, constraints in place
- [ ] **All repository methods tested** - Unit tests pass
- [ ] **Integration tests pass** - Tests with real PostgreSQL pass
- [ ] **Type hints complete** - MyPy passes without errors
- [ ] **Code quality** - Black, flake8 pass

---

## 🧪 Testing Requirements

### Model Tests (`tests/domain/test_models.py`)

```python
# tests/domain/test_models.py
import pytest
from decimal import Decimal
from datetime import datetime
from app.domain.models import Candle, Order, OrderSide, OrderType, OrderStatus, Position


def test_candle_creation():
    """Test candle creation with valid data"""
    candle = Candle(
        symbol="BTCUSDT",
        timeframe="1s",
        timestamp=datetime.utcnow(),
        open=Decimal("50000"),
        high=Decimal("50100"),
        low=Decimal("49900"),
        close=Decimal("50050"),
        volume=Decimal("100.5"),
        source="binance"
    )
    
    assert candle.symbol == "BTCUSDT"
    assert candle.timeframe == "1s"
    assert candle.open == Decimal("50000")


def test_candle_validation():
    """Test candle validation"""
    # High < Low should fail
    with pytest.raises(ValueError):
        Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("49900"),  # Invalid: high < low
            low=Decimal("50100"),
            close=Decimal("50050"),
            volume=Decimal("100.5"),
            source="binance"
        )


def test_order_fill():
    """Test order fill calculation"""
    order = Order(
        strategy_id="test",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("1.0"),
        exchange="binance"
    )
    
    # Partial fill
    order.fill(Decimal("50000"), Decimal("0.5"), datetime.utcnow())
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.total_filled == Decimal("0.5")
    assert order.avg_fill_price == Decimal("50000")
    
    # Complete fill
    order.fill(Decimal("50100"), Decimal("0.5"), datetime.utcnow())
    assert order.status == OrderStatus.FILLED
    assert order.total_filled == Decimal("1.0")
    assert order.avg_fill_price == Decimal("50050")  # Weighted average


def test_position_pnl():
    """Test position PnL calculation"""
    position = Position(
        strategy_id="test",
        symbol="BTCUSDT",
        quantity=Decimal("1.0"),
        avg_entry_price=Decimal("50000")
    )
    
    # Update with current price
    position.update_pnl(Decimal("51000"))
    assert position.unrealized_pnl == Decimal("1000")
    
    # Close position
    realized = position.close(Decimal("51000"), datetime.utcnow())
    assert realized == Decimal("1000")
    assert position.is_open is False
```

### Repository Tests

Create integration tests for each repository that:
1. Connect to test PostgreSQL database
2. Insert test data
3. Verify CRUD operations
4. Clean up after tests

---

## 🔧 Troubleshooting

### Issue: "asyncpg.exceptions.CannotConnectNowError"

**Solution:** Ensure PostgreSQL is running and connection URL is correct:

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test connection
psql -h localhost -U trading -d trading
```

### Issue: "relation 'candles' does not exist"

**Solution:** Run schema initialization:

```bash
psql -U trading -d trading -f scripts/init_db.sql
```

### Issue: Batch insert slow

**Solution:** Ensure you're using `copy_records_to_table` for large batches (>100 candles).

---

## 📚 References

- `Step1.md` - Project foundation
- `project_overview_for_all_agents.md` - Architecture overview
- asyncpg: https://magicstack.github.io/asyncpg/current/
- PostgreSQL: https://www.postgresql.org/docs/

---

## 🎯 Next Step

After completing Step 2, proceed to **Step 3: Binance Data Ingest - WebSocket & REST** (`Step3.md`).

---

**Ready to implement? Start coding!** 🐾
