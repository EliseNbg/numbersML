"""Tests for anomaly detector service."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from src.domain.models.symbol import Symbol
from src.domain.models.trade import Trade
from src.domain.services.anomaly_detector import (
    AnomalyDetector,
    AnomalyType,
    AnomalySeverity,
)


class TestAnomalyDetector:
    """Test AnomalyDetector service."""
    
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
    def detector(self, btc_symbol: Symbol) -> AnomalyDetector:
        """Create anomaly detector for testing."""
        return AnomalyDetector(
            symbol=btc_symbol,
            price_spike_threshold=Decimal('5.0'),
            volume_spike_threshold=Decimal('10.0'),
            max_gap_seconds=5,
            stale_data_seconds=60,
        )
    
    def test_no_anomaly_for_normal_trade(self, detector: AnomalyDetector) -> None:
        """Test that normal trade doesn't trigger anomaly."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = detector.detect(trade)
        
        assert result.is_anomaly is False
        assert len(result.anomalies) == 0
    
    def test_duplicate_trade_detected(self, detector: AnomalyDetector) -> None:
        """Test that duplicate trade ID is detected."""
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        # First trade should pass
        result1 = detector.detect(trade1)
        assert result1.is_anomaly is False
        
        # Duplicate should be detected
        result2 = detector.detect(trade1)
        assert result2.is_anomaly is True
        assert result2.should_reject is True
        assert result2.anomalies[0].anomaly_type == AnomalyType.DUPLICATE
    
    def test_time_gap_detected(self, detector: AnomalyDetector) -> None:
        """Test that time gaps are detected."""
        # First trade
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        detector.detect(trade1)
        
        # Second trade with gap > 5 seconds
        trade2 = Trade(
            time=datetime.utcnow() + timedelta(seconds=10),
            symbol_id=1,
            trade_id='123457',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = detector.detect(trade2)
        
        assert result.is_anomaly is True
        assert result.anomalies[0].anomaly_type == AnomalyType.TIME_GAP
    
    def test_stale_data_detected(self, detector: AnomalyDetector) -> None:
        """Test that stale data is detected."""
        # Trade from 2 minutes ago
        trade = Trade(
            time=datetime.utcnow() - timedelta(minutes=2),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = detector.detect(trade)
        
        assert result.is_anomaly is True
        assert result.anomalies[0].anomaly_type == AnomalyType.STALE_DATA
    
    def test_price_spike_detected(self, detector: AnomalyDetector) -> None:
        """Test that price spikes are detected."""
        # First trade at $50,000
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        detector.detect(trade1)
        
        # Second trade at $65,000 (30% spike - should be CRITICAL)
        trade2 = Trade(
            time=datetime.utcnow() + timedelta(seconds=1),
            symbol_id=1,
            trade_id='123457',
            price=Decimal('65000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = detector.detect(trade2)
        
        assert result.is_anomaly is True
        assert result.should_reject is True
        assert result.anomalies[0].anomaly_type == AnomalyType.PRICE_SPIKE
        assert result.anomalies[0].severity == AnomalySeverity.HIGH
    
    def test_price_drop_detected(self, detector: AnomalyDetector) -> None:
        """Test that price drops are detected."""
        # First trade at $50,000
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        detector.detect(trade1)
        
        # Second trade at $40,000 (20% drop)
        trade2 = Trade(
            time=datetime.utcnow() + timedelta(seconds=1),
            symbol_id=1,
            trade_id='123457',
            price=Decimal('40000.00'),
            quantity=Decimal('0.001'),
            side='SELL',
        )
        
        result = detector.detect(trade2)
        
        assert result.is_anomaly is True
        assert result.should_reject is True
        assert result.anomalies[0].anomaly_type == AnomalyType.PRICE_DROP
    
    def test_volume_spike_detected(self, detector: AnomalyDetector) -> None:
        """Test that volume spikes are detected."""
        # Create several normal trades to establish average
        for i in range(20):
            trade = Trade(
                time=datetime.utcnow() + timedelta(seconds=i),
                symbol_id=1,
                trade_id=f'12345{i}',
                price=Decimal('50000.00'),
                quantity=Decimal('0.001'),
                side='BUY',
            )
            detector.detect(trade)
        
        # Large volume trade (15x average)
        large_trade = Trade(
            time=datetime.utcnow() + timedelta(seconds=20),
            symbol_id=1,
            trade_id='123470',
            price=Decimal('50000.00'),
            quantity=Decimal('0.015'),  # 15x normal
            side='BUY',
        )
        
        result = detector.detect(large_trade)
        
        assert result.is_anomaly is True
        assert result.should_flag is True
        assert result.anomalies[0].anomaly_type == AnomalyType.VOLUME_SPIKE
    
    def test_out_of_order_detected(self, detector: AnomalyDetector) -> None:
        """Test that out-of-order trades are detected."""
        # First trade
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        detector.detect(trade1)
        
        # Second trade with earlier timestamp
        trade2 = Trade(
            time=datetime.utcnow() - timedelta(seconds=10),
            symbol_id=1,
            trade_id='123457',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = detector.detect(trade2)
        
        assert result.is_anomaly is True
        assert result.should_flag is True
        assert result.anomalies[0].anomaly_type == AnomalyType.OUT_OF_ORDER
    
    def test_wash_trade_detected(self, detector: AnomalyDetector) -> None:
        """Test that potential wash trades are detected."""
        # First trade
        trade1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        detector.detect(trade1)
        
        # Second trade with same price, quantity, within 1 second
        trade2 = Trade(
            time=datetime.utcnow() + timedelta(milliseconds=500),
            symbol_id=1,
            trade_id='123457',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='SELL',
        )
        
        result = detector.detect(trade2)
        
        assert result.is_anomaly is True
        assert result.anomalies[0].anomaly_type == AnomalyType.WASH_TRADE
        assert result.anomalies[0].severity == AnomalySeverity.LOW
    
    def test_detector_statistics(self, detector: AnomalyDetector) -> None:
        """Test getting detector statistics."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        detector.detect(trade)
        
        stats = detector.get_statistics()
        
        assert stats['recent_trades'] == 1
        assert stats['last_price'] == 50000.00
    
    def test_detector_reset(self, detector: AnomalyDetector) -> None:
        """Test resetting detector state."""
        trade = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id='123456',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        detector.detect(trade)
        
        detector.reset()
        
        stats = detector.get_statistics()
        assert stats['recent_trades'] == 0
        assert stats['last_price'] is None
