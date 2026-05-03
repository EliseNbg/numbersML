"""Paper trading market service implementation."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from src.domain.market.order import Balance, Order, OrderRequest, OrderSide, OrderStatus, Position
from src.domain.services.market_service import MarketService


class PaperMarketService(MarketService):
    """Simulated market service with deterministic fills and balances."""

    def __init__(
        self,
        base_asset: str = "USDC",
        initial_balance: Decimal = Decimal("10000"),
        fee_bps: Decimal = Decimal("10"),
        slippage_bps: Decimal = Decimal("5"),
    ) -> None:
        self._base_asset = base_asset
        self._balances: dict[str, Balance] = {
            base_asset: Balance(asset=base_asset, free=initial_balance, locked=Decimal("0"))
        }
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._fee_bps = fee_bps
        self._slippage_bps = slippage_bps

    async def get_balance(self, asset: str) -> Balance:
        return self._balances.get(
            asset, Balance(asset=asset, free=Decimal("0"), locked=Decimal("0"))
        )

    async def get_balances(self) -> dict[str, dict[str, Decimal]]:
        """Return all balances as {asset: {"free": free, "locked": locked, "total": total}}."""
        return {
            asset: {
                "free": balance.free,
                "locked": balance.locked,
                "total": balance.free + balance.locked,
            }
            for asset, balance in self._balances.items()
        }

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def place_order(self, request: OrderRequest) -> Order:
        market_price = self._extract_market_price(request)
        fill_price = self._apply_slippage(market_price, request.side)
        notional = fill_price * request.quantity
        fee = notional * (self._fee_bps / Decimal("10000"))
        quote_cost = notional + fee if request.side == OrderSide.BUY else Decimal("0")

        current_balance = self._balances[self._base_asset]
        if request.side == OrderSide.BUY and current_balance.free < quote_cost:
            order = self._build_order(request, OrderStatus.REJECTED, fill_price)
            order.metadata["reason"] = "insufficient_balance"
            self._orders[str(order.id)] = order
            return order

        self._apply_balance_and_position(request, fill_price, fee)
        order = self._build_order(request, OrderStatus.FILLED, fill_price)
        self._orders[str(order.id)] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order is None:
            return False
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}:
            return False
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(UTC)
        return True

    async def get_order_status(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def _extract_market_price(self, request: OrderRequest) -> Decimal:
        if request.order_type.value == "LIMIT":
            if request.limit_price is None:
                raise ValueError("limit_price is required for LIMIT orders.")
            return request.limit_price
        if "market_price" not in request.metadata:
            raise ValueError("market_price is required in metadata for paper MARKET orders.")
        return Decimal(str(request.metadata["market_price"]))

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        ratio = self._slippage_bps / Decimal("10000")
        if side == OrderSide.BUY:
            return price * (Decimal("1") + ratio)
        return price * (Decimal("1") - ratio)

    def _build_order(
        self, request: OrderRequest, status: OrderStatus, fill_price: Decimal
    ) -> Order:
        now = datetime.now(UTC)
        return Order(
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            requested_price=request.limit_price,
            filled_quantity=request.quantity if status == OrderStatus.FILLED else Decimal("0"),
            average_fill_price=fill_price if status == OrderStatus.FILLED else None,
            status=status,
            mode="paper",
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
            return

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

    def seed_order(self, order: Order) -> None:
        """Test helper to inject pending orders for cancel behavior."""
        self._orders[str(order.id)] = order

    def get_order_by_uuid(self, order_id: UUID) -> Order | None:
        """Retrieve order by UUID for convenience in tests."""
        return self._orders.get(str(order_id))
