"""Binance exchange client for live market service (testnet + production)."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import aiohttp

from src.domain.services.market_service import LiveExchangeClient


@dataclass(frozen=True)
class BinanceEnvironment:
    """Supported Binance API environments."""

    name: str
    base_url: str


BINANCE_PROD = BinanceEnvironment(name="prod", base_url="https://api.binance.com")
BINANCE_TESTNET = BinanceEnvironment(name="test", base_url="https://testnet.binance.vision")


class BinanceExchangeClient(LiveExchangeClient):
    """Exchange client implementation with signed order endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        environment: BinanceEnvironment = BINANCE_PROD,
        timeout_seconds: int = 10,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._environment = environment
        self._timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        """Close underlying HTTP session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None,
        client_order_id: str,
        stop_price: Decimal | None = None,
    ) -> dict:
        """Place signed order against selected Binance environment."""
        self._require_credentials()
        payload: dict[str, Any] = {
            "symbol": self._normalize_symbol(symbol),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
            "newClientOrderId": client_order_id,
            "timestamp": self._timestamp_ms(),
        }
        order_type_upper = payload["type"]
        if order_type_upper == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders.")
            payload["price"] = str(price)
            payload["timeInForce"] = "GTC"
        elif order_type_upper in ("STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"):
            if price is None:
                raise ValueError(f"price is required for {order_type_upper} orders.")
            if stop_price is None:
                raise ValueError(f"stop_price is required for {order_type_upper} orders.")
            payload["price"] = str(price)
            payload["stopPrice"] = str(stop_price)
            payload["timeInForce"] = "GTC"
        elif order_type_upper in ("STOP_LOSS", "TAKE_PROFIT_MARKET"):
            if stop_price is None:
                raise ValueError(f"stop_price is required for {order_type_upper} orders.")
            payload["stopPrice"] = str(stop_price)
        signed = self._sign_payload(payload)
        return await self._request("POST", "/api/v3/order", params=signed, signed=True)

    async def cancel_order(self, symbol: str, exchange_order_id: str) -> bool:
        """Cancel signed order by exchange id."""
        self._require_credentials()
        payload = self._sign_payload(
            {
                "symbol": self._normalize_symbol(symbol),
                "orderId": exchange_order_id,
                "timestamp": self._timestamp_ms(),
            }
        )
        await self._request("DELETE", "/api/v3/order", params=payload, signed=True)
        return True

    async def get_order(self, symbol: str, exchange_order_id: str) -> dict | None:
        """Fetch signed order status by exchange id."""
        self._require_credentials()
        payload = self._sign_payload(
            {
                "symbol": self._normalize_symbol(symbol),
                "orderId": exchange_order_id,
                "timestamp": self._timestamp_ms(),
            }
        )
        return await self._request("GET", "/api/v3/order", params=payload, signed=True)

    async def get_ticker_price(self, symbol: str) -> Decimal:
        """Fetch public ticker price for symbol from selected environment."""
        payload = {"symbol": self._normalize_symbol(symbol)}
        data = await self._request("GET", "/api/v3/ticker/price", params=payload, signed=False)
        return Decimal(str(data["price"]))

    async def get_exchange_info(self, symbol: str | None = None) -> dict:
        """Fetch exchange info (symbol filters) from Binance.

        Args:
            symbol: Optional specific symbol to fetch info for.

        Returns:
            Exchange info dict with 'symbols' and 'filters' data.
        """
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = self._normalize_symbol(symbol)
        return await self._request("GET", "/api/v3/exchangeInfo", params=params, signed=False)

    async def get_symbol_filters(self, symbol: str) -> dict | None:
        """Fetch filters for a specific symbol.

        Args:
            symbol: Trading pair symbol.

        Returns:
            Symbol data dict with filters, or None if not found.
        """
        exchange_info = await self.get_exchange_info(symbol)
        symbols_data = exchange_info.get("symbols", [])
        normalized = self._normalize_symbol(symbol)
        for sym_data in symbols_data:
            if sym_data.get("symbol") == normalized:
                return sym_data
        return None

    async def create_test_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None,
        client_order_id: str,
        stop_price: Decimal | None = None,
    ) -> dict:
        """Create test order (Binance test endpoint).

        Uses /api/v3/order/test — validates order but does NOT execute.
        Returns what the order would look like if submitted.
        Perfect for backtesting without real execution.

        Args:
            symbol: Trading pair symbol.
            side: BUY or SELL.
            order_type: MARKET, LIMIT, STOP_LOSS_LIMIT, TAKE_PROFIT_LIMIT.
            quantity: Order quantity.
            price: Limit price (required for LIMIT and conditional orders).
            client_order_id: Client-supplied order ID.
            stop_price: Trigger price for STOP_LOSS/TAKE_PROFIT orders.

        Returns:
            Test order response dict.
        """
        self._require_credentials()
        payload: dict[str, Any] = {
            "symbol": self._normalize_symbol(symbol),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
            "newClientOrderId": client_order_id,
            "timestamp": self._timestamp_ms(),
        }
        order_type_upper = payload["type"]
        if order_type_upper == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders.")
            payload["price"] = str(price)
            payload["timeInForce"] = "GTC"
        elif order_type_upper in ("STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"):
            if price is None:
                raise ValueError(f"price is required for {order_type_upper} orders.")
            if stop_price is None:
                raise ValueError(f"stop_price is required for {order_type_upper} orders.")
            payload["price"] = str(price)
            payload["stopPrice"] = str(stop_price)
            payload["timeInForce"] = "GTC"
        elif order_type_upper in ("STOP_LOSS", "TAKE_PROFIT_MARKET"):
            if stop_price is None:
                raise ValueError(f"stop_price is required for {order_type_upper} orders.")
            payload["stopPrice"] = str(stop_price)
        signed = self._sign_payload(payload)
        return await self._request("POST", "/api/v3/order/test", params=signed, signed=True)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        signed: bool,
    ) -> dict:
        session = await self._get_session()
        url = f"{self._environment.base_url}{path}"
        headers = {"X-MBX-APIKEY": self._api_key} if signed and self._api_key else {}
        async with session.request(
            method=method, url=url, params=params, headers=headers
        ) as response:
            data = await response.json()
            if response.status >= 400:
                raise RuntimeError(f"Binance API error ({response.status}): {data}")
            return data

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout_seconds)
            )
        return self._session

    def _require_credentials(self) -> None:
        if not self._api_key or not self._api_secret:
            raise RuntimeError("Binance API key/secret required for signed endpoints.")

    def _sign_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._api_secret is None:
            raise RuntimeError("Binance API secret is required for signing.")
        query_string = urlencode(payload, doseq=True)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signed = dict(payload)
        signed["signature"] = signature
        return signed

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").upper()

    @staticmethod
    def _timestamp_ms() -> int:
        return int(time.time() * 1000)
