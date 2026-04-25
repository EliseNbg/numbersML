"""Unit tests for live market service."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.domain.market.order import OrderRequest, OrderSide, OrderStatus, OrderType
from src.infrastructure.market.live_market_service import LiveMarketService


@pytest.mark.unit
class TestLiveMarketService:
    """Validate live execution guardrails and adapter behavior."""

    @pytest.mark.asyncio
    async def test_live_execution_disabled_raises(self) -> None:
        client = AsyncMock()
        service = LiveMarketService(exchange_client=client, execution_enabled=False)

        with pytest.raises(RuntimeError, match="Live execution is disabled"):
            await service.place_order(
                OrderRequest(
                    symbol="BTC/USDC",
                    side=OrderSide.BUY,
                    quantity=Decimal("0.1"),
                    order_type=OrderType.MARKET,
                )
            )

    @pytest.mark.asyncio
    async def test_place_order_retries_then_succeeds(self) -> None:
        client = AsyncMock()
        client.create_order.side_effect = [
            RuntimeError("temporary outage"),
            {
                "orderId": "abc123",
                "status": "FILLED",
                "executedQty": "0.1",
                "avgPrice": "50000",
            },
        ]
        service = LiveMarketService(
            exchange_client=client,
            execution_enabled=True,
            max_retries=2,
            retry_delay_seconds=0.0,
        )

        order = await service.place_order(
            OrderRequest(
                symbol="BTC/USDC",
                side=OrderSide.BUY,
                quantity=Decimal("0.1"),
                order_type=OrderType.MARKET,
                client_order_id="client-1",
            )
        )

        assert order.status == OrderStatus.FILLED
        assert order.external_order_id == "abc123"
        assert client.create_order.call_count == 2

    @pytest.mark.asyncio
    async def test_idempotent_client_order_id_returns_existing_order(self) -> None:
        client = AsyncMock()
        client.create_order.return_value = {
            "orderId": "abc123",
            "status": "NEW",
            "executedQty": "0",
            "avgPrice": None,
        }
        service = LiveMarketService(exchange_client=client, execution_enabled=True)
        request = OrderRequest(
            symbol="ETH/USDC",
            side=OrderSide.SELL,
            quantity=Decimal("1.5"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("4000"),
            client_order_id="same-id",
        )

        order1 = await service.place_order(request)
        order2 = await service.place_order(request)

        assert order1.id == order2.id
        assert client.create_order.call_count == 1
