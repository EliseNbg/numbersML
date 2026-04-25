"""Unit tests for Binance exchange client helpers."""

from src.infrastructure.market.binance_exchange_client import BinanceExchangeClient


class TestBinanceExchangeClient:
    """Validate pure helper behavior for symbol normalization."""

    def test_normalize_symbol(self) -> None:
        assert BinanceExchangeClient._normalize_symbol("BTC/USDC") == "BTCUSDC"
        assert BinanceExchangeClient._normalize_symbol("shib/usdc") == "SHIBUSDC"
