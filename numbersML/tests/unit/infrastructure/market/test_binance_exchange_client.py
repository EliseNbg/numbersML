"""Unit tests for Binance exchange client helpers."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.market.binance_exchange_client import BinanceExchangeClient


class TestNormalizeSymbol:
    """Validate pure helper behavior for symbol normalization."""

    def test_normalize_symbol(self) -> None:
        assert BinanceExchangeClient._normalize_symbol("BTC/USDC") == "BTCUSDC"
        assert BinanceExchangeClient._normalize_symbol("shib/usdc") == "SHIBUSDC"


class TestNormalizePrice:
    """Price rounding via _normalize_price."""

    @pytest.fixture
    def client(self) -> BinanceExchangeClient:
        return BinanceExchangeClient(api_key="test", api_secret="test")

    def test_rounds_to_tick_size(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"tick_size": Decimal("0.001")}
        assert client._normalize_price("ATOM/USDC", Decimal("1.87912345")) == Decimal("1.879")

    def test_rounds_half_up(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"tick_size": Decimal("0.01")}
        assert client._normalize_price("ATOM/USDC", Decimal("1.875")) == Decimal("1.88")

    def test_returns_raw_when_tick_size_zero(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"tick_size": Decimal("0")}
        assert client._normalize_price("ATOM/USDC", Decimal("1.879")) == Decimal("1.879")

    def test_returns_raw_when_no_cache(self, client: BinanceExchangeClient) -> None:
        assert client._normalize_price("ATOM/USDC", Decimal("1.879")) == Decimal("1.879")

    def test_tick_size_with_trailing_zeros(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"tick_size": Decimal("0.001")}
        assert client._normalize_price("ATOM/USDC", Decimal("1.87912345")) == Decimal("1.879")


class TestNormalizeQuantity:
    """Quantity rounding via _normalize_qty."""

    @pytest.fixture
    def client(self) -> BinanceExchangeClient:
        return BinanceExchangeClient(api_key="test", api_secret="test")

    # --- MARKET orders ---

    def test_market_uses_market_lot_size(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {
            "market_step_size": Decimal("0.01"),
            "step_size": Decimal("0.001"),
        }
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80452788"), True) == Decimal("13.80")

    def test_market_falls_back_to_lot_size_when_market_lot_size_is_zero(
        self, client: BinanceExchangeClient
    ) -> None:
        """Bug reproduction: Binance returns MARKET_LOT_SIZE stepSize=0 for some symbols."""
        client._filter_cache["ATOMUSDC"] = {
            "market_step_size": Decimal("0"),
            "step_size": Decimal("0.01"),
        }
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80452788"), True) == Decimal("13.80")

    def test_market_falls_back_to_lot_size_when_market_lot_size_is_missing(
        self, client: BinanceExchangeClient
    ) -> None:
        """Some symbols lack MARKET_LOT_SIZE filter entirely."""
        client._filter_cache["ATOMUSDC"] = {
            "step_size": Decimal("0.01"),
        }
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80452788"), True) == Decimal("13.80")

    def test_market_returns_raw_when_both_step_sizes_zero(
        self, client: BinanceExchangeClient
    ) -> None:
        client._filter_cache["ATOMUSDC"] = {
            "market_step_size": Decimal("0"),
            "step_size": Decimal("0"),
        }
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80452788"), True) == Decimal("13.80452788")

    def test_market_returns_raw_when_no_cache(self, client: BinanceExchangeClient) -> None:
        rounded = client._normalize_qty("ATOM/USDC", Decimal("13.80452788"), True)
        assert rounded == Decimal("13.80452")

    # --- LIMIT / non-MARKET orders ---

    def test_limit_uses_lot_size(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {
            "step_size": Decimal("0.01"),
            "market_step_size": Decimal("0.001"),
        }
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80452788"), False) == Decimal("13.80")

    def test_limit_falls_back_when_step_size_zero(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {
            "step_size": Decimal("0"),
        }
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80452788"), False) == Decimal("13.80452788")

    # --- Edge cases ---

    def test_quantity_already_aligned(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"step_size": Decimal("0.01")}
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80"), False) == Decimal("13.80")

    def test_quantity_with_no_decimal_places(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"step_size": Decimal("1")}
        assert client._normalize_qty("ATOM/USDC", Decimal("13.80"), False) == Decimal("13")

    def test_very_small_step_size(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"step_size": Decimal("0.00001")}
        assert client._normalize_qty("ATOM/USDC", Decimal("1.23456789"), False) == Decimal("1.23456")

    def test_large_quantity(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ATOMUSDC"] = {"step_size": Decimal("0.01")}
        q = Decimal("999999.99999999")
        assert client._normalize_qty("ATOM/USDC", q, False) == Decimal("999999.99")


class TestCreateOrderIntegration:
    """End-to-end tests: _load_filters → _normalize_qty/price → create_order payload."""

    @pytest.fixture
    def client(self) -> BinanceExchangeClient:
        return BinanceExchangeClient(api_key="test", api_secret="test")

    EXCHANGE_INFO_FULL = {
        "symbols": [
            {
                "symbol": "ATOMUSDC",
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                     "stepSize": "0.01000000"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                     "stepSize": "0"},
                    {"filterType": "PRICE_FILTER", "minPrice": "0.001", "maxPrice": "1000",
                     "tickSize": "0.00100000"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                ],
            },
            {
                "symbol": "BTCUSDC",
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "9000",
                     "stepSize": "0.00001000"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "0.00001", "maxQty": "9000",
                     "stepSize": "0.00001000"},
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000",
                     "tickSize": "0.01000000"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                ],
            },
            {
                "symbol": "SHIBUSDC",
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "9999999999",
                     "stepSize": "1"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "1", "maxQty": "9999999999",
                     "stepSize": "1"},
                    {"filterType": "PRICE_FILTER", "minPrice": "0.00000001", "maxPrice": "1000",
                     "tickSize": "0.00000001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                ],
            },
            {
                "symbol": "NOFILTERUSDC",
                "filters": [],
            },
        ],
    }

    # --- ATOM: MARKET order with MARKET_LOT_SIZE=0 (falls back to LOT_SIZE) ---

    async def test_atom_market_order_falls_back_from_zero_market_lot_size(
        self, client: BinanceExchangeClient
    ) -> None:
        """The exact bug: ATOM MARKET_LOT_SIZE stepSize=0 → falls back to LOT_SIZE 0.01."""
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="ATOM/USDC", side="BUY", order_type="MARKET",
                    quantity=Decimal("14.08450704225352112676056338"),
                    price=None, client_order_id="t1",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "14.08"
        # Verify trailing-zero step_size 0.01000000 was normalized to 0.01

    async def test_atom_market_order_also_rounds_price_when_limit(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="ATOM/USDC", side="BUY", order_type="LIMIT",
                    quantity=Decimal("14.08450704225352112676056338"),
                    price=Decimal("1.77500000"), client_order_id="t2",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "14.08"
        assert params["price"] == "1.775"

    # --- BTC: both LOT_SIZE and MARKET_LOT_SIZE have step_size=0.00001 ---

    async def test_btc_market_order_uses_market_lot_size(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="BTC/USDC", side="SELL", order_type="MARKET",
                    quantity=Decimal("0.12345678"),
                    price=None, client_order_id="t3",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "0.12345"

    async def test_btc_limit_order_rounds_price_to_tick_size(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="BTC/USDC", side="BUY", order_type="LIMIT",
                    quantity=Decimal("0.1"),
                    price=Decimal("67123.456"), client_order_id="t4",
                )
        params = mock_request.call_args[1]["params"]
        assert params["price"] == "67123.46"
        assert params["quantity"] == "0.10000"

    # --- SHIB: integer step_size, very small tick_size ---

    async def test_shib_market_order_rounds_to_integer(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="SHIB/USDC", side="BUY", order_type="MARKET",
                    quantity=Decimal("1234567.89"),
                    price=None, client_order_id="t5",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "1234567"

    async def test_shib_limit_order_uses_tiny_tick_size(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="SHIB/USDC", side="BUY", order_type="LIMIT",
                    quantity=Decimal("1000000"),
                    price=Decimal("0.0000256789"), client_order_id="t6",
                )
        params = mock_request.call_args[1]["params"]
        assert params["price"] == "0.00002568"
        assert params["quantity"] == "1000000"

    # --- No filters symbol ---

    async def test_no_filter_symbol_uses_defaults(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="NOFILTER/USDC", side="BUY", order_type="MARKET",
                    quantity=Decimal("99.12345678"),
                    price=None, client_order_id="t7",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "99.12345"

    # --- Unknown symbol (not in exchangeInfo) ---

    async def test_unknown_symbol_uses_defaults(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_order(
                    symbol="UNKNOWN/USDC", side="BUY", order_type="MARKET",
                    quantity=Decimal("99.12345678"),
                    price=None, client_order_id="t8",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "99.12345"

    # --- ExchangeInfo fetch fails entirely ---

    async def test_exchange_info_failure_uses_defaults(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={"orderId": "abc", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(side_effect=RuntimeError("network error"))):
                await client.create_order(
                    symbol="ATOM/USDC", side="BUY", order_type="MARKET",
                    quantity=Decimal("99.12345678"),
                    price=None, client_order_id="t9",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "99.12345"

    # --- Test that create_test_order also normalizes (same code path) ---

    async def test_create_test_order_normalizes_quantity(
        self, client: BinanceExchangeClient
    ) -> None:
        mock_request = AsyncMock(return_value={})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info",
                              AsyncMock(return_value=self.EXCHANGE_INFO_FULL)):
                await client.create_test_order(
                    symbol="ATOM/USDC", side="BUY", order_type="MARKET",
                    quantity=Decimal("14.08450704225352112676056338"),
                    price=None, client_order_id="test-t10",
                )
        params = mock_request.call_args[1]["params"]
        assert params["quantity"] == "14.08"


class TestNormalizeDecimal:
    """_normalize_decimal strips unnecessary trailing zeros."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.01000000", Decimal("0.01")),
            ("0.00100000", Decimal("0.001")),
            ("0.00001000", Decimal("0.00001")),
            ("1", Decimal("1")),
            ("0", Decimal("0")),
            ("0.00000001", Decimal("0.00000001")),
            ("100.00", Decimal("100")),
        ],
    )
    def test_normalize_decimal(
        self, raw: str, expected: Decimal
    ) -> None:
        assert BinanceExchangeClient._normalize_decimal(raw) == expected


class TestLoadFilters:
    """_load_filters caches correctly."""

    EXCHANGE_INFO = {
        "symbols": [
            {
                "symbol": "ATOMUSDC",
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                     "stepSize": "0.01000000"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                     "stepSize": "0"},
                ],
            },
        ],
    }

    async def test_cache_hit_after_load(self) -> None:
        client = BinanceExchangeClient(api_key="test", api_secret="test")
        with patch.object(client, "get_exchange_info",
                          AsyncMock(return_value=self.EXCHANGE_INFO)):
            f1 = await client._load_filters("ATOM/USDC")
        assert f1["step_size"] == Decimal("0.01")
        assert f1["market_step_size"] == Decimal("0")

        # Second call should use cache (no exchangeInfo call)
        with patch.object(client, "get_exchange_info",
                          AsyncMock(side_effect=AssertionError("should not be called"))):
            f2 = await client._load_filters("ATOM/USDC")
        assert f2["step_size"] == Decimal("0.01")

    async def test_unknown_symbol_fills_cache_with_defaults(self) -> None:
        client = BinanceExchangeClient(api_key="test", api_secret="test")
        with patch.object(client, "get_exchange_info",
                          AsyncMock(return_value=self.EXCHANGE_INFO)):
            filters = await client._load_filters("NONEXISTENT/USDC")
        assert filters["step_size"] == Decimal("0.00001")

    async def test_exchange_info_failure_fills_cache_with_defaults(self) -> None:
        client = BinanceExchangeClient(api_key="test", api_secret="test")
        with patch.object(client, "get_exchange_info",
                          AsyncMock(side_effect=RuntimeError("timeout"))):
            filters = await client._load_filters("ATOM/USDC")
        assert filters["step_size"] == Decimal("0.00001")


class TestValidateNotional:
    """MIN_NOTIONAL validation via _validate_notional."""

    @pytest.fixture
    def client(self) -> BinanceExchangeClient:
        c = BinanceExchangeClient(api_key="test", api_secret="test")
        c._filter_cache["ATOMUSDC"] = {"notional_min": Decimal("5")}
        c._filter_cache["BTCUSDC"] = {"notional_min": Decimal("10")}
        return c

    def test_passes_when_notional_above_min(self, client: BinanceExchangeClient) -> None:
        client._validate_notional("ATOM/USDC", Decimal("10"), Decimal("1"))
        # No exception = pass

    def test_raises_when_notional_below_min(self, client: BinanceExchangeClient) -> None:
        with pytest.raises(ValueError, match="Order notional 4.5 < minimum 5"):
            client._validate_notional("ATOM/USDC", Decimal("3"), Decimal("1.5"))

    def test_passes_when_no_price(self, client: BinanceExchangeClient) -> None:
        # MARKET orders may not have a price set
        client._validate_notional("ATOM/USDC", Decimal("0.001"), None)
        # No exception = pass

    def test_passes_when_no_cache(self, client: BinanceExchangeClient) -> None:
        client2 = BinanceExchangeClient(api_key="test", api_secret="test")
        client2._validate_notional("ATOM/USDC", Decimal("0.001"), Decimal("1000"))
        # No exception = pass

    def test_passes_when_min_notional_zero(self, client: BinanceExchangeClient) -> None:
        client._filter_cache["ETHUSDC"] = {"notional_min": Decimal("0")}
        client._validate_notional("ETH/USDC", Decimal("0.001"), Decimal("1"))
        # No exception = pass

    def test_raises_with_btc_min_notional(self, client: BinanceExchangeClient) -> None:
        with pytest.raises(ValueError, match="Order notional .* < minimum 10"):
            client._validate_notional("BTC/USDC", Decimal("0.5"), Decimal("10"))
