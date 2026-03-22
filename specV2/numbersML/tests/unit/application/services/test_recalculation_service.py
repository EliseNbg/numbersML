"""Tests for recalculation service."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from src.application.services.recalculation_service import RecalculationService


class TestRecalculationService:
    """Test RecalculationService."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    @pytest.fixture
    def recalc_service(self, mock_db_pool: MagicMock) -> RecalculationService:
        """Create recalculation service for testing."""
        return RecalculationService(
            db_pool=mock_db_pool,
            batch_size=1000,
            max_workers=2,
        )

    def test_service_initialization(
        self,
        recalc_service: RecalculationService,
    ) -> None:
        """Test service initialization."""
        assert recalc_service.batch_size == 1000
        assert recalc_service.max_workers == 2
        assert recalc_service._running is False
        assert recalc_service._stats['jobs_started'] == 0

    def test_get_stats(self, recalc_service: RecalculationService) -> None:
        """Test getting statistics."""
        recalc_service._stats = {
            'jobs_started': 10,
            'jobs_completed': 8,
            'jobs_failed': 2,
            'ticks_recalculated': 50000,
        }

        stats = recalc_service.get_stats()

        assert stats['jobs_started'] == 10
        assert stats['jobs_completed'] == 8
        assert stats['jobs_failed'] == 2
        assert stats['ticks_recalculated'] == 50000

    @pytest.mark.asyncio
    async def test_start_service(
        self,
        recalc_service: RecalculationService,
    ) -> None:
        """Test starting the service."""
        # Mock the listen method
        with patch.object(recalc_service, '_listen_for_changes') as mock_listen:
            mock_listen.side_effect = asyncio.CancelledError()

            try:
                await recalc_service.start()
            except asyncio.CancelledError:
                pass

        assert recalc_service._running is True

    @pytest.mark.asyncio
    async def test_stop_service(
        self,
        recalc_service: RecalculationService,
    ) -> None:
        """Test stopping the service."""
        recalc_service._running = True

        # Add mock active job with proper cancel behavior
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        recalc_service._active_jobs['job_1'] = mock_task

        await recalc_service.stop()

        assert recalc_service._running is False
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_heartbeat_logging(
        self,
        recalc_service: RecalculationService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test heartbeat logging."""
        import logging
        recalc_service._stats['jobs_started'] = 10

        # Set up logging to capture INFO level
        logger = logging.getLogger('src.application.services.recalculation_service')
        original_level = logger.level
        logger.setLevel(logging.INFO)

        try:
            await recalc_service._heartbeat()
            # Should log stats at 10 jobs
            assert 'Recalculation stats' in caplog.text
        finally:
            logger.setLevel(original_level)

    @pytest.mark.asyncio
    async def test_load_ticks(
        self,
        recalc_service: RecalculationService,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test loading ticks from database."""
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {'time': '2024-01-01', 'price': 50000.0, 'quantity': 0.001},
            {'time': '2024-01-02', 'price': 51000.0, 'quantity': 0.002},
        ])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Load ticks
        ticks = await recalc_service._load_ticks(
            symbol_id=1,
            offset=0,
            limit=1000,
        )

        assert len(ticks) == 2
        assert ticks[0]['price'] == 50000.0
        assert ticks[1]['price'] == 51000.0

    @pytest.mark.asyncio
    async def test_get_active_symbols(
        self,
        recalc_service: RecalculationService,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test getting active symbols."""
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {'id': 1, 'symbol': 'BTC/USDT'},
            {'id': 2, 'symbol': 'ETH/USDT'},
        ])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Get active symbols
        symbols = await recalc_service._get_active_symbols()

        assert len(symbols) == 2
        assert symbols[0] == (1, 'BTC/USDT')
        assert symbols[1] == (2, 'ETH/USDT')

    @pytest.mark.asyncio
    async def test_update_job_status_completed(
        self,
        recalc_service: RecalculationService,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test updating job status to completed."""
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Update status
        await recalc_service._update_job_status(
            job_id='job_1',
            status='completed',
            ticks_processed=10000,
        )

        # Verify database call
        assert mock_conn.execute.called

    @pytest.mark.asyncio
    async def test_update_job_status_failed(
        self,
        recalc_service: RecalculationService,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test updating job status to failed."""
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Update status
        await recalc_service._update_job_status(
            job_id='job_1',
            status='failed',
            error='Test error',
        )

        # Verify database call
        assert mock_conn.execute.called

    @pytest.mark.asyncio
    async def test_update_job_progress(
        self,
        recalc_service: RecalculationService,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test updating job progress."""
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Update progress
        await recalc_service._update_job_progress(
            job_id='job_1',
            ticks_processed=5000,
        )

        # Verify database call
        assert mock_conn.execute.called

    @pytest.mark.asyncio
    async def test_store_indicator_results_batch_insert(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test that indicator results are stored using batch insert."""
        from src.indicators.momentum import RSIIndicator
        import numpy as np

        # Create mock connection with proper async context manager
        mock_conn = AsyncMock()
        mock_conn.executemany = AsyncMock()
        
        # Set up async context manager properly
        async_context = AsyncMock()
        async_context.__aenter__.return_value = mock_conn
        async_context.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_context

        # Create recalc service
        service = RecalculationService(
            db_pool=mock_db_pool,
            batch_size=1000,
        )

        # Create mock ticks - need at least period+1 ticks for RSI to produce values
        ticks = [
            {'time': f'2024-01-{i:02d}', 'price': 50.0 + i, 'quantity': 0.001}
            for i in range(1, 20)  # 19 ticks, RSI period is 14
        ]

        indicator = RSIIndicator(period=14)
        prices = np.array([t['price'] for t in ticks])
        volumes = np.array([t['quantity'] for t in ticks])
        result = indicator.calculate(prices, volumes)

        # Verify we have some non-NaN values
        assert np.sum(~np.isnan(result.values['rsi'])) > 0

        # Store results
        await service._store_indicator_results(
            symbol_id=1,
            ticks=ticks,
            result=result,
        )

        # Verify executemany was called (not execute in a loop)
        assert mock_conn.executemany.called
        # Verify it was called only once (batch insert)
        assert mock_conn.executemany.call_count == 1

    @pytest.mark.asyncio
    async def test_recalculate_symbol_max_iterations_protection(
        self,
        mock_db_pool: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that recalculation stops after max iterations."""
        from src.indicators.momentum import RSIIndicator

        service = RecalculationService(
            db_pool=mock_db_pool,
            batch_size=100,
        )

        # Mock database connection to always return data (simulating infinite data)
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {'time': f'2024-01-{i:02d}', 'price': 50.0 + i, 'quantity': 0.001}
            for i in range(1, 101)
        ])
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

        indicator = RSIIndicator(period=14)

        # Recalculate - should stop after max_iterations (1000)
        ticks_processed = await service._recalculate_symbol(
            symbol_id=1,
            symbol='BTC/USDT',
            indicator=indicator,
            job_id='job_1',
        )

        # Should have processed exactly 1000 * 100 = 100000 ticks
        assert ticks_processed == 100000

        # Verify error was logged about max iterations
        assert 'Max iterations' in caplog.text
        assert '1000' in caplog.text


class TestRecalculationServiceIntegration:
    """Test recalculation service integration."""

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    @pytest.mark.asyncio
    async def test_recalculate_symbol(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test recalculation for a single symbol."""
        from src.indicators.momentum import RSIIndicator

        service = RecalculationService(
            db_pool=mock_db_pool,
            batch_size=100,
        )

        # Mock database connection - return data once, then empty
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            # First call returns 50 ticks
            [
                {'time': f'2024-01-{i:02d}', 'price': 50.0 + i, 'quantity': 0.001}
                for i in range(1, 51)
            ],
            # Second call returns empty (no more data)
            [],
        ])
        mock_conn.executemany = AsyncMock()
        
        # Set up async context manager properly
        async_context = AsyncMock()
        async_context.__aenter__.return_value = mock_conn
        async_context.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_context

        # Create indicator
        indicator = RSIIndicator(period=14)

        # Recalculate
        ticks_processed = await service._recalculate_symbol(
            symbol_id=1,
            symbol='BTC/USDT',
            indicator=indicator,
            job_id='job_1',
        )

        # Should have processed 50 ticks (one batch)
        assert ticks_processed == 50

    @pytest.mark.asyncio
    async def test_empty_tick_window(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test recalculation with no ticks."""
        from src.indicators.momentum import RSIIndicator

        service = RecalculationService(
            db_pool=mock_db_pool,
            batch_size=100,
        )

        # Mock database connection - always returns empty
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        
        # Set up async context manager properly
        async_context = AsyncMock()
        async_context.__aenter__.return_value = mock_conn
        async_context.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_context

        indicator = RSIIndicator(period=14)

        ticks_processed = await service._recalculate_symbol(
            symbol_id=1,
            symbol='BTC/USDT',
            indicator=indicator,
            job_id='job_1',
        )

        # Should have processed 0 ticks
        assert ticks_processed == 0

    @pytest.mark.asyncio
    async def test_insufficient_data_for_indicator(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test recalculation with insufficient data."""
        from src.indicators.momentum import RSIIndicator

        service = RecalculationService(
            db_pool=mock_db_pool,
            batch_size=100,
        )

        # Mock database connection - return 9 ticks once, then empty
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            # First call returns 9 ticks (less than RSI period of 14)
            [
                {'time': f'2024-01-{i:02d}', 'price': 50.0 + i, 'quantity': 0.001}
                for i in range(1, 10)
            ],
            # Second call returns empty
            [],
        ])
        mock_conn.executemany = AsyncMock()
        
        # Set up async context manager properly
        async_context = AsyncMock()
        async_context.__aenter__.return_value = mock_conn
        async_context.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_context

        indicator = RSIIndicator(period=14)

        # Should not raise, just process with NaN values
        ticks_processed = await service._recalculate_symbol(
            symbol_id=1,
            symbol='BTC/USDT',
            indicator=indicator,
            job_id='job_1',
        )

        assert ticks_processed == 9
