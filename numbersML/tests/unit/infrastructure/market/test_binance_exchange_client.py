"""Unit tests for Binance exchange client helpers."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.market.binance_exchange_client import BinanceExchangeClient


class TestBinanceExchangeClient:
    """Validate pure helper behavior for symbol normalization."""

    def test_normalize_symbol(self) -> None:
        assert BinanceExchangeClient._normalize_symbol("BTC/USDC") == "BTCUSDC"
        assert BinanceExchangeClient._normalize_symbol("shib/usdc") == "SHIBUSDC"


class TestBinanceExchangeClientQuantityNormalization:
    """Quantity rounding to LOT_SIZE step size before API call."""

    @pytest.fixture
    def client(self) -> BinanceExchangeClient:
        return BinanceExchangeClient(api_key="test", api_secret="test")

    @pytest.fixture
    def exchange_info(self) -> dict:
        """Simulates Binance API returning stepSize with trailing zeros (e.g. 0.01000000)."""
        return {
            "symbols": [
                {
                    "symbol": "ATOMUSDC",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                         "stepSize": "0.01000000"},
                        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                         "stepSize": "0.01000000"},
                        {"filterType": "PRICE_FILTER", "minPrice": "0.001", "maxPrice": "1000",
                         "tickSize": "0.00100000"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                    ],
                },
            ],
        }

    async def test_create_order_rounds_quantity_to_step_size(
        self, client: BinanceExchangeClient, exchange_info: dict
    ) -> None:
        """Quantity with excess decimal places is rounded down to LOT_SIZE step_size."""
        mock_request = AsyncMock(return_value={"orderId": "abc123", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info", AsyncMock(return_value=exchange_info)):
                await client.create_order(
                    symbol="ATOM/USDC",
                    side="BUY",
                    order_type="MARKET",
                    quantity=Decimal("13.80452788514632799558255108"),
                    price=None,
                    client_order_id="test-1",
                )

        call_kwargs = mock_request.call_args
        params = call_kwargs[1]["params"]
        assert params["quantity"] == "13.80"

    async def test_create_order_rounds_quantity_market(
        self, client: BinanceExchangeClient, exchange_info: dict
    ) -> None:
        """MARKET order quantity rounds per MARKET_LOT_SIZE."""
        mock_request = AsyncMock(return_value={"orderId": "abc123", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info", AsyncMock(return_value=exchange_info)):
                await client.create_order(
                    symbol="ATOM/USDC",
                    side="BUY",
                    order_type="MARKET",
                    quantity=Decimal("1.23456789"),
                    price=None,
                    client_order_id="test-2",
                )

        call_kwargs = mock_request.call_args
        params = call_kwargs[1]["params"]
        assert params["quantity"] == "1.23"

    async def test_create_order_rounds_price_to_tick_size(
        self, client: BinanceExchangeClient, exchange_info: dict
    ) -> None:
        """LIMIT order price is rounded to PRICE_FILTER tick_size."""
        mock_request = AsyncMock(return_value={"orderId": "abc123", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info", AsyncMock(return_value=exchange_info)):
                await client.create_order(
                    symbol="ATOM/USDC",
                    side="BUY",
                    order_type="LIMIT",
                    quantity=Decimal("10"),
                    price=Decimal("1.87912345"),
                    client_order_id="test-3",
                )

        call_kwargs = mock_request.call_args
        params = call_kwargs[1]["params"]
        assert params["price"] == "1.879"
        assert params["quantity"] == "10.00"

    async def test_create_order_handles_unknown_symbol_gracefully(
        self, client: BinanceExchangeClient
    ) -> None:
        """Unknown symbol falls back to default rounding (5 decimal places)."""
        mock_request = AsyncMock(return_value={"orderId": "abc123", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info", AsyncMock(return_value={"symbols": []})):
                await client.create_order(
                    symbol="UNKNOWN/USDC",
                    side="BUY",
                    order_type="MARKET",
                    quantity=Decimal("99.12345678"),
                    price=None,
                    client_order_id="test-4",
                )

        call_kwargs = mock_request.call_args
        params = call_kwargs[1]["params"]
        assert params["quantity"] == "99.12345"

    async def test_create_order_with_real_binance_step_size_trailing_zeros(
        self, client: BinanceExchangeClient
    ) -> None:
        """Reproduce bug: Binance returns stepSize=0.01000000 (trailing zeros),
        which made quantize round to 8 decimal places instead of 2."""
        exchange_info = {
            "symbols": [
                {
                    "symbol": "ATOMUSDC",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                         "stepSize": "0.01000000"},
                        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "900000",
                         "stepSize": "0.01000000"},
                        {"filterType": "PRICE_FILTER", "minPrice": "0.001", "maxPrice": "1000",
                         "tickSize": "0.00100000"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                    ],
                },
            ],
        }
        mock_request = AsyncMock(return_value={"orderId": "abc123", "status": "NEW"})
        with patch.object(client, "_request", mock_request):
            with patch.object(client, "get_exchange_info", AsyncMock(return_value=exchange_info)):
                await client.create_order(
                    symbol="ATOM/USDC",
                    side="BUY",
                    order_type="MARKET",
                    quantity=Decimal("13.80452788514632799558255108"),
                    price=None,
                    client_order_id="test-5",
                )

        call_kwargs = mock_request.call_args
        params = call_kwargs[1]["params"]
        assert params["quantity"] == "13.80"
        assert "_" not in params["quantity"]  # no extra trailing zeros from quantize
