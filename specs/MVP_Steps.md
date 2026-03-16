# MVP Implementation Steps

**Project:** Trading Backend  
**Version:** 1.0  
**Date:** 2026-03-15  
**Author:** Claw (Senior Software Architect)

---

## Overview

This document defines **6 independent implementation steps** for the trading backend MVP. Each step is:
- **Self-contained** - Can be implemented, tested, and validated separately
- **Ordered** - Steps build on previous work
- **Testable** - Clear acceptance criteria
- **Agent-ready** - Detailed enough for a Coder-Agent to implement

**Development Mode:** Local development without Docker (faster iterations). Docker Compose used only for final deployment after each successful step.

**Target Latency:** <40ms end-to-end  
**Minimum Interval:** 1 second (scalping requirement)

---

## Step 0: Critical Safety Infrastructure

**Objective:** Implement critical safety controls that MUST be in place before any live trading.

### Deliverables
```
app/
├── services/
│   ├── market_data_validator.py    # Data quality checks
│   ├── order_validator.py          # Order sanity checks
│   ├── risk_manager.py             # Multi-layer risk management
│   ├── position_reconciler.py      # Exchange reconciliation
│   └── kill_switch.py              # Emergency stops
├── modes/
│   ├── paper_trading.py            # Simulation mode
│   └── live_trading.py             # Real trading mode
└── adapters/
    └── validators/
        ├── price_bounds_validator.py
        ├── timestamp_validator.py
        └── volume_validator.py

tests/
├── safety/
│   ├── test_market_data_validator.py
│   ├── test_order_validator.py
│   ├── test_risk_manager.py
│   ├── test_kill_switch.py
│   └── test_paper_trading.py
└── failure_modes/
    ├── test_exchange_failure.py
    ├── test_data_corruption.py
    └── test_cascade_failure.py

runbooks/
├── daily/
│   ├── RUNBOOK-001-daily-startup.md
│   └── RUNBOOK-002-daily-monitoring.md
├── incident/
│   ├── RUNBOOK-100-emergency-stop.md
│   └── RUNBOOK-101-exchange-outage.md
└── recovery/
    └── RUNBOOK-300-recover-from-backup.md
```

### Specifications

#### 0.1 Market Data Validator
- Price bounds checking (reject >5% deviation from fair value)
- Timestamp validation (reject candles older than 10 seconds)
- Volume sanity checks (reject zero or anomalous volume)
- OHLC consistency validation
- Cross-venue validation (compare Binance vs. Coinbase)

#### 0.2 Order Validator
- Quantity limits (max 0.01 BTC per order)
- Value limits (max $500 per order)
- Rate limiting (max 10 orders/minute per strategy)
- Price collars (limit orders within 1% of market)
- Fat finger detection
- Signal age check (reject signals older than 5 seconds)

#### 0.3 Risk Manager (Multi-Layer)
**Layer 1: Pre-Trade Limits**
- Max order quantity: 0.01 BTC
- Max order value: $500
- Max position value per strategy: $5000

**Layer 2: Intra-Day Risk**
- Max daily loss: $100
- Max consecutive losses: 5
- Max drawdown: 5%
- Max open positions: 10

**Layer 3: Portfolio Risk**
- Max total exposure: $10000
- Max concentration: 30% in one symbol
- Max leverage: 2x

**Layer 4: Circuit Breakers**
- Volatility threshold: 5% move in 5 minutes
- Spread threshold: 1% bid-ask spread
- Loss rate threshold: 10%

**Layer 5: Kill Switches**
- Global emergency stop
- Exchange-specific stop
- Strategy-specific stop

#### 0.4 Paper Trading Mode
- Simulated order execution
- Tracks hypothetical PnL
- Same order flow as live trading
- Minimum 2 weeks paper trading before live

#### 0.5 Kill Switch
- API endpoint activation
- Automatic activation on risk triggers
- Immediate position closure
- Audit trail of activation

### Acceptance Criteria
- [ ] Market data validator rejects bad candles (test with malformed data)
- [ ] Order validator rejects fat finger orders
- [ ] Risk manager enforces all 5 layers
- [ ] Kill switch stops trading in <100ms
- [ ] Paper trading mode works identically to live
- [ ] All validators have correlation ID tracking
- [ ] All validators have latency tracking
- [ ] All runbooks documented and tested
- [ ] Performance tests pass (latency <40ms end-to-end)

### Testing Requirements
- **Unit tests:** 100% coverage on all validators
- **Integration tests:** Full safety chain tested
- **Failure mode tests:** Exchange failure, data corruption, network issues
- **Performance tests:** Latency, throughput, stress, endurance
- **Runbook tests:** All runbooks executed and validated

### Dependencies
- None (implement before Step 1)

### Estimated Effort
- 16-24 hours

### ⚠️ Critical Warning

**DO NOT SKIP STEP 0.**

Trading without these controls is gambling. The specifications in Steps 1-6 build a functional system, but Step 0 builds a SAFE system.

**Before proceeding to Step 1:**
- [ ] All Step 0 deliverables implemented
- [ ] All tests passing
- [ ] All runbooks documented
- [ ] Paper trading successful for 2 weeks
- [ ] Senior architect sign-off

---

## Step 1: Project Foundation & Infrastructure Setup

**Objective:** Create project structure, configuration management, and base dependencies.

### Deliverables
```
trading-backend/
├── app/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   └── logging_config.py      # Structured logging setup
├── tests/
│   ├── __init__.py
│   └── conftest.py            # Pytest fixtures
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml             # Project metadata, black, mypy config
├── .env.example
├── .gitignore
└── README.md
```

### Specifications

#### 1.1 Configuration Management (`app/config.py`)
- Use `pydantic-settings` for type-safe configuration
- Support environment variables and `.env` file
- Required config fields:
  ```python
  class Settings(BaseSettings):
      # Database
      database_url: str = "postgresql://trading:secret@localhost:5432/trading"
      database_pool_size: int = 10
      database_pool_min_size: int = 5
      
      # Redis
      redis_url: str = "redis://localhost:6379/0"
      
      # Application
      environment: str = "development"  # development | staging | production
      log_level: str = "INFO"
      
      # Binance
      binance_api_key: Optional[str] = None
      binance_secret_key: Optional[str] = None
      
      # Trading
      max_strategies: int = 10
      default_timeframe: str = "1s"  # 1-second intervals for scalping
      
      class Config:
          env_file = ".env"
  ```

#### 1.2 Logging Setup (`app/logging_config.py`)
- Use `structlog` for structured JSON logging
- Include: timestamp, level, logger, event, context (strategy_id, symbol, etc.)
- Different formats for development (console) vs. production (JSON)

#### 1.3 Dependencies (`requirements.txt`)
```txt
# Core
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0

# Async
asyncio==3.4.3

# Database
asyncpg==0.29.0

# Redis
redis==5.0.1
aioredis==2.0.1

# Logging
structlog==23.2.0

# Testing (dev)
pytest==7.4.3
pytest-asyncio==0.23.2
pytest-cov==4.1.0
```

#### 1.4 Development Setup
- Provide setup script: `scripts/setup.sh`
- Instructions for:
  - Python 3.11+ installation
  - Virtual environment creation
  - Installing PostgreSQL locally
  - Installing Redis locally
  - Running tests

### Acceptance Criteria
- [ ] Can import `app.config` and get settings
- [ ] Configuration loads from `.env` file
- [ ] Configuration loads from environment variables
- [ ] Logging outputs structured logs
- [ ] All tests pass: `pytest tests/ -v`
- [ ] No Docker required for development

### Testing Requirements
- Unit tests for config loading
- Unit tests for different environments (dev, staging, prod)
- Test logging output format

### Dependencies
- None (foundational step)

### Estimated Effort
- 2-4 hours

---

## Step 2: Database Layer - Schema & Repositories

**Objective:** Implement PostgreSQL schema and repository pattern for data persistence.

### Deliverables
```
app/
├── domain/
│   └── models.py              # Domain entities (Candle, Order, Trade, Position, etc.)
├── ports/
│   └── repositories.py        # Repository interfaces
└── adapters/
    └── repositories/
        ├── __init__.py
        ├── postgres_pool.py   # Connection pool management
        ├── candles.py         # Candle repository
        ├── orders.py          # Order repository
        ├── trades.py          # Trade repository
        └── positions.py       # Position repository

tests/
├── domain/
│   └── test_models.py
└── adapters/
    └── repositories/
        ├── test_candles.py
        ├── test_orders.py
        └── test_positions.py

scripts/
└── init_db.sql                # Database initialization script
```

### Specifications

#### 2.1 Domain Models (`app/domain/models.py`)
Define dataclasses for:
```python
@dataclass
class Candle:
    """1-second OHLCV candle for scalping"""
    symbol: str
    timeframe: str  # "1s", "5s", "10s", "1m", etc.
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str
    trade_count: int = 0  # Number of trades in this candle
    quote_volume: Decimal = Decimal("0")  # Quote asset volume

@dataclass
class Order:
    order_id: str
    strategy_id: str
    symbol: str
    side: str  # "BUY" | "SELL"
    type: str  # "MARKET" | "LIMIT" | "STOP_LOSS" | "TAKE_PROFIT"
    price: Optional[Decimal]
    quantity: Decimal
    status: str  # "PENDING" | "SUBMITTED" | "PARTIALLY_FILLED" | "FILLED" | "CANCELLED" | "REJECTED"
    created_at: datetime
    filled_at: Optional[datetime]
    exchange: str
    client_order_id: Optional[str]  # Exchange-specific order ID
    avg_fill_price: Optional[Decimal]
    total_filled: Decimal = Decimal("0")

@dataclass
class Trade:
    trade_id: str
    order_id: str
    strategy_id: str
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    fee_currency: str
    pnl: Optional[Decimal]
    executed_at: datetime
    is_maker: bool = False  # Maker vs taker

@dataclass
class Position:
    strategy_id: str
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal = Decimal("0")
    updated_at: datetime
    opened_at: datetime
    closed_at: Optional[datetime] = None
```

#### 2.2 Repository Interfaces (`app/ports/repositories.py`)
```python
class CandleRepository(ABC):
    @abstractmethod
    async def save(self, candle: Candle) -> None:
        pass
    
    @abstractmethod
    async def save_batch(self, candles: List[Candle]) -> None:
        pass
    
    @abstractmethod
    async def get_range(
        self, 
        symbol: str, 
        timeframe: str, 
        start: datetime, 
        end: datetime
    ) -> List[Candle]:
        pass
    
    @abstractmethod
    async def get_latest(self, symbol: str, timeframe: str) -> Optional[Candle]:
        pass
    
    @abstractmethod
    async def get_last_n(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        pass

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
    async def get_pending(self) -> List[Order]:
        pass
    
    @abstractmethod
    async def update_status(self, order_id: str, status: str) -> None:
        pass

# Similar for TradeRepository, PositionRepository
```

#### 2.3 PostgreSQL Implementation
- Use `asyncpg` for async database access
- Connection pooling (min 5, max 10 connections)
- Implement all repository interfaces
- Batch insert support for candles (performance critical)

#### 2.4 Database Schema (`scripts/init_db.sql`)
**NOTE:** Schema will be finalized after Step 3 (Binance data exploration). For now, create placeholder tables with basic structure.

Key considerations:
- 1-second candles = high write volume → optimize for inserts
- Partitioning strategy for `candles` table (by date or symbol)
- Indexes for common queries (symbol + timestamp)
- Foreign keys where appropriate
- Audit trail for orders/trades

### Acceptance Criteria
- [ ] All domain models defined and tested
- [ ] All repository interfaces defined
- [ ] PostgreSQL repositories implemented
- [ ] Connection pooling works correctly
- [ ] Batch insert for candles: 1000 candles in <100ms
- [ ] All repository methods have unit tests
- [ ] Integration tests with real PostgreSQL pass
- [ ] Schema migration script works

### Testing Requirements
- Unit tests for all models (validation, methods)
- Unit tests for repositories (with mocked DB)
- Integration tests with real PostgreSQL (use test database)
- Performance test: batch insert 1000 candles

### Dependencies
- Step 1 (Project Foundation)

### Estimated Effort
- 6-8 hours

---

## Step 3: Binance Data Ingest - WebSocket & REST

**Objective:** Implement Binance connectivity for real-time market data (1-second candles) and historical data fetch.

### Deliverables
```
app/
├── domain/
│   └── models.py              # Update with Binance-specific fields
├── adapters/
│   └── exchanges/
│       ├── __init__.py
│       ├── binance_market_data.py   # WebSocket stream
│       ├── binance_rest.py          # REST API client
│       └── binance_schema.py        # Binance-specific data structures
└── services/
    └── data_ingest.py         # Data ingestion coordinator

tests/
└── adapters/
    └── exchanges/
        ├── test_binance_websocket.py
        └── test_binance_rest.py

scripts/
├── fetch_binance_schema.py    # Explore Binance API, output schema
└── explore_binance_data.py    # Fetch sample data, analyze structure
```

### Specifications

#### 3.1 Binance WebSocket Market Data (`app/adapters/exchanges/binance_market_data.py`)
- Connect to Binance WebSocket: `wss://stream.binance.com:9443/ws`
- Subscribe to kline (candlestick) streams
- **Support 1-second intervals** (Binance supports: 1s, 3s, 5s, 10s, 15s, 30s, 1m, etc.)
- Handle reconnection with exponential backoff
- Parse WebSocket messages to domain `Candle` objects
- Publish to Redis pub/sub for strategy consumption

**WebSocket Stream Format:**
```
<symbol>@kline_<interval>
Example: btcusdt@kline_1s
```

**Message Structure (to be confirmed with actual Binance data):**
```json
{
  "e": "kline",
  "E": 123456789,
  "s": "BNBBTC",
  "k": {
    "t": 123400000,
    "T": 123460000,
    "s": "BNBBTC",
    "i": "1m",
    "f": 100,
    "L": 200,
    "o": "0.0010",
    "c": "0.0020",
    "h": "0.0025",
    "l": "0.0010",
    "v": "1000",
    "n": 100,
    "x": false,
    "q": "1.00",
    "V": "500",
    "Q": "0.50"
  }
}
```

#### 3.2 Binance REST Client (`app/adapters/exchanges/binance_rest.py`)
- Fetch historical candles: `/api/v3/klines`
- Fetch current price: `/api/v3/ticker/price`
- Fetch order book: `/api/v3/depth`
- Rate limiting compliance (Binance: 1200 requests/minute per IP)
- Retry logic with exponential backoff

#### 3.3 Data Exploration Scripts
**`scripts/fetch_binance_schema.py`:**
- Connect to Binance API
- Fetch candle data for multiple symbols
- Output complete schema with all fields
- Save to `docs/binance_api_schema.md`

**`scripts/explore_binance_data.py`:**
- Fetch 1-second candles for BTCUSDT, ETHUSDT
- Analyze: field types, nullability, ranges
- Output findings to `docs/binance_data_analysis.md`
- **Use this to finalize database schema**

#### 3.4 Data Ingest Service (`app/services/data_ingest.py`)
- Coordinate WebSocket subscriptions
- Manage multiple symbol subscriptions
- Cache latest ticks in Redis
- Persist candles to PostgreSQL (batch writes)
- Publish to Redis pub/sub channels: `candles:{symbol}:{timeframe}`

### Acceptance Criteria
- [ ] WebSocket connection stable (auto-reconnect)
- [ ] Can subscribe to 1-second candle streams
- [ ] Real-time candles parsed correctly
- [ ] Historical candles fetched via REST
- [ ] Redis pub/sub working (candles published)
- [ ] PostgreSQL persistence working (batch inserts)
- [ ] Rate limiting respected
- [ ] Binance schema documented
- [ ] Database schema updated based on findings

### Testing Requirements
- Unit tests for message parsing
- Integration tests with Binance testnet (if available)
- Test reconnection logic
- Test rate limiting
- Performance test: handle 10 symbols × 1-second candles = 10 messages/second

### Dependencies
- Step 1 (Project Foundation)
- Step 2 (Database Layer)

### Estimated Effort
- 8-12 hours

### Output
- **Updated database schema** based on actual Binance data structure
- Working real-time data ingestion for 1-second candles

---

## Step 4: Redis Cache Layer & Pub/Sub

**Objective:** Implement Redis caching for low-latency data access and real-time pub/sub communication.

### Deliverables
```
app/
├── ports/
│   └── cache.py               # Cache interface
├── adapters/
│   └── cache/
│       ├── __init__.py
│       └── redis_cache.py     # Redis implementation
└── services/
    └── cache_manager.py       # Cache coordination

tests/
└── adapters/
    └── cache/
        └── test_redis_cache.py
```

### Specifications

#### 4.1 Cache Interface (`app/ports/cache.py`)
```python
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
    async def set_latest_tick(self, tick: Tick, ttl: int = 60) -> None:
        pass
    
    @abstractmethod
    async def get_position(self, strategy_id: str, symbol: str) -> Optional[Position]:
        pass
    
    @abstractmethod
    async def set_position(self, position: Position) -> None:
        pass
    
    @abstractmethod
    async def get_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        pass
    
    @abstractmethod
    async def set_candle(self, candle: Candle, ttl: int = 300) -> None:
        pass
```

#### 4.2 Redis Implementation (`app/adapters/cache/redis_cache.py`)
- Use `aioredis` for async Redis access
- JSON serialization with `Decimal` support
- TTL management for volatile data
- Pub/sub for real-time data distribution
- Connection pooling

**Cache Strategy:**
| Key Pattern | Data Type | TTL | Description |
|-------------|-----------|-----|-------------|
| `tick:{symbol}` | Tick | 60s | Latest price tick |
| `candle:{symbol}:{timeframe}` | Candle | 300s | Latest candle |
| `position:{strategy_id}:{symbol}` | Position | None | Current position (also in DB) |
| `signal:{strategy_id}:{symbol}` | Signal | 300s | Latest trading signal |
| `order:{order_id}` | Order | 86400s (24h) | Recent order state |

#### 4.3 Cache Manager Service (`app/services/cache_manager.py`)
- Coordinate cache operations
- Cache invalidation strategies
- Monitor cache hit/miss rates
- Health checks

### Acceptance Criteria
- [ ] All cache operations implemented
- [ ] Pub/sub working (publish + subscribe)
- [ ] TTL working correctly
- [ ] JSON serialization handles Decimal, datetime
- [ ] Connection pooling configured
- [ ] Performance: <5ms for get/set operations
- [ ] All methods have unit tests
- [ ] Integration tests with real Redis pass

### Testing Requirements
- Unit tests for serialization
- Unit tests for TTL behavior
- Integration tests with real Redis
- Performance tests (latency <5ms)
- Test pub/sub message delivery

### Dependencies
- Step 1 (Project Foundation)
- Step 2 (Database Layer) - for domain models

### Estimated Effort
- 4-6 hours

---

## Step 5: Strategy Engine & Signal Generation

**Objective:** Implement strategy execution engine with signal generation and Redis pub/sub integration.

### Deliverables
```
app/
├── domain/
│   ├── models.py              # Add Signal, StrategyState
│   └── services.py            # Strategy domain logic
├── ports/
│   └── strategies.py          # Strategy interface
├── adapters/
│   └── strategies/
│       ├── __init__.py
│       └── base_strategy.py   # Base strategy implementation
├── services/
│   ├── strategy_runner.py     # Strategy execution engine
│   └── signal_processor.py    # Signal handling
└── strategies/
    ├── __init__.py
    ├── base.py                # User-facing base class
    └── example_sma.py         # Example: Simple Moving Average

tests/
├── services/
│   ├── test_strategy_runner.py
│   └── test_signal_processor.py
└── strategies/
    └── test_example_sma.py
```

### Specifications

#### 5.1 Domain Models Update
```python
@dataclass
class Signal:
    """Trading signal from strategy"""
    signal_id: str
    strategy_id: str
    symbol: str
    action: str  # "BUY" | "SELL" | "HOLD" | "CLOSE"
    quantity: Decimal
    price: Optional[Decimal]  # None for market orders
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StrategyState:
    """Runtime state for a strategy"""
    strategy_id: str
    is_running: bool
    last_candle_time: Optional[datetime]
    last_signal_time: Optional[datetime]
    total_signals: int
    errors: List[str]
    started_at: datetime
```

#### 5.2 Strategy Interface (`app/ports/strategies.py`)
```python
class StrategyPort(ABC):
    @abstractmethod
    async def on_candle(self, candle: Candle) -> Optional[Signal]:
        """Called when new candle arrives"""
        pass
    
    @abstractmethod
    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        """Called on real-time tick (for scalping)"""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Called when strategy is activated"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Called when strategy is deactivated"""
        pass
```

#### 5.3 Base Strategy (`strategies/base.py`)
User-facing base class for creating strategies:
```python
class BaseStrategy(ABC):
    """
    Base class for all trading strategies.
    Users inherit from this and implement on_candle() and/or on_tick().
    """
    
    def __init__(self, config: dict):
        self.strategy_id = config.get("strategy_id", str(uuid4()))
        self.symbol = config.get("symbol", "BTCUSDT")
        self.timeframe = config.get("timeframe", "1s")
        self.config = config
        
    @abstractmethod
    async def on_candle(self, candle: Candle) -> Optional[Signal]:
        pass
    
    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        """Optional: override for tick-based strategies"""
        return None
```

#### 5.4 Strategy Runner (`app/services/strategy_runner.py`)
- Manage multiple strategy instances
- Subscribe to candle streams from Redis
- Route candles to appropriate strategies
- Execute strategies concurrently (asyncio)
- Publish signals to Redis pub/sub
- Handle strategy errors (isolate failures)
- Track strategy state and metrics

#### 5.5 Signal Processor (`app/services/signal_processor.py`)
- Subscribe to signal pub/sub channel
- Validate signals (quantity, price, etc.)
- Route signals to Order Manager (Step 6)
- Track signal history

#### 5.6 Example Strategy (`strategies/example_sma.py`)
Simple Moving Average crossover strategy:
- Fast SMA: 10 periods
- Slow SMA: 30 periods
- BUY when fast crosses above slow
- SELL when fast crosses below slow

### Acceptance Criteria
- [ ] Strategy interface defined
- [ ] Base strategy class implemented
- [ ] Strategy runner manages multiple strategies
- [ ] Candles routed to strategies correctly
- [ ] Signals published to Redis
- [ ] Example SMA strategy works
- [ ] Strategies run concurrently without blocking
- [ ] Error isolation (one strategy failure doesn't crash others)
- [ ] All components have unit tests

### Testing Requirements
- Unit tests for strategy runner
- Unit tests for signal processor
- Integration test with example strategy
- Test concurrent strategy execution
- Test error handling and isolation

### Dependencies
- Step 1 (Project Foundation)
- Step 2 (Database Layer)
- Step 3 (Binance Data Ingest)
- Step 4 (Redis Cache Layer)

### Estimated Effort
- 8-12 hours

---

## Step 6: Order Management & Execution

**Objective:** Implement order management system (OMS) with order lifecycle, execution, and risk controls.

### Deliverables
```
app/
├── domain/
│   └── models.py              # Add OrderBook, RiskLimits
├── adapters/
│   └── exchanges/
│       └── binance_trading.py # Binance order execution
├── services/
│   ├── order_manager.py       # Order lifecycle management
│   ├── risk_manager.py        # Risk controls
│   └── position_tracker.py    # Real-time position tracking
└── api/
    └── routes.py              # Optional: REST API for manual orders

tests/
├── services/
│   ├── test_order_manager.py
│   ├── test_risk_manager.py
│   └── test_position_tracker.py
└── adapters/
    └── exchanges/
        └── test_binance_trading.py
```

### Specifications

#### 6.1 Order Manager (`app/services/order_manager.py`)
- Subscribe to signal pub/sub channel
- Create orders from signals
- Submit orders to exchange (via adapter)
- Track order lifecycle (PENDING → SUBMITTED → FILLED/CANCELLED)
- Handle partial fills
- Update PostgreSQL and Redis
- Publish order events to Redis pub/sub

**Order Lifecycle:**
```
PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                     ↓
              CANCELLED / REJECTED
```

#### 6.2 Binance Trading Adapter (`app/adapters/exchanges/binance_trading.py`)
- Place orders (market, limit, stop-loss, take-profit)
- Cancel orders
- Query order status
- Fetch account balance
- Handle Binance-specific order responses
- Rate limiting compliance

#### 6.3 Risk Manager (`app/services/risk_manager.py`)
**Pre-trade checks:**
- Position size limits (max quantity per trade)
- Daily loss limits (stop trading if exceeded)
- Order rate limiting (max orders per minute)
- Symbol restrictions (allowed symbols per strategy)
- Capital allocation (max capital per strategy)

**Circuit Breakers:**
- Stop all trading if loss > X% in Y minutes
- Pause strategy after N consecutive losses
- Emergency kill switch

```python
class RiskLimits:
    max_order_quantity: Decimal
    max_daily_loss: Decimal
    max_orders_per_minute: int
    max_position_value: Decimal
    allowed_symbols: List[str]
```

#### 6.4 Position Tracker (`app/services/position_tracker.py`)
- Track real-time positions per strategy
- Calculate unrealized PnL (using latest price from Redis)
- Calculate realized PnL (on trade execution)
- Update PostgreSQL and Redis
- Publish position updates to Redis pub/sub

#### 6.5 Database Schema Update
Based on Step 3 findings, finalize:
- `candles` table (all Binance fields)
- `orders` table (all order states)
- `trades` table (execution details)
- `positions` table (current holdings)
- `strategy_performance` table (daily metrics)

### Acceptance Criteria
- [ ] Order manager handles full lifecycle
- [ ] Orders submitted to Binance correctly
- [ ] Order status updates tracked
- [ ] Risk checks performed before every order
- [ ] Circuit breakers working
- [ ] Position tracking accurate (real-time PnL)
- [ ] PostgreSQL persistence for all orders/trades
- [ ] Redis cache for active orders/positions
- [ ] All components have unit tests
- [ ] Integration tests with Binance testnet

### Testing Requirements
- Unit tests for order manager (state machine)
- Unit tests for risk manager (all limits)
- Unit tests for position tracker (PnL calculations)
- Integration tests with Binance testnet (paper trading)
- Test order lifecycle (submit → fill → verify)
- Test risk limit enforcement

### Dependencies
- Step 1 (Project Foundation)
- Step 2 (Database Layer)
- Step 3 (Binance Data Ingest)
- Step 4 (Redis Cache Layer)
- Step 5 (Strategy Engine)

### Estimated Effort
- 12-16 hours

---

## Summary

| Step | Title | Effort | Dependencies |
|------|-------|--------|--------------|
| 0 | Critical Safety Infrastructure | 16-24h | None (REQUIRED FIRST) |
| 1 | Project Foundation & Infrastructure | 2-4h | Step 0 |
| 2 | Database Layer - Schema & Repositories | 6-8h | Step 0, 1 |
| 3 | Binance Data Ingest - WebSocket & REST | 8-12h | Step 0, 1, 2 |
| 4 | Redis Cache Layer & Pub/Sub | 4-6h | Step 0, 1, 2 |
| 5 | Strategy Engine & Signal Generation | 8-12h | Step 0-4 |
| 6 | Order Management & Execution | 12-16h | Step 0-5 |

**Total Estimated Effort:** 56-82 hours

**Critical Path:** Step 0 → Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6

---

## Development Workflow

For each step:

1. **Implement** - Coder-Agent writes code
2. **Test Locally** - Run without Docker:
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Run tests
   pytest tests/ -v
   
   # Run manual tests (if applicable)
   python scripts/test_step_X.py
   ```
3. **Validate** - Check acceptance criteria
4. **Docker Build** - After success, build Docker image:
   ```bash
   docker-compose build
   docker-compose up -d
   ```
5. **Commit** - Push to version control
6. **Proceed** - Move to next step

---

## Notes for Coder-Agent

- **Work sequentially** - Don't skip steps
- **Test thoroughly** - Each step must pass all tests before proceeding
- **Document findings** - Especially Step 3 (Binance schema)
- **Ask for clarification** - If specs are unclear
- **Optimize for iteration speed** - Local dev first, Docker second
- **1-second intervals** - Critical for scalping, ensure throughout

---

**Ready to begin?** Start with Step 1. 🐾
