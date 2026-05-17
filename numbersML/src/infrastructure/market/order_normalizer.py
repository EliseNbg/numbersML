"""Order normalizer with retry logic for Binance filter compliance."""

from __future__ import annotations

import logging
from decimal import Decimal

from src.domain.market.order import OrderSide, OrderType
from src.domain.services.market_service import MarketService
from src.infrastructure.market.binance_filters import (
    BinanceFilterEngine,
    BinanceFilterError,
    OrderNormalizationError,
)

logger = logging.getLogger(__name__)


class OrderNormalizer:
    """Applies filters and retries on failure with incremental adjustment.

    Retry strategy:
    1. Try exact normalized values
    2. On filter error, adjust price ±0.5% and re-normalize
    3. On filter error, adjust quantity ±0.5% and re-normalize
    4. Max 3 retries total
    5. If all fail, return error with details

    Args:
        filter_engine: Binance filter engine for normalization.

    Example:
        >>> normalizer = OrderNormalizer(filter_engine)
        >>> order = await normalizer.place_with_retry(service, request)
    """

    MAX_RETRIES = 3
    ADJUSTMENT_PCT = Decimal("0.005")  # 0.5%

    def __init__(self, filter_engine: BinanceFilterEngine) -> None:
        self._filter_engine = filter_engine

    async def place_with_retry(
        self,
        market_service: MarketService,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> dict:
        """Place order with filter retry logic.

        Args:
            market_service: Market service to place the order.
            symbol: Trading pair symbol.
            side: Order side (BUY/SELL).
            quantity: Raw quantity.
            order_type: Order type (MARKET/LIMIT).
            price: Raw price (None for MARKET orders).
            client_order_id: Optional client order ID for idempotency.

        Returns:
            Dict with normalized 'price' and 'quantity'.

        Raises:
            OrderNormalizationError: If all retries fail.
        """
        from src.domain.market.order import OrderRequest

        last_error: Exception | None = None
        current_price = price
        current_quantity = quantity

        for attempt in range(self.MAX_RETRIES):
            try:
                normalized = await self._filter_engine.normalize_order(
                    symbol=symbol,
                    price=current_price,
                    quantity=current_quantity,
                    order_type=order_type,
                    side=side,
                )

                request = OrderRequest(
                    symbol=symbol,
                    side=side,
                    quantity=normalized["quantity"],
                    order_type=order_type,
                    limit_price=normalized["price"],
                    client_order_id=client_order_id,
                )

                await market_service.place_order(request)
                return normalized

            except BinanceFilterError as exc:
                last_error = exc
                logger.warning(
                    f"Filter error on attempt {attempt + 1} for {symbol}: {exc}"
                )

                if attempt == 0:
                    current_price = self._adjust_price(current_price, exc.filter_type, side)
                elif attempt == 1:
                    current_quantity = self._adjust_quantity(current_quantity, exc.filter_type)
                elif attempt == 2:
                    current_price = self._adjust_price(current_price, exc.filter_type, side)
                    current_quantity = self._adjust_quantity(current_quantity, exc.filter_type)

        raise OrderNormalizationError(
            f"Failed to normalize order after {self.MAX_RETRIES} retries: {last_error}"
        )

    def _adjust_price(
        self,
        price: Decimal | None,
        filter_type: str | None,
        side: OrderSide,
    ) -> Decimal | None:
        """Adjust price by ±0.5% based on filter type and side.

        Args:
            price: Current price.
            filter_type: Type of filter that failed.
            side: Order side.

        Returns:
            Adjusted price or None if price was None.
        """
        if price is None:
            return None

        # For MIN_NOTIONAL errors, increase price for BUY, decrease for SELL
        if filter_type == "MIN_NOTIONAL":
            if side == OrderSide.BUY:
                return price * (Decimal("1") + self.ADJUSTMENT_PCT)
            return price * (Decimal("1") - self.ADJUSTMENT_PCT)

        # For NOTIONAL max errors, decrease price
        if filter_type == "NOTIONAL":
            return price * (Decimal("1") - self.ADJUSTMENT_PCT)

        # Default: adjust slightly based on side
        if side == OrderSide.BUY:
            return price * (Decimal("1") + self.ADJUSTMENT_PCT)
        return price * (Decimal("1") - self.ADJUSTMENT_PCT)

    def _adjust_quantity(
        self,
        quantity: Decimal,
        filter_type: str | None,
    ) -> Decimal:
        """Adjust quantity by ±0.5% based on filter type.

        Args:
            quantity: Current quantity.
            filter_type: Type of filter that failed.

        Returns:
            Adjusted quantity.
        """
        # For MIN_NOTIONAL errors, increase quantity
        if filter_type == "MIN_NOTIONAL":
            return quantity * (Decimal("1") + self.ADJUSTMENT_PCT)

        # For NOTIONAL max errors, decrease quantity
        if filter_type == "NOTIONAL":
            return quantity * (Decimal("1") - self.ADJUSTMENT_PCT)

        # For LOT_SIZE errors, increase slightly
        if filter_type == "LOT_SIZE":
            return quantity * (Decimal("1") + self.ADJUSTMENT_PCT)

        # Default: increase slightly
        return quantity * (Decimal("1") + self.ADJUSTMENT_PCT)
