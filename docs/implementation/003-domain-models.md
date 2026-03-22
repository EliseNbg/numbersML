# Step 003: Domain Models

## Context

**Phase**: 1 - Foundation  
**Effort**: 4 hours  
**Dependencies**: Step 002 (Database Schema) completed

---

## Goal

Implement the domain layer with entities, value objects, domain events, and domain services following DDD principles.

---

## Domain Model

### Core Entities

```
┌────────────────────────────────────────────────────────────────┐
│                         DOMAIN ENTITIES                         │
│                                                                 │
│  Symbol ──┬── Trade ──┬── TickIndicators                       │
│           │           │                                         │
│           │           └── IndicatorDefinition                   │
│           │                                                   │
│           └── RecalculationJob                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Implementation Tasks

### Task 3.1: Base Classes

**File**: `src/domain/models/base.py`

```python
"""Base classes for domain models."""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Entity(ABC):
    """Base class for all entities."""
    
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Entity):
            return False
        if self.id is None or other.id is None:
            return False
        return self.id == other.id
    
    def __hash__(self) -> int:
        return hash(self.id) if self.id else id(self)


@dataclass(frozen=True)
class ValueObject(ABC):
    """Base class for all value objects."""
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ValueObject):
            return False
        return self.__dict__ == other.__dict__
    
    def __hash__(self) -> int:
        return hash(tuple(self.__dict__.values()))


@dataclass(frozen=True)
class DomainEvent:
    """Base class for domain events."""
    
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def event_type(self) -> str:
        """Get event type from class name."""
        return self.__class__.__name__
```

---

### Task 3.2: Symbol Entity

**File**: `src/domain/models/symbol.py`

```python
"""Symbol entity."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .base import Entity


@dataclass
class Symbol(Entity):
    """
    Trading pair symbol (e.g., BTC/USDT).
    
    Invariants:
    - symbol must be unique (format: BASE/QUOTE)
    - tick_size > 0
    - step_size > 0
    - min_notional >= 0
    """
    
    symbol: str = ""
    base_asset: str = ""
    quote_asset: str = ""
    exchange: str = "binance"
    tick_size: Decimal = field(default_factory=lambda: Decimal("0.00000001"))
    step_size: Decimal = field(default_factory=lambda: Decimal("0.00000001"))
    min_notional: Decimal = field(default_factory=lambda: Decimal("10"))
    is_active: bool = False
    
    def __post_init__(self):
        """Validate invariants."""
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.step_size <= 0:
            raise ValueError("step_size must be positive")
        if self.min_notional < 0:
            raise ValueError("min_notional must be non-negative")
        if not self._is_valid_symbol_format():
            raise ValueError(f"Invalid symbol format: {self.symbol}")
    
    def _is_valid_symbol_format(self) -> bool:
        """Validate symbol format (BASE/QUOTE)."""
        if not self.symbol:
            return False
        parts = self.symbol.split('/')
        return len(parts) == 2 and all(parts)
    
    @property
    def base(self) -> str:
        """Get base asset (e.g., BTC from BTC/USDT)."""
        return self.base_asset
    
    @property
    def quote(self) -> str:
        """Get quote asset (e.g., USDT from BTC/USDT)."""
        return self.quote_asset
    
    def activate(self) -> None:
        """Activate symbol for data collection."""
        self.is_active = True
    
    def deactivate(self) -> None:
        """Deactivate symbol (stop data collection)."""
        self.is_active = False
    
    def price_to_tick(self, price: Decimal) -> Decimal:
        """Round price to tick size."""
        return (price / self.tick_size).quantize(Decimal('1')) * self.tick_size
    
    def quantity_to_step(self, quantity: Decimal) -> Decimal:
        """Round quantity to step size."""
        return (quantity / self.step_size).quantize(Decimal('1')) * self.step_size
    
    def is_valid_order(self, price: Decimal, quantity: Decimal) -> tuple[bool, str]:
        """
        Validate order parameters.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        notional = price * quantity
        
        if notional < self.min_notional:
            return False, f"Order value {notional} below minimum {self.min_notional}"
        
        if self.price_to_tick(price) != price:
            return False, f"Price not aligned with tick size {self.tick_size}"
        
        if self.quantity_to_step(quantity) != quantity:
            return False, f"Quantity not aligned with step size {self.step_size}"
        
        return True, ""
```

---

### Task 3.3: Trade Entity

**File**: `src/domain/models/trade.py`

```python
"""Trade entity."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .base import Entity, ValueObject


class TradeId(ValueObject):
    """Trade ID value object."""
    
    value: str
    
    def __post_init__(self):
        if not self.value:
            raise ValueError("Trade ID cannot be empty")


@dataclass
class Trade(Entity):
    """
    Individual trade (tick).
    
    Invariants:
    - price > 0
    - quantity > 0
    - side must be 'BUY' or 'SELL'
    """
    
    time: datetime = datetime.utcnow
    symbol_id: int = 0
    trade_id: str = ""  # Exchange trade ID
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    side: str = ""
    is_buyer_maker: bool = False
    
    def __post_init__(self):
        """Validate invariants."""
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.side not in ('BUY', 'SELL'):
            raise ValueError(f"Invalid side: {self.side}")
    
    @property
    def notional(self) -> Decimal:
        """Calculate notional value (price * quantity)."""
        return self.price * self.quantity
    
    def is_buy(self) -> bool:
        """Check if this is a buy trade."""
        return self.side == 'BUY'
    
    def is_sell(self) -> bool:
        """Check if this is a sell trade."""
        return self.side == 'SELL'
```

---

### Task 3.4: Indicator Definition Entity

**File**: `src/domain/models/indicator.py`

```python
"""Indicator Definition entity."""

from dataclasses import dataclass, field
from typing import Dict, List, Any
import hashlib
import inspect

from .base import Entity


@dataclass
class IndicatorDefinition(Entity):
    """
    Indicator definition (metadata + configuration).
    
    Supports dynamic indicators - can add/change without schema changes.
    """
    
    name: str = ""
    class_name: str = ""
    module_path: str = ""
    category: str = ""  # 'trend', 'momentum', 'volatility', 'volume'
    params_schema: Dict = field(default_factory=dict)
    params: Dict = field(default_factory=dict)
    code_hash: str = ""
    code_version: int = 1
    description: str = ""
    input_fields: List[str] = field(default_factory=lambda: ["price", "volume"])
    output_fields: List[str] = field(default_factory=list)
    is_active: bool = True
    last_calculated_at: datetime = None
    
    def __post_init__(self):
        """Validate invariants."""
        if not self.name:
            raise ValueError("name is required")
        if not self.class_name:
            raise ValueError("class_name is required")
        if not self.module_path:
            raise ValueError("module_path is required")
        if not self.category:
            raise ValueError("category is required")
    
    def update_params(self, new_params: Dict) -> None:
        """
        Update parameters (triggers version increment).
        
        This will trigger recalculation of historical data.
        """
        self.params = new_params
        self.code_version += 1
        # code_hash stays the same for param changes
    
    def update_code(self, new_code_hash: str) -> None:
        """
        Update code hash (indicates code change).
        
        This will trigger recalculation of historical data.
        """
        self.code_hash = new_code_hash
        self.code_version += 1
    
    def mark_calculated(self) -> None:
        """Mark indicator as calculated."""
        from datetime import datetime
        self.last_calculated_at = datetime.utcnow()
    
    @classmethod
    def from_indicator_class(cls, indicator_class: type, params: Dict) -> "IndicatorDefinition":
        """Create IndicatorDefinition from Python indicator class."""
        instance = indicator_class(**params)
        
        return cls(
            name=instance.name,
            class_name=indicator_class.__name__,
            module_path=indicator_class.__module__,
            category=instance.category or 'custom',
            params_schema=instance.params_schema(),
            params=params,
            code_hash=instance.get_code_hash(),
            description=instance.description or '',
            input_fields=['price', 'volume'],  # Default
            output_fields=list(instance.calculate.__annotations__.get('return', [])),
        )
```

---

### Task 3.5: Tick Indicators Entity

**File**: `src/domain/models/tick_indicators.py`

```python
"""Tick Indicators entity."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

from .base import Entity


@dataclass
class TickIndicators(Entity):
    """
    Enriched tick data with indicator values.
    
    Stores all indicator values for a specific time+symbol.
    Uses JSONB for flexibility (any number of indicators).
    """
    
    time: datetime = datetime.utcnow
    symbol_id: int = 0
    price: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    values: Dict[str, float] = field(default_factory=dict)
    indicator_keys: List[str] = field(default_factory=list)
    indicator_version: int = 1
    
    def __post_init__(self):
        """Validate invariants."""
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
    
    def add_indicator(self, name: str, value: float) -> None:
        """Add or update indicator value."""
        self.values[name] = value
        if name not in self.indicator_keys:
            self.indicator_keys.append(name)
    
    def get_indicator(self, name: str) -> float | None:
        """Get indicator value by name."""
        return self.values.get(name)
    
    def has_indicator(self, name: str) -> bool:
        """Check if indicator exists."""
        return name in self.values
    
    @property
    def indicator_count(self) -> int:
        """Get number of indicators."""
        return len(self.values)
```

---

### Task 3.6: Domain Events

**File**: `src/domain/events/indicator_events.py`

```python
"""Indicator-related domain events."""

from dataclasses import dataclass
from datetime import datetime

from ..models.base import DomainEvent


@dataclass
class IndicatorChangedEvent(DomainEvent):
    """
    Raised when an indicator definition changes.
    
    Triggers automatic recalculation of historical data.
    """
    
    indicator_id: int = 0
    indicator_name: str = ""
    change_type: str = ""  # 'code_changed' or 'params_changed'
    old_code_hash: str = ""
    new_code_hash: str = ""
    old_params: dict = None
    new_params: dict = None


@dataclass
class IndicatorCalculatedEvent(DomainEvent):
    """
    Raised when indicator recalculation completes.
    """
    
    indicator_id: int = 0
    indicator_name: str = ""
    ticks_processed: int = 0
    duration_seconds: float = 0.0
    success: bool = True
```

**File**: `src/domain/events/symbol_events.py`

```python
"""Symbol-related domain events."""

from dataclasses import dataclass

from ..models.base import DomainEvent


@dataclass
class SymbolActivatedEvent(DomainEvent):
    """Raised when a symbol is activated."""
    
    symbol_id: int = 0
    symbol_name: str = ""


@dataclass
class SymbolDeactivatedEvent(DomainEvent):
    """Raised when a symbol is deactivated."""
    
    symbol_id: int = 0
    symbol_name: str = ""
```

---

### Task 3.7: Domain Services

**File**: `src/domain/services/indicator_service.py`

```python
"""Indicator domain service."""

from typing import List, Dict, Any
from datetime import datetime
import hashlib

from ..models.indicator import IndicatorDefinition
from ..events.indicator_events import IndicatorChangedEvent


class IndicatorService:
    """
    Domain service for indicator management.
    
    Handles business logic that doesn't fit in a single entity.
    """
    
    def __init__(self, event_publisher=None):
        self.event_publisher = event_publisher
    
    def create_indicator(
        self,
        name: str,
        class_name: str,
        module_path: str,
        category: str,
        params: Dict[str, Any],
        description: str = ""
    ) -> IndicatorDefinition:
        """
        Create a new indicator definition.
        
        Publishes: IndicatorChangedEvent
        """
        indicator = IndicatorDefinition(
            name=name,
            class_name=class_name,
            module_path=module_path,
            category=category,
            params=params,
            code_hash=self._generate_code_hash(class_name, module_path),
            description=description,
        )
        
        # Publish event
        if self.event_publisher:
            self.event_publisher.publish(
                IndicatorChangedEvent(
                    indicator_id=indicator.id or 0,
                    indicator_name=name,
                    change_type='created',
                )
            )
        
        return indicator
    
    def update_params(
        self,
        indicator: IndicatorDefinition,
        new_params: Dict[str, Any]
    ) -> IndicatorChangedEvent:
        """
        Update indicator parameters.
        
        Returns event that should be published.
        """
        old_params = indicator.params.copy()
        old_version = indicator.code_version
        
        indicator.update_params(new_params)
        
        return IndicatorChangedEvent(
            indicator_id=indicator.id or 0,
            indicator_name=indicator.name,
            change_type='params_changed',
            old_params=old_params,
            new_params=new_params,
        )
    
    def _generate_code_hash(self, class_name: str, module_path: str) -> str:
        """Generate hash from indicator code."""
        # In real implementation, would load and hash actual source
        source = f"{module_path}.{class_name}"
        return hashlib.sha256(source.encode()).hexdigest()
```

**File**: `src/domain/services/__init__.py`

```python
"""Domain services."""

from .indicator_service import IndicatorService

__all__ = ["IndicatorService"]
```

---

### Task 3.8: Domain Module Exports

**File**: `src/domain/__init__.py`

```python
"""Domain layer."""

from .models.base import Entity, ValueObject, DomainEvent
from .models.symbol import Symbol
from .models.trade import Trade, TradeId
from .models.indicator import IndicatorDefinition
from .models.tick_indicators import TickIndicators
from .events.indicator_events import IndicatorChangedEvent, IndicatorCalculatedEvent
from .events.symbol_events import SymbolActivatedEvent, SymbolDeactivatedEvent
from .services.indicator_service import IndicatorService

__all__ = [
    # Base
    "Entity",
    "ValueObject",
    "DomainEvent",
    
    # Entities
    "Symbol",
    "Trade",
    "TradeId",
    "IndicatorDefinition",
    "TickIndicators",
    
    # Events
    "IndicatorChangedEvent",
    "IndicatorCalculatedEvent",
    "SymbolActivatedEvent",
    "SymbolDeactivatedEvent",
    
    # Services
    "IndicatorService",
]
```

---

## Test Requirements

### Test Coverage Target: **90%**

### Unit Tests

**File**: `tests/unit/domain/models/test_symbol.py`

```python
"""Test Symbol entity."""

import pytest
from decimal import Decimal
from src.domain.models.symbol import Symbol


class TestSymbol:
    """Test Symbol entity."""
    
    def test_create_valid_symbol(self):
        """Test creating a valid symbol."""
        symbol = Symbol(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
        )
        
        assert symbol.symbol == "BTC/USDT"
        assert symbol.base_asset == "BTC"
        assert symbol.quote_asset == "USDT"
        assert symbol.is_active is False
    
    def test_symbol_must_have_valid_format(self):
        """Test symbol format validation."""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol(symbol="INVALID", base_asset="BTC", quote_asset="USDT")
    
    def test_tick_size_must_be_positive(self):
        """Test tick_size validation."""
        with pytest.raises(ValueError, match="tick_size must be positive"):
            Symbol(
                symbol="BTC/USDT",
                base_asset="BTC",
                quote_asset="USDT",
                tick_size=Decimal("-0.01"),
            )
    
    def test_activate_symbol(self):
        """Test activating a symbol."""
        symbol = Symbol(symbol="BTC/USDT", base_asset="BTC", quote_asset="USDT")
        
        symbol.activate()
        
        assert symbol.is_active is True
    
    def test_deactivate_symbol(self):
        """Test deactivating a symbol."""
        symbol = Symbol(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            is_active=True
        )
        
        symbol.deactivate()
        
        assert symbol.is_active is False
    
    def test_price_to_tick(self):
        """Test rounding price to tick size."""
        symbol = Symbol(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
        )
        
        result = symbol.price_to_tick(Decimal("50123.456"))
        
        assert result == Decimal("50123.46")
    
    def test_is_valid_order(self):
        """Test order validation."""
        symbol = Symbol(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            min_notional=Decimal("10"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.001"),
        )
        
        # Valid order
        is_valid, error = symbol.is_valid_order(
            Decimal("50000.00"),
            Decimal("0.001")
        )
        assert is_valid is True
        assert error == ""
        
        # Invalid - below minimum
        is_valid, error = symbol.is_valid_order(
            Decimal("50000.00"),
            Decimal("0.0001")
        )
        assert is_valid is False
        assert "below minimum" in error
```

**File**: `tests/unit/domain/models/test_trade.py`

```python
"""Test Trade entity."""

import pytest
from decimal import Decimal
from datetime import datetime
from src.domain.models.trade import Trade


class TestTrade:
    """Test Trade entity."""
    
    def test_create_valid_trade(self):
        """Test creating a valid trade."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="123456",
            price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
            is_buyer_maker=False,
        )
        
        assert trade.price == Decimal("50000.00")
        assert trade.quantity == Decimal("0.001")
        assert trade.side == "BUY"
        assert trade.is_buy() is True
    
    def test_price_must_be_positive(self):
        """Test price validation."""
        with pytest.raises(ValueError, match="price must be positive"):
            Trade(
                time=datetime.utcnow(),
                symbol_id=1,
                trade_id="123",
                price=Decimal("0"),
                quantity=Decimal("0.001"),
                side="BUY",
            )
    
    def test_side_must_be_buy_or_sell(self):
        """Test side validation."""
        with pytest.raises(ValueError, match="Invalid side"):
            Trade(
                time=datetime.utcnow(),
                symbol_id=1,
                trade_id="123",
                price=Decimal("50000"),
                quantity=Decimal("0.001"),
                side="INVALID",
            )
    
    def test_notional_calculation(self):
        """Test notional value calculation."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="123",
            price=Decimal("50000"),
            quantity=Decimal("0.002"),
            side="BUY",
        )
        
        assert trade.notional == Decimal("100")
```

**File**: `tests/unit/domain/models/test_indicator.py`

```python
"""Test IndicatorDefinition entity."""

import pytest
from src.domain.models.indicator import IndicatorDefinition


class TestIndicatorDefinition:
    """Test IndicatorDefinition entity."""
    
    def test_create_valid_indicator(self):
        """Test creating a valid indicator."""
        indicator = IndicatorDefinition(
            name="rsi_14",
            class_name="RSIIndicator",
            module_path="indicators.momentum",
            category="momentum",
            params={"period": 14},
        )
        
        assert indicator.name == "rsi_14"
        assert indicator.category == "momentum"
        assert indicator.params == {"period": 14}
        assert indicator.is_active is True
    
    def test_name_is_required(self):
        """Test name validation."""
        with pytest.raises(ValueError, match="name is required"):
            IndicatorDefinition(
                name="",
                class_name="RSIIndicator",
                module_path="indicators.momentum",
                category="momentum",
            )
    
    def test_update_params_increments_version(self):
        """Test updating params increments version."""
        indicator = IndicatorDefinition(
            name="rsi_14",
            class_name="RSIIndicator",
            module_path="indicators.momentum",
            category="momentum",
            params={"period": 14},
        )
        
        initial_version = indicator.code_version
        
        indicator.update_params({"period": 21})
        
        assert indicator.code_version == initial_version + 1
        assert indicator.params == {"period": 21}
```

**File**: `tests/unit/domain/services/test_indicator_service.py`

```python
"""Test IndicatorService."""

import pytest
from src.domain.services.indicator_service import IndicatorService
from src.domain.events.indicator_events import IndicatorChangedEvent


class MockEventPublisher:
    """Mock event publisher for testing."""
    
    def __init__(self):
        self.events = []
    
    def publish(self, event):
        self.events.append(event)


class TestIndicatorService:
    """Test IndicatorService."""
    
    def test_create_indicator(self):
        """Test creating an indicator."""
        publisher = MockEventPublisher()
        service = IndicatorService(event_publisher=publisher)
        
        indicator = service.create_indicator(
            name="rsi_14",
            class_name="RSIIndicator",
            module_path="indicators.momentum",
            category="momentum",
            params={"period": 14},
        )
        
        assert indicator.name == "rsi_14"
        assert indicator.code_version == 1
        assert len(publisher.events) == 1
        assert isinstance(publisher.events[0], IndicatorChangedEvent)
    
    def test_update_params_returns_event(self):
        """Test updating params returns event."""
        service = IndicatorService()
        
        indicator = IndicatorDefinition(
            name="rsi_14",
            class_name="RSIIndicator",
            module_path="indicators.momentum",
            category="momentum",
            params={"period": 14},
        )
        
        event = service.update_params(indicator, {"period": 21})
        
        assert isinstance(event, IndicatorChangedEvent)
        assert event.change_type == 'params_changed'
        assert event.old_params == {"period": 14}
        assert event.new_params == {"period": 21}
```

---

## Acceptance Criteria

- [ ] Base classes (Entity, ValueObject, DomainEvent) implemented
- [ ] Symbol entity with all business logic
- [ ] Trade entity with validation
- [ ] IndicatorDefinition entity with versioning
- [ ] TickIndicators entity for storing values
- [ ] Domain events for indicators and symbols
- [ ] IndicatorService domain service
- [ ] Unit tests pass (90%+ coverage)
- [ ] All invariants enforced
- [ ] No external dependencies in domain layer

---

## Verification Commands

```bash
# Run domain layer tests
pytest tests/unit/domain/ -v --cov=src/domain --cov-fail-under=90

# Type checking
mypy src/domain

# Verify no infrastructure dependencies
# (domain layer should be pure Python)
```

---

## Next Step

After completing this step, proceed to **[004-data-collection-service.md](004-data-collection-service.md)**
