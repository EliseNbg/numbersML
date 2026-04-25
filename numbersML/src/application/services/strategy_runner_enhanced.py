"""
Enhanced Strategy Runner - extends StrategyRunner with lifecycle and risk controls.

Wraps StrategyRunner to add:
- Per-strategy error isolation (failures don't crash global runner)
- Runtime activation/deactivation coordination
- Risk rule enforcement before signal generation
- Graceful cancellation and cleanup
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from uuid import UUID

from src.domain.strategies.base import (
    Strategy,
    StrategyManager,
    EnrichedTick,
    Signal,
    StrategyState,
)
from src.domain.strategies.runtime import (
    StrategyRuntimeState,
    RuntimeState,
    StrategyLifecycleEvent,
)
from src.infrastructure.redis.message_bus import MessageBus
from src.application.services.strategy_lifecycle import StrategyLifecycleService
from src.application.services.strategy_runner import StrategyRunner, ChannelManager

logger = logging.getLogger(__name__)


class EnhancedStrategyRunner(StrategyRunner):
    """Enhanced strategy runner with lifecycle and risk controls.
    
    Extends StrategyRunner to add:
    - Per-strategy error isolation via per-strategy exception handling
    - Coordination with StrategyLifecycleService for state tracking
    - Risk rule enforcement (max errors, position limits)
    - Graceful shutdown with cancellation scopes
    
    Architecture:
        Redis Pub/Sub
            → EnhancedStrategyRunner (per-strategy error isolation)
                → StrategyLifecycleService (state + risk validation)
                    → StrategyManager (tick processing)
                        → Individual Strategies
    """

    def __init__(
        self,
        lifecycle_service: StrategyLifecycleService,
        redis_url: str = "redis://localhost:6379",
        symbols: Optional[List[str]] = None,
    ) -> None:
        """Initialize enhanced runner.
        
        Args:
            lifecycle_service: Coordinates lifecycle, state, and risk rules
            redis_url: Redis connection URL
            symbols: Symbols to subscribe to
        """
        # Get strategy manager from lifecycle service
        super().__init__(
            strategy_manager=lifecycle_service._strategy_manager,
            redis_url=redis_url,
            symbols=symbols,
        )
        self._lifecycle = lifecycle_service
        self._running = False
        # Track per-strategy tick processing tasks for cancellation
        self._strategy_tasks: Dict[UUID, asyncio.Task] = {}
        logger.info("EnhancedStrategyRunner initialized")

    async def start(self) -> None:
        """Start enhanced strategy runner."""
        logger.info("Starting EnhancedStrategyRunner...")

        # Connect to Redis
        await self._message_bus.connect()

        # Subscribe to enriched tick channels
        symbols = self._symbols or self._get_all_symbols()
        for symbol in symbols:
            channel = ChannelManager.enriched_tick_channel(symbol)
            await self._message_bus.subscribe(channel, self._on_tick_enhanced)
            logger.info(f"Subscribed to {channel}")

        self._running = True
        logger.info(f"EnhancedStrategyRunner started with {len(symbols)} symbols")

    async def _on_tick_enhanced(self, message: Dict[str, Any]) -> None:
        """Handle incoming tick with per-strategy error isolation.
        
        Each strategy processes the tick independently. If one fails,
        it doesn't affect others. Failures are recorded but don't crash
        the runner.
        
        Args:
            message: Redis message with enriched tick data
        """
        try:
            tick = EnrichedTick.from_message(message)
            self._stats['ticks_received'] += 1

            # Get all active (RUNNING) strategies
            active_strategies = [
                sid for sid in self._lifecycle._runtime_states.keys()
                if (self._lifecycle._runtime_states[sid].state == RuntimeState.RUNNING)
            ]

            # Process tick through each active strategy with error isolation
            for strategy_id in active_strategies:
                try:
                    await self._process_tick_for_strategy(strategy_id, tick)
                except asyncio.CancelledError:
                    # Task was cancelled, re-raise
                    raise
                except Exception as e:
                    # Per-strategy error - isolate and record
                    logger.error(
                        f"Strategy {strategy_id} error (isolated): {e}",
                        exc_info=True,
                    )
                    await self._lifecycle.record_strategy_error(
                        strategy_id,
                        str(e),
                        {"tick_symbol": tick.symbol, "tick_time": tick.time.isoformat()},
                    )
                    self._stats['errors'] += 1

        except Exception as e:
            # Critical error (tick parsing, etc.)
            logger.error(f"Critical error processing tick: {e}", exc_info=True)
            self._stats['errors'] += 1

    async def _process_tick_for_strategy(
        self,
        strategy_id: UUID,
        tick: EnrichedTick,
    ) -> None:
        """Process a single tick through a specific strategy.
        
        Includes risk rule enforcement before signal generation.
        
        Args:
            strategy_id: ID of strategy to process
            tick: Enriched tick data
            
        Raises:
            Exception: Any error during processing (will be caught upstream)
        """
        strategy = self._lifecycle._strategy_manager.get_strategy(strategy_id)
        if not strategy:
            return

        # Check if strategy should process this symbol
        if tick.symbol not in strategy.symbols:
            return

        # Generate signal (strategy-specific logic)
        signal = strategy.process_tick(tick)

        if signal:
            # Check risk rules before publishing
            is_allowed, reason = await self._lifecycle.is_order_allowed(
                strategy_id=strategy_id,
                order=None,  # Would create Order from signal in production
                current_positions={},  # Would fetch from portfolio
                daily_pnl=0.0,  # Would fetch from P&L service
            )

            if not is_allowed:
                logger.warning(
                    f"Signal from {strategy_id} blocked by risk rules: {reason}"
                )
                return

            # Publish signal
            await self._publish_signal(signal)
            self._stats['signals_generated'] += 1

    async def activate_strategy(self, strategy_id: UUID, **kwargs) -> bool:
        """Activate a strategy via lifecycle service.
        
        Args:
            strategy_id: Strategy to activate
            **kwargs: Passed to lifecycle service
            
        Returns:
            True if activation succeeded
        """
        return await self._lifecycle.activate_strategy(strategy_id, **kwargs)

    async def deactivate_strategy(self, strategy_id: UUID, **kwargs) -> bool:
        """Deactivate a strategy via lifecycle service.
        
        Args:
            strategy_id: Strategy to deactivate
            **kwargs: Passed to lifecycle service
            
        Returns:
            True if deactivation succeeded
        """
        return await self._lifecycle.deactivate_strategy(strategy_id, **kwargs)

    async def pause_strategy(self, strategy_id: UUID, **kwargs) -> bool:
        """Pause a strategy via lifecycle service.
        
        Args:
            strategy_id: Strategy to pause
            **kwargs: Passed to lifecycle service
            
        Returns:
            True if pause succeeded
        """
        return await self._lifecycle.pause_strategy(strategy_id, **kwargs)

    async def resume_strategy(self, strategy_id: UUID, **kwargs) -> bool:
        """Resume a strategy via lifecycle service.
        
        Args:
            strategy_id: Strategy to resume
            **kwargs: Passed to lifecycle service
            
        Returns:
            True if resume succeeded
        """
        return await self._lifecycle.resume_strategy(strategy_id, **kwargs)

    async def stop(self) -> None:
        """Stop runner with graceful cancellation of all tasks.
        
        Ensures all strategies are properly stopped and Redis is disconnected.
        """
        logger.info("Stopping EnhancedStrategyRunner...")

        self._running = False

        # Cancel all strategy tasks
        for task in self._strategy_tasks.values():
            if not task.done():
                task.cancel()

        # Wait for tasks to complete (with timeout)
        if self._strategy_tasks:
            try:
                await asyncio.wait(
                    list(self._strategy_tasks.values()),
                    timeout=5.0,
                    return_when=asyncio.ALL_COMPLETED,
                )
            except asyncio.TimeoutError:
                logger.warning("Some strategy tasks did not complete in time")
            except Exception as e:
                logger.error(f"Error during task cancellation: {e}")

        # Stop all strategies
        try:
            await self._lifecycle._strategy_manager.stop_all()
        except Exception as e:
            logger.error(f"Error stopping strategies: {e}")

        # Disconnect from Redis
        try:
            await self._message_bus.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting from Redis: {e}")

        logger.info("EnhancedStrategyRunner stopped")

    def get_runtime_state(self, strategy_id: UUID) -> Optional[StrategyRuntimeState]:
        """Get runtime state for a strategy."""
        return self._lifecycle._runtime_states.get(strategy_id)

    def get_all_runtime_states(self) -> List[StrategyRuntimeState]:
        """Get runtime states for all strategies."""
        return list(self._lifecycle._runtime_states.values())
