"""
Unit tests for IndicatorCalculator service.

Tests:
    - Definition loading
    - Indicator class import
    - Candle fetching
    - Indicator calculation
    - Result writing
"""

import pytest
import json
import numpy as np
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.pipeline.indicator_calculator import IndicatorCalculator


class TestIndicatorCalculator:
    """Test IndicatorCalculator service."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    def test_init(self, mock_db_pool: MagicMock) -> None:
        """Test initialization."""
        calc = IndicatorCalculator(mock_db_pool)
        assert calc.db_pool is mock_db_pool
        assert calc._definitions == []
        assert calc._class_cache == {}

    @pytest.mark.asyncio
    async def test_load_definitions(self, mock_db_pool: MagicMock) -> None:
        """Test loading indicator definitions from DB."""
        mock_rows = [
            {
                "name": "rsi_14",
                "class_name": "RSIIndicator",
                "module_path": "src.indicators.momentum",
                "params": {"period": 14},
            },
            {
                "name": "sma_20",
                "class_name": "SMAIndicator",
                "module_path": "src.indicators.trend",
                "params": {"period": 20},
            },
        ]
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        calc = IndicatorCalculator(mock_db_pool)
        await calc.load_definitions()

        assert len(calc._definitions) == 2
        assert calc._definitions[0]["name"] == "rsi_14"
        assert calc._definitions[1]["name"] == "sma_20"

    @pytest.mark.asyncio
    async def test_load_definitions_with_string_params(self, mock_db_pool: MagicMock) -> None:
        """Test loading definitions when params is a JSON string."""
        mock_rows = [
            {
                "name": "rsi_14",
                "class_name": "RSIIndicator",
                "module_path": "src.indicators.momentum",
                "params": '{"period": 14}',
            },
        ]
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        calc = IndicatorCalculator(mock_db_pool)
        await calc.load_definitions()

        assert len(calc._definitions) == 1
        assert calc._definitions[0]["params"] == {"period": 14}

    @pytest.mark.asyncio
    async def test_load_definitions_empty(self, mock_db_pool: MagicMock) -> None:
        """Test loading with no definitions."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        calc = IndicatorCalculator(mock_db_pool)
        await calc.load_definitions()

        assert calc._definitions == []

    def test_get_indicator_class_valid(self) -> None:
        """Test importing a valid indicator class."""
        calc = IndicatorCalculator(MagicMock())
        cls = calc._get_indicator_class("RSIIndicator", "src.indicators.momentum")
        assert cls is not None
        assert cls.__name__ == "RSIIndicator"

    def test_get_indicator_class_cached(self) -> None:
        """Test that class is cached after first import."""
        calc = IndicatorCalculator(MagicMock())
        cls1 = calc._get_indicator_class("RSIIndicator", "src.indicators.momentum")
        cls2 = calc._get_indicator_class("RSIIndicator", "src.indicators.momentum")
        assert cls1 is cls2

    def test_get_indicator_class_invalid(self) -> None:
        """Test importing an invalid class returns None."""
        calc = IndicatorCalculator(MagicMock())
        cls = calc._get_indicator_class("NonExistentIndicator", "src.indicators.momentum")
        assert cls is None

    def test_get_indicator_class_invalid_module(self) -> None:
        """Test importing from invalid module returns None."""
        calc = IndicatorCalculator(MagicMock())
        cls = calc._get_indicator_class("RSIIndicator", "nonexistent.module")
        assert cls is None

    @pytest.mark.asyncio
    async def test_get_symbol_id(self, mock_db_pool: MagicMock) -> None:
        """Test getting symbol ID."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=42)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        calc = IndicatorCalculator(mock_db_pool)
        symbol_id = await calc._get_symbol_id("BTC/USDC")

        assert symbol_id == 42
        assert calc._symbol_id_cache["BTC/USDC"] == 42

    @pytest.mark.asyncio
    async def test_get_symbol_id_cached(self, mock_db_pool: MagicMock) -> None:
        """Test symbol ID is cached."""
        calc = IndicatorCalculator(mock_db_pool)
        calc._symbol_id_cache["BTC/USDC"] = 42

        symbol_id = await calc._get_symbol_id("BTC/USDC")
        assert symbol_id == 42

    @pytest.mark.asyncio
    async def test_get_symbol_id_not_found(self, mock_db_pool: MagicMock) -> None:
        """Test getting symbol ID when symbol doesn't exist."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        calc = IndicatorCalculator(mock_db_pool)
        symbol_id = await calc._get_symbol_id("FAKE/USDC")

        assert symbol_id is None

    @pytest.mark.asyncio
    async def test_calculate_no_symbol(self, mock_db_pool: MagicMock) -> None:
        """Test calculate with unknown symbol returns 0."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        calc = IndicatorCalculator(mock_db_pool)
        result = await calc.calculate("FAKE/USDC")

        assert result == 0

    @pytest.mark.asyncio
    async def test_calculate_no_candles(self, mock_db_pool: MagicMock) -> None:
        """Test calculate with no candles returns 0."""
        calc = IndicatorCalculator(mock_db_pool)
        calc._symbol_id_cache["BTC/USDC"] = 1

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await calc.calculate("BTC/USDC")
        assert result == 0

    @pytest.mark.asyncio
    async def test_calculate_with_indicators(self, mock_db_pool: MagicMock) -> None:
        """Test full calculation with real indicators."""
        calc = IndicatorCalculator(mock_db_pool)
        calc._symbol_id_cache["BTC/USDC"] = 1
        calc._definitions = [
            {
                "name": "sma_5",
                "class_name": "SMAIndicator",
                "module_path": "src.indicators.trend",
                "params": {"period": 5},
            },
        ]

        now = datetime.now(timezone.utc).replace(microsecond=0)
        mock_candles = [
            {
                "time": now,
                "open": 100 + i,
                "high": 101 + i,
                "low": 99 + i,
                "close": 100 + i,
                "volume": 10 + i,
                "quote_volume": 1000 + i * 100,
            }
            for i in range(20)
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_candles)
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await calc.calculate("BTC/USDC")
        assert result == 1
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_bad_indicator_class(self, mock_db_pool: MagicMock) -> None:
        """Test calculation with unimportable indicator class."""
        calc = IndicatorCalculator(mock_db_pool)
        calc._symbol_id_cache["BTC/USDC"] = 1
        calc._definitions = [
            {
                "name": "fake",
                "class_name": "NonExistent",
                "module_path": "nonexistent.module",
                "params": {},
            },
        ]

        now = datetime.now(timezone.utc).replace(microsecond=0)
        mock_candles = [
            {
                "time": now,
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
                "quote_volume": 1000,
            }
            for _ in range(5)
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_candles)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await calc.calculate("BTC/USDC")
        assert result == 0

    @pytest.mark.asyncio
    async def test_write_results(self, mock_db_pool: MagicMock) -> None:
        """Test writing indicator results."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        calc = IndicatorCalculator(mock_db_pool)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        await calc._write_results(
            symbol="BTC/USDC",
            symbol_id=1,
            time=now,
            price=50000.0,
            volume=1.5,
            values={"rsi": 65.3, "sma": 49900.0},
        )

        mock_conn.execute.assert_called_once()
        args = mock_conn.execute.call_args[0]
        assert args[2] == 1  # symbol_id
        assert args[3] == 50000.0  # price
        # Check that indicator_keys (arg 6) is derived from values keys
        assert "rsi" in args[6]
        assert "sma" in args[6]
