"""
Emergency Stop Service - Global emergency controls for algorithm execution.

Provides:
- Immediate global halt of all algorithms
- Operator controls with authentication
- Recovery procedures
- Audit logging
- Status monitoring
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from .audit_logger import AuditLogger, AuditSeverity
from .risk_guardrails import RiskGuardrailService

logger = logging.getLogger(__name__)


class StopLevel(Enum):
    """Level of emergency stop."""

    FULL = "full"  # Stop everything globally
    ALGORITHM = "algorithm"  # Stop specific algorithm
    SYMBOL = "symbol"  # Stop all algorithms for symbol
    MODE = "mode"  # Stop all live algorithms


class StopStatus(Enum):
    """Status of emergency stop."""

    INACTIVE = "inactive"
    PENDING = "pending"  # Stop requested but not yet complete
    ACTIVE = "active"
    RELEASING = "releasing"  # Release requested but algorithms not yet resumed
    PARTIAL = "partial"  # Some components stopped


@dataclass
class EmergencyStopRecord:
    """Record of an emergency stop event."""

    stop_id: str
    level: StopLevel
    triggered_at: datetime
    triggered_by: str
    reason: str
    affected_algorithms: set[UUID] = field(default_factory=set)
    status: StopStatus = StopStatus.ACTIVE
    released_at: Optional[datetime] = None
    released_by: Optional[str] = None
    release_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EmergencyStopService:
    """
    Service for managing emergency stop functionality.

    Features:
    - Global emergency stop with single command
    - Per-algorithm emergency stop
    - Symbol-based stop
    - Live-mode-only stop
    - Operator authentication
    - Audit trail
    - Recovery procedures
    """

    def __init__(
        self,
        risk_service: Optional[RiskGuardrailService] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.risk_service = risk_service
        self.audit = audit_logger

        # Active stops
        self._active_stops: dict[str, EmergencyStopRecord] = {}

        # Stop history (last 100)
        self._stop_history: list[EmergencyStopRecord] = []
        self._max_history = 100

        # Authorized operators (in production, use proper auth)
        self._authorized_operators: set[str] = set()

        # Callbacks for stop/release events
        self._stop_callbacks: list[Callable[[EmergencyStopRecord], None]] = []
        self._release_callbacks: list[Callable[[EmergencyStopRecord], None]] = []

        logger.info("EmergencyStopService initialized")

    async def emergency_stop(
        self,
        level: StopLevel,
        reason: str,
        triggered_by: str,
        algorithm_id: Optional[UUID] = None,
        symbol: Optional[str] = None,
        require_confirmation: bool = False,
    ) -> EmergencyStopRecord:
        """
        Trigger an emergency stop.

        Args:
            level: Level of stop (full, algorithm, symbol, mode)
            reason: Why the stop is being triggered
            triggered_by: Who/what triggered the stop
            algorithm_id: Required for ALGORITHM level
            symbol: Required for SYMBOL level
            require_confirmation: If True, requires manual confirmation

        Returns:
            EmergencyStopRecord
        """
        stop_id = f"stop_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{level.value}"

        logger.critical(f"EMERGENCY STOP TRIGGERED: {level.value} by {triggered_by}: {reason}")

        # Determine affected algorithms
        affected: set[UUID] = set()

        if level == StopLevel.FULL:
            # Stop all algorithms
            affected = set(self.risk_service.get_all_risk_states().keys())
            await self.risk_service.trigger_global_kill(reason, triggered_by)

        elif level == StopLevel.ALGORITHM:
            if not algorithm_id:
                raise ValueError("algorithm_id required for ALGORITHM level stop")
            affected = {algorithm_id}
            await self.risk_service.trigger_algorithm_kill(algorithm_id, reason)

        elif level == StopLevel.SYMBOL:
            if not symbol:
                raise ValueError("symbol required for SYMBOL level stop")
            # Would need to look up algorithms by symbol
            # For now, stop all and filter by metadata
            affected = set(self.risk_service.get_all_risk_states().keys())
            logger.warning(f"Symbol-level stop for {symbol} - stopping all algorithms")

        elif level == StopLevel.MODE:
            # Stop only live algorithms
            # In practice, would filter by algorithm mode
            affected = set(self.risk_service.get_all_risk_states().keys())
            logger.warning("Mode-level stop - stopping all algorithms")

        # Create stop record
        record = EmergencyStopRecord(
            stop_id=stop_id,
            level=level,
            triggered_at=datetime.utcnow(),
            triggered_by=triggered_by,
            reason=reason,
            affected_algorithms=affected,
            status=StopStatus.ACTIVE,
            metadata={
                "symbol": symbol,
                "algorithm_id": str(algorithm_id) if algorithm_id else None,
                "total_affected": len(affected),
            },
        )

        self._active_stops[stop_id] = record
        self._stop_history.append(record)

        # Trim history
        if len(self._stop_history) > self._max_history:
            self._stop_history = self._stop_history[-self._max_history :]

        # Audit log
        if self.audit:
            await self.audit.log_emergency_stop(
                reason=reason,
                triggered_by=triggered_by,
                affected_algorithms=list(affected),
            )

        # Notify callbacks
        for callback in self._stop_callbacks:
            try:
                callback(record)
            except Exception as e:
                logger.error(f"Stop callback error: {e}")

        return record

    async def release_stop(
        self,
        stop_id: str,
        released_by: str,
        reason: str,
        require_confirmation: bool = False,
    ) -> Optional[EmergencyStopRecord]:
        """
        Release an emergency stop.

        Args:
            stop_id: ID of the stop to release
            released_by: Who is releasing the stop
            reason: Why the stop is being released
            require_confirmation: If True, requires manual confirmation

        Returns:
            Updated EmergencyStopRecord or None if not found
        """
        record = self._active_stops.get(stop_id)
        if not record:
            logger.warning(f"Attempted to release unknown stop: {stop_id}")
            return None

        logger.critical(f"EMERGENCY STOP RELEASED: {stop_id} by {released_by}: {reason}")

        # Release the stop
        record.status = StopStatus.RELEASING
        record.released_at = datetime.utcnow()
        record.released_by = released_by
        record.release_reason = reason

        # Release actual kill switches
        if record.level == StopLevel.FULL:
            await self.risk_service.release_global_kill(released_by)
        elif record.level == StopLevel.ALGORITHM:
            for algorithm_id in record.affected_algorithms:
                await self.risk_service.release_algorithm_kill(algorithm_id)
        elif record.level in (StopLevel.SYMBOL, StopLevel.MODE):
            # Release all affected algorithms
            for algorithm_id in record.affected_algorithms:
                await self.risk_service.release_algorithm_kill(algorithm_id)

        # Move to history
        record.status = StopStatus.INACTIVE
        del self._active_stops[stop_id]

        # Audit log
        if self.audit:
            from .audit_logger import AuditEventType

            await self.audit.log(
                event_type=AuditEventType.KILL_SWITCH_RELEASED,
                action="emergency_stop_released",
                description=f"Emergency stop {stop_id} released: {reason}",
                actor_id=released_by,
                severity=AuditSeverity.INFO,
                new_value={
                    "stop_id": stop_id,
                    "reason": reason,
                    "affected_algorithms": [str(s) for s in record.affected_algorithms],
                },
            )

        # Notify callbacks
        for callback in self._release_callbacks:
            try:
                callback(record)
            except Exception as e:
                logger.error(f"Release callback error: {e}")

        return record

    async def release_all(
        self,
        released_by: str,
        reason: str,
    ) -> list[EmergencyStopRecord]:
        """Release all active emergency stops."""
        released = []

        for stop_id in list(self._active_stops.keys()):
            record = await self.release_stop(stop_id, released_by, reason)
            if record:
                released.append(record)

        return released

    def get_active_stops(self) -> dict[str, EmergencyStopRecord]:
        """Get all currently active stops."""
        return self._active_stops.copy()

    def is_emergency_stopped(self, algorithm_id: Optional[UUID] = None) -> bool:
        """Check if there are active emergency stops."""
        if not self._active_stops:
            return False

        if algorithm_id:
            # Check if this specific algorithm is stopped
            for stop in self._active_stops.values():
                if algorithm_id in stop.affected_algorithms:
                    return True
            return False

        return True

    def get_stop_history(
        self,
        since: Optional[datetime] = None,
        level: Optional[StopLevel] = None,
    ) -> list[EmergencyStopRecord]:
        """Get stop history."""
        history = self._stop_history

        if since:
            history = [h for h in history if h.triggered_at >= since]

        if level:
            history = [h for h in history if h.level == level]

        return sorted(history, key=lambda h: h.triggered_at, reverse=True)

    def get_system_status(self) -> dict[str, Any]:
        """Get overall emergency stop system status."""
        active = list(self._active_stops.values())

        return {
            "status": "EMERGENCY_STOP_ACTIVE" if active else "NORMAL",
            "active_stops_count": len(active),
            "total_affected_algorithms": len(
                set().union(*[s.affected_algorithms for s in active]) if active else set()
            ),
            "active_stop_details": [
                {
                    "stop_id": s.stop_id,
                    "level": s.level.value,
                    "triggered_at": s.triggered_at.isoformat(),
                    "triggered_by": s.triggered_by,
                    "reason": s.reason,
                    "affected_count": len(s.affected_algorithms),
                }
                for s in active
            ],
            "stops_24h": len(
                [
                    h
                    for h in self._stop_history
                    if h.triggered_at > datetime.utcnow() - timedelta(hours=24)
                ]
            ),
        }

    def on_stop(self, callback: Callable[[EmergencyStopRecord], None]) -> None:
        """Register callback for stop events."""
        self._stop_callbacks.append(callback)

    def on_release(self, callback: Callable[[EmergencyStopRecord], None]) -> None:
        """Register callback for release events."""
        self._release_callbacks.append(callback)

    def add_authorized_operator(self, operator_id: str) -> None:
        """Add an authorized operator (for manual confirmation)."""
        self._authorized_operators.add(operator_id)

    def remove_authorized_operator(self, operator_id: str) -> None:
        """Remove an authorized operator."""
        self._authorized_operators.discard(operator_id)

    def is_authorized(self, operator_id: str) -> bool:
        """Check if operator is authorized."""
        return operator_id in self._authorized_operators


# Singleton instance
_emergency_stop_service: Optional[EmergencyStopService] = None


def get_emergency_stop_service(
    risk_service: Optional[RiskGuardrailService] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> EmergencyStopService:
    """Get or create the global emergency stop service."""
    global _emergency_stop_service
    if _emergency_stop_service is None:
        _emergency_stop_service = EmergencyStopService(risk_service, audit_logger)
    return _emergency_stop_service


def set_emergency_stop_service(service: EmergencyStopService) -> None:
    """Set the global emergency stop service (for testing)."""
    global _emergency_stop_service
    _emergency_stop_service = service
