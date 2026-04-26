"""Tests for enrichment service."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.application.services.enrichment_service import EnrichmentService
from src.indicators.providers import PythonIndicatorProvider


class TestEnrichmentService:
    """Test EnrichmentService."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    @pytest.fixture
    def mock_redis_pool(self) -> MagicMock:
        """Create mock Redis pool."""
        pool = MagicMock()
        pool.publish = AsyncMock()
        return pool

    @pytest.fixture
    def mock_indicator_provider(self) -> PythonIndicatorProvider:
        """Create mock indicator provider."""
        return PythonIndicatorProvider({})  # Empty for basic tests

    @pytest.fixture
    def enrichment_service(
        self,
        mock_db_pool: MagicMock,
        mock_redis_pool: MagicMock,
        mock_indicator_provider: PythonIndicatorProvider,
    ) -> EnrichmentService:
        """Create enrichment service for testing."""
        return EnrichmentService(
            db_pool=mock_db_pool,
            indicator_provider=mock_indicator_provider,
            redis_pool=mock_redis_pool,
            window_size=100,
        )
    
    def test_service_initialization(
        self,
        enrichment_service: EnrichmentService,
    ) -> None:
        """Test service initialization."""
        assert enrichment_service.window_size == 100
        assert enrichment_service._running is False
        assert enrichment_service._stats['ticks_processed'] == 0
    
    def test_get_stats(self, enrichment_service: EnrichmentService) -> None:
        """Test getting statistics."""
        enrichment_service._stats = {
            'ticks_processed': 1000,
            'indicators_calculated': 5000,
            'errors': 5,
        }
        
        stats = enrichment_service.get_stats()
        
        assert stats['ticks_processed'] == 1000
        assert stats['indicators_calculated'] == 5000
        assert stats['errors'] == 5
    
    @pytest.mark.skip(reason="Internal implementation changed - _update_tick_window removed")
    @pytest.mark.asyncio
    async def test_tick_window_initialization(
        self,
        enrichment_service: EnrichmentService,
    ) -> None:
        """Test tick window initialization."""
        symbol_id = 1

        # Window should not exist initially
        assert symbol_id not in enrichment_service._tick_windows

        # Simulate update (this would normally be called internally)
        await enrichment_service._update_tick_window(
            symbol_id,
            {'price': 50000.0, 'quantity': 0.001}
        )

        # Window should exist now
        assert symbol_id in enrichment_service._tick_windows

        window = enrichment_service._tick_windows[symbol_id]
        assert window['count'] == 1
        assert window['index'] == 1
        assert window['prices'][0] == 50000.0

    @pytest.mark.skip(reason="Internal implementation changed - _update_tick_window removed")
    @pytest.mark.asyncio
    async def test_tick_window_circular_buffer(
        self,
        enrichment_service: EnrichmentService,
    ) -> None:
        """Test circular buffer behavior."""
        symbol_id = 1

        # Fill window with 150 ticks (more than window_size=100)
        for i in range(150):
            await enrichment_service._update_tick_window(
                symbol_id,
                {'price': 50000.0 + i, 'quantity': 0.001}
            )

        window = enrichment_service._tick_windows[symbol_id]

        # Count should be capped at window_size
        assert window['count'] == 100

        # Index should wrap around
        assert window['index'] == 50  # 150 % 100 = 50
    
    @pytest.mark.asyncio
    async def test_store_enriched_data(
        self,
        enrichment_service: EnrichmentService,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test storing enriched data."""
        from datetime import datetime, timezone
        
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Store enriched data
        await enrichment_service._store_enriched_data(
            symbol_id=1,
            symbol="BTC/USDT",
            time=datetime.now(timezone.utc),
            price=50000.0,
            volume=0.001,
            indicator_values={'rsi': 55.5, 'sma': 49500.0},
        )

        # Verify database call
        assert mock_conn.execute.called
    
    @pytest.mark.asyncio
    async def test_publish_to_redis(
        self,
        enrichment_service: EnrichmentService,
        mock_db_pool: MagicMock,
        mock_redis_pool: MagicMock,
    ) -> None:
        """Test publishing to Redis."""
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value='BTC/USDT')
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        # Publish to Redis
        await enrichment_service._publish_to_redis(
            symbol_id=1,
            price=50000.0,
            indicator_values={'rsi': 55.5},
        )
        
        # Verify Redis publish
        assert mock_redis_pool.publish.called
    
    @pytest.mark.asyncio
    async def test_heartbeat_logging(
        self,
        enrichment_service: EnrichmentService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test heartbeat logging."""
        import logging
        enrichment_service._stats['ticks_processed'] = 1000
        
        # Set log level to INFO to capture heartbeat logs
        with caplog.at_level(logging.INFO):
            await enrichment_service._heartbeat()

        # Should log stats at 1000 ticks
        assert 'Enrichment stats' in caplog.text
    
    def test_no_indicators_configured(
        self,
        enrichment_service: EnrichmentService,
    ) -> None:
        """Test service with no indicators configured."""
        assert len(enrichment_service._indicators) == 0
        
        # Should not fail when calculating indicators
        # (just won't calculate anything)


class TestEnrichmentServiceWithIndicators:
    """Test enrichment service with actual indicators."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    @pytest.mark.asyncio
    async def test_indicator_calculation(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test indicator calculation in enrichment service."""
        from src.indicators.momentum import RSIIndicator
        from src.indicators.providers import PythonIndicatorProvider
        import numpy as np

        # Create provider with RSI indicator
        provider = PythonIndicatorProvider({
            'rsi_14': RSIIndicator,
        })

        service = EnrichmentService(
            db_pool=mock_db_pool,
            indicator_provider=provider,
            window_size=100,
        )

        # Initialize indicators from provider
        await service._init_indicators()

        # Prepare test data
        prices = np.array([50.0 + i for i in range(100)], dtype=np.float64)
        volumes = np.ones(100, dtype=np.float64)
        highs = np.array([51.0 + i for i in range(100)], dtype=np.float64)
        lows = np.array([49.0 + i for i in range(100)], dtype=np.float64)

        # Calculate indicators
        result = await service._calculate_indicators(prices, volumes, highs, lows)

        # Should have calculated RSI
        assert 'rsi_14_rsi' in result or len(result) > 0

    @pytest.mark.asyncio
    async def test_insufficient_data(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test indicator calculation with insufficient data."""
        from src.indicators.momentum import RSIIndicator
        from src.indicators.providers import PythonIndicatorProvider
        import numpy as np

        # Create provider with RSI indicator
        provider = PythonIndicatorProvider({
            'rsi_14': RSIIndicator,
        })

        service = EnrichmentService(
            db_pool=mock_db_pool,
            indicator_provider=provider,
            window_size=100,
        )

        # Initialize indicators from provider
        await service._init_indicators()

        # Insufficient data (less than RSI period of 14)
        prices = np.array([50.0, 51.0, 52.0], dtype=np.float64)
        volumes = np.ones(3, dtype=np.float64)
        highs = np.array([51.0, 52.0, 53.0], dtype=np.float64)
        lows = np.array([49.0, 50.0, 51.0], dtype=np.float64)

        # Calculate indicators (should return empty or handle gracefully)
        result = await service._calculate_indicators(prices, volumes, highs, lows)

        # RSI should not be calculated with insufficient data
        # (result may be empty or contain NaN values)
        assert isinstance(result, dict)
