"""Unit tests for BacktestMarketService."""
from decimal import Decimal

import pytest

from src.domain.market.order import OrderRequest, OrderSide, OrderStatus, OrderType
from src.infrastructure.market.backtest_market_service import BacktestMarketService


class TestBacktestMarketFill:
    """Tests for MARKET order fills."""

    def _make_service(self) -> BacktestMarketService:
        return BacktestMarketService(
            base_asset="USDC",
            initial_balance=Decimal("10000"),
            fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
        )

    @pytest.mark.asyncio
    async def test_backtest_market_fill_buy(self) -> None:
        service = self._make_service()
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            order_type=OrderType.MARKET,
            metadata={"market_price": "67000"},
        )

        order = await service.place_order(request)
        assert order.status == OrderStatus.FILLED
        assert order.mode == "backtest"
        assert order.average_fill_price is not None
        assert order.average_fill_price > Decimal("67000")

    @pytest.mark.asyncio
    async def test_backtest_market_fill_sell(self) -> None:
        service = self._make_service()
        service._balances["BTC"] = type(service._balances["USDC"])(
            asset="BTC", free=Decimal("1"), locked=Decimal("0")
        )
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.SELL,
            quantity=Decimal("0.01"),
            order_type=OrderType.MARKET,
            metadata={"market_price": "67000"},
        )

        order = await service.place_order(request)
        assert order.status == OrderStatus.FILLED
        assert order.average_fill_price is not None
        assert order.average_fill_price < Decimal("67000")


class TestBacktestLimitFill:
    """Tests for LIMIT order fills."""

    def _make_service(self) -> BacktestMarketService:
        return BacktestMarketService(
            base_asset="USDC",
            initial_balance=Decimal("10000"),
        )

    @pytest.mark.asyncio
    async def test_backtest_limit_fill_buy(self) -> None:
        service = self._make_service()
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("68000"),
            metadata={"market_price": "67000"},
        )

        order = await service.place_order(request)
        assert order.status == OrderStatus.FILLED
        assert order.average_fill_price == Decimal("68000")

    @pytest.mark.asyncio
    async def test_backtest_limit_fill_sell(self) -> None:
        service = self._make_service()
        service._balances["BTC"] = type(service._balances["USDC"])(
            asset="BTC", free=Decimal("1"), locked=Decimal("0")
        )
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.SELL,
            quantity=Decimal("0.01"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("66000"),
            metadata={"market_price": "67000"},
        )

        order = await service.place_order(request)
        assert order.status == OrderStatus.FILLED
        assert order.average_fill_price == Decimal("66000")

    @pytest.mark.asyncio
    async def test_backtest_rejected_order(self) -> None:
        service = self._make_service()
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("66000"),
            metadata={"market_price": "67000"},
        )

        order = await service.place_order(request)
        assert order.status == OrderStatus.REJECTED
        assert order.metadata.get("reason") == "price_not_reached"


class TestBacktestSlippageAndFees:
    """Tests for slippage and fee application."""

    def _make_service(self) -> BacktestMarketService:
        return BacktestMarketService(
            base_asset="USDC",
            initial_balance=Decimal("10000"),
            fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
        )

    @pytest.mark.asyncio
    async def test_backtest_slippage_applied(self) -> None:
        service = self._make_service()
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            order_type=OrderType.MARKET,
            metadata={"market_price": "67000"},
        )

        order = await service.place_order(request)
        assert order.average_fill_price is not None
        slippage = order.average_fill_price - Decimal("67000")
        assert slippage > 0

    @pytest.mark.asyncio
    async def test_backtest_fee_deducted(self) -> None:
        service = self._make_service()
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            order_type=OrderType.MARKET,
            metadata={"market_price": "67000"},
        )

        balance_before = (await service.get_balance("USDC")).free
        await service.place_order(request)
        balance_after = (await service.get_balance("USDC")).free

        notional = Decimal("67000") * Decimal("0.01")

        assert balance_before - balance_after > notional

    @pytest.mark.asyncio
    async def test_backtest_portfolio_tracking(self) -> None:
        service = self._make_service()
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            order_type=OrderType.MARKET,
            metadata={"market_price": "67000"},
        )

        await service.place_order(request)
        positions = await service.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USDC"
        assert positions[0].quantity == Decimal("0.1")

        balances = await service.get_balances()
        assert "BTC" in balances
        assert balances["BTC"]["free"] == Decimal("0.1")
