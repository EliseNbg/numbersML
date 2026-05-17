"""Unit tests for BinanceFilterEngine."""
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.market.order import OrderSide, OrderType, SymbolFilters
from src.infrastructure.market.binance_filters import (
    BinanceFilterEngine,
    BinanceFilterError,
)


class TestNormalizePrice:
    """Tests for price normalization."""

    def _make_engine(self, filters: SymbolFilters | None = None) -> BinanceFilterEngine:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        if filters is not None:
            engine._filter_cache[filters.symbol] = (filters, time.monotonic())
        return engine

    def test_normalize_price_to_tick_size(self) -> None:
        filters = SymbolFilters(symbol="BTC/USDC", tick_size=Decimal("0.01"))
        engine = self._make_engine(filters)
        result = engine.normalize_price("BTC/USDC", Decimal("67123.456"))
        assert result == Decimal("67123.46")

    def test_normalize_price_rounds_down(self) -> None:
        filters = SymbolFilters(symbol="BTC/USDC", tick_size=Decimal("0.01"))
        engine = self._make_engine(filters)
        result = engine.normalize_price("BTC/USDC", Decimal("67123.454"))
        assert result == Decimal("67123.45")

    def test_normalize_price_clamp_min(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            min_price=Decimal("100"),
            tick_size=Decimal("0.01"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_price("BTC/USDC", Decimal("50"))
        assert result == Decimal("100")

    def test_normalize_price_clamp_max(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            max_price=Decimal("100000"),
            tick_size=Decimal("0.01"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_price("BTC/USDC", Decimal("150000"))
        assert result == Decimal("100000")

    def test_normalize_price_negative_rejected(self) -> None:
        engine = self._make_engine()
        with pytest.raises(BinanceFilterError, match="Price must be positive"):
            engine.normalize_price("BTC/USDC", Decimal("-100"))

    def test_normalize_price_zero_rejected(self) -> None:
        engine = self._make_engine()
        with pytest.raises(BinanceFilterError, match="Price must be positive"):
            engine.normalize_price("BTC/USDC", Decimal("0"))

    def test_normalize_doge_usdc(self) -> None:
        filters = SymbolFilters(
            symbol="DOGE/USDC",
            tick_size=Decimal("0.00001"),
            min_price=Decimal("0.00001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_price("DOGE/USDC", Decimal("0.15234"))
        assert result == Decimal("0.15234")

    def test_normalize_shib_usdc(self) -> None:
        filters = SymbolFilters(
            symbol="SHIB/USDC",
            tick_size=Decimal("0.00000001"),
            min_price=Decimal("0.00000001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_price("SHIB/USDC", Decimal("0.000012345"))
        assert result == Decimal("0.00001235")

    def test_filter_precision_for_tiny_prices(self) -> None:
        filters = SymbolFilters(
            symbol="SHIB/USDC",
            tick_size=Decimal("0.00000001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_price("SHIB/USDC", Decimal("0.00000123"))
        assert result == Decimal("0.00000123")


class TestNormalizeQuantity:
    """Tests for quantity normalization."""

    def _make_engine(self, filters: SymbolFilters | None = None) -> BinanceFilterEngine:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        if filters is not None:
            engine._filter_cache[filters.symbol] = (filters, time.monotonic())
        return engine

    def test_normalize_quantity_to_step_size(self) -> None:
        filters = SymbolFilters(symbol="BTC/USDC", step_size=Decimal("0.00001"))
        engine = self._make_engine(filters)
        result = engine.normalize_quantity("BTC/USDC", Decimal("0.00123456"), OrderType.LIMIT)
        assert result == Decimal("0.00123")

    def test_normalize_quantity_clamp_min(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            min_qty=Decimal("0.001"),
            step_size=Decimal("0.00001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_quantity("BTC/USDC", Decimal("0.0005"), OrderType.LIMIT)
        assert result == Decimal("0.001")

    def test_normalize_quantity_clamp_max(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            max_qty=Decimal("100"),
            step_size=Decimal("0.00001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_quantity("BTC/USDC", Decimal("150"), OrderType.LIMIT)
        assert result == Decimal("100")

    def test_normalize_zero_quantity_rejected(self) -> None:
        engine = self._make_engine()
        with pytest.raises(BinanceFilterError, match="Quantity must be positive"):
            engine.normalize_quantity("BTC/USDC", Decimal("0"), OrderType.LIMIT)

    def test_normalize_negative_quantity_rejected(self) -> None:
        engine = self._make_engine()
        with pytest.raises(BinanceFilterError, match="Quantity must be positive"):
            engine.normalize_quantity("BTC/USDC", Decimal("-1"), OrderType.LIMIT)

    def test_market_lot_size_normalization(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            market_step_size=Decimal("0.001"),
            market_min_qty=Decimal("0.001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_quantity("BTC/USDC", Decimal("0.0015"), OrderType.MARKET)
        assert result == Decimal("0.001")

    def test_normalize_limit_order(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            step_size=Decimal("0.00001"),
            min_qty=Decimal("0.00001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_quantity("BTC/USDC", Decimal("0.00567"), OrderType.LIMIT)
        assert result == Decimal("0.00567")

    def test_normalize_market_order(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            market_step_size=Decimal("0.001"),
            market_min_qty=Decimal("0.001"),
        )
        engine = self._make_engine(filters)
        result = engine.normalize_quantity("BTC/USDC", Decimal("0.00567"), OrderType.MARKET)
        assert result == Decimal("0.005")


class TestValidateNotional:
    """Tests for notional validation."""

    def _make_engine(self, filters: SymbolFilters | None = None) -> BinanceFilterEngine:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        if filters is not None:
            engine._filter_cache[filters.symbol] = (filters, time.monotonic())
        return engine

    def test_min_notional_validation(self) -> None:
        filters = SymbolFilters(symbol="BTC/USDC", min_notional=Decimal("10"))
        engine = self._make_engine(filters)
        with pytest.raises(BinanceFilterError, match="below minimum"):
            engine.validate_notional("BTC/USDC", Decimal("100"), Decimal("0.01"), OrderType.LIMIT)

    def test_min_notional_passes(self) -> None:
        filters = SymbolFilters(symbol="BTC/USDC", min_notional=Decimal("10"))
        engine = self._make_engine(filters)
        result = engine.validate_notional("BTC/USDC", Decimal("67000"), Decimal("0.001"), OrderType.LIMIT)
        assert result is True

    def test_notional_max_validation(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            max_notional=Decimal("1000000"),
        )
        engine = self._make_engine(filters)
        with pytest.raises(BinanceFilterError, match="above maximum"):
            engine.validate_notional("BTC/USDC", Decimal("67000"), Decimal("100"), OrderType.LIMIT)


class TestFilterCache:
    """Tests for filter caching behavior."""

    def test_filter_cache_hit_skips_api_call(self) -> None:
        mock_client = MagicMock()
        mock_client.get_exchange_info = AsyncMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        filters = SymbolFilters(symbol="BTC/USDC")
        engine._filter_cache["BTC/USDC"] = (filters, 0)

        result = engine._get_cached_or_default("BTC/USDC")
        assert result.symbol == "BTC/USDC"
        mock_client.get_exchange_info.assert_not_called()

    def test_filter_cache_respects_ttl(self) -> None:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client, cache_ttl=1)
        filters = SymbolFilters(symbol="BTC/USDC")
        engine._filter_cache["BTC/USDC"] = (filters, -100)

        result = engine._get_cached_or_default("BTC/USDC")
        assert result == engine._default_filters("BTC/USDC")

    def test_invalidate_cache_single(self) -> None:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        engine._filter_cache["BTC/USDC"] = (SymbolFilters(symbol="BTC/USDC"), 0)
        engine._filter_cache["ETH/USDC"] = (SymbolFilters(symbol="ETH/USDC"), 0)

        engine.invalidate_cache("BTC/USDC")
        assert "BTC/USDC" not in engine._filter_cache
        assert "ETH/USDC" in engine._filter_cache

    def test_invalidate_cache_all(self) -> None:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        engine._filter_cache["BTC/USDC"] = (SymbolFilters(symbol="BTC/USDC"), 0)

        engine.invalidate_cache()
        assert len(engine._filter_cache) == 0


class TestParseFilters:
    """Tests for parsing raw Binance filters."""

    def test_parse_price_filter(self) -> None:
        raw = [
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.01",
                "maxPrice": "100000",
                "tickSize": "0.01",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.min_price == Decimal("0.01")
        assert result.max_price == Decimal("100000")
        assert result.tick_size == Decimal("0.01")

    def test_parse_lot_size_filter(self) -> None:
        raw = [
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.00001",
                "maxQty": "9000",
                "stepSize": "0.00001",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.min_qty == Decimal("0.00001")
        assert result.max_qty == Decimal("9000")
        assert result.step_size == Decimal("0.00001")

    def test_parse_market_lot_size_filter(self) -> None:
        raw = [
            {
                "filterType": "MARKET_LOT_SIZE",
                "minQty": "0.001",
                "maxQty": "500",
                "stepSize": "0.001",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.market_min_qty == Decimal("0.001")
        assert result.market_max_qty == Decimal("500")
        assert result.market_step_size == Decimal("0.001")

    def test_parse_min_notional_filter(self) -> None:
        raw = [
            {
                "filterType": "MIN_NOTIONAL",
                "minNotional": "10",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.min_notional == Decimal("10")

    def test_parse_notional_filter(self) -> None:
        raw = [
            {
                "filterType": "NOTIONAL",
                "minNotional": "10",
                "maxNotional": "1000000",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.min_notional == Decimal("10")
        assert result.max_notional == Decimal("1000000")

    def test_parse_percent_price_filter(self) -> None:
        raw = [
            {
                "filterType": "PERCENT_PRICE_BY_SIDE",
                "bidMultiplierUp": "1.3",
                "bidMultiplierDown": "0.7",
                "askMultiplierUp": "5.0",
                "askMultiplierDown": "0.8",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.bid_multiplier_up == Decimal("1.3")
        assert result.bid_multiplier_down == Decimal("0.7")
        assert result.ask_multiplier_up == Decimal("5.0")
        assert result.ask_multiplier_down == Decimal("0.8")

    def test_parse_max_num_orders(self) -> None:
        raw = [
            {
                "filterType": "MAX_NUM_ORDERS",
                "maxNumOrders": "200",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.max_num_orders == 200

    def test_parse_max_position(self) -> None:
        raw = [
            {
                "filterType": "MAX_POSITION",
                "maxPosition": "100000",
            }
        ]
        result = BinanceFilterEngine._parse_filters("BTC/USDC", raw)
        assert result.max_position == Decimal("100000")


class TestNormalizeOrder:
    """Tests for full order normalization."""

    def _make_engine(self, filters: SymbolFilters | None = None) -> BinanceFilterEngine:
        mock_client = MagicMock()
        engine = BinanceFilterEngine(exchange_client=mock_client)
        if filters is not None:
            engine._filter_cache[filters.symbol] = (filters, time.monotonic())
        return engine

    @pytest.mark.asyncio
    async def test_normalize_limit_order(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_notional=Decimal("10"),
        )
        engine = self._make_engine(filters)
        result = await engine.normalize_order(
            symbol="BTC/USDC",
            price=Decimal("67123.456"),
            quantity=Decimal("0.00123456"),
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
        )
        assert result["price"] == Decimal("67123.46")
        assert result["quantity"] == Decimal("0.00123")

    @pytest.mark.asyncio
    async def test_normalize_market_order(self) -> None:
        filters = SymbolFilters(
            symbol="BTC/USDC",
            market_step_size=Decimal("0.001"),
            market_min_qty=Decimal("0.001"),
        )
        engine = self._make_engine(filters)
        result = await engine.normalize_order(
            symbol="BTC/USDC",
            price=None,
            quantity=Decimal("0.00567"),
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
        )
        assert result["price"] is None
        assert result["quantity"] == Decimal("0.005")
