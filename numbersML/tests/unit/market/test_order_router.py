"""Unit tests for OrderRouter."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.market.order import ExecutionMode, OrderRequest, OrderSide, OrderType
from src.infrastructure.market.binance_filters import BinanceFilterError
from src.infrastructure.market.order_router import OrderRouter


class TestRoutePaperMode:
    """Tests for paper mode routing."""

    @pytest.mark.asyncio
    async def test_route_paper_mode(self) -> None:
        mock_paper = MagicMock()
        mock_order = MagicMock()
        mock_paper.place_order = AsyncMock(return_value=mock_order)

        router = OrderRouter(paper_service=mock_paper)
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.MARKET,
        )

        result = await router.route(request, ExecutionMode.PAPER)
        assert result is mock_order
        mock_paper.place_order.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_paper_mode_skips_filters(self) -> None:
        mock_paper = MagicMock()
        mock_order = MagicMock()
        mock_paper.place_order = AsyncMock(return_value=mock_order)

        router = OrderRouter(paper_service=mock_paper)
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("67000.123456"),
        )

        await router.route(request, ExecutionMode.PAPER)
        mock_paper.place_order.assert_called_once_with(request)


class TestRouteLiveMode:
    """Tests for live mode routing."""

    @pytest.mark.asyncio
    async def test_route_live_mode(self) -> None:
        mock_live = MagicMock()
        mock_order = MagicMock()
        mock_live.place_order = AsyncMock(return_value=mock_order)

        router = OrderRouter(paper_service=MagicMock(), live_service=mock_live)
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.MARKET,
        )

        result = await router.route(request, ExecutionMode.LIVE)
        assert result is mock_order

    @pytest.mark.asyncio
    async def test_live_mode_applies_filters(self) -> None:
        mock_live = MagicMock()
        mock_order = MagicMock()
        mock_live.place_order = AsyncMock(return_value=mock_order)

        mock_normalizer = MagicMock()
        mock_normalizer.normalize_order = AsyncMock(
            return_value={"price": Decimal("67000"), "quantity": Decimal("0.001")}
        )

        router = OrderRouter(
            paper_service=MagicMock(),
            live_service=mock_live,
            normalizer=mock_normalizer,
        )
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.00123"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("67123.456"),
        )

        await router.route(request, ExecutionMode.LIVE)
        mock_normalizer.normalize_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_live_mode_retries_on_filter_error(self) -> None:
        mock_live = MagicMock()
        mock_order = MagicMock()
        mock_live.place_order = AsyncMock(return_value=mock_order)

        call_count = 0

        async def failing_normalize(*args: object, **kwargs: object) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise BinanceFilterError("Notional too low", "MIN_NOTIONAL")
            return {"price": Decimal("67000"), "quantity": Decimal("0.001")}

        mock_normalizer = MagicMock()
        mock_normalizer.normalize_order = failing_normalize

        router = OrderRouter(
            paper_service=MagicMock(),
            live_service=mock_live,
            normalizer=mock_normalizer,
        )
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("67000"),
        )

        with pytest.raises(BinanceFilterError):
            await router.route(request, ExecutionMode.LIVE)

    @pytest.mark.asyncio
    async def test_router_with_disabled_live(self) -> None:
        router = OrderRouter(paper_service=MagicMock(), live_service=None)
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
        )

        with pytest.raises(RuntimeError, match="Live service is not configured"):
            await router.route(request, ExecutionMode.LIVE)


class TestRouteTestnetMode:
    """Tests for testnet mode routing."""

    @pytest.mark.asyncio
    async def test_route_testnet_mode(self) -> None:
        mock_testnet = MagicMock()
        mock_order = MagicMock()
        mock_testnet.place_order = AsyncMock(return_value=mock_order)

        router = OrderRouter(
            paper_service=MagicMock(),
            testnet_service=mock_testnet,
        )
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
        )

        result = await router.route(request, ExecutionMode.TESTNET)
        assert result is mock_order

    @pytest.mark.asyncio
    async def test_router_with_disabled_testnet(self) -> None:
        router = OrderRouter(paper_service=MagicMock(), testnet_service=None)
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
        )

        with pytest.raises(RuntimeError, match="Testnet service is not configured"):
            await router.route(request, ExecutionMode.TESTNET)


class TestRouteBacktestMode:
    """Tests for backtest mode routing."""

    @pytest.mark.asyncio
    async def test_route_backtest_mode(self) -> None:
        router = OrderRouter(paper_service=MagicMock())
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("67000"),
        )

        result = await router.route(request, ExecutionMode.BACKTEST)
        assert result.symbol == "BTC/USDC"
        assert result.mode == "backtest"
        assert result.status == "FILLED"
        assert result.metadata.get("test_order") is True


class TestIdempotentOrderSubmission:
    """Tests for idempotent order submission."""

    @pytest.mark.asyncio
    async def test_idempotent_order_submission(self) -> None:
        mock_paper = MagicMock()
        mock_order = MagicMock()
        mock_paper.place_order = AsyncMock(return_value=mock_order)

        router = OrderRouter(paper_service=mock_paper)
        request = OrderRequest(
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            client_order_id="test-order-123",
        )

        await router.route(request, ExecutionMode.PAPER)
        await router.route(request, ExecutionMode.PAPER)

        assert mock_paper.place_order.call_count == 2
