"""Unit tests for OrderNormalizer."""
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.market.order import OrderSide, OrderType, SymbolFilters
from src.infrastructure.market.binance_filters import (
    BinanceFilterEngine,
    BinanceFilterError,
    OrderNormalizationError,
)
from src.infrastructure.market.order_normalizer import OrderNormalizer


class TestAdjustPrice:
    """Tests for price adjustment logic."""

    def _make_normalizer(self) -> OrderNormalizer:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        return OrderNormalizer(filter_engine=engine)

    def test_adjust_price_buy_increases(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_price(Decimal("100"), "PRICE_FILTER", OrderSide.BUY)
        assert result == Decimal("100.5")

    def test_adjust_price_sell_decreases(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_price(Decimal("100"), "PRICE_FILTER", OrderSide.SELL)
        assert result == Decimal("99.5")

    def test_adjust_price_min_notional_buy(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_price(Decimal("100"), "MIN_NOTIONAL", OrderSide.BUY)
        assert result == Decimal("100.5")

    def test_adjust_price_notional_max(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_price(Decimal("100"), "NOTIONAL", OrderSide.BUY)
        assert result == Decimal("99.5")

    def test_adjust_price_none_returns_none(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_price(None, "PRICE_FILTER", OrderSide.BUY)
        assert result is None


class TestAdjustQuantity:
    """Tests for quantity adjustment logic."""

    def _make_normalizer(self) -> OrderNormalizer:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        return OrderNormalizer(filter_engine=engine)

    def test_adjust_quantity_min_notional(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_quantity(Decimal("1"), "MIN_NOTIONAL")
        assert result == Decimal("1.005")

    def test_adjust_quantity_notional_max(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_quantity(Decimal("1"), "NOTIONAL")
        assert result == Decimal("0.995")

    def test_adjust_quantity_lot_size(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_quantity(Decimal("1"), "LOT_SIZE")
        assert result == Decimal("1.005")

    def test_adjust_quantity_default(self) -> None:
        normalizer = self._make_normalizer()
        result = normalizer._adjust_quantity(Decimal("1"), "UNKNOWN")
        assert result == Decimal("1.005")


class TestPlaceWithRetry:
    """Tests for retry logic."""

    def _make_normalizer_with_filters(
        self, filters: SymbolFilters | None = None
    ) -> tuple[OrderNormalizer, MagicMock]:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        if filters is not None:
            engine._filter_cache[filters.symbol] = (filters, time.monotonic())
        normalizer = OrderNormalizer(filter_engine=engine)
        return normalizer, mock_client

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_attempt(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_notional=Decimal("10"),
        )
        normalizer, _ = self._make_normalizer_with_filters(filters)
        mock_service = MagicMock()
        mock_service.place_order = AsyncMock()

        result = await normalizer.place_with_retry(
            market_service=mock_service,
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=Decimal("67000"),
        )
        assert result["price"] == Decimal("67000")
        assert result["quantity"] == Decimal("0.001")
        mock_service.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_fails_after_max_attempts(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            min_notional=Decimal("999999999999"),
        )
        normalizer, _ = self._make_normalizer_with_filters(filters)
        mock_service = MagicMock()
        mock_service.place_order = AsyncMock()

        with pytest.raises(OrderNormalizationError, match="Failed to normalize order"):
            await normalizer.place_with_retry(
                market_service=mock_service,
                symbol="BTC/USDC",
                side=OrderSide.BUY,
                quantity=Decimal("0.000001"),
                order_type=OrderType.LIMIT,
                price=Decimal("0.001"),
            )

    @pytest.mark.asyncio
    async def test_retry_adjusts_price_on_filter_error(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_notional=Decimal("10"),
        )
        normalizer, _ = self._make_normalizer_with_filters(filters)
        mock_service = MagicMock()
        call_count = 0

        async def failing_place_order(request: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise BinanceFilterError("Notional too low", "MIN_NOTIONAL")

        mock_service.place_order = failing_place_order

        await normalizer.place_with_retry(
            market_service=mock_service,
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=Decimal("67000"),
        )
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_adjusts_quantity_on_second_error(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_notional=Decimal("10"),
        )
        normalizer, _ = self._make_normalizer_with_filters(filters)
        mock_service = MagicMock()
        call_count = 0

        async def failing_place_order(request: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise BinanceFilterError("Notional too low", "MIN_NOTIONAL")

        mock_service.place_order = failing_place_order

        await normalizer.place_with_retry(
            market_service=mock_service,
            symbol="BTC/USDC",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=Decimal("67000"),
        )
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_adjusts_both_on_third_attempt(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_notional=Decimal("10"),
        )
        normalizer, _ = self._make_normalizer_with_filters(filters)
        mock_service = MagicMock()
        call_count = 0

        async def failing_place_order(request: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise BinanceFilterError("Notional too low", "MIN_NOTIONAL")

        mock_service.place_order = failing_place_order

        with pytest.raises(OrderNormalizationError):
            await normalizer.place_with_retry(
                market_service=mock_service,
                symbol="BTC/USDC",
                side=OrderSide.BUY,
                quantity=Decimal("0.001"),
                order_type=OrderType.LIMIT,
                price=Decimal("67000"),
            )
        assert call_count == 3
