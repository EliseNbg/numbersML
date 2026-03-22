"""
Strategy Runner - Executes strategies with Redis pub/sub integration.

Connects strategies to Redis message bus for real-time tick processing.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.domain.strategies.base import Strategy, StrategyManager, EnrichedTick, Signal
from src.infrastructure.redis.message_bus import MessageBus, ChannelManager

logger = logging.getLogger(__name__)


class StrategyRunner:
    """
    Strategy runner with Redis integration.

    Purpose:
        - Connects to Redis pub/sub
        - Subscribes to enriched tick channels
        - Routes ticks to strategies
        - Publishes strategy signals

    Architecture:
        Redis Pub/Sub → StrategyRunner → Strategies → Signals

    Example:
        >>> runner = StrategyRunner(
        ...     redis_url="redis://localhost:6379",
        ...     strategy_manager=strategy_manager,
        ... )
        >>> await runner.start()
        >>> # Runs until stopped
        >>> await runner.stop()
    """

    def __init__(
        self,
        strategy_manager: StrategyManager,
        redis_url: str = "redis://localhost:6379",
        symbols: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize strategy runner.

        Args:
            strategy_manager: Manager with registered strategies
            redis_url: Redis connection URL
            symbols: Symbols to subscribe to (None = all from strategies)

        Raises:
            ValueError: If strategy_manager is None
        """
        if strategy_manager is None:
            raise ValueError("strategy_manager cannot be None")

        self._strategy_manager: StrategyManager = strategy_manager
        self._redis_url: str = redis_url
        self._symbols: Optional[List[str]] = symbols

        self._message_bus: MessageBus = MessageBus(redis_url=redis_url)
        self._running: bool = False
        self._stats: Dict[str, int] = {
            'ticks_received': 0,
            'signals_generated': 0,
            'errors': 0,
        }

        logger.info(f"StrategyRunner initialized for {len(symbols or [])} symbols")

    async def start(self) -> None:
        """
        Start strategy runner.

        Connects to Redis, subscribes to channels, starts strategies.
        """
        logger.info("Starting StrategyRunner...")

        # Connect to Redis
        await self._message_bus.connect()

        # Start strategies
        await self._strategy_manager.start_all()

        # Subscribe to enriched tick channels
        symbols = self._symbols or self._get_all_symbols()
        for symbol in symbols:
            channel = ChannelManager.enriched_tick_channel(symbol)
            await self._message_bus.subscribe(channel, self._on_tick)
            logger.info(f"Subscribed to {channel}")

        self._running = True
        logger.info(f"StrategyRunner started with {len(symbols)} symbols")

    async def stop(self) -> None:
        """Stop strategy runner."""
        logger.info("Stopping StrategyRunner...")

        self._running = False

        # Stop strategies
        await self._strategy_manager.stop_all()

        # Disconnect from Redis
        await self._message_bus.disconnect()

        logger.info("StrategyRunner stopped")

    async def _on_tick(self, message: Dict[str, Any]) -> None:
        """
        Handle incoming tick message.

        Args:
            message: Redis message with enriched tick data
        """
        try:
            # Parse enriched tick
            tick = EnrichedTick.from_message(message)
            self._stats['ticks_received'] += 1

            # Process through strategies
            signals = self._strategy_manager.process_tick(tick)

            # Publish signals
            for signal in signals:
                await self._publish_signal(signal)
                self._stats['signals_generated'] += 1

        except Exception as e:
            logger.error(f"Error processing tick message: {e}")
            self._stats['errors'] += 1

    async def _publish_signal(self, signal: Signal) -> None:
        """
        Publish strategy signal to Redis.

        Args:
            signal: Signal to publish
        """
        channel = ChannelManager.strategy_signal_channel(signal.strategy_id)
        await self._message_bus.publish(channel, signal.to_dict())
        logger.debug(
            f"Published signal: {signal.signal_type.value} "
            f"{signal.symbol} @ {signal.price}"
        )

    def _get_all_symbols(self) -> List[str]:
        """Get all symbols from all strategies."""
        symbols = set()
        for strategy_id in self._strategy_manager.list_strategies():
            strategy = self._strategy_manager.get_strategy(strategy_id)
            if strategy:
                symbols.update(strategy.symbols)
        return list(symbols)

    def get_stats(self) -> Dict[str, Any]:
        """Get runner statistics."""
        return {
            **self._stats,
            'running': self._running,
            'strategy_stats': self._strategy_manager.get_stats(),
            'bus_stats': self._message_bus.get_stats(),
        }


class SignalHandler:
    """
    Handles strategy signals for execution or logging.

    Purpose:
        - Subscribe to strategy signal channels
        - Process signals (execute, log, forward)
        - Track signal history

    Example:
        >>> handler = SignalHandler()
        >>> await handler.subscribe('rsi_strategy')
        >>> # Process signals as they arrive
    """

    def __init__(
        self,
        on_signal_callback: Optional[callable] = None,
    ) -> None:
        """
        Initialize signal handler.

        Args:
            on_signal_callback: Callback for received signals
        """
        self._on_signal = on_signal_callback
        self._signals: List[Signal] = []
        self._running: bool = False
        logger.info("SignalHandler initialized")

    async def subscribe(
        self,
        message_bus: MessageBus,
        strategy_id: str,
    ) -> None:
        """
        Subscribe to strategy signal channel.

        Args:
            message_bus: Message bus instance
            strategy_id: Strategy ID to subscribe to
        """
        channel = ChannelManager.strategy_signal_channel(strategy_id)
        await message_bus.subscribe(channel, self._handle_signal)
        logger.info(f"Subscribed to signals from {strategy_id}")

    def _handle_signal(self, message: Dict[str, Any]) -> None:
        """
        Handle incoming signal message.

        Args:
            message: Signal message dictionary
        """
        try:
            # Parse signal
            signal = Signal(
                strategy_id=message.get('strategy_id', ''),
                symbol=message.get('symbol', ''),
                signal_type=message.get('signal_type', 'HOLD'),
                price=message.get('price', 0),
                confidence=message.get('confidence', 0.5),
                metadata=message.get('metadata', {}),
            )

            # Store
            self._signals.append(signal)

            # Callback
            if self._on_signal:
                self._on_signal(signal)

            logger.info(
                f"Signal received: {signal.signal_type} "
                f"{signal.symbol} (confidence: {signal.confidence:.2f})"
            )

        except Exception as e:
            logger.error(f"Error handling signal: {e}")

    def get_signals(self, symbol: Optional[str] = None) -> List[Signal]:
        """
        Get received signals.

        Args:
            symbol: Filter by symbol (None = all)

        Returns:
            List of signals
        """
        if symbol:
            return [s for s in self._signals if s.symbol == symbol]
        return self._signals.copy()

    def get_latest_signal(self, symbol: str) -> Optional[Signal]:
        """Get latest signal for symbol."""
        symbol_signals = [s for s in self._signals if s.symbol == symbol]
        return symbol_signals[-1] if symbol_signals else None

    def clear(self) -> None:
        """Clear signal history."""
        self._signals = []
