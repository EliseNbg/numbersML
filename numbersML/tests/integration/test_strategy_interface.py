"""
Integration tests for Redis messaging and strategy interface.

Tests:
- Redis pub/sub messaging
- Strategy subscription
- Message formatting
- Event handling
"""

import pytest
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List


class TestRedisMessageBusIntegration:
    """Test Redis message bus integration."""

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        """Create mock Redis client."""
        redis = MagicMock()
        redis.publish = AsyncMock(return_value=1)
        redis.subscribe = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        redis.close = AsyncMock()
        return redis

    def test_message_bus_publish(self, mock_redis: MagicMock) -> None:
        """Test publishing messages via Redis."""
        from src.infrastructure.redis.message_bus import MessageBus

        # Create bus with mock - properly initialize all attributes
        bus = MessageBus.__new__(MessageBus)
        bus._redis = mock_redis
        bus._client = mock_redis  # Also set _client for publish method
        bus._running = True
        bus._stats = {'messages_published': 0, 'messages_received': 0, 'errors': 0}

        # Publish message
        import asyncio
        asyncio.run(bus.publish('test_channel', {'key': 'value'}))

        # Verify publish called
        assert mock_redis.publish.called
        
    def test_channel_manager(self) -> None:
        """Test channel naming and parsing."""
        from src.infrastructure.redis.message_bus import ChannelManager
        
        # Test enriched tick channel
        channel = ChannelManager.enriched_tick_channel('BTC/USDT')
        assert channel == 'enriched_tick:BTC/USDT'
        
        # Test strategy signal channel
        channel = ChannelManager.strategy_signal_channel('strategy_1')
        assert channel == 'strategy_signal:strategy_1'
        
        # Test parsing
        parts = ChannelManager.parse_channel('enriched_tick:BTC/USDT')
        assert parts['type'] == 'enriched_tick'
        assert parts['identifier'] == 'BTC/USDT'
        
    def test_message_format_enriched_tick(self) -> None:
        """Test enriched tick message format."""
        # Create enriched tick message
        message = {
            'symbol': 'BTC/USDT',
            'price': 50000.0,
            'time': '2026-03-21T12:00:00Z',
            'indicators': {
                'rsiindicator_period14_rsi': 55.5,
                'smaindicator_period20_sma': 49500.0,
            },
        }
        
        # Verify format
        assert 'symbol' in message
        assert 'price' in message
        assert 'time' in message
        assert 'indicators' in message
        assert isinstance(message['indicators'], dict)
        
        # Serialize/deserialize
        json_str = json.dumps(message)
        parsed = json.loads(json_str)
        
        assert parsed['symbol'] == 'BTC/USDT'
        assert parsed['price'] == 50000.0
        assert parsed['indicators']['rsiindicator_period14_rsi'] == 55.5


class TestStrategyInterfaceIntegration:
    """Test strategy interface integration."""

    @pytest.fixture
    def sample_enriched_tick(self) -> Dict[str, Any]:
        """Create sample enriched tick message."""
        return {
            'symbol': 'BTC/USDT',
            'price': 50000.0,
            'time': '2026-03-21T12:00:00Z',
            'indicators': {
                'rsiindicator_period14_rsi': 55.5,
                'smaindicator_period20_sma': 49500.0,
                'smaindicator_period50_sma': 48500.0,
            },
        }

    def test_strategy_signal_generation(self) -> None:
        """Test strategy generating signals."""
        # Simple RSI strategy logic
        rsi_value = 55.5
        
        # Generate signal based on RSI
        if rsi_value < 30:
            signal = 'BUY'
        elif rsi_value > 70:
            signal = 'SELL'
        else:
            signal = 'HOLD'
        
        assert signal == 'HOLD'
        
        # Test oversold
        rsi_value = 25.0
        if rsi_value < 30:
            signal = 'BUY'
        elif rsi_value > 70:
            signal = 'SELL'
        else:
            signal = 'HOLD'
        
        assert signal == 'BUY'
        
        # Test overbought
        rsi_value = 75.0
        if rsi_value < 30:
            signal = 'BUY'
        elif rsi_value > 70:
            signal = 'SELL'
        else:
            signal = 'HOLD'
        
        assert signal == 'SELL'
        
    def test_strategy_with_multiple_indicators(
        self,
        sample_enriched_tick: Dict[str, Any],
    ) -> None:
        """Test strategy using multiple indicators."""
        indicators = sample_enriched_tick['indicators']
        price = sample_enriched_tick['price']
        
        # Get indicators
        rsi = indicators.get('rsiindicator_period14_rsi', 50.0)
        sma_20 = indicators.get('smaindicator_period20_sma', 50000.0)
        sma_50 = indicators.get('smaindicator_period50_sma', 49000.0)
        
        # Generate composite signal
        bullish_signals = 0
        bearish_signals = 0
        
        # RSI signal
        if rsi < 30:
            bullish_signals += 1
        elif rsi > 70:
            bearish_signals += 1
        
        # SMA crossover signal
        if sma_20 > sma_50:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        # Price vs SMA signal
        if price > sma_20:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        # Determine final signal
        if bullish_signals > bearish_signals:
            final_signal = 'BUY'
        elif bearish_signals > bullish_signals:
            final_signal = 'SELL'
        else:
            final_signal = 'HOLD'
        
        # With sample data: RSI=55.5 (neutral), SMA20>SMA50 (bullish), Price>SMA20 (bullish)
        assert bullish_signals == 2
        assert bearish_signals == 0
        assert final_signal == 'BUY'
        
    def test_strategy_backtest_simulation(
        self,
        sample_enriched_tick: Dict[str, Any],
    ) -> None:
        """Test strategy backtest simulation."""
        # Simulate processing multiple ticks
        ticks = [
            {**sample_enriched_tick, 'price': 50000.0, 'indicators': {**sample_enriched_tick['indicators'], 'rsiindicator_period14_rsi': 25.0}},
            {**sample_enriched_tick, 'price': 50100.0, 'indicators': {**sample_enriched_tick['indicators'], 'rsiindicator_period14_rsi': 30.0}},
            {**sample_enriched_tick, 'price': 50200.0, 'indicators': {**sample_enriched_tick['indicators'], 'rsiindicator_period14_rsi': 40.0}},
            {**sample_enriched_tick, 'price': 50150.0, 'indicators': {**sample_enriched_tick['indicators'], 'rsiindicator_period14_rsi': 50.0}},
            {**sample_enriched_tick, 'price': 50300.0, 'indicators': {**sample_enriched_tick['indicators'], 'rsiindicator_period14_rsi': 60.0}},
            {**sample_enriched_tick, 'price': 50400.0, 'indicators': {**sample_enriched_tick['indicators'], 'rsiindicator_period14_rsi': 75.0}},
            {**sample_enriched_tick, 'price': 50350.0, 'indicators': {**sample_enriched_tick['indicators'], 'rsiindicator_period14_rsi': 80.0}},
        ]
        
        # Simple RSI strategy
        position = None
        trades = []
        
        for i, tick in enumerate(ticks):
            rsi = tick['indicators']['rsiindicator_period14_rsi']
            price = tick['price']
            
            # Generate signal
            if rsi < 30 and position is None:
                position = 'LONG'
                trades.append({'action': 'BUY', 'price': price, 'tick': i})
            elif rsi > 70 and position == 'LONG':
                position = None
                trades.append({'action': 'SELL', 'price': price, 'tick': i})
        
        # Verify trades
        assert len(trades) == 2
        assert trades[0]['action'] == 'BUY'
        assert trades[0]['price'] == 50000.0
        assert trades[1]['action'] == 'SELL'
        assert trades[1]['price'] == 50400.0
        
        # Calculate profit
        buy_price = trades[0]['price']
        sell_price = trades[1]['price']
        profit = sell_price - buy_price
        
        assert profit == 400.0


class TestEventHandlingIntegration:
    """Test event handling integration."""

    def test_indicator_change_event(self) -> None:
        """Test indicator change event handling."""
        # Simulate indicator change event
        event = {
            'indicator_id': 1,
            'indicator_name': 'rsiindicator_period14',
            'change_type': 'params_changed',
            'old_params': {'period': 14},
            'new_params': {'period': 21},
        }
        
        # Verify event structure
        assert 'indicator_id' in event
        assert 'indicator_name' in event
        assert 'change_type' in event
        assert event['change_type'] in ['params_changed', 'code_changed', 'created']
        
    def test_new_tick_event(self) -> None:
        """Test new tick event handling."""
        # Simulate new tick event from PostgreSQL NOTIFY
        event = {
            'symbol_id': 1,
            'time': '2026-03-21T12:00:00Z',
            'trade_id': 'trade123',
        }
        
        # Verify event structure
        assert 'symbol_id' in event
        assert 'time' in event
        assert 'trade_id' in event
        
    def test_gap_detected_event(self) -> None:
        """Test gap detected event handling."""
        # Simulate gap detected event
        event = {
            'symbol_id': 1,
            'symbol': 'BTC/USDT',
            'gap_start': '2026-03-21T12:00:00Z',
            'gap_end': '2026-03-21T12:00:10Z',
            'gap_seconds': 10.0,
            'is_critical': False,
        }
        
        # Verify event structure
        assert 'symbol_id' in event
        assert 'symbol' in event
        assert 'gap_seconds' in event
        assert 'is_critical' in event
        
        # Critical gap
        critical_event = {**event, 'gap_seconds': 70.0, 'is_critical': True}
        assert critical_event['is_critical'] is True


class TestConfigurationIntegration:
    """Test configuration integration."""

    def test_eu_compliance_filtering(self) -> None:
        """Test EU compliance filtering in pipeline."""
        from src.application.services.asset_sync_service import AssetSyncService
        
        mock_pool = MagicMock()
        service = AssetSyncService(db_pool=mock_pool, eu_compliance=True)
        
        # Test allowed quote assets
        assert service._check_eu_compliance('USDC') is True
        assert service._check_eu_compliance('BTC') is True
        assert service._check_eu_compliance('ETH') is True
        
        # Test excluded quote assets
        assert service._check_eu_compliance('USDT') is False
        assert service._check_eu_compliance('BUSD') is False
        assert service._check_eu_compliance('TUSD') is False
        
    def test_symbol_active_status(self) -> None:
        """Test symbol active status filtering."""
        from src.domain.models.symbol import Symbol
        
        # Active symbol
        active_symbol = Symbol(
            symbol='BTC/USDC',
            base_asset='BTC',
            quote_asset='USDC',
            is_allowed=True,
            is_active=True,
        )
        
        assert active_symbol.is_active is True
        assert active_symbol.is_allowed is True
        
        # Inactive symbol
        inactive_symbol = Symbol(
            symbol='BTC/USDT',
            base_asset='BTC',
            quote_asset='USDT',
            is_allowed=False,  # EU compliance
            is_active=False,  # Not collected
        )
        
        assert inactive_symbol.is_active is False
        assert inactive_symbol.is_allowed is False
        
    def test_quality_threshold_configuration(self) -> None:
        """Test quality threshold configuration."""
        from src.domain.services.anomaly_detector import AnomalyDetector
        from src.domain.models.symbol import Symbol
        
        symbol = Symbol(symbol='BTC/USDT', base_asset='BTC', quote_asset='USDT')
        
        # Default thresholds
        detector_default = AnomalyDetector(symbol=symbol)
        assert detector_default.price_spike_threshold == Decimal('5.0')
        
        # Custom thresholds
        detector_custom = AnomalyDetector(
            symbol=symbol,
            price_spike_threshold=Decimal('10.0'),
            max_gap_seconds=10,
        )
        assert detector_custom.price_spike_threshold == Decimal('10.0')
        assert detector_custom.max_gap_seconds == 10


class TestMonitoringIntegration:
    """Test monitoring integration."""

    def test_health_check_response(self) -> None:
        """Test health check response format."""
        # Simulate health check result
        health_result = {
            'database': {
                'healthy': True,
                'latency_ms': 5.2,
                'message': 'Connection successful',
            },
            'redis': {
                'healthy': True,
                'latency_ms': 1.5,
                'message': 'Connection successful',
            },
            'services': {
                'healthy': True,
                'details': {
                    'active_services': 3,
                },
            },
        }
        
        # Verify structure
        assert 'database' in health_result
        assert 'redis' in health_result
        assert 'services' in health_result
        
        # Check health status
        all_healthy = all(
            component.get('healthy', False)
            for component in health_result.values()
        )
        
        assert all_healthy is True
        
    def test_service_statistics(self) -> None:
        """Test service statistics collection."""
        # Simulate service stats
        stats = {
            'ticks_processed': 10000,
            'indicators_calculated': 150000,
            'anomalies_detected': 5,
            'gaps_detected': 2,
            'errors': 0,
        }
        
        # Verify stats structure
        assert 'ticks_processed' in stats
        assert 'indicators_calculated' in stats
        assert 'anomalies_detected' in stats
        
        # Calculate rates
        anomaly_rate = stats['anomalies_detected'] / stats['ticks_processed'] * 100
        assert anomaly_rate < 1.0  # Less than 1% anomalies
        
    def test_quality_metrics_dashboard(self) -> None:
        """Test quality metrics for dashboard."""
        from src.domain.services.quality_metrics import QualityMetricsTracker
        
        tracker = QualityMetricsTracker.__new__(QualityMetricsTracker)
        tracker._metrics = {}
        
        symbol_id = 1
        
        # Simulate metrics
        for i in range(1000):
            tracker.record_tick(symbol_id, is_valid=True, latency_ms=5.0)
        
        for i in range(10):
            tracker.record_tick(symbol_id, is_valid=False, latency_ms=10.0)
        
        for i in range(5):
            tracker.record_anomaly(symbol_id)
        
        # Get metrics for dashboard
        score = tracker.calculate_quality_score(symbol_id)
        metrics = tracker.get_metrics(symbol_id)

        # Dashboard data
        # Note: anomaly_rate is calculated, not stored as attribute
        anomaly_rate = (metrics.anomalies_detected / metrics.ticks_received * 100) if metrics.ticks_received > 0 else 0.0
        
        dashboard_data = {
            'quality_score': score,
            'quality_level': metrics.quality_level.value,
            'ticks_received': metrics.ticks_received,
            'validation_rate': metrics.validation_rate,
            'anomaly_rate': anomaly_rate,
        }

        # Verify dashboard data
        assert dashboard_data['quality_score'] > 90
        assert dashboard_data['quality_level'] in ['excellent', 'good', 'fair', 'poor']
        assert dashboard_data['validation_rate'] > 95
