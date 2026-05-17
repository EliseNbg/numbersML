"""Order router for mode-based order execution."""

from __future__ import annotations

import logging

from src.domain.market.order import ExecutionMode, Order, OrderRequest
from src.domain.services.market_service import MarketService
from src.infrastructure.market.order_normalizer import OrderNormalizer

logger = logging.getLogger(__name__)


class OrderRouter:
    """Routes orders to the correct execution backend based on mode.

    Mode 1 (PAPER):
      - Order handled by PaperMarketService
      - Deterministic fills with configurable slippage/fees
      - No external API calls

    Mode 2 (LIVE/TESTNET):
      - Order sent to BinanceExchangeClient
      - Filter normalization applied first
      - Retry logic on filter violations
      - Idempotent via client_order_id

    Mode BACKTEST:
      - Uses create_test_order() endpoint
      - Simulated execution against historical data

    Args:
        paper_service: Paper trading market service.
        live_service: Live market service (mainnet).
        testnet_service: Testnet market service.
        normalizer: Order normalizer with filter retry logic.

    Example:
        >>> router = OrderRouter(paper_svc, live_svc, testnet_svc, normalizer)
        >>> order = await router.route(request, ExecutionMode.PAPER)
    """

    def __init__(
        self,
        paper_service: MarketService,
        live_service: MarketService | None = None,
        testnet_service: MarketService | None = None,
        normalizer: OrderNormalizer | None = None,
    ) -> None:
        self._paper_service = paper_service
        self._live_service = live_service
        self._testnet_service = testnet_service
        self._normalizer = normalizer

    async def route(self, request: OrderRequest, mode: ExecutionMode) -> Order:
        """Route order to appropriate backend.

        Args:
            request: Order request with symbol, side, quantity, etc.
            mode: Execution mode (PAPER, LIVE, TESTNET, BACKTEST).

        Returns:
            Order execution result.

        Raises:
            RuntimeError: If the requested mode is not configured.
            OrderNormalizationError: If filter normalization fails.
        """
        if mode == ExecutionMode.PAPER:
            return await self._paper_service.place_order(request)

        if mode == ExecutionMode.BACKTEST:
            return await self._place_test_order(request)

        if mode == ExecutionMode.TESTNET:
            if self._testnet_service is None:
                raise RuntimeError("Testnet service is not configured.")
            return await self._place_with_retry(self._testnet_service, request)

        if mode == ExecutionMode.LIVE:
            if self._live_service is None:
                raise RuntimeError("Live service is not configured.")
            return await self._place_with_retry(self._live_service, request)

        raise ValueError(f"Unknown execution mode: {mode}")

    async def _place_with_retry(
        self,
        market_service: MarketService,
        request: OrderRequest,
    ) -> Order:
        """Place order with filter normalization and retry logic.

        Args:
            market_service: Market service to place the order.
            request: Order request.

        Returns:
            Order execution result.
        """
        if self._normalizer is None:
            return await market_service.place_order(request)

        normalized = await self._normalizer.normalize_order(
            symbol=request.symbol,
            price=request.limit_price,
            quantity=request.quantity,
            order_type=request.order_type,
            side=request.side,
        )

        normalized_request = OrderRequest(
            symbol=request.symbol,
            side=request.side,
            quantity=normalized["quantity"],
            order_type=request.order_type,
            limit_price=normalized["price"],
            client_order_id=request.client_order_id,
            metadata=request.metadata,
        )

        return await market_service.place_order(normalized_request)

    async def _place_test_order(self, request: OrderRequest) -> Order:
        """Place test order for backtesting.

        Args:
            request: Order request.

        Returns:
            Simulated order result.
        """
        from datetime import UTC, datetime

        order = Order(
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            requested_price=request.limit_price,
            filled_quantity=request.quantity,
            average_fill_price=request.limit_price,
            status="FILLED",
            mode="backtest",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            client_order_id=request.client_order_id,
            metadata={"test_order": True, **request.metadata},
        )
        return order
