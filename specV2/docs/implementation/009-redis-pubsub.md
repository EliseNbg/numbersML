# Step 009: Redis Pub/Sub - Implementation Guide

**Phase**: 4 - Enrichment  
**Effort**: 4 hours  
**Dependencies**: Step 008 (Enrichment Service) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements **Redis Pub/Sub messaging** for strategy communication:
- Channel management per symbol
- Message serialization/deserialization
- Subscription management
- Reconnection handling
- Message history (optional)
- Comprehensive tests (85%+ coverage)

---

## Implementation Tasks

### Task 1: Redis Message Bus

**File**: `src/infrastructure/redis/message_bus.py`

```python
"""
Redis Pub/Sub message bus.

Provides publish/subscribe functionality for strategy communication.
"""

import asyncio
import json
import redis.asyncio as redis
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MessageBus:
    """
    Redis Pub/Sub message bus.
    
    Provides publish/subscribe functionality for distributing
    enriched tick data to strategies.
    
    Attributes:
        redis_url: Redis connection URL
        channels: Active channels
        subscribers: Active subscribers per channel
    
    Example:
        >>> bus = MessageBus(redis_url="redis://localhost:6379")
        >>> await bus.connect()
        >>> await bus.subscribe('enriched_tick:BTC/USDT', callback)
        >>> await bus.publish('enriched_tick:BTC/USDT', message)
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_connections: int = 10,
    ) -> None:
        """
        Initialize message bus.
        
        Args:
            redis_url: Redis connection URL
            max_connections: Maximum connections in pool
        """
        self.redis_url: str = redis_url
        self.max_connections: int = max_connections
        
        self._pool: Optional[redis.ConnectionPool] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._client: Optional[redis.Redis] = None
        self._running: bool = False
        self._channels: Dict[str, List[Callable]] = {}  # channel -> callbacks
        self._stats: Dict[str, int] = {
            'messages_published': 0,
            'messages_received': 0,
            'errors': 0,
        }
    
    async def connect(self) -> None:
        """Connect to Redis."""
        logger.info(f"Connecting to Redis: {self.redis_url}")
        
        self._pool = redis.ConnectionPool.from_url(
            self.redis_url,
            max_connections=self.max_connections,
        )
        
        self._client = redis.Redis(connection_pool=self._pool)
        self._pubsub = self._client.pubsub()
        
        self._running = True
        
        # Start message listener
        asyncio.create_task(self._listen())
        
        logger.info("Connected to Redis")
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        logger.info("Disconnecting from Redis...")
        
        self._running = False
        
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
        
        if self._client:
            await self._client.close()
        
        if self._pool:
            await self._pool.disconnect()
        
        logger.info("Disconnected from Redis")
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """
        Publish message to channel.
        
        Args:
            channel: Channel name (e.g., 'enriched_tick:BTC/USDT')
            message: Message dictionary
        
        Returns:
            Number of subscribers that received the message
        
        Example:
            >>> await bus.publish('enriched_tick:BTC/USDT', {
            ...     'symbol': 'BTC/USDT',
            ...     'price': 50000.0,
            ...     'indicators': {'rsi': 55.5}
            ... })
        """
        try:
            # Add timestamp
            message['timestamp'] = datetime.utcnow().isoformat()
            
            # Serialize
            message_json = json.dumps(message)
            
            # Publish
            num_subscribers = await self._client.publish(channel, message_json)
            
            self._stats['messages_published'] += 1
            
            logger.debug(
                f"Published to {channel}: {num_subscribers} subscribers"
            )
            
            return num_subscribers
        
        except Exception as e:
            logger.error(f"Error publishing to {channel}: {e}")
            self._stats['errors'] += 1
            return 0
    
    async def subscribe(
        self,
        channel: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """
        Subscribe to channel.
        
        Args:
            channel: Channel name
            callback: Callback function for messages
        
        Example:
            >>> def on_message(msg):
            ...     print(f"Received: {msg}")
            >>> await bus.subscribe('enriched_tick:BTC/USDT', on_message)
        """
        if channel not in self._channels:
            self._channels[channel] = []
            
            # Subscribe in Redis
            await self._pubsub.subscribe(channel)
            logger.info(f"Subscribed to {channel}")
        
        self._channels[channel].append(callback)
        logger.info(f"Added callback to {channel} (total: {len(self._channels[channel])})")
    
    async def unsubscribe(self, channel: str) -> None:
        """
        Unsubscribe from channel.
        
        Args:
            channel: Channel name
        """
        if channel in self._channels:
            del self._channels[channel]
            await self._pubsub.unsubscribe(channel)
            logger.info(f"Unsubscribed from {channel}")
    
    async def _listen(self) -> None:
        """Listen for messages from Redis."""
        logger.info("Starting message listener...")
        
        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                
                if message and message['type'] == 'message':
                    await self._process_message(message)
            
            except Exception as e:
                logger.error(f"Error in message listener: {e}")
                self._stats['errors'] += 1
                
                # Reconnect on error
                if self._running:
                    logger.info("Reconnecting to Redis...")
                    await asyncio.sleep(5)
                    await self.connect()
    
    async def _process_message(self, message: Dict) -> None:
        """
        Process received message.
        
        Args:
            message: Redis message
        """
        try:
            channel = message['channel']
            if isinstance(channel, bytes):
                channel = channel.decode('utf-8')
            
            data = message['data']
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            
            # Parse JSON
            message_data = json.loads(data)
            
            self._stats['messages_received'] += 1
            
            # Call callbacks
            if channel in self._channels:
                for callback in self._channels[channel]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(message_data)
                        else:
                            callback(message_data)
                    except Exception as e:
                        logger.error(f"Error in callback for {channel}: {e}")
            
            logger.debug(f"Processed message from {channel}")
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self._stats['errors'] += 1
    
    def get_stats(self) -> Dict[str, int]:
        """Get message bus statistics."""
        return self._stats.copy()
    
    def get_subscribed_channels(self) -> List[str]:
        """Get list of subscribed channels."""
        return list(self._channels.keys())
    
    def get_subscriber_count(self, channel: str) -> int:
        """Get number of subscribers for channel."""
        return len(self._channels.get(channel, []))


class ChannelManager:
    """
    Manages Redis channel naming and organization.
    
    Provides consistent channel naming conventions.
    """
    
    # Channel prefixes
    ENRICHED_TICK = "enriched_tick"
    SIGNAL = "strategy_signal"
    ORDER = "order"
    ALERT = "alert"
    
    @classmethod
    def enriched_tick_channel(cls, symbol: str) -> str:
        """Get enriched tick channel for symbol."""
        return f"{cls.ENRICHED_TICK}:{symbol}"
    
    @classmethod
    def strategy_signal_channel(cls, strategy_id: str) -> str:
        """Get strategy signal channel."""
        return f"{cls.SIGNAL}:{strategy_id}"
    
    @classmethod
    def order_channel(cls, strategy_id: str) -> str:
        """Get order channel for strategy."""
        return f"{cls.ORDER}:{strategy_id}"
    
    @classmethod
    def alert_channel(cls, alert_type: str) -> str:
        """Get alert channel."""
        return f"{cls.ALERT}:{alert_type}"
    
    @classmethod
    def parse_channel(cls, channel: str) -> Dict[str, str]:
        """Parse channel name into components."""
        parts = channel.split(':')
        
        if len(parts) != 2:
            return {'type': 'unknown', 'identifier': channel}
        
        return {
            'type': parts[0],
            'identifier': parts[1],
        }

```

---

## Acceptance Criteria

- [ ] MessageBus implemented
- [ ] Publish/subscribe working
- [ ] Reconnection handling
- [ ] Channel management
- [ ] Unit tests (85%+ coverage)
- [ ] Integration test with enrichment service

---

## Next Steps

After completing this step, proceed to **Step 010: Recalculation Service**
