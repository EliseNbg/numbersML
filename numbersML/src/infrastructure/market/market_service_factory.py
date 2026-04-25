"""Factory for building market service implementations by mode."""

from src.domain.services.market_service import LiveExchangeClient, MarketService
from src.infrastructure.market.binance_exchange_client import (
    BINANCE_PROD,
    BINANCE_TESTNET,
    BinanceExchangeClient,
)
from src.infrastructure.market.live_market_service import LiveMarketService
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
