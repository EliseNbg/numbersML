"""Backtest market service for simulated order execution."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from src.domain.market.order import (
    Balance,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from src.domain.services.market_service import MarketService

logger = logging.getLogger(__name__)


class BacktestMarketService(MarketService):
    """Market service for backtesting with simulated order execution.

    Uses historical price data from DB to simulate fills based on OHLCV data.
    Applies realistic slippage and fees, tracks portfolio performance.

    Args:
        base_asset: Quote asset for balance tracking (default USDC).
        initial_balance: Starting balance (default 10000).
        fee_bps: Fee in basis points (default 10 = 0.1%).
        slippage_bps: Slippage in basis points (default 5 = 0.05%).
        db_pool: asyncpg connection pool for fetching candle data.

    Example:
        >>> service = BacktestMarketService(db_pool=pool)
        >>> order = await service.place_order(request)
    """

    def __init__(
        self,
        db_pool: object | None = None,
        base_asset: str = "USDC",
        initial_balance: Decimal = Decimal("10000"),
        fee_bps: Decimal = Decimal("10"),
        slippage_bps: Decimal = Decimal("5"),
    ) -> None:
        self._db_pool = db_pool
        self._base_asset = base_asset
        self._balances: dict[str, Balance] = {
            base_asset: Balance(asset=base_asset, free=initial_balance, locked=Decimal("0"))
        }
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._fee_bps = fee_bps
        self._slippage_bps = slippage_bps

    async def get_balance(self, asset: str) -> Balance:
        """Return account balance snapshot for an asset.

        Args:
            asset: Asset symbol.

        Returns:
            Balance snapshot.
        """
        return self._balances.get(
            asset, Balance(asset=asset, free=Decimal("0"), locked=Decimal("0"))
        )

    async def get_balances(self) -> dict[str, dict[str, Decimal]]:
        """Return all account balances.

        Returns:
            Dict of asset -> {free, locked, total}.
        """
        return {
            asset: {
                "free": balance.free,
                "locked": balance.locked,
                "total": balance.free + balance.locked,
            }
            for asset, balance in self._balances.items()
        }

    async def get_positions(self) -> list[Position]:
        """Return all open positions.

        Returns:
            List of Position snapshots.
        """
        return list(self._positions.values())

    async def place_order(self, request: OrderRequest) -> Order:
        """Simulate order execution against historical data.

        Args:
            request: Order request.

        Returns:
            Simulated order result.
        """
        market_price = self._extract_market_price(request)
        fill_price = self._simulate_fill(market_price, request)

        if fill_price is None:
            order = self._build_order(request, OrderStatus.REJECTED, None)
            order.metadata["reason"] = "price_not_reached"
            self._orders[str(order.id)] = order
            return order

        notional = fill_price * request.quantity
        fee = notional * (self._fee_bps / Decimal("10000"))

        if request.side == OrderSide.BUY:
            quote_cost = notional + fee
            current_balance = self._balances[self._base_asset]
            if current_balance.free < quote_cost:
                order = self._build_order(request, OrderStatus.REJECTED, fill_price)
                order.metadata["reason"] = "insufficient_balance"
                self._orders[str(order.id)] = order
                return order

        self._apply_balance_and_position(request, fill_price, fee)
        order = self._build_order(request, OrderStatus.FILLED, fill_price)
        self._orders[str(order.id)] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order by internal or external identifier.

        Args:
            order_id: Order ID.

        Returns:
            True if canceled, False otherwise.
        """
        order = self._orders.get(order_id)
        if order is None:
            return False
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}:
            return False
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(UTC)
        return True

    async def get_order_status(self, order_id: str) -> Order | None:
        """Fetch order status by internal or external identifier.

        Args:
            order_id: Order ID.

        Returns:
            Order or None if not found.
        """
        return self._orders.get(order_id)

    async def get_orders(self, filters: dict | None = None) -> list[Order]:
        """Fetch orders with optional filtering.

        Args:
            filters: Optional filter dict.

        Returns:
            List of orders.
        """
        orders = list(self._orders.values())
        if not filters:
            return orders
        if filters.get("symbol"):
            orders = [o for o in orders if o.symbol == filters["symbol"]]
        if filters.get("status"):
            orders = [o for o in orders if o.status.value == filters["status"]]
        return orders

    def _extract_market_price(self, request: OrderRequest) -> Decimal:
        """Extract market price from request or metadata.

        Args:
            request: Order request.

        Returns:
            Market price as Decimal.

        Raises:
            ValueError: If no price available.
        """
        if "market_price" not in request.metadata:
            raise ValueError("market_price is required in metadata for backtest orders.")
        return Decimal(str(request.metadata["market_price"]))

    def _simulate_fill(
        self,
        market_price: Decimal,
        request: OrderRequest,
    ) -> Decimal | None:
        """Simulate fill based on order type and market price.

        Args:
            market_price: Current market price.
            request: Order request.

        Returns:
            Fill price or None if order would not fill.
        """
        slippage_ratio = self._slippage_bps / Decimal("10000")

        if request.order_type == OrderType.MARKET:
            if request.side == OrderSide.BUY:
                return market_price * (Decimal("1") + slippage_ratio)
            return market_price * (Decimal("1") - slippage_ratio)

        if request.order_type == OrderType.LIMIT:
            if request.limit_price is None:
                return None
            if request.side == OrderSide.BUY:
                if request.limit_price >= market_price:
                    return request.limit_price
                return None
            if request.limit_price <= market_price:
                return request.limit_price
            return None

        return None

    def _build_order(
        self,
        request: OrderRequest,
        status: OrderStatus,
        fill_price: Decimal | None,
    ) -> Order:
        """Build Order domain model from request and fill.

        Args:
            request: Order request.
            status: Order status.
            fill_price: Fill price (None if not filled).

        Returns:
            Order domain model.
        """
        now = datetime.now(UTC)
        return Order(
            id=uuid4(),
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            requested_price=request.limit_price,
            filled_quantity=request.quantity if status == OrderStatus.FILLED else Decimal("0"),
            average_fill_price=fill_price,
            status=status,
            mode="backtest",
            created_at=now,
            updated_at=now,
            client_order_id=request.client_order_id,
            metadata=dict(request.metadata),
        )

    def _apply_balance_and_position(
        self,
        request: OrderRequest,
        fill_price: Decimal,
        fee: Decimal,
    ) -> None:
        """Apply balance and position changes after fill.

        Args:
            request: Order request.
            fill_price: Fill price.
            fee: Trading fee.
        """
        notional = fill_price * request.quantity
        quote_balance = self._balances[self._base_asset]
        base_asset = request.symbol.split("/")[0]
        base_balance = self._balances.get(
            base_asset,
            Balance(asset=base_asset, free=Decimal("0"), locked=Decimal("0")),
        )

        if request.side == OrderSide.BUY:
            self._balances[self._base_asset] = Balance(
                asset=self._base_asset,
                free=quote_balance.free - notional - fee,
                locked=quote_balance.locked,
            )
            self._balances[base_asset] = Balance(
                asset=base_asset,
                free=base_balance.free + request.quantity,
                locked=base_balance.locked,
            )
            self._positions[request.symbol] = Position(
                symbol=request.symbol,
                quantity=request.quantity,
                average_entry_price=fill_price,
                side=OrderSide.BUY,
            )
        else:
            if base_balance.free < request.quantity:
                raise ValueError(f"Insufficient {base_asset} balance for SELL.")
            self._balances[base_asset] = Balance(
                asset=base_asset,
                free=base_balance.free - request.quantity,
                locked=base_balance.locked,
            )
            self._balances[self._base_asset] = Balance(
                asset=self._base_asset,
                free=quote_balance.free + notional - fee,
                locked=quote_balance.locked,
            )
            self._positions.pop(request.symbol, None)
