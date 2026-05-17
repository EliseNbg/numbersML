"""Domain models for strategy trade signals.

Trade signals are emitted by strategies during pipeline execution
and routed to the MarketService for order placement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class SignalStatus(str, Enum):  # noqa: UP042
    """Lifecycle status of a trade signal."""

    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TradeSignal:
    """Signal emitted by a strategy during pipeline execution.

    Attributes:
        signal_id: Unique identifier for the signal
        strategy_id: UUID of the originating strategy
        strategy_name: Human-readable strategy name
        symbol: Trading pair (e.g., 'BTC/USDC')
        side: BUY or SELL
        order_type: MARKET or LIMIT
        quantity: Order quantity
        price: Limit price (None for MARKET orders)
        timestamp: When the signal was generated
        metadata: Additional context (expected_profit_price, reason, etc.)
        status: Current signal status
    """

    signal_id: UUID = field(default_factory=uuid4)
    strategy_id: UUID = field(default_factory=uuid4)
    strategy_name: str = ""
    symbol: str = ""
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: Decimal = Decimal("0")
    price: Decimal | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    status: SignalStatus = SignalStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        """Convert signal to dictionary for serialization."""
        return {
            "signal_id": str(self.signal_id),
            "strategy_id": str(self.strategy_id),
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": float(self.quantity),
            "price": float(self.price) if self.price is not None else None,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeSignal:
        """Create TradeSignal from dictionary."""
        return cls(
            signal_id=UUID(data["signal_id"]) if isinstance(data["signal_id"], str) else data["signal_id"],
            strategy_id=UUID(data["strategy_id"]) if isinstance(data["strategy_id"], str) else data["strategy_id"],
            strategy_name=data.get("strategy_name", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", "BUY"),
            order_type=data.get("order_type", "MARKET"),
            quantity=Decimal(str(data.get("quantity", 0))),
            price=Decimal(str(data["price"])) if data.get("price") is not None else None,
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data.get("timestamp"), str) else data.get("timestamp", datetime.now(UTC)),
            metadata=data.get("metadata", {}),
            status=SignalStatus(data.get("status", "PENDING")),
        )
