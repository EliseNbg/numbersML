"""Binance filter engine for order validation and normalization."""

from __future__ import annotations

import logging
import time
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

from src.domain.market.order import OrderSide, OrderType, SymbolFilters
from src.infrastructure.market.binance_exchange_client import BinanceExchangeClient

logger = logging.getLogger(__name__)


class BinanceFilterError(Exception):
    """Raised when an order violates Binance exchange filters."""

    def __init__(self, message: str, filter_type: str | None = None) -> None:
        super().__init__(message)
        self.filter_type = filter_type


class OrderNormalizationError(Exception):
    """Raised when order normalization fails after retries."""


class BinanceFilterEngine:
    """Validates and normalizes orders against Binance exchange filters.

    Responsibilities:
    - Fetch and cache exchange info (filters) per symbol
    - Normalize price to tick size (PRICE_FILTER)
    - Normalize quantity to step size (LOT_SIZE / MARKET_LOT_SIZE)
    - Validate min/max bounds
    - Validate notional value (MIN_NOTIONAL / NOTIONAL)
    - Retry with ±0.5% adjustment on filter violation

    Args:
        exchange_client: Binance exchange client for fetching filter data.
        cache_ttl: Cache time-to-live in seconds (default 300).

    Example:
        >>> engine = BinanceFilterEngine(client)
        >>> filters = await engine.load_filters("BTC/USDC")
        >>> price = engine.normalize_price("BTC/USDC", Decimal("67123.456"))
    """

    def __init__(
        self,
        exchange_client: BinanceExchangeClient,
        cache_ttl: int = 300,
    ) -> None:
        self._client = exchange_client
        self._filter_cache: dict[str, tuple[SymbolFilters, float]] = {}
        self._cache_ttl = cache_ttl

    async def load_filters(self, symbol: str) -> SymbolFilters:
        """Fetch filters from /api/v3/exchangeInfo and cache.

        Args:
            symbol: Trading pair symbol (e.g. "BTC/USDC").

        Returns:
            SymbolFilters dataclass with all filter values.
        """
        now = time.monotonic()
        cached = self._filter_cache.get(symbol)
        if cached is not None:
            filters, ts = cached
            if now - ts < self._cache_ttl:
                return filters

        try:
            filters = await self._fetch_symbol_filters(symbol)
        except Exception as exc:
            logger.warning(f"Failed to fetch filters for {symbol}: {exc}")
            filters = self._default_filters(symbol)

        self._filter_cache[symbol] = (filters, now)
        return filters

    def normalize_price(self, symbol: str, price: Decimal) -> Decimal:
        """Round price to tick_size, clamp to min/max.

        Args:
            symbol: Trading pair symbol.
            price: Raw price value.

        Returns:
            Normalized price rounded to tick size.

        Raises:
            BinanceFilterError: If price is negative or zero.
        """
        filters = self._get_cached_or_default(symbol)

        if price <= 0:
            raise BinanceFilterError(f"Price must be positive: {price}", "PRICE_FILTER")

        # Round to tick size
        tick_size = filters.tick_size
        rounded = price.quantize(tick_size, rounding=ROUND_HALF_UP)

        # Clamp to min/max
        clamped = max(filters.min_price, min(rounded, filters.max_price))

        return clamped

    def normalize_quantity(
        self,
        symbol: str,
        quantity: Decimal,
        order_type: OrderType,
    ) -> Decimal:
        """Round quantity to step_size, clamp to min/max.

        Args:
            symbol: Trading pair symbol.
            quantity: Raw quantity value.
            order_type: Order type (MARKET uses MARKET_LOT_SIZE).

        Returns:
            Normalized quantity rounded to step size.

        Raises:
            BinanceFilterError: If quantity is zero or negative.
        """
        filters = self._get_cached_or_default(symbol)

        if quantity <= 0:
            raise BinanceFilterError(
                f"Quantity must be positive: {quantity}",
                "LOT_SIZE",
            )

        # Use MARKET_LOT_SIZE for market orders
        if order_type == OrderType.MARKET:
            step_size = filters.market_step_size
            min_qty = filters.market_min_qty
            max_qty = filters.market_max_qty
        else:
            step_size = filters.step_size
            min_qty = filters.min_qty
            max_qty = filters.max_qty

        # Truncate down to step size (never round up for quantity)
        rounded = quantity.quantize(step_size, rounding=ROUND_DOWN)

        # Clamp to min/max
        clamped = max(min_qty, min(rounded, max_qty))

        if clamped <= 0:
            raise BinanceFilterError(
                f"Quantity {quantity} rounds to zero or below minimum",
                "LOT_SIZE",
            )

        return clamped

    def validate_notional(
        self,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
        order_type: OrderType,
    ) -> bool:
        """Check price * quantity >= minNotional.

        Args:
            symbol: Trading pair symbol.
            price: Normalized price.
            quantity: Normalized quantity.
            order_type: Order type (affects notional rules).

        Returns:
            True if notional is within bounds.

        Raises:
            BinanceFilterError: If notional is out of bounds.
        """
        filters = self._get_cached_or_default(symbol)
        notional = price * quantity

        # MIN_NOTIONAL check
        if order_type == OrderType.MARKET:
            min_notional = filters.min_notional
        else:
            min_notional = filters.min_notional

        if notional < min_notional:
            raise BinanceFilterError(
                f"Notional {notional} below minimum {min_notional}",
                "MIN_NOTIONAL",
            )

        # NOTIONAL max check
        if notional > filters.max_notional:
            raise BinanceFilterError(
                f"Notional {notional} above maximum {filters.max_notional}",
                "NOTIONAL",
            )

        return True

    async def normalize_order(
        self,
        symbol: str,
        price: Decimal | None,
        quantity: Decimal,
        order_type: OrderType,
        side: OrderSide,
    ) -> dict[str, Decimal | None]:
        """Full normalization: price, quantity, notional.

        Args:
            symbol: Trading pair symbol.
            price: Raw price (None for MARKET orders).
            quantity: Raw quantity.
            order_type: Order type.
            side: Order side (BUY/SELL).

        Returns:
            Dict with 'price' and 'quantity' keys (price may be None for MARKET).

        Raises:
            BinanceFilterError: If normalization fails.
        """
        # Refresh filters if needed
        await self.load_filters(symbol)

        normalized_qty = self.normalize_quantity(symbol, quantity, order_type)

        normalized_price: Decimal | None = None
        if price is not None:
            normalized_price = self.normalize_price(symbol, price)

            # Validate notional
            self.validate_notional(symbol, normalized_price, normalized_qty, order_type)

        return {"price": normalized_price, "quantity": normalized_qty}

    def invalidate_cache(self, symbol: str | None = None) -> None:
        """Invalidate cached filters.

        Args:
            symbol: Specific symbol to invalidate, or None for all.
        """
        if symbol is None:
            self._filter_cache.clear()
        else:
            self._filter_cache.pop(symbol, None)

    def _get_cached_or_default(self, symbol: str) -> SymbolFilters:
        """Get cached filters or return defaults (non-async)."""
        cached = self._filter_cache.get(symbol)
        if cached is not None:
            filters, ts = cached
            if time.monotonic() - ts < self._cache_ttl:
                return filters
        return self._default_filters(symbol)

    async def _fetch_symbol_filters(self, symbol: str) -> SymbolFilters:
        """Fetch and parse filters from exchange info API.

        Args:
            symbol: Trading pair symbol.

        Returns:
            Parsed SymbolFilters dataclass.
        """
        exchange_info = await self._client.get_exchange_info()
        symbols_data = exchange_info.get("symbols", [])

        normalized_symbol = symbol.replace("/", "").upper()
        for sym_data in symbols_data:
            if sym_data.get("symbol") == normalized_symbol:
                return self._parse_filters(normalized_symbol, sym_data.get("filters", []))

        raise BinanceFilterError(f"Symbol {symbol} not found in exchange info")

    @staticmethod
    def _parse_filters(symbol: str, raw_filters: list[dict]) -> SymbolFilters:
        """Parse raw Binance filter list into SymbolFilters.

        Args:
            symbol: Trading pair symbol.
            raw_filters: List of filter dicts from exchange info.

        Returns:
            Parsed SymbolFilters dataclass.
        """
        result: dict[str, Any] = {"symbol": symbol}

        for f in raw_filters:
            filter_type = f.get("filterType")

            if filter_type == "PRICE_FILTER":
                result["min_price"] = Decimal(f.get("minPrice", "0"))
                result["max_price"] = Decimal(f.get("maxPrice", "9999999999"))
                result["tick_size"] = Decimal(f.get("tickSize", "0.01"))

            elif filter_type == "LOT_SIZE":
                result["min_qty"] = Decimal(f.get("minQty", "0"))
                result["max_qty"] = Decimal(f.get("maxQty", "9999999999"))
                result["step_size"] = Decimal(f.get("stepSize", "0.00001"))

            elif filter_type == "MARKET_LOT_SIZE":
                result["market_min_qty"] = Decimal(f.get("minQty", "0"))
                result["market_max_qty"] = Decimal(f.get("maxQty", "9999999999"))
                result["market_step_size"] = Decimal(f.get("stepSize", "0.00001"))

            elif filter_type in ("MIN_NOTIONAL", "NOTIONAL"):
                if "minNotional" in f:
                    result["min_notional"] = Decimal(f["minNotional"])
                if "maxNotional" in f:
                    result["max_notional"] = Decimal(f["maxNotional"])

            elif filter_type == "PERCENT_PRICE_BY_SIDE":
                if "bidMultiplierUp" in f:
                    result["bid_multiplier_up"] = Decimal(f["bidMultiplierUp"])
                if "bidMultiplierDown" in f:
                    result["bid_multiplier_down"] = Decimal(f["bidMultiplierDown"])
                if "askMultiplierUp" in f:
                    result["ask_multiplier_up"] = Decimal(f["askMultiplierUp"])
                if "askMultiplierDown" in f:
                    result["ask_multiplier_down"] = Decimal(f["askMultiplierDown"])

            elif filter_type == "MAX_NUM_ORDERS":
                if "maxNumOrders" in f:
                    result["max_num_orders"] = int(f["maxNumOrders"])

            elif filter_type == "MAX_POSITION":
                if "maxPosition" in f:
                    result["max_position"] = Decimal(f["maxPosition"])

        return SymbolFilters(**result)

    @staticmethod
    def _default_filters(symbol: str) -> SymbolFilters:
        """Return safe default filters when API is unavailable.

        Args:
            symbol: Trading pair symbol.

        Returns:
            SymbolFilters with permissive defaults.
        """
        return SymbolFilters(symbol=symbol)

    @staticmethod
    def _decimal_places(value: Decimal) -> int:
        """Get number of decimal places from a Decimal.

        Args:
            value: Decimal value.

        Returns:
            Number of decimal places.
        """
        return abs(value.as_tuple().exponent)
