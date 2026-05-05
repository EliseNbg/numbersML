"""
Algorithm Runner - Executes algorithms with Redis pub/sub integration.

Connects algorithms to Redis message bus for real-time tick processing.
"""

import logging
from typing import Any, Optional

from src.domain.algorithms.base import EnrichedTick, Signal, AlgorithmManager
from src.infrastructure.redis.message_bus import ChannelManager, MessageBus

logger = logging.getLogger(__name__)


class AlgorithmRunner:
    """
    Algorithm runner with Redis integration.

    Purpose:
        - Connects to Redis pub/sub
        - Subscribes to enriched tick channels
        - Routes ticks to algorithms
        - Publishes algorithm signals

    Architecture:
        Redis Pub/Sub → AlgorithmRunner → Algorithms → Signals

    Example:
        >>> runner = AlgorithmRunner(
        ...     redis_url="redis://localhost:6379",
        ...     algorithm_manager=algorithm_manager,
        ... )
        >>> await runner.start()
        >>> # Runs until stopped
        >>> await runner.stop()
    """

    def __init__(
        self,
        algorithm_manager: AlgorithmManager,
        redis_url: str = "redis://localhost:6379",
        symbols: Optional[list[str]] = None,
    ) -> None:
        """
        Initialize algorithm runner.

        Args:
            algorithm_manager: Manager with registered algorithms
            redis_url: Redis connection URL
            symbols: Symbols to subscribe to (None = all from algorithms)

        Raises:
            ValueError: If algorithm_manager is None
        """
        if algorithm_manager is None:
            raise ValueError("algorithm_manager cannot be None")

        self._algorithm_manager: AlgorithmManager = algorithm_manager
        self._redis_url: str = redis_url
        self._symbols: Optional[list[str]] = symbols

        self._message_bus: MessageBus = MessageBus(redis_url=redis_url)
        self._running: bool = False
        self._stats: dict[str, int] = {
            "ticks_received": 0,
            "signals_generated": 0,
            "errors": 0,
        }

        logger.info(f"AlgorithmRunner initialized for {len(symbols or [])} symbols")

    async def start(self) -> None:
        """
        Start algorithm runner.

        Connects to Redis, subscribes to channels, starts algorithms.
        """
        logger.info("Starting AlgorithmRunner...")

        # Connect to Redis
        await self._message_bus.connect()

        # Start algorithms
        await self._algorithm_manager.start_all()

        # Subscribe to enriched tick channels
        symbols = self._symbols or self._get_all_symbols()
        for symbol in symbols:
            channel = ChannelManager.enriched_tick_channel(symbol)
            await self._message_bus.subscribe(channel, self._on_tick)
            logger.info(f"Subscribed to {channel}")

        self._running = True
        logger.info(f"AlgorithmRunner started with {len(symbols)} symbols")

    async def stop(self) -> None:
        """Stop algorithm runner."""
        logger.info("Stopping AlgorithmRunner...")

        self._running = False

        # Stop algorithms
        await self._algorithm_manager.stop_all()

        # Disconnect from Redis
        await self._message_bus.disconnect()

        logger.info("AlgorithmRunner stopped")

    async def _on_tick(self, message: dict[str, Any]) -> None:
        """
        Handle incoming tick message.

        Args:
            message: Redis message with enriched tick data
        """
        try:
            # Parse enriched tick
            tick = EnrichedTick.from_message(message)
            self._stats["ticks_received"] += 1

            # Process through algorithms
            signals = self._algorithm_manager.process_tick(tick)

            # Publish signals
            for signal in signals:
                await self._publish_signal(signal)
                self._stats["signals_generated"] += 1

        except Exception as e:
            logger.error(f"Error processing tick message: {e}")
            self._stats["errors"] += 1

    async def _publish_signal(self, signal: Signal) -> None:
        """
        Publish algorithm signal to Redis.

        Args:
            signal: Signal to publish
        """
        channel = ChannelManager.algorithm_signal_channel(signal.algorithm_id)
        await self._message_bus.publish(channel, signal.to_dict())
        logger.debug(
            f"Published signal: {signal.signal_type.value} " f"{signal.symbol} @ {signal.price}"
        )

    def _get_all_symbols(self) -> list[str]:
        """Get all symbols from all algorithms."""
        symbols = set()
        for algorithm_id in self._algorithm_manager.list_algorithms():
            algorithm = self._algorithm_manager.get_algorithm(algorithm_id)
            if algorithm:
                symbols.update(algorithm.symbols)
        return list(symbols)

    def get_stats(self) -> dict[str, Any]:
        """Get runner statistics."""
        return {
            **self._stats,
            "running": self._running,
            "algorithm_stats": self._algorithm_manager.get_stats(),
            "bus_stats": self._message_bus.get_stats(),
        }


class SignalHandler:
    """
    Handles algorithm signals for execution or logging.

    Purpose:
        - Subscribe to algorithm signal channels
        - Process signals (execute, log, forward)
        - Track signal history

    Example:
        >>> handler = SignalHandler()
        >>> await handler.subscribe('rsi_algorithm')
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
        self._signals: list[Signal] = []
        self._running: bool = False
        logger.info("SignalHandler initialized")

    async def subscribe(
        self,
        message_bus: MessageBus,
        algorithm_id: str,
    ) -> None:
        """
        Subscribe to algorithm signal channel.

        Args:
            message_bus: Message bus instance
            algorithm_id: Algorithm ID to subscribe to
        """
        channel = ChannelManager.algorithm_signal_channel(algorithm_id)
        await message_bus.subscribe(channel, self._handle_signal)
        logger.info(f"Subscribed to signals from {algorithm_id}")

    def _handle_signal(self, message: dict[str, Any]) -> None:
        """
        Handle incoming signal message.

        Args:
            message: Signal message dictionary
        """
        try:
            # Parse signal
            signal = Signal(
                algorithm_id=message.get("algorithm_id", ""),
                symbol=message.get("symbol", ""),
                signal_type=message.get("signal_type", "HOLD"),
                price=message.get("price", 0),
                confidence=message.get("confidence", 0.5),
                metadata=message.get("metadata", {}),
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

    def get_signals(self, symbol: Optional[str] = None) -> list[Signal]:
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
