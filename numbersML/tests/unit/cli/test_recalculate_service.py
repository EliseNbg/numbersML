"""
Tests for the recalculation CLI service functions.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.cli.recalculate import (
    get_symbol_ids,
    reset_processed,
)


class TestGetSymbolIds:
    """Test symbol ID retrieval."""

    @pytest.mark.asyncio
    async def test_get_specific_symbols(self):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": 58}, {"id": 59}])
        result = await get_symbol_ids(mock_conn, ["BTC/USDC", "ETH/USDC"])
        assert result == [58, 59]

    @pytest.mark.asyncio
    async def test_get_all_active_symbols(self):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": 58}, {"id": 59}, {"id": 60}])
        result = await get_symbol_ids(mock_conn, None)
        assert result == [58, 59, 60]

    @pytest.mark.asyncio
    async def test_get_no_symbols(self):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        result = await get_symbol_ids(mock_conn, None)
        assert result == []


class TestResetProcessed:
    """Test reset processed flag functionality."""

    @pytest.mark.asyncio
    async def test_reset_with_to_time(self):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 150")
        from_time = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        to_time = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)
        result = await reset_processed(mock_conn, [58, 59], from_time, to_time)
        assert result == 150

    @pytest.mark.asyncio
    async def test_reset_without_to_time(self):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 300")
        from_time = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = await reset_processed(mock_conn, [58, 59], from_time, None)
        assert result == 300