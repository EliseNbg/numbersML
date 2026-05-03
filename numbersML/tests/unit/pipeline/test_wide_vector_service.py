"""
Tests for WideVectorService.

Tests:
    - Vector generation from candle_indicators
    - Missing indicators handled gracefully
    - Vector has correct column names
    - Vector stored in DB
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pipeline.wide_vector_service import WideVectorService


class TestWideVectorService:
    """Test WideVectorService."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    def test_init(self, mock_db_pool: MagicMock) -> None:
        """Test initialization."""
        service = WideVectorService(mock_db_pool)
        assert service.db_pool is mock_db_pool
        assert service._active_symbols == []
        assert service._indicator_keys is None  # None means not loaded yet

    def test_init_with_symbols(self, mock_db_pool: MagicMock) -> None:
        """Test initialization with symbols."""
        symbols = [(58, "BTC/USDC"), (59, "ETH/USDC")]
        service = WideVectorService(mock_db_pool, symbols)
        assert service._active_symbols == symbols

    @pytest.mark.asyncio
    async def test_load_symbols(self, mock_db_pool: MagicMock) -> None:
        """Test loading symbols from DB."""
        mock_rows = [
            {"id": 58, "symbol": "BTC/USDC"},
            {"id": 59, "symbol": "ETH/USDC"},
        ]
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        await service.load_symbols()

        assert len(service._active_symbols) == 2
        assert service._active_symbols[0] == (58, "BTC/USDC")
        assert service._active_symbols[1] == (59, "ETH/USDC")

    @pytest.mark.asyncio
    async def test_generate_no_symbols(self, mock_db_pool: MagicMock) -> None:
        """Test generate with no active symbols."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        service._indicator_keys = []  # Skip schema load
        result = await service.generate(datetime.now(UTC))

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_with_candles_and_indicators(self, mock_db_pool: MagicMock) -> None:
        """Test full vector generation."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

        candle_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "close": Decimal("67000"),
                "volume": Decimal("1.5"),
            },
            {
                "symbol_id": 59,
                "symbol": "ETH/USDC",
                "close": Decimal("3500"),
                "volume": Decimal("10"),
            },
        ]
        indicator_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "values": json.dumps({"rsi": 65.0, "sma": 66900.0}),
                "indicator_keys": ["rsi", "sma"],
            },
            {
                "symbol_id": 59,
                "symbol": "ETH/USDC",
                "values": json.dumps({"rsi": 45.0, "sma": 3480.0}),
                "indicator_keys": ["rsi", "sma"],
            },
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, "BTC/USDC"), (59, "ETH/USDC")],
        )
        service._external_provider = None  # Disable external features for this test
        service._indicator_keys = ["rsi", "sma"]  # Skip schema load
        result = await service.generate(now)

        assert result is not None
        assert result["symbol_count"] == 2
        assert result["indicator_count"] == 2
        assert result["vector_size"] == 8  # 2 symbols * (2 candle + 2 indicator)

        # Check column order
        assert result["column_names"] == [
            "BTC_USDC_close",
            "BTC_USDC_volume",
            "BTC_USDC_rsi",
            "BTC_USDC_sma",
            "ETH_USDC_close",
            "ETH_USDC_volume",
            "ETH_USDC_rsi",
            "ETH_USDC_sma",
        ]

        # Check vector values
        assert result["vector"][0] == 67000.0  # BTC close
        assert result["vector"][4] == 3500.0  # ETH close

    @pytest.mark.asyncio
    async def test_generate_no_candles(self, mock_db_pool: MagicMock) -> None:
        """Test generate returns None when no candles and no history exist."""
        mock_conn = AsyncMock()
        # No candles, no history → all forward-fill queries return []
        mock_conn.fetch = AsyncMock(
            side_effect=[
                [],  # candle_rows (empty)
                [],  # indicator_rows (empty)
                [],  # last_candle_rows (no history)
                [],  # last_indicator_rows (no history)
            ]
        )
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, "BTC/USDC")],
        )
        service._indicator_keys = []  # Skip schema load
        # Mock external provider to return predictable features
        mock_external_features = {"ext_feat": 0.0}
        service._external_provider = lambda candles, indicators, candle_time: mock_external_features
        result = await service.generate(datetime.now(UTC))
        # Returns vector with external features + 0.0 values for candle features since no data
        expected_vector = list(mock_external_features.values()) + [0.0, 0.0]
        assert result is not None
        assert result["vector"] == expected_vector

    @pytest.mark.asyncio
    async def test_get_vector(self, mock_db_pool: MagicMock) -> None:
        """Test reading stored vector from DB."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)
        vector = [67000.0, 1.5, 65.0, 3500.0, 10.0, 45.0]

        mock_row = {
            "time": now,
            "vector": json.dumps(vector),
            "column_names": [
                "BTC/USDC_close",
                "BTC/USDC_vol",
                "BTC/USDC_rsi",
                "ETH/USDC_close",
                "ETH/USDC_vol",
                "ETH/USDC_rsi",
            ],
            "symbols": ["BTC/USDC", "ETH/USDC"],
            "vector_size": 6,
            "symbol_count": 2,
            "indicator_count": 1,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        result = await service.get_vector(now)

        assert result is not None
        assert result["vector"] == vector
        assert result["symbol_count"] == 2
        assert len(result["column_names"]) == 6

    @pytest.mark.asyncio
    async def test_get_vector_not_found(self, mock_db_pool: MagicMock) -> None:
        """Test reading nonexistent vector returns None."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        result = await service.get_vector(datetime.now(UTC))
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_missing_indicators_handled(self, mock_db_pool: MagicMock) -> None:
        """Test that missing indicators for one symbol are handled."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

        candle_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "close": Decimal("67000"),
                "volume": Decimal("1.5"),
            },
            {
                "symbol_id": 59,
                "symbol": "ETH/USDC",
                "close": Decimal("3500"),
                "volume": Decimal("10"),
            },
        ]
        # Only BTC has indicators, ETH does not
        indicator_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "values": json.dumps({"rsi": 65.0}),
                "indicator_keys": ["rsi"],
            },
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, "BTC/USDC"), (59, "ETH/USDC")],
        )
        service._external_provider = None  # Disable external features for this test
        service._indicator_keys = ["rsi", "sma"]  # Skip schema load
        result = await service.generate(now)

        assert result is not None
        # Layout: [BTC_close, BTC_vol, BTC_rsi, BTC_sma, ETH_close, ETH_vol, ETH_rsi, ETH_sma]
        assert result["vector"][0] == 67000.0  # BTC close
        assert result["vector"][2] == 65.0  # BTC rsi
        assert result["vector"][3] == 0.0  # BTC sma (no data in this batch)
        assert result["vector"][4] == 3500.0  # ETH close
        assert result["vector"][6] == 0.0  # ETH rsi (missing)
        assert result["vector"][7] == 0.0  # ETH sma (missing)

    @pytest.mark.asyncio
    async def test_generate_with_external_provider(self, mock_db_pool: MagicMock) -> None:
        """Test that external provider features are prepended to vector."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

        candle_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "close": Decimal("67000"),
                "volume": Decimal("1.5"),
            },
        ]
        indicator_rows = []

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        def mock_provider(candles, indicators, candle_time):
            return {"my_feature": 42.0, "another_feature": 3.14}

        service = WideVectorService(
            mock_db_pool,
            [(58, "BTC/USDC")],
        )
        service._external_provider = mock_provider
        service._indicator_keys = ["my_feature", "another_feature", "rsi"]  # Skip schema load
        result = await service.generate(now)

        assert result is not None
        # External features: sorted(['another_feature', 'my_feature']) = ['another_feature', 'my_feature']
        # Then inserted at index 0: first 'another_feature' -> [3.14], then 'my_feature' -> [42.0, 3.14]
        # So vector[0]=my_feature (42.0), vector[1]=another_feature (3.14)
        assert (
            result["vector_size"] == 7
        )  # 2 external + 2 candle + 3 indicators (all 0.0 since no data)
        assert result["vector"][0] == 42.0  # my_feature (last inserted at 0)
        assert result["vector"][1] == 3.14  # another_feature (first inserted at 0)
        assert result["vector"][2] == 67000.0  # BTC close
        assert result["vector"][3] == 1.5  # BTC volume

    @pytest.mark.asyncio
    async def test_external_provider_receives_normalized_keys(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Test that external provider gets BTC_USDC not BTC/USDC."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

        candle_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "close": Decimal("67000"),
                "volume": Decimal("1.5"),
            },
        ]
        indicator_rows = []

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        received_candles = {}

        def mock_provider(candles, indicators, candle_time):
            received_candles.update(candles)
            return {}

        service = WideVectorService(
            mock_db_pool,
            [(58, "BTC/USDC")],
        )
        service._external_provider = mock_provider
        service._indicator_keys = []  # Skip schema load
        await service.generate(now)

        assert "BTC_USDC" in received_candles
        assert "BTC/USDC" not in received_candles

    @pytest.mark.asyncio
    async def test_external_provider_error_handled(self, mock_db_pool: MagicMock) -> None:
        """Test that external provider exception does not break vector generation."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

        candle_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "close": Decimal("67000"),
                "volume": Decimal("1.5"),
            },
        ]
        indicator_rows = []

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        def bad_provider(candles, indicators, candle_time):
            raise ValueError("External API down")

        service = WideVectorService(
            mock_db_pool,
            [(58, "BTC/USDC")],
        )
        service._external_provider = bad_provider
        service._indicator_keys = []  # Skip schema load
        result = await service.generate(now)

        # Should still succeed without external features
        assert result is not None
        assert result["vector_size"] == 2  # Only close + volume

    @pytest.mark.asyncio
    async def test_no_external_provider_works(self, mock_db_pool: MagicMock) -> None:
        """Test that None provider works normally."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

        candle_rows = [
            {
                "symbol_id": 58,
                "symbol": "BTC/USDC",
                "close": Decimal("67000"),
                "volume": Decimal("1.5"),
            },
        ]
        indicator_rows = []

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, "BTC/USDC")],
        )
        service._external_provider = None
        service._indicator_keys = []  # Skip schema load
        result = await service.generate(now)

        assert result is not None
        assert result["vector_size"] == 2
