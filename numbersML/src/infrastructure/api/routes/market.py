"""
Market/Order management API endpoints.

Provides REST API for market operations:
- Balances and positions
- Order creation, cancellation, status
- Trade history

Architecture: Infrastructure Layer (API)
Dependencies: Application services, Domain models
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

try:
    from pydantic import field_validator
except ImportError:
    from pydantic import validator as field_validator

from src.domain.market.order import Order, OrderSide, OrderStatus, OrderType
from src.domain.services.market_service import MarketService
from src.domain.strategies.base import Position
from src.infrastructure.api.auth import AuthContext, require_trader
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.market.market_service_factory import create_market_service

router = APIRouter(prefix="/api/market", tags=["market"])

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models - Request/Response validation
# ============================================================================


class BalanceResponse(BaseModel):
    """Response model for account balance."""

    asset: str
    free: float
    locked: float
    total: float


class PositionResponse(BaseModel):
    """Response model for trading position."""

    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_percent: float
    opened_at: datetime

    @classmethod
    def from_domain(cls, position: Position) -> "PositionResponse":
        return cls(
            symbol=position.symbol,
            side=position.side,
            quantity=float(position.quantity),
            entry_price=float(position.entry_price),
            current_price=float(position.current_price),
            unrealized_pnl=float(position.unrealized_pnl),
            pnl_percent=position.pnl_percent,
            opened_at=position.opened_at,
        )


class OrderCreateRequest(BaseModel):
    """Request model for creating an order."""

    symbol: str = Field(..., description="Trading pair e.g. BTC/USDC")
    side: OrderSide = Field(..., description="BUY or SELL")
    order_type: OrderType = Field(default=OrderType.LIMIT, description="Order type")
    quantity: float = Field(..., gt=0, description="Order quantity")
    price: float | None = Field(None, gt=0, description="Limit price (required for LIMIT orders)")
    time_in_force: str = Field(default="GTC", description="Time in force: GTC, IOC, FOK")
    strategy_id: UUID | None = Field(None, description="Associated strategy ID")
    metadata: dict[str, Any] | None = None

    @field_validator("price")
    def validate_price_for_limit_orders(cls, v, info):
        if info.data.get("order_type") == OrderType.LIMIT and v is None:
            raise ValueError("Price is required for LIMIT orders")
        return v


class OrderResponse(BaseModel):
    """Response model for order."""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None
    filled_quantity: float
    remaining_quantity: float
    status: OrderStatus
    time_in_force: str
    strategy_id: UUID | None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]

    @classmethod
    def from_domain(cls, order: Order) -> "OrderResponse":
        return cls(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=float(order.quantity),
            price=float(order.price) if order.price else None,
            filled_quantity=float(order.filled_quantity),
            remaining_quantity=float(order.remaining_quantity),
            status=order.status,
            time_in_force=order.time_in_force,
            strategy_id=order.strategy_id,
            created_at=order.created_at,
            updated_at=order.updated_at,
            metadata=order.metadata,
        )


class TradeResponse(BaseModel):
    """Response model for trade/fill."""

    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float
    fee_asset: str
    timestamp: datetime


class MarketDataResponse(BaseModel):
    """Response model for market data."""

    symbol: str
    bid: float
    ask: float
    last_price: float
    volume_24h: float
    price_change_24h: float
    high_24h: float
    low_24h: float
    timestamp: datetime


try:
    from pydantic import field_validator
except ImportError:
    from pydantic import validator as field_validator

    # Override field_validator for older pydantic
    pass


# ============================================================================
# Dependency injections
# ============================================================================


async def get_market_service(mode: str = "paper") -> MarketService:
    """Get MarketService instance."""
    db_pool = await get_db_pool_async()
    # For paper mode by default; live mode requires API keys
    return create_market_service(
        mode=mode,
        exchange_client=None,
        execution_enabled=True,
    )


# ============================================================================
# Balance & Position Endpoints
# ============================================================================


@router.get(
    "/balances",
    response_model=list[BalanceResponse],
    summary="Get account balances",
    description="Get all account balances (free, locked, total) per asset.",
)
async def get_balances(
    asset: str | None = None,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> list[BalanceResponse]:
    """
    Get all account balances.

    Args:
        asset: Optional asset filter (e.g., 'USDC', 'BTC')
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        List of balance information per asset

    Raises:
        500: Failed to fetch balances
    """
    try:
        balances = await market_service.get_balances()
        result = []
        for asset_name, balance in balances.items():
            if asset and asset_name != asset:
                continue
            result.append(
                BalanceResponse(
                    asset=asset_name,
                    free=float(balance.get("free", 0)),
                    locked=float(balance.get("locked", 0)),
                    total=float(balance.get("total", 0)),
                )
            )
        return result

    except Exception as e:
        logger.error(f"Failed to get balances: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch balances: {str(e)}",
        )


@router.get(
    "/balances/{asset}",
    response_model=BalanceResponse,
    summary="Get specific asset balance",
    description="Get balance for a specific asset.",
)
async def get_balance(
    asset: str,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> BalanceResponse:
    """
    Get balance for a specific asset.

    Args:
        asset: Asset symbol (e.g., 'USDC')
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        Balance information

    Raises:
        404: Asset not found
        500: Failed to fetch balance
    """
    try:
        balances = await market_service.get_balances()
        if asset not in balances:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset {asset} not found",
            )
        balance = balances[asset]
        return BalanceResponse(
            asset=asset,
            free=float(balance.get("free", 0)),
            locked=float(balance.get("locked", 0)),
            total=float(balance.get("total", 0)),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get balance for {asset}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch balance: {str(e)}",
        )


@router.get(
    "/positions",
    response_model=list[PositionResponse],
    summary="Get all positions",
    description="Get all open trading positions.",
)
async def get_positions(
    symbol: str | None = None,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> list[PositionResponse]:
    """
    Get all open trading positions.

    Args:
        symbol: Optional symbol filter
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        List of open positions

    Raises:
        500: Failed to fetch positions
    """
    try:
        positions = await market_service.get_positions()
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        return [PositionResponse.from_domain(p) for p in positions]

    except Exception as e:
        logger.error(f"Failed to get positions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch positions: {str(e)}",
        )


@router.get(
    "/positions/{symbol}",
    response_model=PositionResponse,
    summary="Get position by symbol",
    description="Get a specific trading position by symbol.",
)
async def get_position(
    symbol: str,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> PositionResponse:
    """
    Get a specific trading position by symbol.

    Args:
        symbol: Trading pair symbol
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        Position information

    Raises:
        404: Position not found
        500: Failed to fetch position
    """
    try:
        positions = await market_service.get_positions()
        for position in positions:
            if position.symbol == symbol:
                return PositionResponse.from_domain(position)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No position found for {symbol}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get position for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch position: {str(e)}",
        )


# ============================================================================
# Order Management Endpoints
# ============================================================================


@router.post(
    "/orders",
    response_model=OrderResponse,
    summary="Create order",
    description="Create and submit a new order.",
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    request: OrderCreateRequest,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
    auth: AuthContext = Depends(require_trader),
) -> OrderResponse:
    """
    Create and submit a new order.

    Args:
        request: Order creation request
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        Created order

    Raises:
        400: Invalid order data
        500: Failed to create order
    """
    try:
        # Handle price for market orders
        price = request.price if request.price else 0.0

        order = await market_service.create_order(
            symbol=request.symbol,
            side=request.side.value,
            order_type=request.order_type.value,
            quantity=request.quantity,
            price=price,
            time_in_force=request.time_in_force,
            metadata={
                "strategy_id": str(request.strategy_id) if request.strategy_id else None,
                **(request.metadata or {}),
            },
        )
        return OrderResponse.from_domain(order)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to create order: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}",
        )


@router.get(
    "/orders",
    response_model=list[OrderResponse],
    summary="List orders",
    description="List all orders with optional filtering.",
)
async def list_orders(
    symbol: str | None = None,
    status: str | None = None,
    strategy_id: UUID | None = None,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> list[OrderResponse]:
    """
    List all orders with optional filtering.

    Args:
        symbol: Optional symbol filter
        status: Optional status filter
        strategy_id: Optional strategy filter
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        List of orders

    Raises:
        500: Failed to fetch orders
    """
    try:
        filters = {}
        if symbol:
            filters["symbol"] = symbol
        if status:
            filters["status"] = status
        if strategy_id:
            filters["strategy_id"] = strategy_id

        orders = await market_service.get_orders(filters)
        return [OrderResponse.from_domain(o) for o in orders]

    except Exception as e:
        logger.error(f"Failed to list orders: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch orders: {str(e)}",
        )


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    summary="Get order",
    description="Get order details by ID.",
)
async def get_order(
    order_id: str,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> OrderResponse:
    """
    Get order details by ID.

    Args:
        order_id: Order ID
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        Order details

    Raises:
        404: Order not found
        500: Failed to fetch order
    """
    try:
        order = await market_service.get_order(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found",
            )
        return OrderResponse.from_domain(order)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch order: {str(e)}",
        )


@router.delete(
    "/orders/{order_id}",
    response_model=dict[str, Any],
    summary="Cancel order",
    description="Cancel an open order.",
)
async def cancel_order(
    order_id: str,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
    auth: AuthContext = Depends(require_trader),
) -> dict[str, Any]:
    """
    Cancel an open order.

    Args:
        order_id: Order ID
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        Success message

    Raises:
        404: Order not found
        400: Order cannot be cancelled
        500: Failed to cancel order
    """
    try:
        success = await market_service.cancel_order(order_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order {order_id} cannot be cancelled",
            )
        return {"message": f"Order {order_id} cancelled"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order: {str(e)}",
        )


# ============================================================================
# Trade History Endpoints
# ============================================================================


@router.get(
    "/trades",
    response_model=list[TradeResponse],
    summary="List trades",
    description="List all trades with optional filtering.",
)
async def list_trades(
    symbol: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> list[TradeResponse]:
    """
    List all trades with optional filtering.

    Args:
        symbol: Optional symbol filter
        start_time: Optional start time filter
        end_time: Optional end time filter
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        List of trades

    Raises:
        500: Failed to fetch trades
    """
    try:
        trades = await market_service.get_trades()
        # Apply filters
        if symbol:
            trades = [t for t in trades if t.symbol == symbol]
        if start_time:
            trades = [t for t in trades if t.timestamp >= start_time]
        if end_time:
            trades = [t for t in trades if t.timestamp <= end_time]

        return [
            TradeResponse(
                trade_id=t.trade_id,
                order_id=t.order_id,
                symbol=t.symbol,
                side=t.side,
                quantity=float(t.quantity),
                price=float(t.price),
                fee=float(t.fee) if t.fee else 0.0,
                fee_asset=t.fee_asset if hasattr(t, "fee_asset") else "USDC",
                timestamp=t.timestamp,
            )
            for t in trades
        ]

    except Exception as e:
        logger.error(f"Failed to list trades: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch trades: {str(e)}",
        )


# ============================================================================
# Market Data Endpoints
# ============================================================================


@router.get(
    "/ticker/{symbol}",
    response_model=MarketDataResponse,
    summary="Get market ticker",
    description="Get current market data for a symbol.",
)
async def get_ticker(
    symbol: str,
    mode: str = "paper",
    market_service: MarketService = Depends(get_market_service),
) -> MarketDataResponse:
    """
    Get current market data for a symbol.

    Args:
        symbol: Trading pair symbol
        mode: Market mode (paper/live)
        market_service: Market service instance

    Returns:
        Current market data

    Raises:
        404: Symbol not found
        500: Failed to fetch market data
    """
    try:
        ticker = await market_service.get_ticker(symbol)
        return MarketDataResponse(
            symbol=ticker["symbol"],
            bid=float(ticker["bid"]),
            ask=float(ticker["ask"]),
            last_price=float(ticker["last_price"]),
            volume_24h=float(ticker.get("volume_24h", 0)),
            price_change_24h=float(ticker.get("price_change_24h", 0)),
            high_24h=float(ticker.get("high_24h", 0)),
            low_24h=float(ticker.get("low_24h", 0)),
            timestamp=datetime.now(UTC),
        )

    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol {symbol} not found",
        )
    except Exception as e:
        logger.error(f"Failed to get ticker for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch market data: {str(e)}",
        )
