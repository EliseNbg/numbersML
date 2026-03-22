# Coding Standards & Requirements for LLM Agents

## Overview

**This document specifies mandatory coding standards for all LLM agents implementing this system.**

**Principle**: Quality over Quantity - Better to have less, working, well-documented code than more, buggy, undocumented code.

---

## 1. Core Principles

### 1.1 KISS (Keep It Simple, Stupid)

```python
# ❌ BAD: Over-engineered, clever but unreadable
def process_ticks(ticks: List[Tick]) -> Dict[str, Any]:
    return reduce(
        lambda acc, t: {**acc, t.symbol: acc.get(t.symbol, []) + [t]},
        ticks,
        {}
    )

# ✅ GOOD: Simple, clear, readable
def process_ticks(ticks: List[Tick]) -> Dict[str, List[Tick]]:
    """Group ticks by symbol."""
    ticks_by_symbol: Dict[str, List[Tick]] = {}
    
    for tick in ticks:
        if tick.symbol not in ticks_by_symbol:
            ticks_by_symbol[tick.symbol] = []
        ticks_by_symbol[tick.symbol].append(tick)
    
    return ticks_by_symbol
```

**Requirements**:
- ✅ Simple is better than complex
- ✅ Readable is better than clever
- ✅ Explicit is better than implicit
- ✅ Flat is better than nested (max 2-3 levels)
- ✅ Functions should do ONE thing (Single Responsibility)
- ✅ Functions should be short (< 50 lines ideally)

---

### 1.2 DDD (Domain-Driven Design)

```
┌─────────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER (Pure)                       │
│  - Entities (Symbol, Trade, Indicator)                       │
│  - Value Objects (SymbolId, TradeId)                         │
│  - Domain Events (IndicatorChanged, SymbolActivated)         │
│  - Domain Services (validation, business logic)              │
│  - NO external dependencies (no DB, no HTTP, no framework)   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                 APPLICATION LAYER (Orchestration)            │
│  - Use Cases / Commands / Queries                            │
│  - Application Services                                      │
│  - DTOs (Data Transfer Objects)                              │
│  - Depends on Domain Layer                                   │
│  - NO infrastructure dependencies                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              INFRASTRUCTURE LAYER (Implementation)           │
│  - Database repositories (PostgreSQL)                        │
│  - External services (Binance, Redis)                        │
│  - Framework code (FastAPI, Click)                           │
│  - Depends on Application & Domain Layers                    │
└─────────────────────────────────────────────────────────────┘
```

**Requirements**:
- ✅ **Strict layer separation**: Domain → Application → Infrastructure
- ✅ **Dependency rule**: Dependencies point inward only
- ✅ **Domain entities**: Pure Python, no framework annotations
- ✅ **Application layer**: Orchestrates, doesn't implement business logic
- ✅ **Infrastructure layer**: Implements interfaces from inner layers

---

### 1.3 Hexagonal Architecture (Ports & Adapters)

```python
# PORT (Domain Layer) - Interface definition
class SymbolRepository(ABC):
    """Port: Defines what we need from a symbol repository."""
    
    @abstractmethod
    def get_by_id(self, symbol_id: int) -> Optional[Symbol]:
        """Get symbol by ID."""
        pass
    
    @abstractmethod
    def get_active_symbols(self) -> List[Symbol]:
        """Get all active symbols."""
        pass
    
    @abstractmethod
    def save(self, symbol: Symbol) -> None:
        """Save symbol."""
        pass


# ADAPTER (Infrastructure Layer) - Implementation
class PostgreSQLSymbolRepository(SymbolRepository):
    """Adapter: PostgreSQL implementation of SymbolRepository."""
    
    def __init__(self, connection: asyncpg.Connection):
        """Initialize with database connection."""
        self.conn = connection
    
    async def get_by_id(self, symbol_id: int) -> Optional[Symbol]:
        """Get symbol by ID from PostgreSQL."""
        row = await self.conn.fetchrow(
            "SELECT * FROM symbols WHERE id = $1",
            symbol_id
        )
        return self._map_to_entity(row) if row else None
    
    # ... other methods
```

**Requirements**:
- ✅ **Ports first**: Define interfaces in domain layer
- ✅ **Adapters second**: Implement in infrastructure layer
- ✅ **Dependency injection**: Pass ports to application layer
- ✅ **Testability**: Easy to mock ports for testing

---

## 2. Code Quality Requirements

### 2.1 Type Hints (Mandatory)

```python
# ❌ BAD: No type hints
def calculate_sma(prices, period):
    return sum(prices[-period:]) / period

# ✅ GOOD: Complete type hints with descriptions
def calculate_sma(
    prices: Sequence[Decimal],
    period: int
) -> Optional[Decimal]:
    """
    Calculate Simple Moving Average (SMA).
    
    Args:
        prices: Sequence of prices (e.g., [50000.00, 50100.00, ...])
        period: Number of periods to average (e.g., 20 for 20-day SMA)
    
    Returns:
        Simple Moving Average value, or None if insufficient data
    
    Raises:
        ValueError: If period is less than 1
        IndexError: If prices sequence is empty
    """
    if period < 1:
        raise ValueError(f"Period must be >= 1, got {period}")
    
    if len(prices) < period:
        return None
    
    return sum(prices[-period:]) / Decimal(period)
```

**Requirements**:
- ✅ **All parameters**: Must have type hints
- ✅ **All return values**: Must have type hints
- ✅ **Complex types**: Use TypedDict or dataclass for clarity
- ✅ **Optional values**: Use `Optional[T]` or `T | None`
- ✅ **Generics**: Use `List[T]`, `Dict[K, V]`, `Sequence[T]`
- ✅ **No `Any`**: Avoid `Any` type unless absolutely necessary

---

### 2.2 Documentation (Comprehensive)

```python
# ❌ BAD: No docstring
class TickerCollector:
    def __init__(self, db_pool, symbols):
        self.db_pool = db_pool
        self.symbols = symbols

# ✅ GOOD: Comprehensive documentation
class TickerCollector:
    """
    Collects 24hr ticker statistics from Binance WebSocket.
    
    Purpose:
        Collects real-time ticker data (price, volume, etc.) for all
        active symbols and stores in PostgreSQL for backtesting.
    
    Data Collected:
        - Last price, open, high, low
        - Price change (absolute and percent)
        - Total volume, quote volume
        - Trade count
    
    Frequency:
        Every 1 second per symbol (configurable)
    
    Storage:
        ~43 MB/day/symbol in ticker_24hr_stats table
    
    Example:
        >>> collector = TickerCollector(db_pool, ['BTC/USDT', 'ETH/USDT'])
        >>> await collector.start()
        >>> # Collects ticker data until stopped
        >>> await collector.stop()
    
    Attributes:
        db_pool: PostgreSQL connection pool (asyncpg.Pool)
        symbols: List of symbols to collect (e.g., ['BTC/USDT'])
        snapshot_interval_sec: Snapshot interval in seconds (default: 1)
    
    Raises:
        ValueError: If symbols list is empty
        DatabaseError: If database connection fails
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        symbols: List[str],
        snapshot_interval_sec: int = 1
    ) -> None:
        """
        Initialize ticker collector.
        
        Args:
            db_pool: PostgreSQL connection pool for data storage
            symbols: List of symbols to collect (e.g., ['BTC/USDT', 'ETH/USDT'])
            snapshot_interval_sec: Interval between snapshots in seconds (default: 1)
        
        Raises:
            ValueError: If symbols list is empty or invalid format
        """
        if not symbols:
            raise ValueError("Symbols list cannot be empty")
        
        self.db_pool: asyncpg.Pool = db_pool
        self.symbols: List[str] = symbols
        self.snapshot_interval_sec: int = snapshot_interval_sec
        
        # Internal state
        self._symbol_ids: Dict[str, int] = {}
        self._running: bool = False
        self._last_ticker: Dict[int, Dict] = {}
```

**Requirements**:
- ✅ **All public classes**: Must have class docstring
- ✅ **All public methods**: Must have method docstring
- ✅ **All modules**: Must have module docstring
- ✅ **Args section**: Document all parameters with types and descriptions
- ✅ **Returns section**: Document return value with type and description
- ✅ **Raises section**: Document all exceptions
- ✅ **Examples**: Provide usage examples for complex functionality

---

### 2.3 Error Handling (Explicit)

```python
# ❌ BAD: Silent failure, no context
async def store_ticker(self, ticker: Dict) -> None:
    try:
        await self.conn.execute("INSERT INTO ...", ticker)
    except:
        pass

# ✅ GOOD: Explicit error handling with context
async def store_ticker(self, ticker: TickerData) -> None:
    """
    Store ticker data in database.
    
    Args:
        ticker: Ticker data to store
    
    Raises:
        TickerStorageError: If ticker cannot be stored
        DatabaseError: If database connection fails
    """
    try:
        await self.conn.execute(
            """
            INSERT INTO ticker_24hr_stats (...)
            VALUES (...)
            ON CONFLICT (time, symbol_id) DO UPDATE SET ...
            """,
            ticker.time,
            ticker.symbol_id,
            ticker.last_price,
            # ... other values
        )
    except asyncpg.PostgresError as e:
        logger.error(
            f"Failed to store ticker for {ticker.symbol}: {e}",
            extra={
                'symbol': ticker.symbol,
                'time': ticker.time,
                'price': ticker.last_price,
            }
        )
        raise TickerStorageError(
            f"Failed to store ticker for {ticker.symbol}",
            ticker.symbol
        ) from e
```

**Requirements**:
- ✅ **Catch specific exceptions**: Never use bare `except:`
- ✅ **Add context**: Include relevant data in error messages
- ✅ **Chain exceptions**: Use `from e` to preserve stack trace
- ✅ **Log errors**: Log with appropriate level and context
- ✅ **Custom exceptions**: Create domain-specific exception classes

---

## 3. Layer-Specific Requirements

### 3.1 Domain Layer

```python
# ✅ GOOD: Pure domain entity
@dataclass
class Symbol(Entity):
    """
    Trading pair symbol (e.g., BTC/USDT).
    
    Invariants:
        - symbol must be unique (format: BASE/QUOTE)
        - tick_size > 0
        - step_size > 0
        - min_notional >= 0
    
    Example:
        >>> symbol = Symbol(
        ...     id=1,
        ...     symbol="BTC/USDT",
        ...     base_asset="BTC",
        ...     quote_asset="USDT",
        ...     tick_size=Decimal("0.01"),
        ... )
        >>> symbol.is_valid_order(Decimal("50000"), Decimal("0.001"))
        (True, "")
    """
    
    # Identity
    id: Optional[int] = None
    
    # Symbol identification
    symbol: str = ""
    base_asset: str = ""
    quote_asset: str = ""
    exchange: str = "binance"
    
    # Trading parameters
    tick_size: Decimal = Decimal("0.00000001")
    step_size: Decimal = Decimal("0.00000001")
    min_notional: Decimal = Decimal("10")
    
    # Regional compliance (EU)
    is_allowed: bool = True
    
    # Status
    is_active: bool = False
    
    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        self._validate_symbol_format()
        self._validate_trading_params()
    
    def _validate_symbol_format(self) -> None:
        """Validate symbol format (BASE/QUOTE)."""
        if not self.symbol or '/' not in self.symbol:
            raise ValueError(f"Invalid symbol format: {self.symbol}")
    
    def _validate_trading_params(self) -> None:
        """Validate trading parameters."""
        if self.tick_size <= 0:
            raise ValueError(f"tick_size must be positive: {self.tick_size}")
        if self.step_size <= 0:
            raise ValueError(f"step_size must be positive: {self.step_size}")
        if self.min_notional < 0:
            raise ValueError(f"min_notional must be non-negative: {self.min_notional}")
    
    def is_valid_order(
        self,
        price: Decimal,
        quantity: Decimal
    ) -> Tuple[bool, str]:
        """
        Validate order parameters.
        
        Args:
            price: Order price
            quantity: Order quantity
        
        Returns:
            Tuple of (is_valid, error_message)
            - (True, "") if order is valid
            - (False, "error message") if order is invalid
        """
        notional: Decimal = price * quantity
        
        if notional < self.min_notional:
            return False, f"Order value {notional} below minimum {self.min_notional}"
        
        return True, ""
```

**Requirements**:
- ✅ **Pure Python**: No framework dependencies
- ✅ **No imports from**: `infrastructure`, `application` layers
- ✅ **Business logic**: All validation in domain entities
- ✅ **Invariants**: Enforced in `__post_init__` or methods
- ✅ **Value objects**: Immutable (frozen=True)
- ✅ **Domain events**: Raised on significant changes

---

### 3.2 Application Layer

```python
# ✅ GOOD: Application service (use case)
class CollectTickerData:
    """
    Use Case: Collect ticker data from Binance.
    
    Purpose:
        Orchestrates ticker data collection from Binance WebSocket,
        validation, and storage.
    
    Dependencies:
        - TickerRepository (Port): For storing ticker data
        - SymbolRepository (Port): For getting symbol configuration
        - ConfigManager (Port): For getting collection settings
    
    Example:
        >>> use_case = CollectTickerData(
        ...     ticker_repo=ticker_repo,
        ...     symbol_repo=symbol_repo,
        ...     config_manager=config_manager,
        ... )
        >>> await use_case.execute(symbols=['BTC/USDT', 'ETH/USDT'])
    """
    
    def __init__(
        self,
        ticker_repo: TickerRepository,
        symbol_repo: SymbolRepository,
        config_manager: ConfigManager,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        """
        Initialize use case.
        
        Args:
            ticker_repo: Repository for storing ticker data (Port)
            symbol_repo: Repository for getting symbol configuration (Port)
            config_manager: Manager for collection configuration (Port)
            event_publisher: Optional event publisher for domain events
        """
        self.ticker_repo: TickerRepository = ticker_repo
        self.symbol_repo: SymbolRepository = symbol_repo
        self.config_manager: ConfigManager = config_manager
        self.event_publisher: Optional[EventPublisher] = event_publisher
    
    async def execute(self, symbols: List[str]) -> CollectTickerResult:
        """
        Execute ticker data collection.
        
        Args:
            symbols: List of symbols to collect (e.g., ['BTC/USDT'])
        
        Returns:
            CollectTickerResult with collection statistics
        
        Raises:
            TickerCollectionError: If collection fails
        """
        logger.info(f"Starting ticker collection for {len(symbols)} symbols")
        
        try:
            # Get configuration for each symbol
            configs: List[SymbolConfig] = await self._get_configs(symbols)
            
            # Filter allowed symbols (EU compliance)
            allowed_configs: List[SymbolConfig] = [
                config for config in configs
                if config.is_allowed
            ]
            
            # Collect ticker data
            stats: Dict[str, CollectionStats] = {}
            
            for config in allowed_configs:
                stats[config.symbol] = await self._collect_symbol(config)
            
            return CollectTickerResult(
                success=True,
                symbols_collected=len(stats),
                stats=stats,
            )
        
        except Exception as e:
            logger.error(f"Ticker collection failed: {e}")
            raise TickerCollectionError(f"Collection failed: {e}") from e
    
    async def _get_configs(self, symbols: List[str]) -> List[SymbolConfig]:
        """Get configuration for symbols."""
        # Implementation...
        pass
    
    async def _collect_symbol(self, config: SymbolConfig) -> CollectionStats:
        """Collect ticker data for single symbol."""
        # Implementation...
        pass
```

**Requirements**:
- ✅ **Use case pattern**: One class per use case
- ✅ **Depends on ports**: Not concrete implementations
- ✅ **Orchestration only**: No business logic (that's domain layer)
- ✅ **Error handling**: Catch and wrap infrastructure errors
- ✅ **Logging**: Log at appropriate level (INFO for success, ERROR for failures)
- ✅ **No framework code**: No FastAPI, Click, etc. in application layer

---

### 3.3 Infrastructure Layer

```python
# ✅ GOOD: Repository adapter
class PostgreSQLTickerRepository(TickerRepository):
    """
    PostgreSQL implementation of TickerRepository.
    
    Purpose:
        Implements TickerRepository port using PostgreSQL.
    
    Dependencies:
        - asyncpg: PostgreSQL async driver
    
    Example:
        >>> repo = PostgreSQLTickerRepository(connection)
        >>> await repo.save(ticker)
    """
    
    def __init__(self, connection: asyncpg.Connection) -> None:
        """
        Initialize repository.
        
        Args:
            connection: PostgreSQL connection (asyncpg.Connection)
        """
        self.conn: asyncpg.Connection = connection
    
    async def save(self, ticker: TickerData) -> None:
        """
        Save ticker data to database.
        
        Args:
            ticker: Ticker data to save
        
        Raises:
            TickerStorageError: If ticker cannot be stored
        """
        try:
            await self.conn.execute(
                """
                INSERT INTO ticker_24hr_stats (...)
                VALUES (...)
                ON CONFLICT (time, symbol_id) DO UPDATE SET ...
                """,
                ticker.time,
                ticker.symbol_id,
                # ... other values
            )
        except asyncpg.PostgresError as e:
            raise TickerStorageError(
                f"Failed to store ticker: {e}",
                ticker.symbol
            ) from e
```

**Requirements**:
- ✅ **Implements port**: Must implement interface from domain layer
- ✅ **Framework code OK**: Can use asyncpg, FastAPI, etc.
- ✅ **Error translation**: Convert infrastructure errors to domain errors
- ✅ **Dependency injection**: Receive dependencies via constructor
- ✅ **No business logic**: Only data access, no validation

---

## 4. Testing Requirements

### 4.1 Test Structure

```
tests/
├── unit/
│   ├── domain/
│   │   ├── test_entities.py
│   │   ├── test_value_objects.py
│   │   └── test_domain_services.py
│   ├── application/
│   │   ├── test_use_cases.py
│   │   └── test_commands.py
│   └── infrastructure/
│       ├── test_repositories.py
│       └── test_services.py
├── integration/
│   ├── test_data_collection.py
│   └── test_enrichment.py
└── e2e/
    └── test_full_pipeline.py
```

### 4.2 Test Quality

```python
# ✅ GOOD: Unit test with clear structure
class TestSymbolEntity:
    """Test Symbol domain entity."""
    
    def test_create_valid_symbol(self) -> None:
        """Test creating a valid symbol."""
        # Arrange
        symbol_data = {
            'id': 1,
            'symbol': 'BTC/USDT',
            'base_asset': 'BTC',
            'quote_asset': 'USDT',
            'tick_size': Decimal('0.01'),
            'step_size': Decimal('0.00001'),
        }
        
        # Act
        symbol = Symbol(**symbol_data)
        
        # Assert
        assert symbol.id == 1
        assert symbol.symbol == 'BTC/USDT'
        assert symbol.base_asset == 'BTC'
        assert symbol.quote_asset == 'USDT'
        assert symbol.is_active is False
    
    def test_symbol_must_have_valid_format(self) -> None:
        """Test that symbol format is validated."""
        # Arrange
        invalid_symbol_data = {
            'symbol': 'INVALID',  # Missing quote asset
            'base_asset': 'BTC',
            'quote_asset': 'USDT',
        }
        
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol(**invalid_symbol_data)
    
    def test_is_valid_order_with_valid_order(self) -> None:
        """Test order validation with valid order."""
        # Arrange
        symbol = Symbol(
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            min_notional=Decimal('10'),
        )
        price = Decimal('50000')
        quantity = Decimal('0.001')
        
        # Act
        is_valid, error_message = symbol.is_valid_order(price, quantity)
        
        # Assert
        assert is_valid is True
        assert error_message == ''
```

**Requirements**:
- ✅ **Test structure**: Arrange-Act-Assert pattern
- ✅ **Test names**: Descriptive (test_method_with_condition)
- ✅ **Test coverage**: 90%+ for domain layer, 80%+ for application
- ✅ **Mocking**: Mock external dependencies
- ✅ **Isolation**: Each test is independent

---

## 5. Code Review Checklist

Before submitting code, verify:

### 5.1 Architecture

- [ ] Strict layer separation (Domain → Application → Infrastructure)
- [ ] No circular dependencies
- [ ] Ports defined in domain layer
- [ ] Adapters implement ports in infrastructure layer
- [ ] Dependency injection used correctly

### 5.2 Code Quality

- [ ] KISS principle followed
- [ ] Functions are short (< 50 lines)
- [ ] Functions do ONE thing
- [ ] No code duplication (DRY)
- [ ] Clear variable names (no abbreviations)

### 5.3 Type Hints

- [ ] All parameters have type hints
- [ ] All return values have type hints
- [ ] Complex types are documented
- [ ] No `Any` types (unless absolutely necessary)

### 5.4 Documentation

- [ ] All public classes have docstrings
- [ ] All public methods have docstrings
- [ ] Args/Returns/Raises documented
- [ ] Examples provided for complex functionality
- [ ] Module docstrings present

### 5.5 Error Handling

- [ ] No bare `except:` clauses
- [ ] Specific exceptions caught
- [ ] Errors logged with context
- [ ] Custom exceptions for domain errors
- [ ] Exception chaining (`from e`)

### 5.6 Testing

- [ ] Unit tests for domain logic
- [ ] Integration tests for repositories
- [ ] Test coverage meets targets
- [ ] Tests are isolated and independent
- [ ] Test names are descriptive

---

## 6. Example: Complete Implementation

See `examples/ticker_collector_implementation.py` for a complete, production-ready implementation following all these standards.

---

## 7. Enforcement

**All code will be reviewed against these standards.** Code that doesn't meet these requirements will be rejected and must be revised.

**Remember**: Quality over Quantity. It's better to have less, working, well-documented code than more, buggy, undocumented code.

---

## Summary

| Principle | Requirement |
|-----------|-------------|
| **KISS** | Simple, readable, no clever code |
| **DDD** | Strict layer separation, pure domain layer |
| **Hexagonal** | Ports in domain, adapters in infrastructure |
| **Type Hints** | Mandatory for all parameters and returns |
| **Documentation** | Comprehensive docstrings with examples |
| **Error Handling** | Explicit, with context and chaining |
| **Testing** | 90%+ domain, 80%+ application, isolated tests |

**These standards are MANDATORY for all LLM agents implementing this system.**
