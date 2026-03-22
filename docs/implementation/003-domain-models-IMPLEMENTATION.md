# Step 003: Domain Models - Implementation Guide

**Phase**: 1 - Foundation  
**Effort**: 4 hours  
**Dependencies**: Step 002 (Database Schema) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements the complete domain layer with:
- Base classes (Entity, ValueObject, DomainEvent)
- Core entities (Symbol, Trade, TickerData, IndicatorDefinition)
- Value objects (SymbolId, TradeId, Price)
- Domain events (IndicatorChanged, SymbolActivated)
- Domain services (TickValidator, SymbolService)
- Comprehensive unit tests (90%+ coverage)

---

## Implementation Tasks

### Task 1: Base Classes (Complete)

**File**: `src/domain/models/base.py`

```python
"""
Base classes for domain entities.

This module provides the foundational classes for Domain-Driven Design:
- Entity: Base class for objects with identity
- ValueObject: Base class for immutable objects
- DomainEvent: Base class for domain events

Example:
    >>> from src.domain.models.base import Entity
    >>> from dataclasses import dataclass
    
    >>> @dataclass
    ... class MyEntity(Entity):
    ...     name: str
    ...     value: int
"""

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Entity(ABC):
    """
    Base class for all domain entities.
    
    Entities are objects with a distinct identity that runs through
    time and different states. They have mutable attributes and
    track creation/update timestamps.
    
    Attributes:
        id: Unique identifier (None until saved to database)
        created_at: Creation timestamp (auto-set)
        updated_at: Last update timestamp (auto-updated)
    
    Example:
        >>> @dataclass
        ... class Symbol(Entity):
        ...     symbol: str
        ...     base_asset: str
        ...     quote_asset: str
        ...
        >>> symbol = Symbol(
        ...     symbol="BTC/USDT",
        ...     base_asset="BTC",
        ...     quote_asset="USDT",
        ... )
        >>> symbol.id  # None until saved
        >>> symbol.created_at  # Auto-set
    """
    
    id: int | None = None
    created_at: datetime = None  # type: ignore
    updated_at: datetime = None  # type: ignore
    
    def __post_init__(self) -> None:
        """
        Initialize timestamps after dataclass initialization.
        
        Sets created_at and updated_at to current UTC time if not provided.
        """
        now = datetime.utcnow()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now
    
    def __eq__(self, other: Any) -> bool:
        """
        Compare entities by ID.
        
        Two entities are equal if they have the same ID and are of the same type.
        Entities without ID (None) are never equal.
        
        Args:
            other: Object to compare with
            
        Returns:
            True if entities are equal, False otherwise
        """
        if not isinstance(other, Entity):
            return False
        if self.id is None or other.id is None:
            return False
        return self.id == other.id
    
    def __hash__(self) -> int:
        """
        Hash entity by ID.
        
        Returns:
            Hash of ID, or object ID if ID is None
        """
        return hash(self.id) if self.id else id(self)


@dataclass(frozen=True)
class ValueObject(ABC):
    """
    Base class for all value objects.
    
    Value Objects are immutable objects defined by their attributes
    rather than identity. They are compared by value, not by ID.
    
    Attributes:
        frozen: Value objects are immutable (frozen=True)
    
    Example:
        >>> @dataclass(frozen=True)
        ... class Price(ValueObject):
        ...     value: Decimal
        ...     currency: str
        ...
        >>> price1 = Price(Decimal("50000"), "USD")
        >>> price2 = Price(Decimal("50000"), "USD")
        >>> price1 == price2  # Equal by value
        True
    """
    
    def __eq__(self, other: Any) -> bool:
        """
        Compare value objects by attributes.
        
        Args:
            other: Object to compare with
            
        Returns:
            True if value objects have same attributes
        """
        if not isinstance(other, ValueObject):
            return False
        return self.__dict__ == other.__dict__
    
    def __hash__(self) -> int:
        """
        Hash value object by attributes.
        
        Returns:
            Hash of all attribute values
        """
        return hash(tuple(sorted(self.__dict__.values())))


@dataclass(frozen=True)
class DomainEvent:
    """
    Base class for domain events.
    
    Domain Events represent significant occurrences in the domain
    that domain experts care about. They are immutable and contain
    all relevant data about the event.
    
    Attributes:
        event_id: Unique event identifier (auto-generated UUID)
        occurred_at: When the event occurred (auto-set to UTC now)
    
    Example:
        >>> @dataclass(frozen=True)
        ... class SymbolActivatedEvent(DomainEvent):
        ...     symbol_id: int
        ...     symbol: str
        ...
        >>> event = SymbolActivatedEvent(symbol_id=1, symbol="BTC/USDT")
        >>> event.event_id  # Auto-generated UUID
        >>> event.occurred_at  # Auto-set timestamp
    """
    
    event_id: UUID = None  # type: ignore
    occurred_at: datetime = None  # type: ignore
    
    def __post_init__(self) -> None:
        """
        Initialize event metadata.
        
        Sets event_id to new UUID and occurred_at to current UTC time.
        """
        # Frozen dataclass requires object.__setattr__
        object.__setattr__(self, 'event_id', uuid4())
        object.__setattr__(self, 'occurred_at', datetime.utcnow())
    
    @property
    def event_type(self) -> str:
        """
        Get event type from class name.
        
        Returns:
            Class name (e.g., "SymbolActivatedEvent")
        """
        return self.__class__.__name__
```

---

### Task 2: Symbol Entity

**File**: `src/domain/models/symbol.py`

```python
"""
Symbol entity - Trading pair representation.

This module contains the Symbol entity which represents
a trading pair (e.g., BTC/USDT) with all its configuration
and validation logic.

Example:
    >>> from decimal import Decimal
    >>> symbol = Symbol(
    ...     symbol="BTC/USDT",
    ...     base_asset="BTC",
    ...     quote_asset="USDT",
    ...     tick_size=Decimal("0.01"),
    ... )
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from src.domain.models.base import Entity


@dataclass
class Symbol(Entity):
    """
    Trading pair symbol (e.g., BTC/USDT).
    
    Represents a cryptocurrency trading pair with all its
    configuration, validation rules, and regional compliance.
    
    Attributes:
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        base_asset: Base asset code (e.g., "BTC")
        quote_asset: Quote asset code (e.g., "USDT")
        exchange: Exchange name (default: "binance")
        tick_size: Price precision (e.g., 0.01)
        step_size: Quantity precision (e.g., 0.00001)
        min_notional: Minimum order value (e.g., 10 USDT)
        is_allowed: EU compliance flag (default: True)
        is_active: Collection active flag (default: False)
    
    Invariants:
        - symbol must be in format BASE/QUOTE
        - tick_size > 0
        - step_size > 0
        - min_notional >= 0
    
    Example:
        >>> symbol = Symbol(
        ...     symbol="BTC/USDT",
        ...     base_asset="BTC",
        ...     quote_asset="USDT",
        ...     tick_size=Decimal("0.01"),
        ...     step_size=Decimal("0.00001"),
        ...     min_notional=Decimal("10"),
        ... )
        >>> symbol.is_valid_order(Decimal("50000"), Decimal("0.001"))
        (True, "")
    """
    
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
        """
        Validate invariants after initialization.
        
        Raises:
            ValueError: If any invariant is violated
        """
        self._validate_symbol_format()
        self._validate_trading_params()
    
    def _validate_symbol_format(self) -> None:
        """
        Validate symbol format (BASE/QUOTE).
        
        Raises:
            ValueError: If symbol format is invalid
        """
        if not self.symbol:
            raise ValueError("Symbol cannot be empty")
        
        if '/' not in self.symbol:
            raise ValueError(
                f"Invalid symbol format: {self.symbol}. "
                f"Expected format: BASE/QUOTE (e.g., BTC/USDT)"
            )
        
        parts = self.symbol.split('/')
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"Invalid symbol format: {self.symbol}. "
                f"Both base and quote assets must be specified"
            )
    
    def _validate_trading_params(self) -> None:
        """
        Validate trading parameters.
        
        Raises:
            ValueError: If any parameter is invalid
        """
        if self.tick_size <= 0:
            raise ValueError(
                f"tick_size must be positive, got {self.tick_size}"
            )
        
        if self.step_size <= 0:
            raise ValueError(
                f"step_size must be positive, got {self.step_size}"
            )
        
        if self.min_notional < 0:
            raise ValueError(
                f"min_notional must be non-negative, got {self.min_notional}"
            )
    
    @property
    def base(self) -> str:
        """
        Get base asset (e.g., BTC from BTC/USDT).
        
        Returns:
            Base asset code
        """
        return self.base_asset
    
    @property
    def quote(self) -> str:
        """
        Get quote asset (e.g., USDT from BTC/USDT).
        
        Returns:
            Quote asset code
        """
        return self.quote_asset
    
    def activate(self) -> None:
        """
        Activate symbol for data collection.
        
        Sets is_active to True.
        
        Example:
            >>> symbol = Symbol(symbol="BTC/USDT", ...)
            >>> symbol.activate()
            >>> assert symbol.is_active is True
        """
        self.is_active = True
    
    def deactivate(self) -> None:
        """
        Deactivate symbol (stop data collection).
        
        Sets is_active to False.
        
        Example:
            >>> symbol = Symbol(symbol="BTC/USDT", ..., is_active=True)
            >>> symbol.deactivate()
            >>> assert symbol.is_active is False
        """
        self.is_active = False
    
    def price_to_tick(self, price: Decimal) -> Decimal:
        """
        Round price to tick size.
        
        Args:
            price: Price to round
        
        Returns:
            Price rounded to tick size
        
        Example:
            >>> symbol = Symbol(symbol="BTC/USDT", tick_size=Decimal("0.01"))
            >>> symbol.price_to_tick(Decimal("50123.456"))
            Decimal('50123.46')
        """
        return (price / self.tick_size).quantize(Decimal('1')) * self.tick_size
    
    def quantity_to_step(self, quantity: Decimal) -> Decimal:
        """
        Round quantity to step size.
        
        Args:
            quantity: Quantity to round
        
        Returns:
            Quantity rounded to step size
        
        Example:
            >>> symbol = Symbol(symbol="BTC/USDT", step_size=Decimal("0.00001"))
            >>> symbol.quantity_to_step(Decimal("0.00123456"))
            Decimal('0.00123')
        """
        return (quantity / self.step_size).quantize(Decimal('1')) * self.step_size
    
    def is_valid_order(
        self,
        price: Decimal,
        quantity: Decimal,
    ) -> tuple[bool, str]:
        """
        Validate order parameters.
        
        Checks:
        - Notional value >= min_notional
        - Price aligned with tick_size
        - Quantity aligned with step_size
        
        Args:
            price: Order price
            quantity: Order quantity
        
        Returns:
            Tuple of (is_valid, error_message)
            - (True, "") if order is valid
            - (False, "error message") if order is invalid
        
        Example:
            >>> symbol = Symbol(
            ...     symbol="BTC/USDT",
            ...     min_notional=Decimal("10"),
            ...     tick_size=Decimal("0.01"),
            ...     step_size=Decimal("0.00001"),
            ... )
            >>> symbol.is_valid_order(Decimal("50000"), Decimal("0.001"))
            (True, "")
            >>> symbol.is_valid_order(Decimal("50000"), Decimal("0.00001"))
            (False, "Order value 0.50 below minimum 10")
        """
        notional: Decimal = price * quantity
        
        if notional < self.min_notional:
            return (
                False,
                f"Order value {notional} below minimum {self.min_notional}"
            )
        
        if self.price_to_tick(price) != price:
            return (
                False,
                f"Price {price} not aligned with tick_size {self.tick_size}"
            )
        
        if self.quantity_to_step(quantity) != quantity:
            return (
                False,
                f"Quantity {quantity} not aligned with step_size {self.step_size}"
            )
        
        return True, ""
```

---

### Task 3: Trade Entity

**File**: `src/domain/models/trade.py`

```python
"""
Trade entity - Individual trade (tick) representation.

This module contains the Trade entity which represents
a single trade (tick) from the exchange.

Example:
    >>> from decimal import Decimal
    >>> from datetime import datetime
    >>> trade = Trade(
    ...     time=datetime.utcnow(),
    ...     symbol_id=1,
    ...     trade_id="123456",
    ...     price=Decimal("50000.00"),
    ...     quantity=Decimal("0.001"),
    ...     side="BUY",
    ... )
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from src.domain.models.base import Entity, ValueObject


class TradeId(ValueObject):
    """
    Trade ID value object.
    
    Immutable identifier for a trade. Ensures trade IDs
    are never empty and are compared by value.
    
    Attributes:
        value: Trade ID string
    
    Example:
        >>> trade_id = TradeId("123456")
        >>> assert trade_id.value == "123456"
    """
    
    value: str
    
    def __post_init__(self) -> None:
        """
        Validate trade ID.
        
        Raises:
            ValueError: If trade ID is empty
        """
        if not self.value:
            raise ValueError("Trade ID cannot be empty")


@dataclass
class Trade(Entity):
    """
    Individual trade (tick).
    
    Represents a single trade executed on the exchange with
    all its attributes (price, quantity, side, etc.).
    
    Attributes:
        time: Trade timestamp
        symbol_id: Reference to symbol
        trade_id: Exchange trade ID
        price: Trade price
        quantity: Trade quantity
        side: Trade side (BUY or SELL)
        is_buyer_maker: True if buyer was maker
    
    Invariants:
        - price > 0
        - quantity > 0
        - side must be 'BUY' or 'SELL'
    
    Example:
        >>> trade = Trade(
        ...     time=datetime.utcnow(),
        ...     symbol_id=1,
        ...     trade_id="123456",
        ...     price=Decimal("50000.00"),
        ...     quantity=Decimal("0.001"),
        ...     side="BUY",
        ... )
        >>> assert trade.is_buy() is True
        >>> assert trade.notional == Decimal("50.00")
    """
    
    # Trade identification
    time: datetime = datetime.utcnow
    symbol_id: int = 0
    trade_id: str = ""
    
    # Trade details
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    side: str = ""
    is_buyer_maker: bool = False
    
    def __post_init__(self) -> None:
        """
        Validate invariants after initialization.
        
        Raises:
            ValueError: If any invariant is violated
        """
        self._validate_price()
        self._validate_quantity()
        self._validate_side()
    
    def _validate_price(self) -> None:
        """
        Validate price is positive.
        
        Raises:
            ValueError: If price <= 0
        """
        if self.price <= 0:
            raise ValueError(f"price must be positive, got {self.price}")
    
    def _validate_quantity(self) -> None:
        """
        Validate quantity is positive.
        
        Raises:
            ValueError: If quantity <= 0
        """
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")
    
    def _validate_side(self) -> None:
        """
        Validate side is BUY or SELL.
        
        Raises:
            ValueError: If side is not BUY or SELL
        """
        if self.side not in ('BUY', 'SELL'):
            raise ValueError(
                f"Invalid side: {self.side}. Expected 'BUY' or 'SELL'"
            )
    
    @property
    def notional(self) -> Decimal:
        """
        Calculate notional value (price * quantity).
        
        Returns:
            Notional value in quote currency
        
        Example:
            >>> trade = Trade(price=Decimal("50000"), quantity=Decimal("0.001"), ...)
            >>> trade.notional
            Decimal('50.00')
        """
        return self.price * self.quantity
    
    def is_buy(self) -> bool:
        """
        Check if this is a buy trade.
        
        Returns:
            True if side is BUY
        
        Example:
            >>> trade = Trade(side="BUY", ...)
            >>> trade.is_buy()
            True
        """
        return self.side == 'BUY'
    
    def is_sell(self) -> bool:
        """
        Check if this is a sell trade.
        
        Returns:
            True if side is SELL
        
        Example:
            >>> trade = Trade(side="SELL", ...)
            >>> trade.is_sell()
            True
        """
        return self.side == 'SELL'
```

---

### Task 4: TickerData Entity

**File**: `src/domain/models/ticker.py`

```python
"""
TickerData entity - 24hr ticker statistics.

This module contains the TickerData entity which represents
24hr ticker statistics from the exchange.

Example:
    >>> from decimal import Decimal
    >>> ticker = TickerData(
    ...     symbol_id=1,
    ...     symbol="BTC/USDT",
    ...     last_price=Decimal("50000.00"),
    ...     total_volume=Decimal("12345.67"),
    ... )
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional
from src.domain.models.base import Entity


@dataclass
class TickerData(Entity):
    """
    24hr ticker statistics.
    
    Represents aggregated ticker data over a 24-hour period,
    including prices, volumes, and trade statistics.
    
    Attributes:
        time: Snapshot timestamp
        symbol_id: Reference to symbol
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        pair: Pair code (e.g., "BTCUSD")
        price_change: Price change (absolute)
        price_change_pct: Price change (percent)
        last_price: Last traded price
        open_price: Open price (24h)
        high_price: High price (24h)
        low_price: Low price (24h)
        weighted_avg_price: Volume-weighted average price
        last_quantity: Last traded quantity
        total_volume: Total volume (24h)
        total_quote_volume: Total quote volume (24h)
        first_trade_id: First trade ID (24h)
        last_trade_id: Last trade ID (24h)
        total_trades: Total number of trades (24h)
        stats_open_time: Statistics period open
        stats_close_time: Statistics period close
    
    Example:
        >>> ticker = TickerData(
        ...     symbol_id=1,
        ...     symbol="BTC/USDT",
        ...     last_price=Decimal("50000.00"),
        ...     open_price=Decimal("49500.00"),
        ...     total_volume=Decimal("12345.67"),
        ... )
        >>> assert ticker.price_change == Decimal("500.00")
        >>> assert ticker.price_change_pct == Decimal("1.01")
    """
    
    # Identification
    time: datetime = datetime.utcnow
    symbol_id: int = 0
    symbol: str = ""
    pair: str = ""
    
    # Price changes
    price_change: Optional[Decimal] = None
    price_change_pct: Optional[Decimal] = None
    
    # Prices
    last_price: Decimal = Decimal("0")
    open_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    weighted_avg_price: Optional[Decimal] = None
    
    # Volumes
    last_quantity: Optional[Decimal] = None
    total_volume: Optional[Decimal] = None
    total_quote_volume: Optional[Decimal] = None
    
    # Trade IDs
    first_trade_id: Optional[int] = None
    last_trade_id: Optional[int] = None
    total_trades: Optional[int] = None
    
    # Times
    stats_open_time: Optional[datetime] = None
    stats_close_time: Optional[datetime] = None
    
    def __post_init__(self) -> None:
        """
        Validate invariants and calculate derived fields.
        
        Raises:
            ValueError: If last_price <= 0
        """
        self._validate_last_price()
        self._calculate_price_change()
    
    def _validate_last_price(self) -> None:
        """
        Validate last price is positive.
        
        Raises:
            ValueError: If last_price <= 0
        """
        if self.last_price <= 0:
            raise ValueError(
                f"last_price must be positive, got {self.last_price}"
            )
    
    def _calculate_price_change(self) -> None:
        """
        Calculate price change if open_price is available.
        
        Sets price_change and price_change_pct based on
        last_price and open_price.
        """
        if self.open_price is not None and self.open_price > 0:
            self.price_change = self.last_price - self.open_price
            self.price_change_pct = (
                self.price_change / self.open_price * Decimal("100")
            )
    
    @property
    def is_price_up(self) -> bool:
        """
        Check if price is up (positive change).
        
        Returns:
            True if price_change > 0, False otherwise
        
        Example:
            >>> ticker = TickerData(
            ...     last_price=Decimal("50000"),
            ...     open_price=Decimal("49500"),
            ... )
            >>> ticker.is_price_up
            True
        """
        if self.price_change is None:
            return False
        return self.price_change > 0
    
    @property
    def is_price_down(self) -> bool:
        """
        Check if price is down (negative change).
        
        Returns:
            True if price_change < 0, False otherwise
        
        Example:
            >>> ticker = TickerData(
            ...     last_price=Decimal("49000"),
            ...     open_price=Decimal("50000"),
            ... )
            >>> ticker.is_price_down
            True
        """
        if self.price_change is None:
            return False
        return self.price_change < 0
```

---

### Task 5: Domain Events

**File**: `src/domain/events/symbol_events.py`

```python
"""
Symbol-related domain events.

This module contains domain events related to symbol
lifecycle and configuration changes.

Example:
    >>> event = SymbolActivatedEvent(
    ...     symbol_id=1,
    ...     symbol="BTC/USDT",
    ... )
"""

from dataclasses import dataclass
from src.domain.models.base import DomainEvent


@dataclass(frozen=True)
class SymbolActivatedEvent(DomainEvent):
    """
    Raised when a symbol is activated for collection.
    
    This event is published when a symbol's is_active
    flag is set to True, indicating that data collection
    should begin for this symbol.
    
    Attributes:
        symbol_id: Symbol ID
        symbol: Trading pair symbol (e.g., "BTC/USDT")
    
    Example:
        >>> event = SymbolActivatedEvent(
        ...     symbol_id=1,
        ...     symbol="BTC/USDT",
        ... )
        >>> print(event.event_type)
        'SymbolActivatedEvent'
    """
    
    symbol_id: int = 0
    symbol: str = ""


@dataclass(frozen=True)
class SymbolDeactivatedEvent(DomainEvent):
    """
    Raised when a symbol is deactivated.
    
    This event is published when a symbol's is_active
    flag is set to False, indicating that data collection
    should stop for this symbol.
    
    Attributes:
        symbol_id: Symbol ID
        symbol: Trading pair symbol
    
    Example:
        >>> event = SymbolDeactivatedEvent(
        ...     symbol_id=1,
        ...     symbol="BTC/USDT",
        ... )
    """
    
    symbol_id: int = 0
    symbol: str = ""


@dataclass(frozen=True)
class SymbolRegionStatusChangedEvent(DomainEvent):
    """
    Raised when a symbol's regional compliance status changes.
    
    This event is published when a symbol's is_allowed
    flag changes, indicating regional compliance status
    has been updated (e.g., EU restrictions).
    
    Attributes:
        symbol_id: Symbol ID
        symbol: Trading pair symbol
        is_allowed: New compliance status
        region: Region code (e.g., "EU")
    
    Example:
        >>> event = SymbolRegionStatusChangedEvent(
        ...     symbol_id=1,
        ...     symbol="BTC/USDT",
        ...     is_allowed=False,
        ...     region="EU",
        ... )
    """
    
    symbol_id: int = 0
    symbol: str = ""
    is_allowed: bool = False
    region: str = ""
```

---

### Task 6: Domain Services

**File**: `src/domain/services/tick_validator.py`

```python
"""
Tick validation service.

This module provides validation for incoming tick data
to ensure data quality before storage.

Example:
    >>> validator = TickValidator(symbol)
    >>> result = validator.validate(tick)
    >>> if result.is_valid:
    ...     await repository.save(tick)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
from src.domain.models.symbol import Symbol
from src.domain.models.trade import Trade


@dataclass
class ValidationResult:
    """
    Result of tick validation.
    
    Contains validation status and any errors or warnings
    encountered during validation.
    
    Attributes:
        is_valid: True if tick passed all validation rules
        errors: List of error messages (critical issues)
        warnings: List of warning messages (non-critical)
    
    Example:
        >>> result = ValidationResult(
        ...     is_valid=True,
        ...     errors=[],
        ...     warnings=["Large quantity spike detected"],
        ... )
    """
    
    is_valid: bool = True
    errors: List[str] = None  # type: ignore
    warnings: List[str] = None  # type: ignore
    
    def __post_init__(self) -> None:
        """Initialize error and warning lists."""
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class TickValidator:
    """
    Validates tick data before storage.
    
    Applies validation rules to ensure data quality:
    - Price sanity (no extreme moves)
    - Time monotonicity (no time travel)
    - Precision (aligned with tick_size/step_size)
    - Duplicates detection
    - Stale data detection
    
    Attributes:
        symbol: Symbol being validated
        max_price_move_pct: Maximum allowed price move %
        max_gap_seconds: Maximum allowed time gap
    
    Example:
        >>> validator = TickValidator(
        ...     symbol=symbol,
        ...     max_price_move_pct=Decimal("10.0"),
        ... )
        >>> result = validator.validate(tick)
        >>> if not result.is_valid:
        ...     print(f"Validation failed: {result.errors}")
    """
    
    def __init__(
        self,
        symbol: Symbol,
        max_price_move_pct: Decimal = Decimal("10.0"),
        max_gap_seconds: int = 5,
    ) -> None:
        """
        Initialize tick validator.
        
        Args:
            symbol: Symbol being validated
            max_price_move_pct: Maximum allowed price move % (default: 10%)
            max_gap_seconds: Maximum allowed time gap (default: 5 seconds)
        """
        self.symbol: Symbol = symbol
        self.max_price_move_pct: Decimal = max_price_move_pct
        self.max_gap_seconds: int = max_gap_seconds
        
        # State for comparison
        self._last_price: Optional[Decimal] = None
        self._last_time: Optional[datetime] = None
        self._seen_trade_ids: set = set()
    
    def validate(self, tick: Trade) -> ValidationResult:
        """
        Validate tick against all rules.
        
        Args:
            tick: Tick to validate
        
        Returns:
            ValidationResult with validation status
        
        Example:
            >>> result = validator.validate(tick)
            >>> if result.is_valid:
            ...     await save(tick)
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        # Run all validation checks
        self._check_price_sanity(tick, errors, warnings)
        self._check_time_monotonicity(tick, errors, warnings)
        self._check_precision(tick, errors, warnings)
        self._check_duplicate(tick, errors, warnings)
        
        # Update state if valid
        if not errors:
            self._update_state(tick)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    def _check_price_sanity(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """
        Check price sanity (no extreme moves).
        
        Validates that price hasn't moved more than the
        configured percentage since the last tick.
        
        Args:
            tick: Tick to validate
            errors: List to append error messages
            warnings: List to append warning messages
        """
        if self._last_price is None:
            return
        
        price_change = abs(tick.price - self._last_price)
        pct_change = price_change / self._last_price * Decimal("100")
        
        if pct_change > self.max_price_move_pct:
            errors.append(
                f"Price move {pct_change:.2f}% exceeds "
                f"maximum {self.max_price_move_pct}%"
            )
        elif pct_change > self.max_price_move_pct / 2:
            warnings.append(
                f"Large price move detected: {pct_change:.2f}%"
            )
    
    def _check_time_monotonicity(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """
        Check time monotonicity (no time travel).
        
        Validates that tick time is not in the past compared
        to the last tick.
        
        Args:
            tick: Tick to validate
            errors: List to append error messages
            warnings: List to append warning messages
        """
        if self._last_time is None:
            return
        
        if tick.time < self._last_time:
            errors.append(
                f"Time travel detected: {tick.time} < {self._last_time}"
            )
        
        # Check for stale data
        age = datetime.utcnow() - tick.time
        if age > timedelta(seconds=self.max_gap_seconds * 12):
            warnings.append(
                f"Stale data: {age.total_seconds():.0f}s old"
            )
    
    def _check_precision(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """
        Check price and quantity precision.
        
        Validates that price and quantity are aligned with
        the symbol's tick_size and step_size.
        
        Args:
            tick: Tick to validate
            errors: List to append error messages
            warnings: List to append warning messages
        """
        if self.symbol.price_to_tick(tick.price) != tick.price:
            errors.append(
                f"Price {tick.price} not aligned with "
                f"tick_size {self.symbol.tick_size}"
            )
        
        if self.symbol.quantity_to_step(tick.quantity) != tick.quantity:
            errors.append(
                f"Quantity {tick.quantity} not aligned with "
                f"step_size {self.symbol.step_size}"
            )
    
    def _check_duplicate(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """
        Check for duplicate trade ID.
        
        Validates that trade ID hasn't been seen before.
        
        Args:
            tick: Tick to validate
            errors: List to append error messages
            warnings: List to append warning messages
        """
        if tick.trade_id in self._seen_trade_ids:
            errors.append(f"Duplicate trade ID: {tick.trade_id}")
        
        # Keep last 10000 trade IDs in memory
        self._seen_trade_ids.add(tick.trade_id)
        if len(self._seen_trade_ids) > 10000:
            self._seen_trade_ids.pop()
    
    def _update_state(self, tick: Trade) -> None:
        """
        Update internal state after valid tick.
        
        Args:
            tick: Valid tick that was just processed
        """
        self._last_price = tick.price
        self._last_time = tick.time
    
    def reset(self) -> None:
        """
        Reset validator state.
        
        Clears all internal state (last price, time, trade IDs).
        Use when switching symbols or restarting collection.
        """
        self._last_price = None
        self._last_time = None
        self._seen_trade_ids.clear()
```

---

### Task 7: Unit Tests

**File**: `tests/unit/domain/models/test_symbol.py`

```python
"""
Tests for Symbol entity.

Tests cover all Symbol functionality including:
- Initialization and validation
- Price/quantity rounding
- Order validation
- Activation/deactivation
"""

import pytest
from decimal import Decimal
from src.domain.models.symbol import Symbol


class TestSymbolInitialization:
    """Test Symbol initialization and validation."""
    
    def test_create_valid_symbol(self) -> None:
        """Test creating a valid symbol."""
        # Arrange
        symbol_data = {
            'symbol': 'BTC/USDT',
            'base_asset': 'BTC',
            'quote_asset': 'USDT',
            'tick_size': Decimal('0.01'),
            'step_size': Decimal('0.00001'),
        }
        
        # Act
        symbol = Symbol(**symbol_data)
        
        # Assert
        assert symbol.symbol == 'BTC/USDT'
        assert symbol.base_asset == 'BTC'
        assert symbol.quote_asset == 'USDT'
        assert symbol.is_active is False
    
    def test_symbol_must_have_valid_format(self) -> None:
        """Test that symbol format is validated."""
        # Arrange
        invalid_data = {'symbol': 'INVALID'}
        
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol(**invalid_data)
    
    def test_symbol_cannot_be_empty(self) -> None:
        """Test that symbol cannot be empty."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Symbol(symbol='')
    
    def test_tick_size_must_be_positive(self) -> None:
        """Test that tick_size must be positive."""
        # Arrange
        invalid_data = {
            'symbol': 'BTC/USDT',
            'tick_size': Decimal('-0.01'),
        }
        
        # Act & Assert
        with pytest.raises(ValueError, match="tick_size must be positive"):
            Symbol(**invalid_data)
    
    def test_step_size_must_be_positive(self) -> None:
        """Test that step_size must be positive."""
        # Arrange
        invalid_data = {
            'symbol': 'BTC/USDT',
            'step_size': Decimal('-0.00001'),
        }
        
        # Act & Assert
        with pytest.raises(ValueError, match="step_size must be positive"):
            Symbol(**invalid_data)


class TestSymbolMethods:
    """Test Symbol methods."""
    
    @pytest.fixture
    def btc_symbol(self) -> Symbol:
        """Create BTC/USDT symbol for testing."""
        return Symbol(
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            tick_size=Decimal('0.01'),
            step_size=Decimal('0.00001'),
            min_notional=Decimal('10'),
        )
    
    def test_activate_symbol(self, btc_symbol: Symbol) -> None:
        """Test activating a symbol."""
        # Act
        btc_symbol.activate()
        
        # Assert
        assert btc_symbol.is_active is True
    
    def test_deactivate_symbol(self, btc_symbol: Symbol) -> None:
        """Test deactivating a symbol."""
        # Arrange
        btc_symbol.is_active = True
        
        # Act
        btc_symbol.deactivate()
        
        # Assert
        assert btc_symbol.is_active is False
    
    def test_price_to_tick(self, btc_symbol: Symbol) -> None:
        """Test rounding price to tick size."""
        # Arrange
        price = Decimal('50123.456')
        expected = Decimal('50123.46')
        
        # Act
        result = btc_symbol.price_to_tick(price)
        
        # Assert
        assert result == expected
    
    def test_quantity_to_step(self, btc_symbol: Symbol) -> None:
        """Test rounding quantity to step size."""
        # Arrange
        quantity = Decimal('0.00123456')
        expected = Decimal('0.00123')
        
        # Act
        result = btc_symbol.quantity_to_step(quantity)
        
        # Assert
        assert result == expected
    
    def test_is_valid_order_with_valid_order(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test order validation with valid order."""
        # Arrange
        price = Decimal('50000.00')
        quantity = Decimal('0.001')
        
        # Act
        is_valid, error = btc_symbol.is_valid_order(price, quantity)
        
        # Assert
        assert is_valid is True
        assert error == ''
    
    def test_is_valid_order_below_min_notional(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test order validation below minimum notional."""
        # Arrange
        price = Decimal('50000.00')
        quantity = Decimal('0.00001')  # Notional = 0.50
        
        # Act
        is_valid, error = btc_symbol.is_valid_order(price, quantity)
        
        # Assert
        assert is_valid is False
        assert 'below minimum' in error
    
    def test_is_valid_order_price_not_aligned(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test order validation with price not aligned."""
        # Arrange
        price = Decimal('50000.001')  # Not aligned with 0.01 tick_size
        quantity = Decimal('0.001')
        
        # Act
        is_valid, error = btc_symbol.is_valid_order(price, quantity)
        
        # Assert
        assert is_valid is False
        assert 'not aligned' in error
        assert 'tick_size' in error
```

---

### Task 8: Test Base Classes

**File**: `tests/unit/domain/models/test_base.py`

```python
"""
Tests for base classes (Entity, ValueObject, DomainEvent).

Tests cover:
- Entity identity and timestamps
- ValueObject immutability and equality
- DomainEvent metadata
"""

import pytest
from datetime import datetime
from dataclasses import dataclass
from src.domain.models.base import Entity, ValueObject, DomainEvent


class TestEntity:
    """Test Entity base class."""
    
    def test_entity_timestamps_auto_initialized(self) -> None:
        """Test that Entity timestamps are auto-initialized."""
        # Arrange
        @dataclass
        class TestEntity(Entity):
            name: str
        
        # Act
        entity = TestEntity(name='test')
        
        # Assert
        assert entity.created_at is not None
        assert entity.updated_at is not None
        assert isinstance(entity.created_at, datetime)
    
    def test_entity_equality_by_id(self) -> None:
        """Test that entities are equal when IDs match."""
        # Arrange
        @dataclass
        class TestEntity(Entity):
            name: str
        
        entity1 = TestEntity(id=1, name='test1')
        entity2 = TestEntity(id=1, name='test2')
        entity3 = TestEntity(id=2, name='test1')
        
        # Act & Assert
        assert entity1 == entity2  # Same ID
        assert entity1 != entity3  # Different ID
    
    def test_entity_without_id_not_equal(self) -> None:
        """Test that entities without ID are never equal."""
        # Arrange
        @dataclass
        class TestEntity(Entity):
            name: str
        
        entity1 = TestEntity(name='test')
        entity2 = TestEntity(name='test')
        
        # Act & Assert
        assert entity1 != entity2  # Both have None ID


class TestValueObject:
    """Test ValueObject base class."""
    
    def test_value_object_immutable(self) -> None:
        """Test that value objects are immutable."""
        # Arrange
        @dataclass(frozen=True)
        class TestValueObject(ValueObject):
            value: int
        
        vo = TestValueObject(value=42)
        
        # Act & Assert
        with pytest.raises(AttributeError):
            vo.value = 43  # type: ignore
    
    def test_value_object_equality_by_value(self) -> None:
        """Test that value objects are equal by value."""
        # Arrange
        @dataclass(frozen=True)
        class TestValueObject(ValueObject):
            value: int
        
        vo1 = TestValueObject(value=42)
        vo2 = TestValueObject(value=42)
        vo3 = TestValueObject(value=43)
        
        # Act & Assert
        assert vo1 == vo2  # Same value
        assert vo1 != vo3  # Different value


class TestDomainEvent:
    """Test DomainEvent base class."""
    
    def test_domain_event_id_auto_generated(self) -> None:
        """Test that event ID is auto-generated UUID."""
        # Arrange
        @dataclass(frozen=True)
        class TestEvent(DomainEvent):
            message: str
        
        # Act
        event = TestEvent(message='test')
        
        # Assert
        assert event.event_id is not None
    
    def test_domain_event_timestamp_auto_set(self) -> None:
        """Test that event timestamp is auto-set."""
        # Arrange
        @dataclass(frozen=True)
        class TestEvent(DomainEvent):
            message: str
        
        # Act
        event = TestEvent(message='test')
        
        # Assert
        assert event.occurred_at is not None
        assert isinstance(event.occurred_at, datetime)
    
    def test_domain_event_type_from_class_name(self) -> None:
        """Test that event type is derived from class name."""
        # Arrange
        @dataclass(frozen=True)
        class TestEvent(DomainEvent):
            message: str
        
        # Act
        event = TestEvent(message='test')
        
        # Assert
        assert event.event_type == 'TestEvent'
```

---

## Acceptance Criteria

- [ ] Base classes implemented (Entity, ValueObject, DomainEvent)
- [ ] Symbol entity with all validation
- [ ] Trade entity with invariants
- [ ] TickerData entity with calculations
- [ ] Domain events for symbols
- [ ] TickValidator service
- [ ] Unit tests pass (90%+ domain coverage)
- [ ] All type hints present
- [ ] All docstrings present
- [ ] Layer separation clear

---

## Verification Commands

```bash
# Run domain layer tests
pytest tests/unit/domain/ -v --cov=src/domain --cov-fail-under=90

# Type checking
mypy src/domain

# Linting
ruff check src/domain
```

---

## Next Step

After completing this step, proceed to **[Step 004: Data Collection Service](004-data-collection-service.md)**
