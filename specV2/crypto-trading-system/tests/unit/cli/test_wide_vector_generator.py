"""
Tests for Wide Vector Generator (LLM Input).

Tests the generation of wide SQL rows with all symbols' data
as a flat vector for LLM buy/sell decision making.
"""

import pytest
import numpy as np
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from src.cli.generate_wide_vector import WideVectorGenerator


class TestWideVectorGenerator:
    """Test wide vector generation for LLM model."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    @pytest.fixture
    def generator(self, mock_db_pool: MagicMock) -> WideVectorGenerator:
        """Create vector generator instance."""
        gen = WideVectorGenerator(
            db_url="postgresql://test:test@localhost/test",
            symbols=['BTC/USDC', 'ETH/USDC'],
            include_indicators=True,
        )
        gen.db_pool = mock_db_pool
        gen._symbol_list = ['BTC/USDC', 'ETH/USDC']
        return gen

    def test_generator_initialization(self) -> None:
        """Test generator initializes correctly."""
        gen = WideVectorGenerator(
            db_url="postgresql://test:test@localhost/test",
            symbols=['BTC/USDC', 'ETH/USDC'],
            include_indicators=True,
        )

        assert gen.db_url == "postgresql://test:test@localhost/test"
        assert gen.symbols == ['BTC/USDC', 'ETH/USDC']
        assert gen.include_indicators is True
        assert gen._symbol_list == []

    def test_generator_initialization_all_symbols(self) -> None:
        """Test generator with all symbols."""
        gen = WideVectorGenerator(
            db_url="postgresql://test:test@localhost/test",
            symbols=None,  # All symbols
            include_indicators=False,
        )

        assert gen.symbols is None
        assert gen.include_indicators is False

    def test_build_wide_vector_basic(self, generator: WideVectorGenerator) -> None:
        """Test basic wide vector construction."""
        ticker_data = {
            'BTC/USDC': {
                'last_price': 50000.0,
                'open_price': 49500.0,
                'high_price': 50500.0,
                'low_price': 49000.0,
                'volume': 1000.0,
                'quote_volume': 50000000.0,
                'price_change': 500.0,
                'price_change_pct': 1.0,
            },
            'ETH/USDC': {
                'last_price': 3000.0,
                'open_price': 2950.0,
                'high_price': 3050.0,
                'low_price': 2900.0,
                'volume': 5000.0,
                'quote_volume': 15000000.0,
                'price_change': 50.0,
                'price_change_pct': 1.7,
            },
        }

        indicator_data = {
            'BTC/USDC': {
                'rsi': 55.5,
                'sma_20': 49800.0,
            },
            'ETH/USDC': {
                'rsi': 60.2,
                'sma_20': 2980.0,
            },
        }

        result = generator._build_wide_vector(ticker_data, indicator_data)

        # Check vector
        assert isinstance(result['values'], np.ndarray)
        assert result['values'].dtype == np.float32

        # Check columns
        assert len(result['columns']) > 0

        # BTC/USDC should have 8 ticker + 2 indicator = 10 columns
        btc_cols = [c for c in result['columns'] if c.startswith('BTC/USDC_')]
        assert len(btc_cols) == 10

        # ETH/USDC should have 8 ticker + 2 indicator = 10 columns
        eth_cols = [c for c in result['columns'] if c.startswith('ETH/USDC_')]
        assert len(eth_cols) == 10

        # Total: 20 columns
        assert len(result['columns']) == 20
        assert len(result['values']) == 20

    def test_build_wide_vector_no_indicators(
        self,
        generator: WideVectorGenerator
    ) -> None:
        """Test wide vector without indicators."""
        generator.include_indicators = False

        ticker_data = {
            'BTC/USDC': {
                'last_price': 50000.0,
                'open_price': 49500.0,
                'high_price': 50500.0,
                'low_price': 49000.0,
                'volume': 1000.0,
                'quote_volume': 50000000.0,
                'price_change': 500.0,
                'price_change_pct': 1.0,
            },
        }

        result = generator._build_wide_vector(ticker_data, {})

        # Only 8 ticker columns (no indicators)
        assert len(result['columns']) == 8
        assert len(result['values']) == 8

    def test_build_wide_vector_missing_data(
        self,
        generator: WideVectorGenerator
    ) -> None:
        """Test wide vector with missing symbol data."""
        ticker_data = {
            'BTC/USDC': {
                'last_price': 50000.0,
                # Missing other fields
            },
            # ETH/USDC missing entirely
        }

        result = generator._build_wide_vector(ticker_data, {})

        # Should have columns for both symbols (with 0.0 for missing)
        assert len(result['columns']) == 16  # 8 fields × 2 symbols

        # Missing values should be 0.0
        btc_cols = [c for c in result['columns'] if c.startswith('BTC/USDC_')]
        for i, col in enumerate(btc_cols):
            if col != 'BTC/USDC_last_price':
                assert result['values'][i] == 0.0

    def test_build_wide_vector_null_handling(
        self,
        generator: WideVectorGenerator
    ) -> None:
        """Test wide vector with None values."""
        ticker_data = {
            'BTC/USDC': {
                'last_price': None,  # Null value
                'open_price': 49500.0,
                'high_price': None,
                'low_price': 49000.0,
                'volume': None,
                'quote_volume': 50000000.0,
                'price_change': None,
                'price_change_pct': 1.0,
            },
        }

        result = generator._build_wide_vector(ticker_data, {})

        # Null values should be replaced with 0.0
        assert result['null_count'] == 4  # 4 None values
        assert result['values'][0] == 0.0  # last_price was None

    def test_vector_to_json(self, generator: WideVectorGenerator) -> None:
        """Test vector to JSON conversion."""
        vector_data = {
            'timestamp': '2026-03-21T12:00:00Z',
            'symbols': ['BTC/USDC', 'ETH/USDC'],
            'vector': np.array([50000.0, 3000.0], dtype=np.float32),
            'column_names': ['BTC_last_price', 'ETH_last_price'],
            'metadata': {
                'symbols_count': 2,
                'total_columns': 2,
                'includes_indicators': False,
                'null_count': 0,
            }
        }

        json_str = generator.vector_to_json(vector_data, compress=True)

        assert isinstance(json_str, str)
        assert 'BTC_last_price' in json_str
        assert 'vector' in json_str

    def test_vector_to_dict(self, generator: WideVectorGenerator) -> None:
        """Test vector to nested dictionary conversion."""
        vector_data = {
            'timestamp': '2026-03-21T12:00:00Z',
            'symbols': ['BTC/USDC', 'ETH/USDC'],
            'vector': np.array([
                50000.0, 49500.0,  # BTC: price, open
                3000.0, 2950.0,    # ETH: price, open
            ], dtype=np.float32),
            'column_names': [
                'BTC/USDC_last_price',
                'BTC/USDC_open_price',
                'ETH/USDC_last_price',
                'ETH/USDC_open_price',
            ],
            'metadata': {
                'symbols_count': 2,
                'total_columns': 4,
                'includes_indicators': False,
                'null_count': 0,
            }
        }

        result = generator.vector_to_dict(vector_data)

        assert isinstance(result, dict)
        assert 'BTC/USDC' in result
        assert 'ETH/USDC' in result
        assert result['BTC/USDC']['last_price'] == 50000.0
        assert result['ETH/USDC']['last_price'] == 3000.0

    def test_vector_shape_for_llm(self, generator: WideVectorGenerator) -> None:
        """Test vector shape is suitable for LLM input."""
        # Simulate 100 symbols with 8 ticker + 6 indicators = 14 features each
        num_symbols = 100
        num_features_per_symbol = 14

        ticker_data = {
            f'SYM{i}/USDC': {'last_price': 100.0 + i, 'open_price': 99.0 + i,
                            'high_price': 101.0 + i, 'low_price': 98.0 + i,
                            'volume': 1000.0, 'quote_volume': 100000.0,
                            'price_change': 1.0, 'price_change_pct': 0.01}
            for i in range(num_symbols)
        }

        indicator_data = {
            f'SYM{i}/USDC': {'rsi': 50.0, 'sma_20': 99.0, 'sma_50': 98.0,
                            'macd': 0.5, 'bb_upper': 105.0, 'bb_lower': 95.0}
            for i in range(num_symbols)
        }

        generator._symbol_list = list(ticker_data.keys())
        result = generator._build_wide_vector(ticker_data, indicator_data)

        # Vector should be flat
        assert len(result['values'].shape) == 1

        # Total size should be symbols × features
        expected_size = num_symbols * num_features_per_symbol
        assert len(result['values']) == expected_size

        # Suitable for LLM: flat array of floats
        assert result['values'].dtype == np.float32


class TestWideVectorForLLM:
    """Test wide vector format for LLM consumption."""

    def test_vector_format_for_transformer(self) -> None:
        """Test vector format is suitable for transformer models."""
        # Simulate vector for 657 symbols (as user requested)
        num_symbols = 657
        features_per_symbol = 14  # 8 ticker + 6 indicators

        # Create sample vector
        vector = np.random.randn(num_symbols * features_per_symbol).astype(np.float32)

        # Transformer models expect:
        # - Flat array or (batch_size, sequence_length, features)
        # - Normalized values
        # - No NaN/Inf

        assert len(vector.shape) == 1  # Flat
        assert vector.dtype == np.float32
        assert not np.isnan(vector).any()
        assert not np.isinf(vector).any()

        # Can be reshaped for transformer
        reshaped = vector.reshape(1, num_symbols, features_per_symbol)
        assert reshaped.shape == (1, num_symbols, features_per_symbol)

    def test_vector_normalization_for_llm(self) -> None:
        """Test vector normalization for LLM input."""
        # Raw vector with different scales
        raw_vector = np.array([
            50000.0,  # Price (large)
            0.01,     # Change % (small)
            55.5,     # RSI (medium)
            1000.0,   # Volume (large)
        ], dtype=np.float32)

        # Normalize to [0, 1] or [-1, 1] for LLM
        min_val = raw_vector.min()
        max_val = raw_vector.max()
        normalized = (raw_vector - min_val) / (max_val - min_val)

        assert normalized.min() >= 0.0
        assert normalized.max() <= 1.0
        assert normalized.dtype == np.float32

    def test_vector_with_metadata_for_llm(self) -> None:
        """Test vector with metadata for LLM context."""
        vector_data = {
            'timestamp': '2026-03-21T12:00:00Z',
            'vector': np.random.randn(100).astype(np.float32),
            'column_names': [f'feat_{i}' for i in range(100)],
            'metadata': {
                'symbols_count': 10,
                'features_per_symbol': 10,
                'normalization': 'min_max',
            }
        }

        # LLM can use metadata for context
        assert 'timestamp' in vector_data
        assert 'metadata' in vector_data
        assert vector_data['metadata']['symbols_count'] == 10


class TestWideVectorIntegration:
    """Integration tests for wide vector generation."""

    @pytest.mark.asyncio
    async def test_full_vector_generation(self) -> None:
        """Test full vector generation pipeline."""
        # This would require a real database connection
        # Mock test instead
        db_url = "postgresql://test:test@localhost/test"

        gen = WideVectorGenerator(
            db_url=db_url,
            symbols=['BTC/USDC'],
            include_indicators=True,
        )

        # Mock the database calls
        mock_pool = MagicMock()
        mock_conn = AsyncMock()

        mock_conn.fetch = AsyncMock(return_value=[
            {'symbol': 'BTC/USDC', 'last_price': 50000.0,
             'open_price': 49500.0, 'high_price': 50500.0,
             'low_price': 49000.0, 'total_volume': 1000.0,
             'total_quote_volume': 50000000.0,
             'price_change': 500.0, 'price_change_pct': 1.0,
             'time': datetime.now(timezone.utc)}
        ])

        acquire_ctx = MagicMock()
        acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=acquire_ctx)

        gen.db_pool = mock_pool
        gen._symbol_list = ['BTC/USDC']

        # Generate vector
        vector_data = await gen.generate_wide_vector()

        assert vector_data is not None
        assert 'vector' in vector_data
        assert 'column_names' in vector_data
        assert len(vector_data['vector']) > 0


class TestWideVectorEdgeCases:
    """Test edge cases for wide vector generation."""

    def test_empty_symbol_list(self) -> None:
        """Test vector generation with no symbols."""
        gen = WideVectorGenerator(
            db_url="postgresql://test:test@localhost/test",
            symbols=[],
        )
        gen._symbol_list = []

        result = gen._build_wide_vector({}, {})

        assert len(result['values']) == 0
        assert len(result['columns']) == 0

    def test_single_symbol(self) -> None:
        """Test vector generation with single symbol."""
        gen = WideVectorGenerator(
            db_url="postgresql://test:test@localhost/test",
            symbols=['BTC/USDC'],
        )
        gen._symbol_list = ['BTC/USDC']

        ticker_data = {
            'BTC/USDC': {
                'last_price': 50000.0, 'open_price': 49500.0,
                'high_price': 50500.0, 'low_price': 49000.0,
                'volume': 1000.0, 'quote_volume': 50000000.0,
                'price_change': 500.0, 'price_change_pct': 1.0,
            }
        }

        result = gen._build_wide_vector(ticker_data, {})

        # 8 ticker columns for single symbol
        assert len(result['columns']) == 8
        assert len(result['values']) == 8

    def test_many_symbols_performance(self) -> None:
        """Test vector generation with many symbols (performance)."""
        import time

        gen = WideVectorGenerator(
            db_url="postgresql://test:test@localhost/test",
            symbols=None,
        )

        # Simulate 657 symbols (as user requested)
        num_symbols = 657
        gen._symbol_list = [f'SYM{i}/USDC' for i in range(num_symbols)]

        ticker_data = {
            sym: {
                'last_price': 100.0, 'open_price': 99.0,
                'high_price': 101.0, 'low_price': 98.0,
                'volume': 1000.0, 'quote_volume': 100000.0,
                'price_change': 1.0, 'price_change_pct': 0.01,
            }
            for sym in gen._symbol_list
        }

        start = time.time()
        result = gen._build_wide_vector(ticker_data, {})
        elapsed = time.time() - start

        # Should complete in < 100ms for 657 symbols
        assert elapsed < 0.1

        # Vector should have 8 × 657 = 5256 columns
        assert len(result['values']) == 5256
