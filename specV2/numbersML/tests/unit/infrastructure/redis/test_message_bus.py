"""Tests for Redis message bus."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.infrastructure.redis.message_bus import MessageBus, ChannelManager


class TestMessageBus:
    """Test MessageBus."""
    
    @pytest.fixture
    def message_bus(self) -> MessageBus:
        """Create message bus for testing."""
        return MessageBus(redis_url="redis://localhost:6379")
    
    def test_message_bus_initialization(self, message_bus: MessageBus) -> None:
        """Test message bus initialization."""
        assert message_bus.redis_url == "redis://localhost:6379"
        assert message_bus.max_connections == 10
        assert message_bus._running is False
        assert message_bus._stats['messages_published'] == 0
    
    def test_get_stats(self, message_bus: MessageBus) -> None:
        """Test getting statistics."""
        message_bus._stats = {
            'messages_published': 100,
            'messages_received': 95,
            'errors': 2,
        }
        
        stats = message_bus.get_stats()
        
        assert stats['messages_published'] == 100
        assert stats['messages_received'] == 95
        assert stats['errors'] == 2
    
    @pytest.mark.asyncio
    async def test_connect_without_redis(self, message_bus: MessageBus) -> None:
        """Test connect when Redis is not available."""
        # Should not raise, just run in mock mode
        await message_bus.connect()
        
        assert message_bus._running is True
    
    @pytest.mark.asyncio
    async def test_disconnect(self, message_bus: MessageBus) -> None:
        """Test disconnect."""
        message_bus._running = True
        
        await message_bus.disconnect()
        
        assert message_bus._running is False
    
    @pytest.mark.asyncio
    async def test_publish_mock_mode(self, message_bus: MessageBus) -> None:
        """Test publish in mock mode (no Redis)."""
        message_bus._running = True
        
        num_subscribers = await message_bus.publish(
            'test_channel',
            {'key': 'value'}
        )
        
        # In mock mode, returns 0
        assert num_subscribers == 0
    
    @pytest.mark.asyncio
    async def test_subscribe(self, message_bus: MessageBus) -> None:
        """Test subscribe to channel."""
        callback = MagicMock()
        
        await message_bus.subscribe('test_channel', callback)
        
        # Should have one subscriber
        assert message_bus.get_subscriber_count('test_channel') == 1
        assert 'test_channel' in message_bus.get_subscribed_channels()
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self, message_bus: MessageBus) -> None:
        """Test unsubscribe from channel."""
        callback = MagicMock()
        
        await message_bus.subscribe('test_channel', callback)
        await message_bus.unsubscribe('test_channel')
        
        # Should have no subscribers
        assert message_bus.get_subscriber_count('test_channel') == 0
        assert 'test_channel' not in message_bus.get_subscribed_channels()
    
    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, message_bus: MessageBus) -> None:
        """Test multiple subscribers to same channel."""
        callback1 = MagicMock()
        callback2 = MagicMock()
        callback3 = MagicMock()
        
        await message_bus.subscribe('test_channel', callback1)
        await message_bus.subscribe('test_channel', callback2)
        await message_bus.subscribe('test_channel', callback3)
        
        # Should have three subscribers
        assert message_bus.get_subscriber_count('test_channel') == 3
    
    @pytest.mark.asyncio
    async def test_callback_invocation(self, message_bus: MessageBus) -> None:
        """Test that callbacks are invoked."""
        callback = MagicMock()
        
        await message_bus.subscribe('test_channel', callback)
        
        # Manually invoke callback (simulating message receipt)
        if 'test_channel' in message_bus._channels:
            for cb in message_bus._channels['test_channel']:
                cb({'test': 'data'})
        
        # Callback should have been called
        callback.assert_called_once_with({'test': 'data'})
    
    @pytest.mark.asyncio
    async def test_async_callback_invocation(self, message_bus: MessageBus) -> None:
        """Test that async callbacks are awaited."""
        callback = AsyncMock()
        
        await message_bus.subscribe('test_channel', callback)
        
        # Manually invoke callback
        if 'test_channel' in message_bus._channels:
            for cb in message_bus._channels['test_channel']:
                if asyncio.iscoroutinefunction(cb):
                    await cb({'test': 'data'})
        
        # Callback should have been awaited
        callback.assert_called_once_with({'test': 'data'})


class TestChannelManager:
    """Test ChannelManager."""
    
    def test_enriched_tick_channel(self) -> None:
        """Test enriched tick channel naming."""
        channel = ChannelManager.enriched_tick_channel('BTC/USDT')
        assert channel == 'enriched_tick:BTC/USDT'
    
    def test_strategy_signal_channel(self) -> None:
        """Test strategy signal channel naming."""
        channel = ChannelManager.strategy_signal_channel('strategy_1')
        assert channel == 'strategy_signal:strategy_1'
    
    def test_order_channel(self) -> None:
        """Test order channel naming."""
        channel = ChannelManager.order_channel('strategy_1')
        assert channel == 'order:strategy_1'
    
    def test_alert_channel(self) -> None:
        """Test alert channel naming."""
        channel = ChannelManager.alert_channel('price_spike')
        assert channel == 'alert:price_spike'
    
    def test_parse_channel(self) -> None:
        """Test channel parsing."""
        result = ChannelManager.parse_channel('enriched_tick:BTC/USDT')
        
        assert result['type'] == 'enriched_tick'
        assert result['identifier'] == 'BTC/USDT'
    
    def test_parse_channel_invalid(self) -> None:
        """Test parsing invalid channel."""
        result = ChannelManager.parse_channel('invalid_channel')
        
        assert result['type'] == 'unknown'
        assert result['identifier'] == 'invalid_channel'


class TestMessageBusIntegration:
    """Test MessageBus integration."""
    
    @pytest.mark.asyncio
    async def test_publish_subscribe_flow(self) -> None:
        """Test publish and subscribe flow."""
        bus = MessageBus(redis_url="redis://localhost:6379")
        
        # Track received messages
        received_messages = []
        
        def on_message(msg):
            received_messages.append(msg)
        
        # Subscribe
        await bus.subscribe('test_channel', on_message)
        
        # Publish (in mock mode, won't actually send)
        await bus.publish('test_channel', {'key': 'value'})
        
        # In mock mode, message won't be received via Redis
        # But we can verify the subscription worked
        assert bus.get_subscriber_count('test_channel') == 1
    
    @pytest.mark.asyncio
    async def test_channel_cleanup(self) -> None:
        """Test channel cleanup on unsubscribe."""
        bus = MessageBus()
        
        callback = MagicMock()
        
        await bus.subscribe('channel_1', callback)
        await bus.subscribe('channel_2', callback)
        
        assert len(bus.get_subscribed_channels()) == 2
        
        await bus.unsubscribe('channel_1')
        
        assert len(bus.get_subscribed_channels()) == 1
        assert 'channel_2' in bus.get_subscribed_channels()
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self) -> None:
        """Test statistics tracking."""
        bus = MessageBus()
        
        # Publish some messages
        for i in range(10):
            await bus.publish(f'channel_{i}', {'i': i})
        
        stats = bus.get_stats()
        
        # In mock mode, all publishes succeed but return 0 subscribers
        assert stats['messages_published'] == 10
        assert stats['errors'] == 0
