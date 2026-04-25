"""Unit tests for market service factory."""

from unittest.mock import AsyncMock

import pytest

from src.infrastructure.market.live_market_service import LiveMarketService
from src.infrastructure.market.market_service_factory import create_market_service
from src.infrastructure.market.paper_market_service import PaperMarketService


@pytest.mark.unit
class TestMarketServiceFactory:
    """Validate service selection and input guards."""

    def test_create_paper_service(self) -> None:
        service = create_market_service(mode="paper")
        assert isinstance(service, PaperMarketService)

    def test_create_live_service_requires_exchange_client(self) -> None:
        with pytest.raises(ValueError, match="exchange_client is required"):
            create_market_service(mode="live")

    def test_create_live_service(self) -> None:
        service = create_market_service(
            mode="live",
            exchange_client=AsyncMock(),
            execution_enabled=False,
        )
        assert isinstance(service, LiveMarketService)

    def test_unsupported_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported market mode"):
            create_market_service(mode="staging")
