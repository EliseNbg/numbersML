"""Tests for TickValidator service."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from src.domain.models.symbol import Symbol
from src.domain.models.trade import Trade
from src.domain.services.tick_validator import TickValidator, ValidationResult


class TestTickValidator:
    """Test TickValidator service."""
    
    @pytest.fixture
    def btc_symbol(self) -> Symbol:
        """Create BTC/USDT symbol for testing."""
        return Symbol(
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            tick_size=Decimal('0.01'),
            step_size=Decimal('0.00001'),
            min_notional=Decimal('10'),
        )
    
    @pytest.fixture
    def validator(self, btc_symbol: Symbol) -> TickValidator:
        """Create validator for testing."""
        return TickValidator(btc_symbol)
    
    def test_valid_trade_passes(self, validator: TickValidator) -> None:
        """Test that valid trade passes validation."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = validator.validate(trade)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_duplicate_trade_id_fails(self, validator: TickValidator) -> None:
        """Test that duplicate trade ID fails validation."""
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        # First trade should pass
        result1 = validator.validate(trade1)
        assert result1.is_valid is True
        
        # Duplicate should fail
        result2 = validator.validate(trade1)
        assert result2.is_valid is False
        assert 'Duplicate' in result2.errors[0]
    
    def test_price_not_aligned_fails(self, validator: TickValidator) -> None:
        """Test that price not aligned with tick_size fails."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.001'),  # Not aligned with 0.01
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = validator.validate(trade)
        
        assert result.is_valid is False
        assert 'not aligned' in result.errors[0]
    
    def test_quantity_not_aligned_fails(self, validator: TickValidator) -> None:
        """Test that quantity not aligned with step_size fails."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001234567'),  # Not aligned with 0.00001
            side='BUY',
        )
        
        result = validator.validate(trade)
        
        assert result.is_valid is False
        assert 'not aligned' in result.errors[0]
    
    def test_price_sanity_check(self, validator: TickValidator) -> None:
        """Test price sanity validation."""
        # Set last price
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        validator.validate(trade1)
        
        # Large price move (>10%)
        trade2 = Trade(
            time=datetime.utcnow() + timedelta(seconds=1),
            symbol_id=1,
            trade_id='123457',
            price=Decimal('60000.00'),  # 20% move
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = validator.validate(trade2)
        
        assert result.is_valid is False
        assert 'Price move' in result.errors[0]
    
    def test_time_travel_fails(self, validator: TickValidator) -> None:
        """Test that time travel fails validation."""
        # Set last time
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        validator.validate(trade1)
        
        # Trade in the past
        trade2 = Trade(
            time=datetime.utcnow() - timedelta(seconds=10),
            symbol_id=1,
            trade_id='123457',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = validator.validate(trade2)
        
        assert result.is_valid is False
        assert 'Time travel' in result.errors[0]
    
    def test_reset_clears_state(self, validator: TickValidator) -> None:
        """Test that reset clears validator state."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        validator.validate(trade)
        
        validator.reset()
        
        # Same trade ID should pass after reset
        result = validator.validate(trade)
        assert result.is_valid is True


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_default_values(self) -> None:
        """Test default values."""
        result = ValidationResult()
        
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
    
    def test_custom_values(self) -> None:
        """Test custom values."""
        result = ValidationResult(
            is_valid=False,
            errors=['Error 1', 'Error 2'],
            warnings=['Warning 1'],
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
