"""Unit tests for BacktestMarketService."""
from datetime import UTC, datetime
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


class TestTPSLTracking:
    """Tests for take-profit / stop-loss position tracking."""

    def _make_service(self) -> BacktestMarketService:
        return BacktestMarketService(
            base_asset="USDC",
            initial_balance=Decimal("10000"),
            fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
        )

    @pytest.mark.asyncio
    async def test_register_position_stores_tracked_position(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        pos = service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("55000"),
            stop_loss=Decimal("48000"),
        )

        assert pos.symbol == "BTC/USDC"
        assert pos.take_profit == Decimal("55000")
        assert pos.stop_loss == Decimal("48000")

        tracked = service.get_tracked_positions()
        assert len(tracked) == 1
        assert tracked[0].symbol == "BTC/USDC"

    @pytest.mark.asyncio
    async def test_register_position_by_symbol(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
        )
        service.register_position(
            symbol="ETH/USDC",
            side="LONG",
            quantity=Decimal("1.0"),
            entry_price=Decimal("3000"),
            entry_time=entry_time,
        )

        assert len(service.get_tracked_positions("BTC/USDC")) == 1
        assert len(service.get_tracked_positions("ETH/USDC")) == 1
        assert len(service.get_tracked_positions()) == 2

    @pytest.mark.asyncio
    async def test_check_positions_take_profit_hit(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("52000"),
        )

        current_prices = {"BTC/USDC": Decimal("52100")}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 1
        assert closed[0].exit_reason == "take_profit"
        assert closed[0].symbol == "BTC/USDC"
        assert closed[0].entry_price == Decimal("50000")
        # Exit price should have slippage applied (slightly below current for LONG)
        assert closed[0].exit_price < Decimal("52100")
        assert closed[0].pnl > 0

        # Position should be removed from tracking
        assert len(service.get_tracked_positions()) == 0

    @pytest.mark.asyncio
    async def test_check_positions_stop_loss_hit(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            stop_loss=Decimal("48000"),
        )

        current_prices = {"BTC/USDC": Decimal("47900")}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 1
        assert closed[0].exit_reason == "stop_loss"
        assert closed[0].pnl < 0

    @pytest.mark.asyncio
    async def test_check_positions_no_exit(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("55000"),
            stop_loss=Decimal("48000"),
        )

        # Price between SL and TP — no exit
        current_prices = {"BTC/USDC": Decimal("51000")}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 0
        assert len(service.get_tracked_positions()) == 1

    @pytest.mark.asyncio
    async def test_check_positions_missing_price_skipped(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("52000"),
        )

        # No price for BTC/USDC
        current_prices: dict[str, Decimal] = {}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 0
        assert len(service.get_tracked_positions()) == 1

    @pytest.mark.asyncio
    async def test_check_positions_multiple_positions(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("52000"),
        )
        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.05"),
            entry_price=Decimal("50500"),
            entry_time=entry_time,
            take_profit=Decimal("53000"),
        )

        current_prices = {"BTC/USDC": Decimal("52500")}
        closed = service.check_positions(current_prices, exit_time)

        # Only first position should hit TP (52000 <= 52500)
        # Second position TP is 53000 > 52500, so not hit
        assert len(closed) == 1
        assert closed[0].entry_price == Decimal("50000")
        assert len(service.get_tracked_positions()) == 1

    @pytest.mark.asyncio
    async def test_check_positions_metadata_carried(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("52000"),
            metadata={"grid_index": 3, "entry_time": entry_time},
        )

        current_prices = {"BTC/USDC": Decimal("52100")}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 1
        assert closed[0].metadata.get("grid_index") == 3
        assert closed[0].metadata.get("entry_time") == entry_time

    @pytest.mark.asyncio
    async def test_check_positions_balance_updated_on_close(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        # First buy to establish position
        buy_request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            order_type=OrderType.MARKET,
            metadata={"market_price": "50000"},
        )
        await service.place_order(buy_request)

        # Also register for TP/SL tracking
        service.register_position(
            symbol="BTC/USDC",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("52000"),
            entry_fees=Decimal("5"),
        )

        balance_before = (await service.get_balance("USDC")).free

        current_prices = {"BTC/USDC": Decimal("52100")}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 1
        balance_after = (await service.get_balance("USDC")).free
        # Balance should increase (profit from TP hit)
        assert balance_after > balance_before

    @pytest.mark.asyncio
    async def test_short_position_take_profit(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="SHORT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            take_profit=Decimal("48000"),
        )

        # Price dropped below TP — should trigger
        current_prices = {"BTC/USDC": Decimal("47900")}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 1
        assert closed[0].exit_reason == "take_profit"
        assert closed[0].pnl > 0

    @pytest.mark.asyncio
    async def test_short_position_stop_loss(self) -> None:
        service = self._make_service()
        entry_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        exit_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        service.register_position(
            symbol="BTC/USDC",
            side="SHORT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            stop_loss=Decimal("52000"),
        )

        # Price rose above SL — should trigger
        current_prices = {"BTC/USDC": Decimal("52100")}
        closed = service.check_positions(current_prices, exit_time)

        assert len(closed) == 1
        assert closed[0].exit_reason == "stop_loss"
        assert closed[0].pnl < 0
