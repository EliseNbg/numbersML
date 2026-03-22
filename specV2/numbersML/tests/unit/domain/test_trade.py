"""Tests for Trade entity."""

import pytest
from datetime import datetime
from decimal import Decimal
from src.domain.models.trade import Trade


class TestTradeInitialization:
    """Test Trade initialization and validation."""
    
    def test_create_valid_trade(self) -> None:
        """Test creating a valid trade."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        assert trade.price == Decimal('50000.00')
        assert trade.quantity == Decimal('0.001')
        assert trade.side == 'BUY'
        assert trade.is_buy() is True
    
    def test_price_must_be_positive(self) -> None:
        """Test that price must be positive."""
        with pytest.raises(ValueError, match="price must be positive"):
            Trade(
                time=datetime.utcnow(),
                symbol_id=1,
                trade_id='123',
                price=Decimal('0'),
                quantity=Decimal('0.001'),
                side='BUY',
            )
    
    def test_quantity_must_be_positive(self) -> None:
        """Test that quantity must be positive."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            Trade(
                time=datetime.utcnow(),
                symbol_id=1,
                trade_id='123',
                price=Decimal('50000'),
                quantity=Decimal('0'),
                side='BUY',
            )
    
    def test_side_must_be_buy_or_sell(self) -> None:
        """Test that side must be BUY or SELL."""
        with pytest.raises(ValueError, match="Invalid side"):
            Trade(
                time=datetime.utcnow(),
                symbol_id=1,
                trade_id='123',
                price=Decimal('50000'),
                quantity=Decimal('0.001'),
                side='INVALID',
            )


class TestTradeMethods:
    """Test Trade methods."""
    
    @pytest.fixture
    def sample_trade(self) -> Trade:
        """Create sample trade for testing."""
        return Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.002'),
            side='BUY',
        )
    
    def test_notional_calculation(self, sample_trade: Trade) -> None:
        """Test notional value calculation."""
        assert sample_trade.notional == Decimal('100.00')
    
    def test_is_buy(self, sample_trade: Trade) -> None:
        """Test is_buy method."""
        assert sample_trade.is_buy() is True
        assert sample_trade.is_sell() is False
    
    def test_is_sell(self) -> None:
        """Test is_sell method."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123',
            price=Decimal('50000'),
            quantity=Decimal('0.001'),
            side='SELL',
        )
        assert trade.is_sell() is True
        assert trade.is_buy() is False
