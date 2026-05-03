"""
Tests for Asset Sync Service.

Tests synchronization of Binance metadata.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.services.asset_sync_service import (
    AssetSyncError,
    AssetSyncService,
)


class TestAssetSyncService:
    """Test AssetSyncService."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    @pytest.fixture
    def service(self, mock_db_pool: MagicMock) -> AssetSyncService:
        """Create AssetSyncService instance."""
        return AssetSyncService(db_pool=mock_db_pool)

    def test_service_initialization(self, mock_db_pool: MagicMock) -> None:
        """Test service initializes correctly."""
        service = AssetSyncService(
            db_pool=mock_db_pool,
            auto_activate=True,
            auto_deactivate_delisted=False,
            eu_compliance=True,
        )

        assert service.db_pool == mock_db_pool
        assert service.auto_activate is True
        assert service.auto_deactivate_delisted is False
        assert service.eu_compliance is True
        assert service._stats == {
            "fetched": 0,
            "added": 0,
            "updated": 0,
            "deactivated": 0,
            "errors": 0,
        }

    def test_service_initialization_with_defaults(self, mock_db_pool: MagicMock) -> None:
        """Test service initializes with default values."""
        service = AssetSyncService(db_pool=mock_db_pool)

        assert service.auto_activate is True
        assert service.auto_deactivate_delisted is False
        assert service.eu_compliance is True

    def test_service_rejects_none_db_pool(self) -> None:
        """Test service rejects None db_pool."""
        with pytest.raises(ValueError, match="db_pool cannot be None"):
            AssetSyncService(db_pool=None)  # type: ignore

    def test_check_eu_compliance_allowed(self, service: AssetSyncService) -> None:
        """Test EU compliance check for allowed assets."""
        assert service._check_eu_compliance("USDC") is True
        assert service._check_eu_compliance("BTC") is True
        assert service._check_eu_compliance("ETH") is True
        assert service._check_eu_compliance("EUR") is True
        assert service._check_eu_compliance("GBP") is True

    def test_check_eu_compliance_excluded(self, service: AssetSyncService) -> None:
        """Test EU compliance check for excluded assets."""
        assert service._check_eu_compliance("USDT") is False
        assert service._check_eu_compliance("BUSD") is False
        assert service._check_eu_compliance("TUSD") is False

    def test_parse_symbol_valid(self, service: AssetSyncService) -> None:
        """Test parsing valid symbol data."""
        binance_data = {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotEnabled": True,
            "filters": [
                {
                    "filterType": "PRICE_FILTER",
                    "tickSize": "0.01",
                },
                {
                    "filterType": "LOT_SIZE",
                    "stepSize": "0.00001",
                },
                {
                    "filterType": "NOTIONAL",
                    "minNotional": "10",
                },
            ],
        }

        symbol = service._parse_symbol(binance_data)

        assert symbol is not None
        assert symbol.symbol == "BTC/USDT"
        assert symbol.base_asset == "BTC"
        assert symbol.quote_asset == "USDT"
        assert symbol.tick_size == Decimal("0.01")
        assert symbol.step_size == Decimal("0.00001")
        assert symbol.min_notional == Decimal("10")
        assert symbol.is_allowed is False  # USDT excluded in EU
        assert symbol.is_active is False  # Not active if not allowed

    def test_parse_symbol_eu_compliant(self, service: AssetSyncService) -> None:
        """Test parsing EU compliant symbol."""
        binance_data = {
            "symbol": "BTCUSDC",
            "baseAsset": "BTC",
            "quoteAsset": "USDC",
            "status": "TRADING",
            "isSpotEnabled": True,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
                {"filterType": "NOTIONAL", "minNotional": "10"},
            ],
        }

        symbol = service._parse_symbol(binance_data)

        assert symbol is not None
        assert symbol.symbol == "BTC/USDC"
        assert symbol.is_allowed is True
        assert symbol.is_active is True  # Auto-activated

    def test_parse_symbol_non_trading(self, service: AssetSyncService) -> None:
        """Test parsing non-trading symbol."""
        binance_data = {
            "symbol": "BTCUSDT",
            "status": "BREAK",  # Not trading
        }

        symbol = service._parse_symbol(binance_data)
        assert symbol is None

    def test_parse_symbol_missing_assets(self, service: AssetSyncService) -> None:
        """Test parsing symbol with missing assets."""
        binance_data = {
            "symbol": "BTCUSDT",
            "baseAsset": "",  # Missing
            "quoteAsset": "USDT",
            "status": "TRADING",
        }

        symbol = service._parse_symbol(binance_data)
        assert symbol is None

    def test_parse_symbol_no_filters(self, service: AssetSyncService) -> None:
        """Test parsing symbol with no filters."""
        binance_data = {
            "symbol": "BTCUSDC",
            "baseAsset": "BTC",
            "quoteAsset": "USDC",
            "status": "TRADING",
            "isSpotEnabled": True,
            "filters": [],
        }

        symbol = service._parse_symbol(binance_data)

        assert symbol is not None
        assert symbol.tick_size == Decimal("0.00000001")  # Default
        assert symbol.step_size == Decimal("0.00000001")  # Default
        assert symbol.min_notional == Decimal("10")  # Default

    def test_extract_filters(self, service: AssetSyncService) -> None:
        """Test extracting filters from Binance data."""
        binance_data = {
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
                {"filterType": "NOTIONAL", "minNotional": "15"},
            ],
        }

        tick_size, step_size, min_notional = service._extract_filters(binance_data)

        assert tick_size == Decimal("0.01")
        assert step_size == Decimal("0.00001")
        assert min_notional == Decimal("15")

    def test_extract_filters_empty(self, service: AssetSyncService) -> None:
        """Test extracting filters with no data."""
        binance_data = {"filters": []}

        tick_size, step_size, min_notional = service._extract_filters(binance_data)

        assert tick_size == Decimal("0.00000001")
        assert step_size == Decimal("0.00000001")
        assert min_notional == Decimal("10")

    def test_extract_filters_partial(self, service: AssetSyncService) -> None:
        """Test extracting filters with partial data."""
        binance_data = {
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                # Missing LOT_SIZE and NOTIONAL
            ],
        }

        tick_size, step_size, min_notional = service._extract_filters(binance_data)

        assert tick_size == Decimal("0.01")
        assert step_size == Decimal("0.00000001")  # Default
        assert min_notional == Decimal("10")  # Default

    def test_get_stats(self, service: AssetSyncService) -> None:
        """Test getting statistics."""
        service._stats = {
            "fetched": 100,
            "added": 10,
            "updated": 5,
            "deactivated": 2,
            "errors": 1,
        }

        stats = service.get_stats()

        assert stats == {
            "fetched": 100,
            "added": 10,
            "updated": 5,
            "deactivated": 2,
            "errors": 1,
        }

    def test_get_stats_returns_copy(self, service: AssetSyncService) -> None:
        """Test that get_stats returns a copy."""
        stats = service.get_stats()
        stats["fetched"] = 999

        assert service.get_stats()["fetched"] == 0


class TestAssetSyncServiceIntegration:
    """Integration tests for AssetSyncService."""

    @pytest.mark.skip(reason="HTTP mocking for aiohttp async context managers needs update")
    @pytest.mark.asyncio
    async def test_fetch_exchange_info(self) -> None:
        """Test fetching exchange info from Binance."""
        # Create service with mock pool
        mock_pool = MagicMock()
        service = AssetSyncService(db_pool=mock_pool)

        # Fetch from real Binance API (mocked HTTP)
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "baseAsset": "BTC",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "isSpotEnabled": True,
                            "filters": [],
                        }
                    ]
                }
            )

            # Setup async context manager for session
            mock_session = AsyncMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response

            # Setup async context manager for ClientSession
            mock_session_class.return_value.__aenter__.return_value = mock_session

            symbols = await service._fetch_exchange_info()

            assert len(symbols) == 1
            assert symbols[0]["symbol"] == "BTCUSDT"

    @pytest.mark.skip(reason="HTTP mocking for aiohttp async context managers needs update")
    @pytest.mark.asyncio
    async def test_fetch_exchange_info_error(self) -> None:
        """Test fetching exchange info with error."""
        mock_pool = MagicMock()
        service = AssetSyncService(db_pool=mock_pool)

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 500  # Error

            # Setup async context manager for session
            mock_session = AsyncMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response

            # Setup async context manager for ClientSession
            mock_session_class.return_value.__aenter__.return_value = mock_session

            with pytest.raises(AssetSyncError, match="status 500"):
                await service._fetch_exchange_info()


class TestAssetSyncError:
    """Test AssetSyncError exception."""

    def test_asset_sync_error_creation(self) -> None:
        """Test creating AssetSyncError."""
        error = AssetSyncError("Test error message")

        assert error.message == "Test error message"
        assert str(error) == "Test error message"

    def test_asset_sync_error_inheritance(self) -> None:
        """Test AssetSyncError inherits from Exception."""
        error = AssetSyncError("Test")

        assert isinstance(error, Exception)
        assert isinstance(error, BaseException)
