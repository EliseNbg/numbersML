"""Factory for building market service implementations by mode."""

from src.domain.services.market_service import LiveExchangeClient, MarketService
from src.infrastructure.market.binance_exchange_client import (
    BINANCE_PROD,
    BINANCE_TESTNET,
    BinanceExchangeClient,
)
from src.infrastructure.market.binance_filters import BinanceFilterEngine
from src.infrastructure.market.live_market_service import LiveMarketService
from src.infrastructure.market.order_normalizer import OrderNormalizer
from src.infrastructure.market.order_router import OrderRouter
from src.infrastructure.market.paper_market_service import PaperMarketService


def create_market_service(
    mode: str,
    exchange_client: LiveExchangeClient | None = None,
    execution_enabled: bool = False,
) -> MarketService:
    """Create market service for paper or live mode."""
    normalized_mode = mode.lower()
    if normalized_mode == "paper":
        return PaperMarketService()
    if normalized_mode == "live":
        if exchange_client is None:
            raise ValueError("exchange_client is required for live mode.")
        return LiveMarketService(
            exchange_client=exchange_client,
            execution_enabled=execution_enabled,
        )
    raise ValueError(f"Unsupported market mode: {mode}")


def create_binance_live_market_service(
    api_key: str,
    api_secret: str,
    environment: str = "prod",
    execution_enabled: bool = False,
) -> MarketService:
    """Create a Binance-backed live market service for prod or testnet."""
    env = environment.lower()
    if env not in {"prod", "test"}:
        raise ValueError("environment must be 'prod' or 'test'.")
    exchange_client = BinanceExchangeClient(
        api_key=api_key,
        api_secret=api_secret,
        environment=BINANCE_PROD if env == "prod" else BINANCE_TESTNET,
    )
    return LiveMarketService(
        exchange_client=exchange_client,
        execution_enabled=execution_enabled,
    )


def create_order_router(
    paper_service: MarketService | None = None,
    live_api_key: str | None = None,
    live_api_secret: str | None = None,
    testnet_api_key: str | None = None,
    testnet_api_secret: str | None = None,
    live_enabled: bool = False,
    testnet_enabled: bool = False,
    filter_cache_ttl: int = 300,
) -> OrderRouter:
    """Create order router with configured execution backends.

    Args:
        paper_service: Paper trading service (created if None).
        live_api_key: Binance live API key.
        live_api_secret: Binance live API secret.
        testnet_api_key: Binance testnet API key.
        testnet_api_secret: Binance testnet API secret.
        live_enabled: Enable live execution.
        testnet_enabled: Enable testnet execution.
        filter_cache_ttl: Filter cache TTL in seconds.

    Returns:
        Configured OrderRouter instance.
    """
    paper = paper_service or PaperMarketService()
    live_service: MarketService | None = None
    testnet_service: MarketService | None = None
    normalizer: OrderNormalizer | None = None

    if live_enabled and live_api_key and live_api_secret:
        live_client = BinanceExchangeClient(
            api_key=live_api_key,
            api_secret=live_api_secret,
            environment=BINANCE_PROD,
        )
        filter_engine = BinanceFilterEngine(
            exchange_client=live_client,
            cache_ttl=filter_cache_ttl,
        )
        normalizer = OrderNormalizer(filter_engine=filter_engine)
        live_service = LiveMarketService(
            exchange_client=live_client,
            execution_enabled=True,
        )

    if testnet_enabled and testnet_api_key and testnet_api_secret:
        testnet_client = BinanceExchangeClient(
            api_key=testnet_api_key,
            api_secret=testnet_api_secret,
            environment=BINANCE_TESTNET,
        )
        if normalizer is None:
            filter_engine = BinanceFilterEngine(
                exchange_client=testnet_client,
                cache_ttl=filter_cache_ttl,
            )
            normalizer = OrderNormalizer(filter_engine=filter_engine)
        testnet_service = LiveMarketService(
            exchange_client=testnet_client,
            execution_enabled=True,
        )

    return OrderRouter(
        paper_service=paper,
        live_service=live_service,
        testnet_service=testnet_service,
        normalizer=normalizer,
    )
