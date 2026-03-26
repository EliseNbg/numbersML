"""
Unit tests for application services (Step 022.2).

Tests:
    - Service initialization
    - Method signatures
    - Basic functionality with mocks
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncpg

from src.application.services.pipeline_monitor import PipelineMonitor
from src.application.services.symbol_manager import SymbolManager
from src.application.services.indicator_manager import IndicatorManager
from src.application.services.config_manager import ConfigManager


class TestPipelineMonitor:
    """Test PipelineMonitor service."""
    
    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool
    
    def test_init(self, mock_db_pool: MagicMock) -> None:
        """Test service initialization."""
        monitor = PipelineMonitor(mock_db_pool)
        
        assert monitor.db_pool is mock_db_pool
    
    @pytest.mark.asyncio
    async def test_get_collector_status_not_running(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test status when collector not running."""
        # Mock database response
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        # Mock context manager for multiple calls
        mock_db_pool.acquire.return_value.__aexit__.return_value = None
        
        monitor = PipelineMonitor(mock_db_pool)
        status = await monitor.get_collector_status()
        
        assert status.is_running is False
        assert status.pid is None
    
    @pytest.mark.asyncio
    async def test_get_sla_metrics(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test fetching SLA metrics."""
        # Mock database response
        mock_row = {
            'second': '2026-03-24T12:00:00',
            'avg_time_ms': 150.5,
            'max_time_ms': 450.0,
            'sla_violations': 0,
            'ticks_processed': 60,
        }
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_row])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        monitor = PipelineMonitor(mock_db_pool)
        metrics = await monitor.get_sla_metrics(seconds=60)
        
        assert len(metrics) == 1
        assert metrics[0].avg_time_ms == 150.5
        assert metrics[0].sla_violations == 0
    
    @pytest.mark.asyncio
    async def test_get_dashboard_stats(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test fetching dashboard statistics."""
        # Mock database responses
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(side_effect=[
            {'ticks': 60},  # ticks_per_minute
            {'avg_time': 150.5},  # avg_processing_time_ms
            {'total': 60, 'compliant': 59},  # sla_compliance
            {'count': 20},  # active_symbols_count
            {'count': 6},  # active_indicators_count
        ])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        monitor = PipelineMonitor(mock_db_pool)
        stats = await monitor.get_dashboard_stats()
        
        assert stats.ticks_per_minute == 60
        assert stats.avg_processing_time_ms == 150.5
        assert stats.active_symbols_count == 20
        assert stats.active_indicators_count == 6


class TestSymbolManager:
    """Test SymbolManager service."""
    
    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool
    
    def test_init(self, mock_db_pool: MagicMock) -> None:
        """Test service initialization."""
        manager = SymbolManager(mock_db_pool)
        
        assert manager.db_pool is mock_db_pool
    
    @pytest.mark.asyncio
    async def test_list_symbols(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test listing symbols."""
        # Mock database response
        mock_row = {
            'symbol_id': 1,
            'symbol': 'BTC/USDT',
            'base_asset': 'BTC',
            'quote_asset': 'USDT',
            'is_active': True,
            'is_allowed': True,
            'tick_size': 0.01,
            'step_size': 0.00001,
            'min_notional': 10.0,
        }
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_row])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = SymbolManager(mock_db_pool)
        symbols = await manager.list_symbols()
        
        assert len(symbols) == 1
        assert symbols[0].symbol == 'BTC/USDT'
        assert symbols[0].is_active is True
    
    @pytest.mark.asyncio
    async def test_activate_symbol(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test activating a symbol."""
        # Mock database response
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = SymbolManager(mock_db_pool)
        result = await manager.activate_symbol(1)
        
        assert result is True
        mock_conn.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_deactivate_symbol(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test deactivating a symbol."""
        # Mock database response
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = SymbolManager(mock_db_pool)
        result = await manager.deactivate_symbol(1)
        
        assert result is True
        mock_conn.execute.assert_called_once()


class TestIndicatorManager:
    """Test IndicatorManager service."""
    
    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool
    
    def test_init(self, mock_db_pool: MagicMock) -> None:
        """Test service initialization."""
        manager = IndicatorManager(mock_db_pool)
        
        assert manager.db_pool is mock_db_pool
    
    @pytest.mark.asyncio
    async def test_list_indicators(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test listing indicators."""
        from datetime import datetime
        
        # Mock database response
        mock_row = {
            'name': 'rsi_14',
            'class_name': 'RSIIndicator',
            'module_path': 'src.indicators.momentum',
            'category': 'momentum',
            'params': {'period': 14},
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_row])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = IndicatorManager(mock_db_pool)
        indicators = await manager.list_indicators()
        
        assert len(indicators) == 1
        assert indicators[0].name == 'rsi_14'
        assert indicators[0].is_active is True
    
    @pytest.mark.asyncio
    async def test_register_indicator(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test registering an indicator."""
        # Mock database response
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = IndicatorManager(mock_db_pool)
        result = await manager.register_indicator(
            name='rsi_14',
            class_name='RSIIndicator',
            module_path='src.indicators.momentum',
            category='momentum',
            params={'period': 14},
        )
        
        assert result is True
        mock_conn.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_activate_indicator(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test activating an indicator."""
        # Mock database response
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = IndicatorManager(mock_db_pool)
        result = await manager.activate_indicator('rsi_14')
        
        assert result is True
        mock_conn.execute.assert_called_once()


class TestConfigManager:
    """Test ConfigManager service."""
    
    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool
    
    def test_init(self, mock_db_pool: MagicMock) -> None:
        """Test service initialization."""
        manager = ConfigManager(mock_db_pool)
        
        assert manager.db_pool is mock_db_pool
    
    def test_validate_table_valid(self, mock_db_pool: MagicMock) -> None:
        """Test table validation with valid table."""
        manager = ConfigManager(mock_db_pool)
        
        # Should not raise
        manager._validate_table('system_config')
        manager._validate_table('symbols')
        manager._validate_table('indicator_definitions')
    
    def test_validate_table_invalid(self, mock_db_pool: MagicMock) -> None:
        """Test table validation with invalid table."""
        manager = ConfigManager(mock_db_pool)
        
        with pytest.raises(ValueError, match="not allowed"):
            manager._validate_table('invalid_table')
    
    def test_get_id_column(self, mock_db_pool: MagicMock) -> None:
        """Test ID column lookup."""
        manager = ConfigManager(mock_db_pool)
        
        assert manager._get_id_column('system_config') == 'id'
        assert manager._get_id_column('collection_config') == 'symbol_id'
        assert manager._get_id_column('symbols') == 'id'
        assert manager._get_id_column('indicator_definitions') == 'name'
    
    @pytest.mark.asyncio
    async def test_get_table_data(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test getting table data."""
        # Mock database responses
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{'column_name': 'id'}, {'column_name': 'key'}],  # columns
            [{'id': 1, 'key': 'test'}],  # data
        ])
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = ConfigManager(mock_db_pool)
        data = await manager.get_table_data('system_config', limit=10)
        
        assert len(data) == 1
        assert data[0]['id'] == 1
    
    @pytest.mark.asyncio
    async def test_get_config_value(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test getting configuration value."""
        # Mock database response
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={'value': {'key': 'value'}})
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        manager = ConfigManager(mock_db_pool)
        value = await manager.get_config_value('test.key')
        
        assert value == {'key': 'value'}
