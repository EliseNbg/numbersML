"""
Enhanced Strategy Runner - extends StrategyRunner with lifecycle, risk, and observability controls.

Wraps StrategyRunner to add:
- Per-strategy error isolation (failures don't crash global runner)
- Runtime activation/deactivation coordination
- Risk rule enforcement before signal generation
- Comprehensive telemetry and metrics collection
- Audit logging for all critical events
- Graceful cancellation and cleanup
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from uuid import UUID, uuid4

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
from src.application.services.risk_guardrails import (
    RiskGuardrailService,
    get_risk_guardrail_service,
)
from src.application.services.strategy_telemetry import (
    StrategyTelemetryService,
    get_telemetry_service,
)
from src.application.services.audit_logger import (
    AuditLogger,
    AuditEventType,
    AuditSeverity,
    get_audit_logger,
)

logger = logging.getLogger(__name__)


class EnhancedStrategyRunner(StrategyRunner):
    """Enhanced strategy runner with lifecycle, risk, and observability controls.

    Extends StrategyRunner to add:
    - Per-strategy error isolation via per-strategy exception handling
    - Coordination with StrategyLifecycleService for state tracking
    - RiskGuardrailService for hard safety limits and kill switches
    - StrategyTelemetryService for comprehensive metrics collection
    - AuditLogger for immutable audit trail
    - Graceful shutdown with cancellation scopes

    Architecture:
        Redis Pub/Sub
            → EnhancedStrategyRunner (per-strategy error isolation)
                → StrategyLifecycleService (state management)
                    → RiskGuardrailService (safety validation)
                        → StrategyTelemetryService (metrics)
                            → AuditLogger (audit trail)
                                → StrategyManager (tick processing)
                                    → Individual Strategies
    """

    def __init__(
        self,
        lifecycle_service: StrategyLifecycleService,
        risk_service: Optional[RiskGuardrailService] = None,
        telemetry_service: Optional[StrategyTelemetryService] = None,
        audit_logger: Optional[AuditLogger] = None,
        redis_url: str = "redis://localhost:6379",
        symbols: Optional[List[str]] = None,
    ) -> None:
        """Initialize enhanced runner.

        Args:
            lifecycle_service: Coordinates lifecycle, state, and risk rules
            risk_service: Hard risk guardrails and kill switches
            telemetry_service: Metrics and telemetry collection
            audit_logger: Audit trail logging
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
        self._risk = risk_service or get_risk_guardrail_service()
        self._telemetry = telemetry_service or get_telemetry_service()
        self._audit = audit_logger or get_audit_logger()

        self._running = False
        # Track per-strategy tick processing tasks for cancellation
        self._strategy_tasks: Dict[UUID, asyncio.Task] = {}

        # Register for telemetry
        for strategy_id in lifecycle_service._strategy_manager._strategies.keys():
            self._telemetry.register_strategy(strategy_id)
            self._risk.register_strategy(strategy_id)

        logger.info("EnhancedStrategyRunner initialized with observability and safety controls")

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
        """Handle incoming tick with per-strategy error isolation and safety checks.

        Each strategy processes the tick independently. If one fails,
        it doesn't affect others. Failures are recorded but don't crash
        the runner.

        Args:
            message: Redis message with enriched tick data
        """
        try:
            tick = EnrichedTick.from_message(message)
            self._stats["ticks_received"] += 1

            # Check global kill switch
            global_status = self._risk.get_global_status()
            if global_status["global_kill_active"]:
                logger.warning(
                    f"Tick dropped - global kill active: {global_status['global_kill_reason']}"
                )
                return

            # Get all active (RUNNING) strategies
            active_strategies = [
                sid
                for sid in self._lifecycle._runtime_states.keys()
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
                    # Record in telemetry
                    self._telemetry.record_error(
                        strategy_id=strategy_id,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        context={"tick_symbol": tick.symbol},
                    )
                    self._stats["errors"] += 1

        except Exception as e:
            # Critical error (tick parsing, etc.)
            logger.error(f"Critical error processing tick: {e}", exc_info=True)
            self._stats["errors"] += 1

    async def _process_tick_for_strategy(
        self,
        strategy_id: UUID,
        tick: EnrichedTick,
    ) -> None:
        """Process a single tick through a specific strategy.

        Includes hard risk guardrail enforcement before signal generation
        and comprehensive telemetry collection.

        Args:
            strategy_id: ID of strategy to process
            tick: Enriched tick data

        Raises:
            Exception: Any error during processing (will be caught upstream)
        """
        start_time = asyncio.get_event_loop().time()

        strategy = self._lifecycle._strategy_manager.get_strategy(strategy_id)
        if not strategy:
            return

        # Check if strategy should process this symbol
        if tick.symbol not in strategy.symbols:
            return

        # Check data freshness with risk guardrails
        data_fresh, stale_reason = await self._risk.check_data_freshness(
            strategy_id=strategy_id,
            data_timestamp=tick.time,
        )
        if not data_fresh:
            logger.warning(f"Strategy {strategy_id} blocked: {stale_reason}")
            self._telemetry.record_guardrail_block(strategy_id, "stale_data", stale_reason)
            return

        # Generate signal (strategy-specific logic)
        signal = strategy.process_tick(tick)

        # Record tick processing
        processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        self._telemetry.record_tick_processed(strategy_id, tick.time, processing_time_ms)

        if signal:
            # Record signal generation in telemetry
            self._telemetry.record_signal(
                strategy_id=strategy_id,
                signal_id=str(uuid4()),
                symbol=signal.symbol,
                signal_type=signal.signal_type.value,
                confidence=signal.confidence,
                indicators_used=list(tick.indicators.keys()) if tick.indicators else [],
            )

            # Check hard risk guardrails before publishing
            notional = float(signal.price) * 0.1  # Example position size
            is_allowed, reason = await self._risk.check_order_allowed(
                strategy_id=strategy_id,
                symbol=signal.symbol,
                side=signal.signal_type.value,
                quantity=0.1,
                price=float(signal.price),
                notional=notional,
            )

            if not is_allowed:
                logger.warning(f"Signal from {strategy_id} blocked by guardrail: {reason}")
                self._telemetry.record_guardrail_block(strategy_id, "guardrail", reason)
                return

            # Check legacy risk rules (backward compatibility)
            is_allowed_old, reason_old = await self._lifecycle.is_order_allowed(
                strategy_id=strategy_id,
                order=None,
                current_positions={},
                daily_pnl=0.0,
            )

            if not is_allowed_old:
                logger.warning(f"Signal from {strategy_id} blocked by lifecycle risk: {reason_old}")
                return

            # Publish signal
            await self._publish_signal(signal)
            self._stats["signals_generated"] += 1

    async def activate_strategy(self, strategy_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Activate a strategy via lifecycle service with audit logging.

        Args:
            strategy_id: Strategy to activate
            actor: Who triggered the activation
            **kwargs: Passed to lifecycle service

        Returns:
            True if activation succeeded
        """
        # Register with observability services if not already
        self._telemetry.register_strategy(strategy_id)
        self._risk.register_strategy(strategy_id)

        success = await self._lifecycle.activate_strategy(strategy_id, **kwargs)

        if success and self._audit:
            await self._audit.log_strategy_lifecycle(
                strategy_id=strategy_id,
                transition="activated",
                actor_id=actor,
                new_status="active",
            )

        return success

    async def deactivate_strategy(self, strategy_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Deactivate a strategy via lifecycle service with audit logging.

        Args:
            strategy_id: Strategy to deactivate
            actor: Who triggered the deactivation
            **kwargs: Passed to lifecycle service

        Returns:
            True if deactivation succeeded
        """
        success = await self._lifecycle.deactivate_strategy(strategy_id, **kwargs)

        if success and self._audit:
            await self._audit.log_strategy_lifecycle(
                strategy_id=strategy_id,
                transition="deactivated",
                actor_id=actor,
                new_status="inactive",
            )

        # Clean up observability
        self._risk.unregister_strategy(strategy_id)
        self._telemetry.unregister_strategy(strategy_id)

        return success

    async def pause_strategy(self, strategy_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Pause a strategy via lifecycle service with audit logging.

        Args:
            strategy_id: Strategy to pause
            actor: Who triggered the pause
            **kwargs: Passed to lifecycle service

        Returns:
            True if pause succeeded
        """
        success = await self._lifecycle.pause_strategy(strategy_id, **kwargs)

        if success and self._audit:
            await self._audit.log_strategy_lifecycle(
                strategy_id=strategy_id,
                transition="paused",
                actor_id=actor,
                new_status="paused",
            )

        return success

    async def resume_strategy(self, strategy_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Resume a strategy via lifecycle service with audit logging.

        Args:
            strategy_id: Strategy to resume
            actor: Who triggered the resume
            **kwargs: Passed to lifecycle service

        Returns:
            True if resume succeeded
        """
        success = await self._lifecycle.resume_strategy(strategy_id, **kwargs)

        if success and self._audit:
            await self._audit.log_strategy_lifecycle(
                strategy_id=strategy_id,
                transition="resumed",
                actor_id=actor,
                new_status="active",
            )

        return success

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
