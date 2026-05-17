"""Domain models for market order execution."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class OrderSide(str, Enum):
    """Supported order sides."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    """Domain-level order lifecycle status."""

    NEW = "NEW"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class ExecutionMode(str, Enum):
    """Order execution mode."""

    PAPER = "paper"
    LIVE = "live"
    TESTNET = "testnet"
    BACKTEST = "backtest"


@dataclass(frozen=True)
class SymbolFilters:
    """Cached Binance exchange filters for a symbol."""

    symbol: str
    # PRICE_FILTER
    min_price: Decimal = Decimal("0")
    max_price: Decimal = Decimal("9999999999")
    tick_size: Decimal = Decimal("0.01")
    # LOT_SIZE
    min_qty: Decimal = Decimal("0")
    max_qty: Decimal = Decimal("9999999999")
    step_size: Decimal = Decimal("0.00001")
    # MARKET_LOT_SIZE (separate from LOT_SIZE)
    market_min_qty: Decimal = Decimal("0")
    market_max_qty: Decimal = Decimal("9999999999")
    market_step_size: Decimal = Decimal("0.00001")
    # NOTIONAL
    min_notional: Decimal = Decimal("10")
    max_notional: Decimal = Decimal("9999999999")
    # PERCENT_PRICE_BY_SIDE
    bid_multiplier_up: Decimal = Decimal("1.3")
    bid_multiplier_down: Decimal = Decimal("0.7")
    ask_multiplier_up: Decimal = Decimal("5.0")
    ask_multiplier_down: Decimal = Decimal("0.8")
    # Other
    max_num_orders: int = 200
    max_position: Decimal = Decimal("9999999999")


@dataclass(frozen=True)
class OrderRequest:
    """Input request for order placement."""

    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    limit_price: Decimal | None = None
    client_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Order:
    """Order execution result and status payload."""

    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: Decimal = Decimal("0")
    requested_price: Decimal | None = None
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    status: OrderStatus = OrderStatus.NEW
    mode: str = "paper"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    client_order_id: str | None = None
    external_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    """Simple position snapshot returned by market services."""

    symbol: str
    quantity: Decimal
    average_entry_price: Decimal
    side: OrderSide


@dataclass(frozen=True)
class Balance:
    """Simple account balance snapshot."""

    asset: str
    free: Decimal
    locked: Decimal
