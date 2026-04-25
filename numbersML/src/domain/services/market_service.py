"""Domain contract for market execution services."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Protocol

from src.domain.market.order import Balance, Order, OrderRequest, Position


class MarketService(ABC):
    """Abstraction for paper and live market execution."""

    @abstractmethod
    async def get_balance(self, asset: str) -> Balance:
        """Return account balance snapshot for an asset."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Return all open positions."""

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> Order:
        """Place an order and return order status payload."""

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order by internal or external identifier."""

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order | None:
        """Fetch order status by internal or external identifier."""


class LiveExchangeClient(Protocol):
    """Minimal exchange client protocol needed by live market service."""

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None,
        client_order_id: str,
    ) -> dict:
        """Create exchange order and return payload."""

    async def cancel_order(self, symbol: str, exchange_order_id: str) -> bool:
        """Cancel exchange order and return success flag."""

    async def get_order(self, symbol: str, exchange_order_id: str) -> dict | None:
        """Fetch exchange order payload by id."""
