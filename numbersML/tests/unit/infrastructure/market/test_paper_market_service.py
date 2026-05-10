"""Unit tests for paper market service."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.market.order import Order, OrderRequest, OrderSide, OrderStatus, OrderType
from src.infrastructure.market.paper_market_service import PaperMarketService


@pytest.mark.unit
class TestPaperMarketService:
    """Validate deterministic paper-mode execution behavior."""

    @pytest.mark.asyncio
    async def test_place_buy_order_updates_balance_and_positions(self) -> None:
        service = PaperMarketService(initial_balance=Decimal("10000"))
        order = await service.place_order(
            OrderRequest(
                symbol="BTC/USDC",
                side=OrderSide.BUY,
                quantity=Decimal("1"),
                order_type=OrderType.MARKET,
                metadata={"market_price": "100"},
            )
        )

        quote_balance = await service.get_balance("USDC")
        positions = await service.get_positions()

        assert order.status == OrderStatus.FILLED
        assert quote_balance.free < Decimal("10000")
        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USDC"

    @pytest.mark.asyncio
    async def test_insufficient_buy_balance_rejects_order(self) -> None:
        service = PaperMarketService(initial_balance=Decimal("1"))
        order = await service.place_order(
            OrderRequest(
                symbol="BTC/USDC",
                side=OrderSide.BUY,
                quantity=Decimal("1"),
                order_type=OrderType.MARKET,
                metadata={"market_price": "100"},
            )
        )

        assert order.status == OrderStatus.REJECTED
        assert order.metadata["reason"] == "insufficient_balance"

    @pytest.mark.asyncio
    async def test_cancel_pending_order(self) -> None:
        service = PaperMarketService()
        pending_order = Order(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            status=OrderStatus.NEW,
            mode="paper",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        service.seed_order(pending_order)

        canceled = await service.cancel_order(str(pending_order.id))
        status = await service.get_order_status(str(pending_order.id))

        assert canceled is True
        assert status is not None
        assert status.status == OrderStatus.CANCELED
