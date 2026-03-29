"""
Tests for WideVectorService.

Tests:
    - Vector generation from candle_indicators
    - Processed flag is set after generation
    - Missing indicators handled gracefully
    - Vector has correct column names
    - Vector stored in DB
"""

import json
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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
        assert service._indicator_keys == []

    def test_init_with_symbols(self, mock_db_pool: MagicMock) -> None:
        """Test initialization with symbols."""
        symbols = [(58, 'BTC/USDC'), (59, 'ETH/USDC')]
        service = WideVectorService(mock_db_pool, symbols)
        assert service._active_symbols == symbols

    @pytest.mark.asyncio
    async def test_load_symbols(self, mock_db_pool: MagicMock) -> None:
        """Test loading symbols from DB."""
        mock_rows = [
            {'id': 58, 'symbol': 'BTC/USDC'},
            {'id': 59, 'symbol': 'ETH/USDC'},
        ]
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        await service.load_symbols()

        assert len(service._active_symbols) == 2
        assert service._active_symbols[0] == (58, 'BTC/USDC')
        assert service._active_symbols[1] == (59, 'ETH/USDC')

    @pytest.mark.asyncio
    async def test_generate_no_symbols(self, mock_db_pool: MagicMock) -> None:
        """Test generate with no active symbols."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        result = await service.generate(datetime.now(timezone.utc))

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_with_candles_and_indicators(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Test full vector generation."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)

        candle_rows = [
            {'symbol_id': 58, 'symbol': 'BTC/USDC', 'close': Decimal('67000'), 'volume': Decimal('1.5')},
            {'symbol_id': 59, 'symbol': 'ETH/USDC', 'close': Decimal('3500'), 'volume': Decimal('10')},
        ]
        indicator_rows = [
            {
                'symbol_id': 58, 'symbol': 'BTC/USDC',
                'values': json.dumps({'rsi': 65.0, 'sma': 66900.0}),
                'indicator_keys': ['rsi', 'sma'],
            },
            {
                'symbol_id': 59, 'symbol': 'ETH/USDC',
                'values': json.dumps({'rsi': 45.0, 'sma': 3480.0}),
                'indicator_keys': ['rsi', 'sma'],
            },
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, 'BTC/USDC'), (59, 'ETH/USDC')],
        )
        result = await service.generate(now)

        assert result is not None
        assert result['symbol_count'] == 2
        assert result['indicator_count'] == 2
        assert result['vector_size'] == 8  # 2 symbols * (2 candle + 2 indicator)

        # Check column order
        assert result['column_names'] == [
            'BTC/USDC_close', 'BTC/USDC_volume', 'BTC/USDC_rsi', 'BTC/USDC_sma',
            'ETH/USDC_close', 'ETH/USDC_volume', 'ETH/USDC_rsi', 'ETH/USDC_sma',
        ]

        # Check vector values
        assert result['vector'][0] == 67000.0  # BTC close
        assert result['vector'][4] == 3500.0   # ETH close

    @pytest.mark.asyncio
    async def test_generate_no_candles(self, mock_db_pool: MagicMock) -> None:
        """Test generate returns None when no candles exist."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, 'BTC/USDC')],
        )
        result = await service.generate(datetime.now(timezone.utc))
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_sets_processed_flag(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Test that processed flag is set after generation."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)

        candle_rows = [
            {'symbol_id': 58, 'symbol': 'BTC/USDC',
             'close': Decimal('67000'), 'volume': Decimal('1.5')},
        ]
        indicator_rows = [
            {'symbol_id': 58, 'symbol': 'BTC/USDC',
             'values': json.dumps({'rsi': 65.0}),
             'indicator_keys': ['rsi']},
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, 'BTC/USDC')],
        )
        await service.generate(now)

        # Check that processed flag was set
        execute_calls = mock_conn.execute.call_args_list
        update_call = execute_calls[-1]  # Last execute is the UPDATE
        assert 'processed = true' in update_call[0][0]

    @pytest.mark.asyncio
    async def test_get_vector(self, mock_db_pool: MagicMock) -> None:
        """Test reading stored vector from DB."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
        vector = [67000.0, 1.5, 65.0, 3500.0, 10.0, 45.0]

        mock_row = {
            'time': now,
            'vector': json.dumps(vector),
            'column_names': ['BTC/USDC_close', 'BTC/USDC_vol', 'BTC/USDC_rsi',
                            'ETH/USDC_close', 'ETH/USDC_vol', 'ETH/USDC_rsi'],
            'symbols': ['BTC/USDC', 'ETH/USDC'],
            'vector_size': 6,
            'symbol_count': 2,
            'indicator_count': 1,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        result = await service.get_vector(now)

        assert result is not None
        assert result['vector'] == vector
        assert result['symbol_count'] == 2
        assert len(result['column_names']) == 6

    @pytest.mark.asyncio
    async def test_get_vector_not_found(self, mock_db_pool: MagicMock) -> None:
        """Test reading nonexistent vector returns None."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(mock_db_pool)
        result = await service.get_vector(datetime.now(timezone.utc))
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_missing_indicators_handled(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Test that missing indicators for one symbol are handled."""
        now = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)

        candle_rows = [
            {'symbol_id': 58, 'symbol': 'BTC/USDC',
             'close': Decimal('67000'), 'volume': Decimal('1.5')},
            {'symbol_id': 59, 'symbol': 'ETH/USDC',
             'close': Decimal('3500'), 'volume': Decimal('10')},
        ]
        # Only BTC has indicators, ETH does not
        indicator_rows = [
            {'symbol_id': 58, 'symbol': 'BTC/USDC',
             'values': json.dumps({'rsi': 65.0}),
             'indicator_keys': ['rsi']},
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[candle_rows, indicator_rows])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        service = WideVectorService(
            mock_db_pool,
            [(58, 'BTC/USDC'), (59, 'ETH/USDC')],
        )
        result = await service.generate(now)

        assert result is not None
        # Layout: [BTC_close, BTC_vol, BTC_rsi, ETH_close, ETH_vol, ETH_rsi]
        assert result['vector'][2] == 65.0    # BTC rsi
        assert result['vector'][5] == 0.0     # ETH rsi (missing)
        assert result['vector'][3] == 3500.0  # ETH close (from candles)
