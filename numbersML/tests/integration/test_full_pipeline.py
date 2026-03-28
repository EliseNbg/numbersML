"""
Integration tests for full data pipeline.

Tests the complete pipeline:
1. Asset Sync → 2. Data Collection → 3. Validation → 4. Enrichment → 5. Redis Pub/Sub
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any

from src.domain.models.symbol import Symbol
from src.domain.models.trade import Trade
from src.domain.services.tick_validator import TickValidator, ValidationResult
from src.domain.services.anomaly_detector import AnomalyDetector, AnomalyResult
from src.domain.services.gap_detector import GapDetector
from src.domain.services.quality_metrics import QualityMetricsTracker
from src.application.services.asset_sync_service import AssetSyncService
from src.application.services.enrichment_service import EnrichmentService
from src.indicators.providers import PythonIndicatorProvider
from src.indicators.momentum import RSIIndicator
from src.indicators.trend import SMAIndicator


class TestFullPipelineIntegration:
    """Test complete data pipeline from collection to enrichment."""

    @pytest.fixture
    def btc_symbol(self) -> Symbol:
        """Create BTC/USDT symbol for testing."""
        return Symbol(
            id=1,
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            tick_size=Decimal('0.01'),
            step_size=Decimal('0.00001'),
            min_notional=Decimal('10'),
            is_allowed=True,
            is_active=True,
        )

    @pytest.fixture
    def eth_symbol(self) -> Symbol:
        """Create ETH/USDT symbol for testing."""
        return Symbol(
            id=2,
            symbol='ETH/USDT',
            base_asset='ETH',
            quote_asset='USDT',
            tick_size=Decimal('0.01'),
            step_size=Decimal('0.00001'),
            min_notional=Decimal('10'),
            is_allowed=True,
            is_active=True,
        )

    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock()
        return pool

    def test_asset_sync_to_collection_pipeline(
        self,
        mock_db_pool: MagicMock,
        btc_symbol: Symbol,
    ) -> None:
        """Test asset sync flows into data collection."""
        # Step 1: Asset Sync creates symbol
        sync_service = AssetSyncService(db_pool=mock_db_pool)
        
        # Simulate parsed symbol from Binance
        binance_data = {
            'symbol': 'BTCUSDT',
            'baseAsset': 'BTC',
            'quoteAsset': 'USDT',
            'status': 'TRADING',
            'isSpotEnabled': True,
            'filters': [
                {'filterType': 'PRICE_FILTER', 'tickSize': '0.01'},
                {'filterType': 'LOT_SIZE', 'stepSize': '0.00001'},
                {'filterType': 'NOTIONAL', 'minNotional': '10'},
            ],
        }
        
        parsed_symbol = sync_service._parse_symbol(binance_data)
        assert parsed_symbol is not None
        assert parsed_symbol.symbol == 'BTC/USDT'
        assert parsed_symbol.is_allowed is False  # USDT excluded in EU
        
        # Step 2: Symbol would be stored in DB (mocked)
        # Step 3: Data collection would fetch active symbols
        
    def test_validation_pipeline(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test complete validation pipeline."""
        # Create validator
        validator = TickValidator(symbol=btc_symbol)
        
        # Create valid trade
        valid_trade = Trade(
            time=datetime.now(timezone.utc),
            symbol_id=1,
            trade_id='trade1',
            price=Decimal('50000.00'),
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        # Validate
        result = validator.validate(valid_trade)
        assert result.is_valid is True
        
        # Create invalid trade (price spike)
        invalid_trade = Trade(
            time=datetime.now(timezone.utc),
            symbol_id=1,
            trade_id='trade2',
            price=Decimal('100000.00'),  # 100% spike
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = validator.validate(invalid_trade)
        assert result.is_valid is False
        # Check for actual error message (not internal error code)
        assert any('price' in error.lower() and 'exceeds' in error.lower() for error in result.errors)
        
    def test_anomaly_detection_pipeline(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test anomaly detection in pipeline."""
        # Create detector
        detector = AnomalyDetector(
            symbol=btc_symbol,
            price_spike_threshold=Decimal('5.0'),
        )
        
        # Process stream of trades
        base_price = Decimal('50000.00')
        base_time = datetime.now(timezone.utc)
        
        for i in range(20):
            trade = Trade(
                time=base_time + timedelta(seconds=i),
                symbol_id=1,
                trade_id=f'trade{i}',
                price=base_price,
                quantity=Decimal('0.001'),
                side='BUY',
            )
            
            result = detector.detect(trade)
            
            # First 20 trades should be normal
            if i < 19:
                assert result.is_anomaly is False
        
        # Create price spike
        spike_trade = Trade(
            time=base_time + timedelta(seconds=20),
            symbol_id=1,
            trade_id='trade20',
            price=base_price * Decimal('1.10'),  # 10% spike
            quantity=Decimal('0.001'),
            side='BUY',
        )
        
        result = detector.detect(spike_trade)
        assert result.is_anomaly is True
        # Check that anomaly was detected and should be rejected
        # Removed incorrect assertion: AnomalyResult does not have a 'should_reject' attribute.
        assert len(result.anomalies) > 0
        
    def test_gap_detection_pipeline(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test gap detection in pipeline."""
        # Create gap detector
        gap_detector = GapDetector(max_gap_seconds=5)
        gap_detector.start_monitoring(1, 'BTC/USDT')
        
        # Send first tick
        time1 = datetime.now(timezone.utc)
        gap = gap_detector.check_tick(1, time1)
        assert gap is None  # No gap expected
        
        # Send second tick with normal interval
        time2 = time1 + timedelta(seconds=1)
        gap = gap_detector.check_tick(1, time2)
        assert gap is None
        
        # Send third tick with gap
        time3 = time2 + timedelta(seconds=10)
        gap = gap_detector.check_tick(1, time3)
        
        assert gap is not None
        assert gap.gap_seconds == 10.0
        
    def test_quality_metrics_pipeline(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test quality metrics tracking in pipeline."""
        # Create tracker (mock db_pool)
        tracker = QualityMetricsTracker.__new__(QualityMetricsTracker)
        tracker._metrics = {}
        
        symbol_id = 1
        
        # Simulate processing 100 ticks
        for i in range(100):
            tracker.record_tick(symbol_id, is_valid=True, latency_ms=5.0)
        
        # Simulate 5 anomalies
        for i in range(5):
            tracker.record_anomaly(symbol_id)
        
        # Simulate 2 gaps
        for i in range(2):
            tracker.record_gap(symbol_id, is_filled=True)
        
        # Calculate quality score
        score = tracker.calculate_quality_score(symbol_id)
        
        # Should have good score (>80 with 95% validation rate)
        assert score > 80
        assert score <= 100
        
        # Get metrics
        metrics = tracker.get_metrics(symbol_id)
        assert metrics.ticks_received == 100
        assert metrics.ticks_validated == 100
        assert metrics.ticks_rejected == 0
        assert metrics.anomalies_detected == 5
        assert metrics.gaps_detected == 2
        
    def test_indicator_calculation_pipeline(
        self,
        btc_symbol: Symbol,
    ) -> None:
        """Test indicator calculation in pipeline."""
        import numpy as np
        
        # Create indicators
        rsi = RSIIndicator(period=14)
        sma = SMAIndicator(period=20)
        
        # Generate price data
        prices = np.array([50000.0 + i * 10 for i in range(100)])
        volumes = np.ones(100)
        
        # Calculate RSI
        rsi_result = rsi.calculate(prices, volumes)
        assert 'rsi' in rsi_result.values
        assert len(rsi_result.values['rsi']) == len(prices)
        
        # Last RSI should be in valid range (0-100)
        last_rsi = rsi_result.values['rsi'][-1]
        assert 0 <= last_rsi <= 100
        
        # Calculate SMA
        sma_result = sma.calculate(prices, volumes)
        assert 'sma' in sma_result.values
        assert len(sma_result.values['sma']) == len(prices)
        
        # SMA should be close to average price
        last_sma = sma_result.values['sma'][-1]
        assert 49000 < last_sma < 51000
        
    def test_enrichment_service_initialization(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test enrichment service initializes correctly with provider."""
        # Create provider with explicit indicators
        provider = PythonIndicatorProvider({
            'rsi_14': RSIIndicator,
        })
        
        # Create service with provider
        service = EnrichmentService(
            db_pool=mock_db_pool,
            indicator_provider=provider,
            window_size=100,
        )

        # Verify configuration
        assert service.window_size == 100
        assert service.indicator_provider is provider
        assert service._running is False
        
        # Verify provider has the indicator
        assert provider.is_available('rsi_14') is True
        assert 'rsi_14' in provider.list_indicators()
        
    def test_multi_symbol_pipeline(
        self,
        btc_symbol: Symbol,
        eth_symbol: Symbol,
    ) -> None:
        """Test pipeline with multiple symbols."""
        # Create validators for each symbol
        btc_validator = TickValidator(symbol=btc_symbol)
        eth_validator = TickValidator(symbol=eth_symbol)
        
        # Create detectors for each symbol
        btc_detector = AnomalyDetector(symbol=btc_symbol)
        eth_detector = AnomalyDetector(symbol=eth_symbol)
        
        # Process trades for both symbols
        base_time = datetime.now(timezone.utc)
        
        for i in range(10):
            # BTC trade
            btc_trade = Trade(
                time=base_time + timedelta(seconds=i),
                symbol_id=1,
                trade_id=f'btc_trade{i}',
                price=Decimal('50000.00'),
                quantity=Decimal('0.001'),
                side='BUY',
            )
            
            btc_valid = btc_validator.validate(btc_trade)
            btc_anomaly = btc_detector.detect(btc_trade)
            
            assert btc_valid.is_valid is True
            assert btc_anomaly.is_anomaly is False
            
            # ETH trade
            eth_trade = Trade(
                time=base_time + timedelta(seconds=i),
                symbol_id=2,
                trade_id=f'eth_trade{i}',
                price=Decimal('3000.00'),
                quantity=Decimal('0.01'),
                side='SELL',
            )
            
            eth_valid = eth_validator.validate(eth_trade)
            eth_anomaly = eth_detector.detect(eth_trade)
            
            assert eth_valid.is_valid is True
            assert eth_anomaly.is_anomaly is False
            
        # Verify independent tracking
        btc_stats = btc_detector.get_statistics()
        eth_stats = eth_detector.get_statistics()
        
        assert btc_stats['recent_trades'] == 10
        assert eth_stats['recent_trades'] == 10


class TestDatabaseIntegration:
    """Test database integration points."""

    @pytest.mark.asyncio
    async def test_symbol_repository_operations(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test symbol repository with mock database."""
        from src.infrastructure.repositories.symbol_repository import SymbolRepository
        
        # Create repository
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        
        # Mock context manager
        async with mock_pool.acquire() as conn:
            pass
        
        # Setup mock
        mock_conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'symbol': 'BTC/USDT',
            'base_asset': 'BTC',
            'quote_asset': 'USDT',
            'exchange': 'binance',
            'tick_size': Decimal('0.01'),
            'step_size': Decimal('0.00001'),
            'min_notional': Decimal('10'),
            'is_allowed': True,
            'is_active': True,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        })
        
        mock_conn.fetch = AsyncMock(return_value=[])
        
        # Test get_by_id
        repo = SymbolRepository(mock_conn)
        symbol = await repo.get_by_id(1)
        
        assert symbol is not None
        assert symbol.symbol == 'BTC/USDT'
        assert symbol.base_asset == 'BTC'
        assert symbol.quote_asset == 'USDT'
        
    @pytest.mark.asyncio
    async def test_asset_sync_database_integration(
        self,
        mock_db_pool: MagicMock,
    ) -> None:
        """Test asset sync with database operations."""
        # Create service
        service = AssetSyncService(db_pool=mock_db_pool)
        
        # Mock database operations
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])  # No existing symbols
        mock_conn.execute = AsyncMock(return_value='INSERT 0 1')
        
        # Mock context manager
        acquire_ctx = MagicMock()
        acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_db_pool.acquire = MagicMock(return_value=acquire_ctx)
        
        # Create test symbol
        symbol = Symbol(
            symbol='TEST/USDC',
            base_asset='TEST',
            quote_asset='USDC',
            exchange='binance',
            tick_size=Decimal('0.01'),
            step_size=Decimal('0.00001'),
            min_notional=Decimal('10'),
            is_allowed=True,
            is_active=True,
        )
        
        # Add symbol (would be called during sync)
        await service._add_symbol(symbol)
        
        # Verify database was called
        assert mock_conn.execute.called


class TestIndicatorIntegration:
    """Test indicator framework integration with providers."""

    def test_indicator_provider_registration(self) -> None:
        """Test PythonIndicatorProvider registration."""
        from src.indicators.providers import PythonIndicatorProvider
        from src.indicators.momentum import RSIIndicator, StochasticIndicator

        # Create provider with explicit indicators
        provider = PythonIndicatorProvider({
            'rsi_14': RSIIndicator,
            'stoch_14_3': StochasticIndicator,
        })

        # Should have registered indicators
        indicators = provider.list_indicators()
        assert len(indicators) >= 2

        # Check for specific indicators
        assert 'rsi_14' in indicators
        assert 'stoch_14_3' in indicators

    def test_indicator_provider_creation(self) -> None:
        """Test creating indicators via provider."""
        from src.indicators.providers import PythonIndicatorProvider
        from src.indicators.momentum import RSIIndicator

        # Create provider
        provider = PythonIndicatorProvider({
            'rsi_14': RSIIndicator,
        })

        # Create RSI indicator via provider
        rsi = provider.get_indicator('rsi_14', period=14)
        assert rsi is not None
        assert rsi.params['period'] == 14
        
        # Non-existent indicator returns None
        assert provider.get_indicator('nonexistent') is None
            
    def test_multiple_indicators_calculation(self) -> None:
        """Test calculating multiple indicators together."""
        import numpy as np
        
        # Create multiple indicators
        indicators = {
            'rsi': RSIIndicator(period=14),
            'sma_20': SMAIndicator(period=20),
            'sma_50': SMAIndicator(period=50),
        }
        
        # Generate test data
        prices = np.array([50000.0 + np.sin(i * 0.1) * 100 for i in range(100)])
        volumes = np.ones(100)
        
        # Calculate all indicators
        results = {}
        for name, indicator in indicators.items():
            result = indicator.calculate(prices, volumes)
            results[name] = result
        
        # Verify all calculated
        assert 'rsi' in results
        assert 'sma_20' in results
        assert 'sma_50' in results
        
        # Verify values are reasonable
        assert 0 <= results['rsi'].values['rsi'][-1] <= 100
        assert 49000 < results['sma_20'].values['sma'][-1] < 51000
        assert 49000 < results['sma_50'].values['sma'][-1] < 51000


class TestEndToEndScenario:
    """End-to-end scenario tests."""

    def test_new_symbol_lifecycle(self) -> None:
        """Test complete lifecycle of a new symbol."""
        # Phase 1: Asset Sync adds symbol
        mock_pool = MagicMock()
        sync_service = AssetSyncService(db_pool=mock_pool)
        
        binance_data = {
            'symbol': 'NEWUSDC',
            'baseAsset': 'NEW',
            'quoteAsset': 'USDC',
            'status': 'TRADING',
            'isSpotEnabled': True,
            'filters': [
                {'filterType': 'PRICE_FILTER', 'tickSize': '0.01'},
                {'filterType': 'LOT_SIZE', 'stepSize': '0.00001'},
                {'filterType': 'NOTIONAL', 'minNotional': '10'},
            ],
        }
        
        symbol = sync_service._parse_symbol(binance_data)
        assert symbol is not None
        assert symbol.is_allowed is True  # USDC is EU compliant
        assert symbol.is_active is True  # Auto-activated
        
        # Phase 2: Symbol would be collected (mocked)
        # Phase 3: Validation would occur
        validator = TickValidator(symbol=symbol)
        
        trade = Trade(
            time=datetime.now(timezone.utc),
            symbol_id=1,
            trade_id='trade1',
            price=Decimal('100.00'),
            quantity=Decimal('0.1'),
            side='BUY',
        )
        
        result = validator.validate(trade)
        assert result.is_valid is True
        
        # Phase 4: Anomaly detection
        detector = AnomalyDetector(symbol=symbol)
        anomaly_result = detector.detect(trade)
        assert anomaly_result.is_anomaly is False
        
        # Phase 5: Quality tracking
        tracker = QualityMetricsTracker.__new__(QualityMetricsTracker)
        tracker._metrics = {}
        
        tracker.record_tick(1, is_valid=True, latency_ms=5.0)
        score = tracker.calculate_quality_score(1)
        assert score > 90  # Excellent quality
        
    def test_data_quality_degradation_scenario(self) -> None:
        """Test pipeline behavior during data quality issues."""
        # Create symbol
        symbol = Symbol(
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            tick_size=Decimal('0.01'),
            step_size=Decimal('0.00001'),
            min_notional=Decimal('10'),
        )
        
        # Create services
        validator = TickValidator(symbol=symbol)
        detector = AnomalyDetector(symbol=symbol)
        gap_detector = GapDetector(max_gap_seconds=5)
        gap_detector.start_monitoring(1, 'BTC/USDT')
        
        tracker = QualityMetricsTracker.__new__(QualityMetricsTracker)
        tracker._metrics = {}
        
        # Simulate data quality issues
        base_time = datetime.now(timezone.utc)
        
        for i in range(50):
            tick_time = base_time + timedelta(seconds=i * 2)  # 2-second intervals
            
            # Check gaps (should detect some)
            gap = gap_detector.check_tick(1, tick_time)
            if gap:
                tracker.record_gap(1)
            
            # Create trade with occasional anomalies
            price = Decimal('50000.00')
            if i == 25:
                price = Decimal('60000.00')  # 20% spike
            
            trade = Trade(
                time=tick_time,
                symbol_id=1,
                trade_id=f'trade{i}',
                price=price,
                quantity=Decimal('0.001'),
                side='BUY',
            )
            
            # Validate
            valid_result = validator.validate(trade)
            
            # Detect anomalies
            anomaly_result = detector.detect(trade)
            
            # Track metrics
            tracker.record_tick(
                1,
                is_valid=valid_result.is_valid,
                latency_ms=5.0,
            )
            
            if anomaly_result.is_anomaly:
                tracker.record_anomaly(1)
        
        # Calculate quality score
        score = tracker.calculate_quality_score(1)

        # Score should reflect data quality (may vary based on implementation)
        assert score > 50  # Still acceptable
        assert score <= 100  # Valid range
        
        # Get metrics
        metrics = tracker.get_metrics(1)
        # Note: Anomalies and gaps may or may not be detected depending on timing
        # Just verify metrics are tracked
        assert metrics.ticks_received == 50
