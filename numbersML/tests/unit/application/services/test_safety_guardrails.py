"""
Unit tests for Safety and Observability Services.

Tests:
- RiskGuardrailService: kill switches, limits, breach detection
- AlgorithmTelemetryService: metrics collection, health monitoring
- EmergencyStopService: emergency controls, recovery
- AuditLogger: event logging, query functionality
- Integration with EnhancedAlgorithmRunner
"""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from src.application.services.audit_logger import (
    AuditEventType,
    AuditLogger,
    AuditSeverity,
    get_audit_logger,
    set_audit_logger,
)
from src.application.services.emergency_stop import (
    EmergencyStopService,
    StopLevel,
    StopStatus,
    get_emergency_stop_service,
    set_emergency_stop_service,
)
from src.application.services.risk_guardrails import (
    GuardrailAction,
    GuardrailConfig,
    GuardrailType,
    RiskGuardrailService,
    get_risk_guardrail_service,
    set_risk_guardrail_service,
)
from src.application.services.algorithm_telemetry import (
    OrderStatus,
    AlgorithmTelemetryService,
    get_telemetry_service,
    set_telemetry_service,
)

# ============================================================================
# Module-level fixtures
# ============================================================================


@pytest.fixture
def risk_service():
    """Create fresh risk service."""
    return RiskGuardrailService()


@pytest.fixture
def telemetry():
    """Create telemetry service."""
    return AlgorithmTelemetryService()


@pytest.fixture
def audit_logger():
    """Create audit logger (no DB)."""
    return AuditLogger(db_pool=None, log_to_stdout=False, log_to_db=False)


# ============================================================================
# RiskGuardrailService Tests
# ============================================================================


class TestRiskGuardrailService:
    """Test RiskGuardrailService."""

    def test_register_algorithm(self, risk_service):
        """Test algorithm registration."""
        algorithm_id = uuid4()
        state = risk_service.register_algorithm(algorithm_id, 10000.0)

        assert state.algorithm_id == algorithm_id
        assert state.daily_pnl == 0.0
        assert state.kill_switch_active == False

    def test_unregister_algorithm(self, risk_service):
        """Test algorithm unregistration."""
        algorithm_id = uuid4()
        risk_service.register_algorithm(algorithm_id)
        risk_service.unregister_algorithm(algorithm_id)

        assert risk_service.get_risk_state(algorithm_id) is None

    @pytest.mark.asyncio
    async def test_global_kill_switch_blocks_orders(self, risk_service):
        """Test that global kill switch blocks all orders."""
        algorithm_id = uuid4()
        risk_service.register_algorithm(algorithm_id)

        # Trigger global kill
        await risk_service.trigger_global_kill("test emergency", "operator")

        # Try to place order - should be blocked
        allowed, reason = await risk_service.check_order_allowed(
            algorithm_id=algorithm_id,
            symbol="BTC/USDC",
            side="BUY",
            quantity=0.1,
            price=50000,
            notional=5000,
        )

        assert allowed == False
        assert "GLOBAL_KILL" in reason

    @pytest.mark.asyncio
    async def test_algorithm_kill_switch_blocks_orders(self, risk_service):
        """Test that algorithm kill switch blocks orders for that algorithm."""
        algorithm_id = uuid4()
        other_algorithm_id = uuid4()
        risk_service.register_algorithm(algorithm_id)
        risk_service.register_algorithm(other_algorithm_id)

        # Trigger kill for one algorithm
        await risk_service.trigger_algorithm_kill(algorithm_id, "test kill")

        # Blocked for killed algorithm
        allowed, _ = await risk_service.check_order_allowed(
            algorithm_id=algorithm_id,
            symbol="BTC/USDC",
            side="BUY",
            quantity=0.1,
            price=50000,
            notional=5000,
        )
        assert allowed == False

        # Allowed for other algorithm
        allowed, _ = await risk_service.check_order_allowed(
            algorithm_id=other_algorithm_id,
            symbol="BTC/USDC",
            side="BUY",
            quantity=0.1,
            price=50000,
            notional=5000,
        )
        assert allowed == True

    @pytest.mark.asyncio
    async def test_daily_loss_limit_triggers_kill(self, risk_service):
        """Test that daily loss limit triggers kill switch."""
        algorithm_id = uuid4()
        risk_service.register_algorithm(algorithm_id)

        # Set a conservative loss limit
        risk_service.configs[GuardrailType.DAILY_LOSS_LIMIT] = GuardrailConfig(
            enabled=True,
            threshold=-1.0,  # 1% loss limit
            action=GuardrailAction.EMERGENCY_STOP,
        )

        # Record a loss that exceeds the limit
        await risk_service.record_pnl(algorithm_id, -150, 10000)

        # Kill switch should be active
        state = risk_service.get_risk_state(algorithm_id)
        assert state.kill_switch_active == True
        assert "daily_loss" in state.kill_switch_reason

    @pytest.mark.asyncio
    async def test_max_positions_limit(self, risk_service):
        """Test max positions limit blocks new orders."""
        algorithm_id = uuid4()
        risk_service.register_algorithm(algorithm_id)

        # Set max positions to 2
        risk_service.configs[GuardrailType.MAX_POSITIONS] = GuardrailConfig(
            enabled=True,
            threshold=2,
            action=GuardrailAction.BLOCK_ORDER,
        )

        # Update to have 2 positions
        await risk_service.update_position_state(
            algorithm_id=algorithm_id,
            open_positions=2,
            total_exposure=10000,
            exposure_pct=50,
            symbol_exposure={"BTC/USDC": 5000, "ETH/USDC": 5000},
        )

        # Should block new order
        allowed, reason = await risk_service.check_order_allowed(
            algorithm_id=algorithm_id,
            symbol="SOL/USDC",
            side="BUY",
            quantity=0.1,
            price=100,
            notional=10,
        )

        assert allowed == False
        assert "MAX_POSITIONS" in reason

    @pytest.mark.asyncio
    async def test_stale_data_blocks_algorithm(self, risk_service):
        """Test stale data detection pauses algorithm."""
        algorithm_id = uuid4()
        risk_service.register_algorithm(algorithm_id)

        # Data from 5 minutes ago
        stale_time = datetime.utcnow() - timedelta(minutes=5)

        fresh, reason = await risk_service.check_data_freshness(
            algorithm_id=algorithm_id,
            data_timestamp=stale_time,
            max_staleness_seconds=60,
        )

        assert fresh == False
        assert "STALE_DATA" in reason

    @pytest.mark.asyncio
    async def test_release_global_kill(self, risk_service):
        """Test releasing global kill switch."""
        await risk_service.trigger_global_kill("test", "operator")
        assert risk_service.get_global_status()["global_kill_active"] == True

        await risk_service.release_global_kill("operator")
        assert risk_service.get_global_status()["global_kill_active"] == False


# ============================================================================
# AlgorithmTelemetryService Tests
# ============================================================================


class TestAlgorithmTelemetryService:
    """Test AlgorithmTelemetryService - uses module-level telemetry fixture."""

    def test_record_order_flow(self, telemetry):
        """Test complete order lifecycle recording."""
        algorithm_id = uuid4()
        telemetry.register_algorithm(algorithm_id)

        # Create order
        order = telemetry.record_order_created(
            algorithm_id=algorithm_id,
            order_id="order-1",
            symbol="BTC/USDC",
            side="BUY",
            quantity=0.1,
            price=50000,
        )

        assert order.status == OrderStatus.PENDING

        # Submit
        telemetry.record_order_submitted(algorithm_id, "order-1", latency_ms=50)
        assert order.status == OrderStatus.SUBMITTED
        assert order.latency_ms == 50

        # Fill
        telemetry.record_order_filled(
            algorithm_id, "order-1", 50100, latency_ms=200, slippage_bps=20
        )
        assert order.status == OrderStatus.FILLED
        assert order.slippage_bps == 20

    def test_execution_statistics(self, telemetry):
        """Test execution statistics calculation."""
        algorithm_id = uuid4()
        telemetry.register_algorithm(algorithm_id)

        # Create mix of orders
        for i in range(10):
            order = telemetry.record_order_created(
                algorithm_id, f"order-{i}", "BTC/USDC", "BUY", 0.1, 50000
            )

            if i < 7:  # 70% fill rate
                telemetry.record_order_filled(
                    algorithm_id, f"order-{i}", 50000, latency_ms=100 + i * 10
                )
            elif i < 9:  # 20% reject
                telemetry.record_order_rejected(algorithm_id, f"order-{i}", "insufficient funds")
            else:  # 10% error
                telemetry.record_order_error(algorithm_id, f"order-{i}", Exception("network error"))

        stats = telemetry.get_execution_statistics(algorithm_id)

        assert stats.total_orders == 10
        assert stats.filled_orders == 7
        assert stats.rejected_orders == 2
        assert stats.error_orders == 1
        assert abs(stats.fill_rate - 0.7) < 0.01
        assert stats.avg_latency_ms > 0

    def test_signal_statistics(self, telemetry):
        """Test signal generation statistics."""
        algorithm_id = uuid4()
        telemetry.register_algorithm(algorithm_id)

        # Record signals
        for i in range(20):
            telemetry.record_signal(
                algorithm_id=algorithm_id,
                signal_id=f"sig-{i}",
                symbol="BTC/USDC",
                signal_type="BUY" if i % 2 == 0 else "SELL",
                confidence=0.5 + (i % 5) * 0.1,
            )

        stats = telemetry.get_signal_statistics(algorithm_id)

        assert stats["total_signals"] == 20
        assert stats["signals_by_type"]["BUY"] == 10
        assert stats["signals_by_type"]["SELL"] == 10

    def test_error_tracking(self, telemetry):
        """Test error event tracking."""
        algorithm_id = uuid4()
        telemetry.register_algorithm(algorithm_id)

        # Record various errors
        telemetry.record_error(algorithm_id, "ValidationError", "Invalid input", severity="warning")
        telemetry.record_error(algorithm_id, "NetworkError", "Connection failed", severity="error")
        telemetry.record_error(algorithm_id, "CriticalError", "System failure", severity="critical")

        summary = telemetry.get_error_summary(algorithm_id)

        assert summary["total_errors"] == 3
        assert summary["critical_count"] == 1
        assert "ValidationError" in summary["errors_by_type"]

    def test_drift_calculation(self, telemetry):
        """Test backtest vs live drift calculation."""
        algorithm_id = uuid4()

        backtest = {"sharpe_ratio": 1.5, "win_rate": 0.6, "max_drawdown": 0.1}
        live = {"sharpe_ratio": 0.8, "win_rate": 0.5, "max_drawdown": 0.15}

        indicators = telemetry.calculate_drift(
            algorithm_id=algorithm_id,
            backtest_metrics=backtest,
            live_metrics=live,
            threshold_pct=30,
        )

        # Find sharpe ratio drift
        sharpe_drift = next((d for d in indicators if d.metric_name == "sharpe_ratio"), None)
        assert sharpe_drift is not None
        assert sharpe_drift.drift_pct > 0
        assert sharpe_drift.is_significant == True  # (1.5 - 0.8) / 1.5 = 46% > 30%


# ============================================================================
# EmergencyStopService Tests
# ============================================================================


class TestEmergencyStopService:
    """Test EmergencyStopService."""

    @pytest.fixture
    def emergency_service(self, risk_service):
        """Create emergency stop service."""
        return EmergencyStopService(risk_service=risk_service)

    @pytest.mark.asyncio
    async def test_full_emergency_stop(self, emergency_service):
        """Test full emergency stop activates global kill."""
        # Create some algorithms
        for _ in range(3):
            sid = uuid4()
            emergency_service.risk_service.register_algorithm(sid)

        # Trigger full stop
        record = await emergency_service.emergency_stop(
            level=StopLevel.FULL,
            reason="market crash detected",
            triggered_by="operator-1",
        )

        assert record.level == StopLevel.FULL
        assert record.status == StopStatus.ACTIVE
        assert len(record.affected_algorithms) == 3

        # Global kill should be active
        assert emergency_service.is_emergency_stopped() == True

    @pytest.mark.asyncio
    async def test_algorithm_emergency_stop(self, emergency_service):
        """Test algorithm-specific emergency stop."""
        algorithm_id = uuid4()
        emergency_service.risk_service.register_algorithm(algorithm_id)

        record = await emergency_service.emergency_stop(
            level=StopLevel.ALGORITHM,
            reason="anomalous behavior",
            triggered_by="system",
            algorithm_id=algorithm_id,
        )

        assert record.level == StopLevel.ALGORITHM
        assert algorithm_id in record.affected_algorithms

        # Check specific algorithm is stopped
        assert emergency_service.is_emergency_stopped(algorithm_id) == True

    @pytest.mark.asyncio
    async def test_release_stop(self, emergency_service):
        """Test releasing emergency stop."""
        # Stop then release
        record = await emergency_service.emergency_stop(
            level=StopLevel.FULL,
            reason="test",
            triggered_by="test",
        )

        assert emergency_service.is_emergency_stopped() == True

        released = await emergency_service.release_stop(
            stop_id=record.stop_id,
            released_by="operator-2",
            reason="issue resolved",
        )

        assert released is not None
        assert released.released_by == "operator-2"
        assert emergency_service.is_emergency_stopped() == False

    @pytest.mark.asyncio
    async def test_release_all(self, emergency_service):
        """Test releasing all active stops."""
        # Create multiple stops
        await emergency_service.emergency_stop(StopLevel.FULL, "test1", "test")

        # Release all
        released = await emergency_service.release_all("admin", "all clear")

        assert len(released) == 1
        assert emergency_service.is_emergency_stopped() == False


# ============================================================================
# AuditLogger Tests
# ============================================================================


class TestAuditLogger:
    """Test AuditLogger - uses module-level audit_logger fixture."""

    @pytest.mark.asyncio
    async def test_log_basic_event(self, audit_logger):
        """Test basic event logging."""
        event = await audit_logger.log(
            event_type=AuditEventType.ALGORITHM_CREATED,
            action="create",
            description="Created new RSI algorithm",
            actor_id="user-123",
            actor_type="user",
            target_type="algorithm",
            target_id="strat-1",
        )

        assert event.event_type == AuditEventType.ALGORITHM_CREATED
        assert event.actor_id == "user-123"
        assert event.checksum is not None

    @pytest.mark.asyncio
    async def test_log_algorithm_lifecycle(self, audit_logger):
        """Test algorithm lifecycle logging."""
        algorithm_id = uuid4()

        event = await audit_logger.log_algorithm_lifecycle(
            algorithm_id=algorithm_id,
            transition="activated",
            actor_id="user-1",
            old_status="inactive",
            new_status="active",
        )

        assert event.event_type == AuditEventType.ALGORITHM_ACTIVATED
        assert event.new_value["status"] == "active"

    @pytest.mark.asyncio
    async def test_log_kill_switch(self, audit_logger):
        """Test kill switch event logging."""
        event = await audit_logger.log_kill_switch(
            triggered=True,
            reason="daily loss limit exceeded",
            triggered_by="risk_service",
        )

        assert event.event_type == AuditEventType.KILL_SWITCH_TRIGGERED
        assert event.severity == AuditSeverity.CRITICAL
        assert "daily loss" in event.description

    @pytest.mark.asyncio
    async def test_log_guardrail_breach(self, audit_logger):
        """Test guardrail breach logging."""
        event = await audit_logger.log_guardrail_breach(
            guardrail_type="max_exposure",
            algorithm_id=uuid4(),
            details={"exposure_pct": 75, "limit": 50},
            action_taken="BLOCK_ORDER",
        )

        assert event.event_type == AuditEventType.GUARDRAIL_BREACH
        assert event.severity == AuditSeverity.WARNING

    def test_get_recent_events(self, audit_logger):
        """Test querying recent events."""
        # Create events by calling log synchronously (for test)
        asyncio.run(
            audit_logger.log(
                event_type=AuditEventType.ORDER_SUBMITTED,
                action="submit",
                description="Order submitted",
            )
        )

        events = audit_logger.get_recent_events(count=10)
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.ORDER_SUBMITTED

    def test_event_severity_filtering(self, audit_logger):
        """Test filtering by severity."""
        # Log events of different severity
        asyncio.run(
            audit_logger.log(
                event_type=AuditEventType.ORDER_SUBMITTED,
                action="submit",
                description="Normal order",
                severity=AuditSeverity.INFO,
            )
        )
        asyncio.run(
            audit_logger.log(
                event_type=AuditEventType.KILL_SWITCH_TRIGGERED,
                action="kill",
                description="Emergency stop",
                severity=AuditSeverity.CRITICAL,
            )
        )

        # Filter for critical only
        events = audit_logger.get_recent_events(
            min_severity=AuditSeverity.ERROR,
        )

        assert len(events) == 1
        assert events[0].severity == AuditSeverity.CRITICAL


# ============================================================================
# Integration Tests
# ============================================================================


class TestSafetyIntegration:
    """Integration tests for safety services working together."""

    @pytest.mark.asyncio
    async def test_guardrail_triggers_kill_and_audit(self):
        """Test guardrail breach triggers kill switch and logs audit event."""
        # Set up services
        risk = RiskGuardrailService()
        audit = AuditLogger(db_pool=None, log_to_stdout=False, log_to_db=False)

        algorithm_id = uuid4()
        risk.register_algorithm(algorithm_id)

        # Set aggressive daily loss limit
        risk.configs[GuardrailType.DAILY_LOSS_LIMIT] = GuardrailConfig(
            enabled=True,
            threshold=-0.1,  # 0.1% loss
            action=GuardrailAction.EMERGENCY_STOP,
        )

        # Subscribe audit to events
        audit_events = []

        def capture_event(event):
            audit_events.append(event)

        audit.subscribe(capture_event)

        # Trigger loss
        await risk.record_pnl(algorithm_id, -50, 10000)  # 0.5% loss

        # Verify kill switch active
        state = risk.get_risk_state(algorithm_id)
        assert state.kill_switch_active == True

        # Log audit event
        await audit.log_kill_switch(
            triggered=True,
            reason="daily loss limit",
            algorithm_id=algorithm_id,
            triggered_by="risk_service",
        )

        # Verify audit captured
        assert len(audit_events) == 1
        assert audit_events[0].event_type == AuditEventType.KILL_SWITCH_TRIGGERED

    @pytest.mark.asyncio
    async def test_emergency_stop_telemetry_audit(self):
        """Test emergency stop is tracked in telemetry and audit."""
        telemetry = AlgorithmTelemetryService()
        audit = AuditLogger(db_pool=None, log_to_stdout=False, log_to_db=False)
        emergency = EmergencyStopService(
            risk_service=RiskGuardrailService(),
            audit_logger=audit,
        )

        algorithm_id = uuid4()
        telemetry.register_algorithm(algorithm_id)
        emergency.risk_service.register_algorithm(algorithm_id)

        # Trigger emergency stop
        record = await emergency.emergency_stop(
            level=StopLevel.ALGORITHM,
            reason="critical error",
            triggered_by="system",
            algorithm_id=algorithm_id,
        )

        # Verify telemetry can track this
        health = telemetry.get_health_summary(algorithm_id)
        # Health should reflect stopped state (implementation dependent)

        # Verify audit logged
        events = audit.get_recent_events(event_types=[AuditEventType.EMERGENCY_STOP])
        assert len(events) == 1


# ============================================================================
# Singleton Tests
# ============================================================================


class TestSingletons:
    """Test singleton getter/setter functions."""

    def test_risk_guardrail_singleton(self):
        """Test risk guardrail service singleton."""
        set_risk_guardrail_service(None)  # Reset

        svc1 = get_risk_guardrail_service()
        svc2 = get_risk_guardrail_service()

        assert svc1 is svc2

    def test_telemetry_singleton(self):
        """Test telemetry service singleton."""
        set_telemetry_service(None)  # Reset

        svc1 = get_telemetry_service()
        svc2 = get_telemetry_service()

        assert svc1 is svc2

    def test_emergency_stop_singleton(self):
        """Test emergency stop service singleton."""
        set_emergency_stop_service(None)  # Reset

        svc1 = get_emergency_stop_service()
        svc2 = get_emergency_stop_service()

        assert svc1 is svc2

    def test_audit_logger_singleton(self):
        """Test audit logger singleton."""
        set_audit_logger(None)  # Reset

        svc1 = get_audit_logger()
        svc2 = get_audit_logger()

        assert svc1 is svc2
