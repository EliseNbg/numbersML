"""
Trade entity - Individual trade (tick) representation.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from src.domain.models.base import Entity


@dataclass
class Trade(Entity):
    """
    Individual trade (tick).

    Attributes:
        time: Trade timestamp
        symbol_id: Reference to symbol
        trade_id: Exchange trade ID
        price: Trade price
        quantity: Trade quantity
        side: Trade side (BUY or SELL)
        is_buyer_maker: True if buyer was maker
    """

    time: datetime = field(default_factory=lambda: datetime.now(UTC))
    symbol_id: int = 0
    trade_id: str = ""
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    side: str = ""
    is_buyer_maker: bool = False

    def __post_init__(self) -> None:
        """Validate invariants."""
        if self.price <= 0:
            raise ValueError(f"price must be positive: {self.price}")
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive: {self.quantity}")
        if self.side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {self.side}")

    @property
    def notional(self) -> Decimal:
        """Calculate notional value."""
        return self.price * self.quantity

    def is_buy(self) -> bool:
        """Check if this is a buy trade."""
        return self.side == "BUY"

    def is_sell(self) -> bool:
        """Check if this is a sell trade."""
        return self.side == "SELL"
