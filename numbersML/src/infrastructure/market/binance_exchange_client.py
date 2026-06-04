"""Binance exchange client for live market service (testnet + production)."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlencode

import logging

import aiohttp

from src.domain.services.market_service import LiveExchangeClient

logger = logging.getLogger(__name__)


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
        self._filter_cache: dict[str, dict[str, Decimal]] = {}

    async def close(self) -> None:
        """Close underlying HTTP session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    def _default_filters(self) -> dict[str, Decimal]:
        """Return safe default filters when exchangeInfo is unavailable."""
        return {
            "step_size": Decimal("0.00001"),
            "min_qty": Decimal("0"),
            "max_qty": Decimal("9999999999"),
            "market_step_size": Decimal("0.00001"),
            "market_min_qty": Decimal("0"),
            "market_max_qty": Decimal("9999999999"),
            "tick_size": Decimal("0.01"),
            "min_price": Decimal("0"),
            "max_price": Decimal("9999999999"),
        }

    @staticmethod
    def _normalize_decimal(value: str) -> Decimal:
        """Parse a string to Decimal and strip trailing zeros.

        Binance returns stepSize/tickSize like '0.01000000' which would make
        Decimal.quantize round to 8 decimal places instead of the intended 2.
        """
        return Decimal(value).normalize()

    async def _load_filters(self, symbol: str) -> dict[str, Decimal]:
        """Fetch and cache LOT_SIZE + PRICE_FILTER values for a symbol."""
        normalized = self._normalize_symbol(symbol)
        if normalized in self._filter_cache:
            cached = self._filter_cache[normalized]
            logger.info(f"[FILTERS] cache hit for {normalized}: step_size={cached.get('step_size')}, tick_size={cached.get('tick_size')}")
            return cached

        logger.info(f"[FILTERS] fetching exchangeInfo for {normalized}")
        try:
            exchange_info = await self.get_exchange_info()
            logger.info(f"[FILTERS] exchangeInfo returned {len(exchange_info.get('symbols', []))} symbols")
        except Exception as exc:
            logger.warning(f"[FILTERS] failed to fetch exchangeInfo: {exc} — using defaults")
            defaults = self._default_filters()
            self._filter_cache[normalized] = defaults
            return defaults

        for sym_data in exchange_info.get("symbols", []):
            if sym_data.get("symbol") != normalized:
                continue
            filters: dict[str, Decimal] = {}
            for f in sym_data.get("filters", []):
                ft = f.get("filterType")
                if ft == "LOT_SIZE":
                    filters["step_size"] = self._normalize_decimal(f.get("stepSize", "0.00001"))
                    filters["min_qty"] = self._normalize_decimal(f.get("minQty", "0"))
                    filters["max_qty"] = self._normalize_decimal(f.get("maxQty", "9999999999"))
                    logger.info(f"[FILTERS] {normalized} LOT_SIZE step_size={filters['step_size']}")
                elif ft == "MARKET_LOT_SIZE":
                    filters["market_step_size"] = self._normalize_decimal(f.get("stepSize", "0.00001"))
                    filters["market_min_qty"] = self._normalize_decimal(f.get("minQty", "0"))
                    filters["market_max_qty"] = self._normalize_decimal(f.get("maxQty", "9999999999"))
                    logger.info(f"[FILTERS] {normalized} MARKET_LOT_SIZE step_size={filters['market_step_size']}")
                elif ft == "PRICE_FILTER":
                    filters["tick_size"] = self._normalize_decimal(f.get("tickSize", "0.01"))
                    filters["min_price"] = self._normalize_decimal(f.get("minPrice", "0"))
                    filters["max_price"] = self._normalize_decimal(f.get("maxPrice", "9999999999"))
                    logger.info(f"[FILTERS] {normalized} PRICE_FILTER tick_size={filters['tick_size']}")
            # Fill in defaults for any missing filter keys
            defaults = self._default_filters()
            for key, val in defaults.items():
                filters.setdefault(key, val)
            self._filter_cache[normalized] = filters
            logger.info(f"[FILTERS] cached filters for {normalized}: keys={list(filters.keys())}")
            return filters

        logger.warning(f"[FILTERS] symbol {normalized} not found in exchangeInfo — using defaults")
        defaults = self._default_filters()
        self._filter_cache[normalized] = defaults
        return defaults

    def _normalize_qty(self, symbol: str, quantity: Decimal, is_market: bool) -> Decimal:
        """Round quantity down to step size."""
        filters = self._filter_cache.get(self._normalize_symbol(symbol))
        if filters is None:
            logger.warning(f"[NORM] no cached filters for {symbol}, rounding to 5 decimal places")
            return quantity.quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
        # For MARKET orders try MARKET_LOT_SIZE first, fall back to LOT_SIZE
        if is_market:
            step_size = filters.get("market_step_size") or filters.get("step_size")
        else:
            step_size = filters.get("step_size")
        if step_size is None or step_size == 0:
            return quantity
        return quantity.quantize(step_size, rounding=ROUND_DOWN)

    def _normalize_price(self, symbol: str, price: Decimal) -> Decimal:
        """Round price to tick size (nearest representable price)."""
        filters = self._filter_cache.get(self._normalize_symbol(symbol))
        if filters is None:
            logger.warning(f"[NORM] no cached filters for {symbol}, skipping price rounding")
            return price
        tick_size = filters.get("tick_size")
        if tick_size is None or tick_size == 0:
            return price
        return price.quantize(tick_size, rounding=ROUND_HALF_UP)

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
        await self._load_filters(symbol)
        is_market = order_type.upper() == "MARKET"
        normalized_qty = self._normalize_qty(symbol, quantity, is_market)
        normalized_price = self._normalize_price(symbol, price) if price is not None else None

        logger.info(
            f"[ORDER] {symbol} {side} {order_type} qty: {quantity} -> {normalized_qty}"
            f"{' price: ' + str(price) + ' -> ' + str(normalized_price) if price is not None else ''}"
        )

        payload: dict[str, Any] = {
            "symbol": self._normalize_symbol(symbol),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(normalized_qty),
            "newClientOrderId": client_order_id,
            "timestamp": self._timestamp_ms(),
        }
        order_type_upper = payload["type"]
        if order_type_upper == "LIMIT":
            if normalized_price is None:
                raise ValueError("price is required for LIMIT orders.")
            payload["price"] = str(normalized_price)
            payload["timeInForce"] = "GTC"
        elif order_type_upper in ("STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"):
            if normalized_price is None:
                raise ValueError(f"price is required for {order_type_upper} orders.")
            if stop_price is None:
                raise ValueError(f"stop_price is required for {order_type_upper} orders.")
            payload["price"] = str(normalized_price)
            payload["stopPrice"] = str(stop_price)
            payload["timeInForce"] = "GTC"
        elif order_type_upper in ("STOP_LOSS", "TAKE_PROFIT_MARKET"):
            if stop_price is None:
                raise ValueError(f"stop_price is required for {order_type_upper} orders.")
            payload["stopPrice"] = str(stop_price)
        signed = self._sign_payload(payload)
        logger.info(f"[ORDER] sending payload: symbol={payload['symbol']} qty={payload['quantity']} type={payload['type']}")
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
        await self._load_filters(symbol)
        is_market = order_type.upper() == "MARKET"
        normalized_qty = self._normalize_qty(symbol, quantity, is_market)
        normalized_price = self._normalize_price(symbol, price) if price is not None else None

        payload: dict[str, Any] = {
            "symbol": self._normalize_symbol(symbol),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(normalized_qty),
            "newClientOrderId": client_order_id,
            "timestamp": self._timestamp_ms(),
        }
        order_type_upper = payload["type"]
        if order_type_upper == "LIMIT":
            if normalized_price is None:
                raise ValueError("price is required for LIMIT orders.")
            payload["price"] = str(normalized_price)
            payload["timeInForce"] = "GTC"
        elif order_type_upper in ("STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"):
            if normalized_price is None:
                raise ValueError(f"price is required for {order_type_upper} orders.")
            if stop_price is None:
                raise ValueError(f"stop_price is required for {order_type_upper} orders.")
            payload["price"] = str(normalized_price)
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
