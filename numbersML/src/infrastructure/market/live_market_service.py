"""Live trading market service backed by exchange client."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.domain.market.order import Balance, Order, OrderRequest, OrderStatus, Position
from src.domain.services.market_service import LiveExchangeClient, MarketService


class LiveMarketService(MarketService):
    """Exchange-backed market service with guarded execution and retries."""

    def __init__(
        self,
        exchange_client: LiveExchangeClient,
        execution_enabled: bool = False,
        max_retries: int = 2,
        retry_delay_seconds: float = 0.2,
    ) -> None:
        self._exchange_client = exchange_client
        self._execution_enabled = execution_enabled
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._orders: dict[str, Order] = {}

    async def get_balance(self, asset: str) -> Balance:
        # Placeholder until account endpoint is implemented by exchange adapter.
        return Balance(asset=asset, free=Decimal("0"), locked=Decimal("0"))

    async def get_balances(self) -> dict[str, dict[str, Decimal]]:
        """Return all balances (placeholder until exchange adapter implements account endpoint)."""
        return {}

    async def get_positions(self) -> list[Position]:
        # Placeholder until account endpoint is implemented by exchange adapter.
        return []

    async def place_order(self, request: OrderRequest) -> Order:
        if not self._execution_enabled:
            raise RuntimeError("Live execution is disabled. Set execution_enabled=True explicitly.")

        client_order_id = request.client_order_id or self._default_client_order_id(request)
        existing = self._orders.get(client_order_id)
        if existing is not None:
            return existing

        payload = await self._retry_create_order(request, client_order_id)
        order = self._from_exchange_payload(request, payload, client_order_id)
        self._orders[client_order_id] = order
        if order.external_order_id:
            self._orders[order.external_order_id] = order
        self._orders[str(order.id)] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order is None or order.external_order_id is None:
            return False
        canceled = await self._exchange_client.cancel_order(order.symbol, order.external_order_id)
        if canceled:
            order.status = OrderStatus.CANCELED
            order.updated_at = datetime.now(UTC)
        return canceled

    async def get_order_status(self, order_id: str) -> Order | None:
        order = self._orders.get(order_id)
        if order is None:
            return None
        if order.external_order_id is None:
            return order
        payload = await self._exchange_client.get_order(order.symbol, order.external_order_id)
        if payload is None:
            return order
        refreshed = self._from_exchange_payload(
            OrderRequest(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                order_type=order.order_type,
                limit_price=order.requested_price,
                client_order_id=order.client_order_id or "",
            ),
            payload,
            order.client_order_id or "",
            fallback_id=order.id,
        )
        self._orders[order_id] = refreshed
        if refreshed.external_order_id:
            self._orders[refreshed.external_order_id] = refreshed
        return refreshed

    async def get_orders(self, filters: dict[str, Any] | None = None) -> list[Order]:
        """Fetch orders with optional filters (placeholder until exchange adapter implements)."""
        return list(self._orders.values())

    async def get_trades(self) -> list[Any]:
        """Fetch all trades/fills (placeholder until exchange adapter implements)."""
        return []

    async def _retry_create_order(self, request: OrderRequest, client_order_id: str) -> dict:
        last_exception: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._exchange_client.create_order(
                    symbol=request.symbol,
                    side=request.side.value,
                    order_type=request.order_type.value,
                    quantity=request.quantity,
                    price=request.limit_price,
                    client_order_id=client_order_id,
                )
            except Exception as exc:  # noqa: BLE001
                last_exception = exc
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(self._retry_delay_seconds * (attempt + 1))
        raise RuntimeError(f"Live order placement failed: {last_exception}") from last_exception

    @staticmethod
    def _default_client_order_id(request: OrderRequest) -> str:
        ts = int(datetime.now(UTC).timestamp() * 1000)
        return f"{request.symbol.replace('/', '')}-{request.side.value.lower()}-{ts}"

    def _from_exchange_payload(
        self,
        request: OrderRequest,
        payload: dict,
        client_order_id: str,
        fallback_id=None,
    ) -> Order:
        status_map = {
            "NEW": OrderStatus.NEW,
            "FILLED": OrderStatus.FILLED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "CANCELED": OrderStatus.CANCELED,
            "REJECTED": OrderStatus.REJECTED,
        }
        status = status_map.get(str(payload.get("status", "NEW")).upper(), OrderStatus.NEW)
        filled_qty = Decimal(str(payload.get("executedQty", "0")))
        avg_price = payload.get("avgPrice")
        avg_fill_price = Decimal(str(avg_price)) if avg_price not in (None, "") else None
        now = datetime.now(UTC)
        order = Order(
            id=fallback_id or uuid4(),
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            requested_price=request.limit_price,
            filled_quantity=filled_qty,
            average_fill_price=avg_fill_price,
            status=status,
            mode="live",
            created_at=now,
            updated_at=now,
            client_order_id=client_order_id,
            external_order_id=(
                str(payload.get("orderId")) if payload.get("orderId") is not None else None
            ),
            metadata={"exchange_payload": payload},
        )
        return order
