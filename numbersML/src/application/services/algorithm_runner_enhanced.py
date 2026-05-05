"""
Enhanced Algorithm Runner - extends AlgorithmRunner with lifecycle, risk, and observability controls.

Wraps AlgorithmRunner to add:
- Per-algorithm error isolation (failures don't crash global runner)
- Runtime activation/deactivation coordination
- Risk rule enforcement before signal generation
- Comprehensive telemetry and metrics collection
- Audit logging for all critical events
- Graceful cancellation and cleanup
"""

import asyncio
import logging
from typing import Any
from uuid import UUID, uuid4

from src.application.services.audit_logger import (
    AuditLogger,
    get_audit_logger,
)
from src.application.services.risk_guardrails import (
    RiskGuardrailService,
    get_risk_guardrail_service,
)
from src.application.services.algorithm_lifecycle import AlgorithmLifecycleService
from src.application.services.algorithm_runner import ChannelManager, AlgorithmRunner
from src.application.services.algorithm_telemetry import (
    AlgorithmTelemetryService,
    get_telemetry_service,
)
from src.domain.algorithms.base import (
    EnrichedTick,
)
from src.domain.algorithms.algorithm_instance import (
    AlgorithmInstance,
    AlgorithmInstanceState,
)

logger = logging.getLogger(__name__)


class EnhancedAlgorithmRunner(AlgorithmRunner):
    """Enhanced algorithm runner with lifecycle, risk, and observability controls.

    Extends AlgorithmRunner to add:
    - Per-algorithm error isolation via per-algorithm exception handling
    - Coordination with AlgorithmLifecycleService for state tracking
    - RiskGuardrailService for hard safety limits and kill switches
    - AlgorithmTelemetryService for comprehensive metrics collection
    - AuditLogger for immutable audit trail
    - Graceful shutdown with cancellation scopes

    Architecture:
        Redis Pub/Sub
            → EnhancedAlgorithmRunner (per-algorithm error isolation)
                → AlgorithmLifecycleService (state management)
                    → RiskGuardrailService (safety validation)
                        → AlgorithmTelemetryService (metrics)
                            → AuditLogger (audit trail)
                                → AlgorithmManager (tick processing)
                                    → Individual Algorithms
    """

    def __init__(
        self,
        lifecycle_service: AlgorithmLifecycleService,
        risk_service: RiskGuardrailService | None = None,
        telemetry_service: AlgorithmTelemetryService | None = None,
        audit_logger: AuditLogger | None = None,
        redis_url: str = "redis://localhost:6379",
        symbols: list[str] | None = None,
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
        # Get algorithm manager from lifecycle service
        super().__init__(
            algorithm_manager=lifecycle_service._algorithm_manager,
            redis_url=redis_url,
            symbols=symbols,
        )
        self._lifecycle = lifecycle_service
        self._risk = risk_service or get_risk_guardrail_service()
        self._telemetry = telemetry_service or get_telemetry_service()
        self._audit = audit_logger or get_audit_logger()

        self._running = False
        # Track per-algorithm tick processing tasks for cancellation
        self._algorithm_tasks: dict[UUID, asyncio.Task] = {}

        # Register for telemetry
        for algorithm_id in lifecycle_service._algorithm_manager._algorithms.keys():
            self._telemetry.register_algorithm(algorithm_id)
            self._risk.register_algorithm(algorithm_id)

        logger.info("EnhancedAlgorithmRunner initialized with observability and safety controls")

    async def start(self) -> None:
        """Start enhanced algorithm runner."""
        logger.info("Starting EnhancedAlgorithmRunner...")

        # Connect to Redis
        await self._message_bus.connect()

        # Subscribe to enriched tick channels
        symbols = self._symbols or self._get_all_symbols()
        for symbol in symbols:
            channel = ChannelManager.enriched_tick_channel(symbol)
            await self._message_bus.subscribe(channel, self._on_tick_enhanced)
            logger.info(f"Subscribed to {channel}")

        self._running = True
        logger.info(f"EnhancedAlgorithmRunner started with {len(symbols)} symbols")

    async def _on_tick_enhanced(self, message: dict[str, Any]) -> None:
        """Handle incoming tick with per-algorithm error isolation and safety checks.

        Each algorithm processes the tick independently. If one fails,
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

            # Get all active (RUNNING) algorithms
            active_algorithms = [
                sid
                for sid in self._lifecycle._instances.keys()
                if (self._lifecycle._instances[sid].state == AlgorithmInstanceState.RUNNING)
            ]

            # Process tick through each active algorithm with error isolation
            for algorithm_id in active_algorithms:
                try:
                    await self._process_tick_for_algorithm(algorithm_id, tick)
                except asyncio.CancelledError:
                    # Task was cancelled, re-raise
                    raise
                except Exception as e:
                    # Per-algorithm error - isolate and record
                    logger.error(
                        f"Algorithm {algorithm_id} error (isolated): {e}",
                        exc_info=True,
                    )
                    await self._lifecycle.record_algorithm_error(
                        algorithm_id,
                        str(e),
                        {"tick_symbol": tick.symbol, "tick_time": tick.time.isoformat()},
                    )
                    # Record in telemetry
                    self._telemetry.record_error(
                        algorithm_id=algorithm_id,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        context={"tick_symbol": tick.symbol},
                    )
                    self._stats["errors"] += 1

        except Exception as e:
            # Critical error (tick parsing, etc.)
            logger.error(f"Critical error processing tick: {e}", exc_info=True)
            self._stats["errors"] += 1

    async def _process_tick_for_algorithm(
        self,
        algorithm_id: UUID,
        tick: EnrichedTick,
    ) -> None:
        """Process a single tick through a specific algorithm.

        Includes hard risk guardrail enforcement before signal generation
        and comprehensive telemetry collection.

        Args:
            algorithm_id: ID of algorithm to process
            tick: Enriched tick data

        Raises:
            Exception: Any error during processing (will be caught upstream)
        """
        start_time = asyncio.get_event_loop().time()

        algorithm = self._lifecycle._algorithm_manager.get_algorithm(algorithm_id)
        if not algorithm:
            return

        # Check if algorithm should process this symbol
        if tick.symbol not in algorithm.symbols:
            return

        # Check data freshness with risk guardrails
        data_fresh, stale_reason = await self._risk.check_data_freshness(
            algorithm_id=algorithm_id,
            data_timestamp=tick.time,
        )
        if not data_fresh:
            logger.warning(f"Algorithm {algorithm_id} blocked: {stale_reason}")
            self._telemetry.record_guardrail_block(algorithm_id, "stale_data", stale_reason)
            return

        # Generate signal (algorithm-specific logic)
        signal = algorithm.process_tick(tick)

        # Record tick processing
        processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        self._telemetry.record_tick_processed(algorithm_id, tick.time, processing_time_ms)

        if signal:
            # Record signal generation in telemetry
            self._telemetry.record_signal(
                algorithm_id=algorithm_id,
                signal_id=str(uuid4()),
                symbol=signal.symbol,
                signal_type=signal.signal_type.value,
                confidence=signal.confidence,
                indicators_used=list(tick.indicators.keys()) if tick.indicators else [],
            )

            # Check hard risk guardrails before publishing
            notional = float(signal.price) * 0.1  # Example position size
            is_allowed, reason = await self._risk.check_order_allowed(
                algorithm_id=algorithm_id,
                symbol=signal.symbol,
                side=signal.signal_type.value,
                quantity=0.1,
                price=float(signal.price),
                notional=notional,
            )

            if not is_allowed:
                logger.warning(f"Signal from {algorithm_id} blocked by guardrail: {reason}")
                self._telemetry.record_guardrail_block(algorithm_id, "guardrail", reason)
                return

            # Check legacy risk rules (backward compatibility)
            is_allowed_old, reason_old = await self._lifecycle.is_order_allowed(
                algorithm_id=algorithm_id,
                order=None,
                current_positions={},
                daily_pnl=0.0,
            )

            if not is_allowed_old:
                logger.warning(f"Signal from {algorithm_id} blocked by lifecycle risk: {reason_old}")
                return

            # Publish signal
            await self._publish_signal(signal)
            self._stats["signals_generated"] += 1

    async def activate_algorithm(self, algorithm_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Activate a algorithm via lifecycle service with audit logging.

        Args:
            algorithm_id: Algorithm to activate
            actor: Who triggered the activation
            **kwargs: Passed to lifecycle service

        Returns:
            True if activation succeeded
        """
        # Register with observability services if not already
        self._telemetry.register_algorithm(algorithm_id)
        self._risk.register_algorithm(algorithm_id)

        success = await self._lifecycle.activate_algorithm(algorithm_id, **kwargs)

        if success and self._audit:
            await self._audit.log_algorithm_lifecycle(
                algorithm_id=algorithm_id,
                transition="activated",
                actor_id=actor,
                new_status="active",
            )

        return success

    async def deactivate_algorithm(self, algorithm_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Deactivate a algorithm via lifecycle service with audit logging.

        Args:
            algorithm_id: Algorithm to deactivate
            actor: Who triggered the deactivation
            **kwargs: Passed to lifecycle service

        Returns:
            True if deactivation succeeded
        """
        success = await self._lifecycle.deactivate_algorithm(algorithm_id, **kwargs)

        if success and self._audit:
            await self._audit.log_algorithm_lifecycle(
                algorithm_id=algorithm_id,
                transition="deactivated",
                actor_id=actor,
                new_status="inactive",
            )

        # Clean up observability
        self._risk.unregister_algorithm(algorithm_id)
        self._telemetry.unregister_algorithm(algorithm_id)

        return success

    async def pause_algorithm(self, algorithm_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Pause a algorithm via lifecycle service with audit logging.

        Args:
            algorithm_id: Algorithm to pause
            actor: Who triggered the pause
            **kwargs: Passed to lifecycle service

        Returns:
            True if pause succeeded
        """
        success = await self._lifecycle.pause_algorithm(algorithm_id, **kwargs)

        if success and self._audit:
            await self._audit.log_algorithm_lifecycle(
                algorithm_id=algorithm_id,
                transition="paused",
                actor_id=actor,
                new_status="paused",
            )

        return success

    async def resume_algorithm(self, algorithm_id: UUID, actor: str = "system", **kwargs) -> bool:
        """Resume a algorithm via lifecycle service with audit logging.

        Args:
            algorithm_id: Algorithm to resume
            actor: Who triggered the resume
            **kwargs: Passed to lifecycle service

        Returns:
            True if resume succeeded
        """
        success = await self._lifecycle.resume_algorithm(algorithm_id, **kwargs)

        if success and self._audit:
            await self._audit.log_algorithm_lifecycle(
                algorithm_id=algorithm_id,
                transition="resumed",
                actor_id=actor,
                new_status="active",
            )

        return success

    async def stop(self) -> None:
        """Stop runner with graceful cancellation of all tasks.

        Ensures all algorithms are properly stopped and Redis is disconnected.
        """
        logger.info("Stopping EnhancedAlgorithmRunner...")

        self._running = False

        # Cancel all algorithm tasks
        for task in self._algorithm_tasks.values():
            if not task.done():
                task.cancel()

        # Wait for tasks to complete (with timeout)
        if self._algorithm_tasks:
            try:
                await asyncio.wait(
                    list(self._algorithm_tasks.values()),
                    timeout=5.0,
                    return_when=asyncio.ALL_COMPLETED,
                )
            except TimeoutError:
                logger.warning("Some algorithm tasks did not complete in time")
            except Exception as e:
                logger.error(f"Error during task cancellation: {e}")

        # Stop all algorithms
        try:
            await self._lifecycle._algorithm_manager.stop_all()
        except Exception as e:
            logger.error(f"Error stopping algorithms: {e}")

        # Disconnect from Redis
        try:
            await self._message_bus.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting from Redis: {e}")

        logger.info("EnhancedAlgorithmRunner stopped")

    def get_runtime_state(self, algorithm_id: UUID) -> AlgorithmInstance | None:
        """Get runtime state for a algorithm."""
        return self._lifecycle._instances.get(algorithm_id)

    def get_all_runtime_states(self) -> list[AlgorithmInstance]:
        """Get runtime states for all algorithms."""
        return list(self._lifecycle._instances.values())
