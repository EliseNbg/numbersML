"""
Unit tests for config domain models.

Tests:
    - Entity creation
    - Field types
    - Default values
    - Property methods
"""

import pytest
from datetime import datetime

from src.domain.models.config import (
    ConfigEntry,
    SymbolConfig,
    IndicatorConfig,
)


class TestConfigEntry:
    """Test ConfigEntry entity."""
    
    def test_create_with_required_fields(self) -> None:
        """Test creating entry with required fields only."""
        entry = ConfigEntry(
            id=1,
            key='test.key',
            value={'value': 'test'},
        )
        
        assert entry.id == 1
        assert entry.key == 'test.key'
        assert entry.value == {'value': 'test'}
        assert entry.description is None
        assert entry.is_sensitive is False
        assert entry.is_editable is True
        assert entry.version == 1
        assert entry.updated_at is None
        assert entry.updated_by is None
    
    def test_create_with_all_fields(self) -> None:
        """Test creating entry with all fields."""
        now = datetime.utcnow()
        entry = ConfigEntry(
            id=1,
            key='test.key',
            value={'value': 'test'},
            description='Test description',
            is_sensitive=True,
            is_editable=False,
            version=2,
            updated_at=now,
            updated_by='admin',
        )
        
        assert entry.description == 'Test description'
        assert entry.is_sensitive is True
        assert entry.is_editable is False
        assert entry.version == 2
        assert entry.updated_at == now
        assert entry.updated_by == 'admin'


class TestSymbolConfig:
    """Test SymbolConfig entity."""
    
    def test_create_with_defaults(self) -> None:
        """Test creating symbol with default values."""
        symbol = SymbolConfig(
            symbol_id=1,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
        )
        
        assert symbol.is_active is True
        assert symbol.is_allowed is True
        assert symbol.tick_size == 0.01
        assert symbol.step_size == 0.00001
        assert symbol.min_notional == 10.0
    
    def test_create_with_values(self) -> None:
        """Test creating symbol with specific values."""
        symbol = SymbolConfig(
            symbol_id=1,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            is_active=False,
            is_allowed=True,
            tick_size=0.1,
            step_size=0.001,
            min_notional=15.0,
        )
        
        assert symbol.is_active is False
        assert symbol.is_allowed is True
        assert symbol.tick_size == 0.1
        assert symbol.step_size == 0.001
        assert symbol.min_notional == 15.0
    
    def test_is_collectable_true(self) -> None:
        """Test collectable check when collectable."""
        symbol = SymbolConfig(
            symbol_id=1,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            is_active=True,
            is_allowed=True,
        )
        assert symbol.is_collectable is True
    
    def test_is_collectable_not_active(self) -> None:
        """Test collectable check when not active."""
        symbol = SymbolConfig(
            symbol_id=1,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            is_active=False,
            is_allowed=True,
        )
        assert symbol.is_collectable is False
    
    def test_is_collectable_not_allowed(self) -> None:
        """Test collectable check when not allowed."""
        symbol = SymbolConfig(
            symbol_id=1,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            is_active=True,
            is_allowed=False,
        )
        assert symbol.is_collectable is False
    
    def test_display_name(self) -> None:
        """Test display name."""
        symbol = SymbolConfig(
            symbol_id=1,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
        )
        assert symbol.display_name == 'BTC/USDT'


class TestIndicatorConfig:
    """Test IndicatorConfig entity."""
    
    def test_create_with_defaults(self) -> None:
        """Test creating indicator with default values."""
        indicator = IndicatorConfig(
            name='rsi_14',
            class_name='RSIIndicator',
            module_path='src.indicators.momentum',
            category='momentum',
        )
        
        assert indicator.params == {}
        assert indicator.is_active is True
        assert indicator.created_at is None
        assert indicator.updated_at is None
    
    def test_create_with_values(self) -> None:
        """Test creating indicator with specific values."""
        now = datetime.utcnow()
        indicator = IndicatorConfig(
            name='rsi_14',
            class_name='RSIIndicator',
            module_path='src.indicators.momentum',
            category='momentum',
            params={'period': 14},
            is_active=False,
            created_at=now,
            updated_at=now,
        )
        
        assert indicator.params == {'period': 14}
        assert indicator.is_active is False
        assert indicator.created_at == now
        assert indicator.updated_at == now
    
    def test_full_class_path(self) -> None:
        """Test full class path."""
        indicator = IndicatorConfig(
            name='rsi_14',
            class_name='RSIIndicator',
            module_path='src.indicators.momentum',
            category='momentum',
        )
        assert indicator.full_class_path == 'src.indicators.momentum.RSIIndicator'
    
    def test_display_name_rsi(self) -> None:
        """Test display name for RSI."""
        indicator = IndicatorConfig(
            name='rsi_14',
            class_name='RSIIndicator',
            module_path='src.indicators.momentum',
            category='momentum',
        )
        assert indicator.display_name == 'RSI (14)'
    
    def test_display_name_sma(self) -> None:
        """Test display name for SMA."""
        indicator = IndicatorConfig(
            name='sma_20',
            class_name='SMAIndicator',
            module_path='src.indicators.trend',
            category='trend',
        )
        assert indicator.display_name == 'SMA (20)'
    
    def test_display_name_macd(self) -> None:
        """Test display name for MACD."""
        indicator = IndicatorConfig(
            name='macd_12_26_9',
            class_name='MACDIndicator',
            module_path='src.indicators.trend',
            category='trend',
        )
        assert indicator.display_name == 'MACD (12_26_9)'
    
    def test_category_icon_momentum(self) -> None:
        """Test category icon for momentum."""
        indicator = IndicatorConfig(
            name='rsi_14',
            class_name='RSIIndicator',
            module_path='src.indicators.momentum',
            category='momentum',
        )
        assert indicator.category_icon == 'bi-speedometer2'
    
    def test_category_icon_trend(self) -> None:
        """Test category icon for trend."""
        indicator = IndicatorConfig(
            name='sma_20',
            class_name='SMAIndicator',
            module_path='src.indicators.trend',
            category='trend',
        )
        assert indicator.category_icon == 'bi-graph-up'
    
    def test_category_icon_volatility(self) -> None:
        """Test category icon for volatility."""
        indicator = IndicatorConfig(
            name='bb_20_2',
            class_name='BollingerBandsIndicator',
            module_path='src.indicators.volatility_volume',
            category='volatility',
        )
        assert indicator.category_icon == 'bi-activity'
    
    def test_category_icon_volume(self) -> None:
        """Test category icon for volume."""
        indicator = IndicatorConfig(
            name='obv',
            class_name='OBVIndicator',
            module_path='src.indicators.volatility_volume',
            category='volume',
        )
        assert indicator.category_icon == 'bi-bar-chart'
    
    def test_category_icon_unknown(self) -> None:
        """Test category icon for unknown category."""
        indicator = IndicatorConfig(
            name='custom',
            class_name='CustomIndicator',
            module_path='src.indicators.custom',
            category='unknown',
        )
        assert indicator.category_icon == 'bi-gear'
