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
        if payload["type"] == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders.")
            payload["price"] = str(price)
            payload["timeInForce"] = "GTC"
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
