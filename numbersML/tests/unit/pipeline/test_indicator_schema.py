"""
Test for wide_vector_service indicator schema fix.
Verifies that multi-output indicators (BollingerBands, MACD) contribute
their full set of output keys to the wide vector.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.pipeline.wide_vector_service import WideVectorService


@pytest.fixture
def mock_db_pool() -> MagicMock:
    """Create mock database pool."""
    pool = MagicMock()
    pool.acquire = MagicMock()
    return pool


class TestIndicatorSchema:
    """Test indicator schema loading."""

    @pytest.mark.asyncio
    async def test_load_indicator_schema_multi_output_indicators(self, mock_db_pool: MagicMock) -> None:
        """Test that multi-output indicators generate all their sub-keys."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                'name': 'bb_20_2',
                'class_name': 'BollingerBandsIndicator',
                'params': '{"period": 20, "std_dev": 2}'
            },
            {
                'name': 'macd_12_26_9',
                'class_name': 'MACDIndicator',
                'params': '{"fast_period": 12, "slow_period": 26, "signal_period": 9}'
            },
            {
                'name': 'rsi_14',
                'class_name': 'RSIIndicator',
                'params': '{"period": 14}'
            },
        ])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        service = WideVectorService(mock_db_pool)
        await service._load_indicator_schema()
        
        # Should have: bb_20_2 (4 keys) + macd_12_26_9 (3 keys) + rsi_14 (1 key) = 8 keys
        expected_keys = [
            'bb_20_2_lower',
            'bb_20_2_middle',
            'bb_20_2_std',
            'bb_20_2_upper',
            'macd_12_26_9_histogram',
            'macd_12_26_9_macd',
            'macd_12_26_9_signal',
            'rsi_14',
        ]
        
        assert len(service._indicator_keys) == 8
        assert service._indicator_keys == expected_keys

    @pytest.mark.asyncio
    async def test_generate_vector_size_with_multi_output_indicators(self, mock_db_pool: MagicMock) -> None:
        """Test that generated vectors have correct size with multi-output indicators."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(return_value=None)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        service = WideVectorService(mock_db_pool, active_symbols=[
            (1, 'BTC/USDC'),
            (2, 'ETH/USDC'),
        ])
        
        # Mock schema load
        service._indicator_keys = [
            'atr_14', 'bb_20_2_lower', 'bb_20_2_middle', 'bb_20_2_std', 'bb_20_2_upper',
            'macd_12_26_9_macd', 'macd_12_26_9_signal', 'macd_12_26_9_histogram',
            'rsi_14', 'sma_20',
        ]
        service._last_known = {
            'BTC/USDC': {
                'close': 50000.0, 'volume': 1000.0,
                'atr_14': 100.0, 'bb_20_2_lower': 49000.0, 'bb_20_2_middle': 50000.0,
                'bb_20_2_std': 50.0, 'bb_20_2_upper': 51000.0,
                'macd_12_26_9_macd': -50.0, 'macd_12_26_9_signal': -40.0,
                'macd_12_26_9_histogram': -10.0, 'rsi_14': 0.5, 'sma_20': 49500.0,
            },
            'ETH/USDC': {
                'close': 3000.0, 'volume': 5000.0,
                'atr_14': 50.0, 'bb_20_2_lower': 2950.0, 'bb_20_2_middle': 3000.0,
                'bb_20_2_std': 25.0, 'bb_20_2_upper': 3050.0,
                'macd_12_26_9_macd': -20.0, 'macd_12_26_9_signal': -15.0,
                'macd_12_26_9_histogram': -5.0, 'rsi_14': 0.6, 'sma_20': 2980.0,
            },
        }
        service._active_symbols = [(1, 'BTC/USDC'), (2, 'ETH/USDC')]
        
        # Mock external provider to return predictable features
        mock_external_features = {'ext_feature_1': 0.5, 'ext_feature_2': 0.3}
        service._external_provider = lambda candles, indicators, candle_time: mock_external_features
        
        result = await service.generate(datetime.now(timezone.utc))

        # Expected: external_features + 2 symbols × (2 candle features + 10 indicators)
        expected_vector_size = len(mock_external_features) + 2 * (2 + 10)
        assert result['vector_size'] == expected_vector_size
        assert result['indicator_count'] == 10
        assert result['symbol_count'] == 2

    @pytest.mark.asyncio
    async def test_load_indicator_schema_active_definitions(self, mock_db_pool: MagicMock) -> None:
        """Test that schema is loaded from active indicator definitions."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                'name': 'atr_14',
                'class_name': 'ATRIndicator',
                'params': '{"period": 14}'
            },
            {
                'name': 'ema_12',
                'class_name': 'EMAIndicator',
                'params': '{"period": 12}'
            },
            {
                'name': 'macd_12_26_9',
                'class_name': 'MACDIndicator',
                'params': '{"fast_period": 12, "slow_period": 26, "signal_period": 9}'
            },
            {
                'name': 'bb_20_2',
                'class_name': 'BollingerBandsIndicator',
                'params': '{"period": 20, "std_dev": 2}'
            },
        ])
        
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        service = WideVectorService(mock_db_pool)
        await service._load_indicator_schema()
        
        # Should have: atr_14 + ema_12 + macd (3) + bb (4) = 9 keys
        assert len(service._indicator_keys) == 9
        assert 'atr_14' in service._indicator_keys
        assert 'ema_12' in service._indicator_keys
        assert 'macd_12_26_9_macd' in service._indicator_keys
        assert 'macd_12_26_9_signal' in service._indicator_keys
        assert 'macd_12_26_9_histogram' in service._indicator_keys
        assert 'bb_20_2_lower' in service._indicator_keys
        assert 'bb_20_2_middle' in service._indicator_keys
        assert 'bb_20_2_std' in service._indicator_keys
        assert 'bb_20_2_upper' in service._indicator_keys
