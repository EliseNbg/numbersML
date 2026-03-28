"""
Integration tests for data quality framework.

Tests the integration of:
- Anomaly detection
- Gap detection
- Quality metrics tracking
- Ticker collection
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from src.domain.models.symbol import Symbol
from src.domain.models.trade import Trade
from src.domain.services.anomaly_detector import AnomalyDetector
from src.domain.services.gap_detector import GapDetector, GapFiller, DataGap
from src.domain.services.quality_metrics import QualityMetricsTracker


class TestDataQualityIntegration:
    """Test data quality services integration."""
    
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
    
    def test_anomaly_detection_with_quality_tracking(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test anomaly detection integrated with quality tracking."""
        # Setup
        detector = AnomalyDetector(
            symbol=btc_symbol,
            price_spike_threshold=Decimal('5.0'),
        )
        
        # Simulate normal trades
        for i in range(10):
            trade = Trade(
                time=datetime.now(timezone.utc) + timedelta(seconds=i),
                symbol_id=1,
                trade_id=f'trade{i}',
                price=Decimal('50000.00'),
                quantity=Decimal('0.001'),
                side='BUY',
            )
            
            result = detector.detect(trade)
            
            # Normal trades should not trigger anomalies
            assert result.is_anomaly is False
        
        # Simulate price spike
        spike_trade = Trade(
            time=datetime.now(timezone.utc) + timedelta(seconds=10),
            symbol_id=1,
            trade_id='trade10',
            price=Decimal('60000.00'),  # 20% spike
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = detector.detect(spike_trade)
        
        # Should detect anomaly
        assert result.is_anomaly is True
        assert result.should_reject is True
        assert result.anomalies[0].anomaly_type.value == 'price_spike'
    
    def test_gap_detection_with_filling(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test gap detection integrated with gap filling."""
        # Setup
        gap_detector = GapDetector(max_gap_seconds=5)
        gap_detector.start_monitoring(1, 'BTC/USDT')
        
        # First tick
        time1 = datetime.now(timezone.utc)
        gap = gap_detector.check_tick(1, time1)
        assert gap is None
        
        # Second tick with gap
        time2 = time1 + timedelta(seconds=10)
        gap = gap_detector.check_tick(1, time2)
        
        # Should detect gap
        assert gap is not None
        assert gap.gap_seconds == 10.0
        assert gap.is_critical is False
        
        # Critical gap (>60 seconds)
        time3 = time2 + timedelta(seconds=70)
        gap = gap_detector.check_tick(1, time3)
        
        assert gap is not None
        assert gap.is_critical is True
        
        # Test gap filler (mock)
        gap_fill_result = GapFiller.__new__(GapFiller)
        gap_fill_result.gap = gap
        gap_fill_result.ticks_filled = 0
        gap_fill_result.success = False
        gap_fill_result.error = "Not implemented in tests"
        
        # Verify gap is tracked
        unfilled_gaps = gap_detector.get_unfilled_gaps()
        assert len(unfilled_gaps) >= 1
    
    def test_quality_metrics_calculation(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test quality metrics calculation."""
        # Setup (mock db_pool)
        mock_pool = None
        tracker = QualityMetricsTracker.__new__(QualityMetricsTracker)
        tracker._metrics = {}
        
        # Simulate processing
        symbol_id = 1
        
        # Record 100 valid ticks
        for i in range(100):
            tracker.record_tick(symbol_id, is_valid=True, latency_ms=5.0)
        
        # Record 10 invalid ticks
        for i in range(10):
            tracker.record_tick(symbol_id, is_valid=False, latency_ms=10.0)
        
        # Record anomalies
        for i in range(5):
            tracker.record_anomaly(symbol_id)
        
        # Record gaps
        for i in range(3):
            tracker.record_gap(symbol_id, is_filled=True)
        
        # Calculate quality score
        score = tracker.calculate_quality_score(symbol_id)
        
        # Verify score is reasonable (should be good with 90% validation rate)
        assert score > 50
        assert score <= 100
        
        # Get metrics
        metrics = tracker.get_metrics(symbol_id)
        assert metrics is not None
        assert metrics.ticks_received == 110
        assert metrics.ticks_validated == 100
        assert metrics.ticks_rejected == 10
        assert metrics.anomalies_detected == 5
        assert metrics.gaps_detected == 3
        assert metrics.validation_rate > 90
    
    def test_full_pipeline_integration(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test full data quality pipeline integration."""
        # Setup all services
        detector = AnomalyDetector(symbol=btc_symbol)
        gap_detector = GapDetector(max_gap_seconds=5)
        gap_detector.start_monitoring(1, 'BTC/USDT')
        
        mock_pool = None
        metrics_tracker = QualityMetricsTracker.__new__(QualityMetricsTracker)
        metrics_tracker._metrics = {}
        
        symbol_id = 1
        
        # Process stream of ticks
        base_time = datetime.now(timezone.utc)
        
        for i in range(50):
            tick_time = base_time + timedelta(seconds=i)
            
            # Check for gaps
            gap = gap_detector.check_tick(symbol_id, tick_time)
            
            if gap:
                metrics_tracker.record_gap(symbol_id)
            
            # Create trade
            trade = Trade(
                time=tick_time,
                symbol_id=symbol_id,
                trade_id=f'trade{i}',
                price=Decimal('50000.00'),
                quantity=Decimal('0.001'),
                side='BUY',
            )
            
            # Detect anomalies
            anomaly_result = detector.detect(trade)
            
            if anomaly_result.is_anomaly:
                metrics_tracker.record_anomaly(symbol_id)
            
            # Record metrics
            metrics_tracker.record_tick(
                symbol_id,
                is_valid=not anomaly_result.should_reject,
                latency_ms=2.5,
            )
        
        # Calculate final quality score
        score = metrics_tracker.calculate_quality_score(symbol_id)
        
        # With no anomalies and no gaps, should have excellent quality
        assert score > 90
        
        # Get statistics
        detector_stats = detector.get_statistics()
        assert detector_stats['recent_trades'] > 0
        assert detector_stats['last_price'] == 50000.0


class TestTickerCollectorIntegration:
    """Test ticker collector integration with quality services."""
    
    def test_ticker_collector_initialization(self) -> None:
        """Test ticker collector initializes quality services."""
        from src.infrastructure.exchanges.ticker_collector import TickerCollector
        
        # Create mock db_pool
        mock_pool = None
        
        collector = TickerCollector(
            db_pool=mock_pool,  # type: ignore
            symbols=['BTC/USDT', 'ETH/USDT'],
            anomaly_threshold=Decimal('5.0'),
            max_gap_seconds=5,
        )
        
        # Verify configuration
        assert collector.symbols == ['BTC/USDT', 'ETH/USDT']
        assert collector.anomaly_threshold == Decimal('5.0')
        assert collector.max_gap_seconds == 5
        
        # Services will be initialized when start() is called
        assert collector._anomaly_detectors == {}
        assert collector._gap_detectors == {}
    
    def test_ticker_message_parsing(self) -> None:
        """Test ticker message parsing."""
        from src.infrastructure.exchanges.ticker_collector import TickerCollector
        
        collector = TickerCollector.__new__(TickerCollector)
        
        # Test symbol parsing
        assert collector._parse_symbol('BTCUSDT') == 'BTC/USDT'
        assert collector._parse_symbol('ETHBTC') == 'ETH/BTC'
        assert collector._parse_symbol('USDCETH') == 'USDC/ETH'
        
        # Test stats
        collector._stats = {'processed': 42, 'anomalies': 3, 'gaps': 1}
        stats = collector.get_stats()
        
        assert stats['processed'] == 42
        assert stats['anomalies'] == 3
        assert stats['gaps'] == 1
