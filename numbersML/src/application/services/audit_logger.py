"""
Audit Logger Service - Comprehensive audit trail for all critical actions.

Provides:
- Config change tracking
- Lifecycle event logging
- Risk guardrail trigger events
- Immutable audit records
- Queryable audit history
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from uuid import UUID

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    # Config changes
    CONFIG_CREATED = "config_created"
    CONFIG_UPDATED = "config_updated"
    CONFIG_VERSION_CREATED = "config_version_created"
    CONFIG_ACTIVATED = "config_activated"
    
    # Lifecycle
    STRATEGY_CREATED = "strategy_created"
    STRATEGY_DELETED = "strategy_deleted"
    STRATEGY_UPDATED = "strategy_updated"
    STRATEGY_ACTIVATED = "strategy_activated"
    STRATEGY_DEACTIVATED = "strategy_deactivated"
    STRATEGY_PAUSED = "strategy_paused"
    STRATEGY_RESUMED = "strategy_resumed"
    
    # Risk
    GUARDRAIL_BREACH = "guardrail_breach"
    KILL_SWITCH_TRIGGERED = "kill_switch_triggered"
    KILL_SWITCH_RELEASED = "kill_switch_released"
    EMERGENCY_STOP = "emergency_stop"
    
    # Orders
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_ERROR = "order_error"
    
    # Backtest
    BACKTEST_STARTED = "backtest_started"
    BACKTEST_COMPLETED = "backtest_completed"
    BACKTEST_FAILED = "backtest_failed"
    
    # LLM
    LLM_GENERATE_REQUEST = "llm_generate_request"
    LLM_MODIFY_REQUEST = "llm_modify_request"
    LLM_CONFIG_APPLIED = "llm_config_applied"
    
    # System
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    ERROR_RECOVERED = "error_recovered"


class AuditSeverity(Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Immutable audit event record."""
    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    
    # Actor information
    actor_id: str  # user, system, strategy, etc.
    actor_type: str  # user, system, strategy, service
    
    # Target information
    target_type: str  # strategy, config, order, system
    
    # Event details (required)
    action: str
    description: str
    
    # Target ID (optional but needed early for dataclass ordering)
    target_id: Optional[str] = None
    
    # Event details (optional)
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    
    # Context
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Integrity
    checksum: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "action": self.action,
            "description": self.description,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "session_id": self.session_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "metadata": self.metadata,
            "checksum": self.checksum,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """
    Service for logging and querying audit events.
    
    Features:
    - Immutable audit records
    - Structured logging
    - Database persistence
    - Query interface
    - Event streaming
    """
    
    def __init__(
        self,
        db_pool=None,
        log_to_stdout: bool = True,
        log_to_db: bool = True,
        max_memory_buffer: int = 10000,
    ) -> None:
        self.db_pool = db_pool
        self.log_to_stdout = log_to_stdout
        self.log_to_db = log_to_db
        self.max_memory_buffer = max_memory_buffer
        
        # In-memory buffer for recent events
        self._event_buffer: List[AuditEvent] = []
        
        # Event subscribers
        self._subscribers: List[Callable[[AuditEvent], None]] = []
        
        # Background flush task
        self._flush_task: Optional[asyncio.Task] = None
        
        logger.info("AuditLogger initialized")
    
    async def start(self) -> None:
        """Start background tasks."""
        if self.log_to_db and self.db_pool:
            self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("AuditLogger started")
    
    async def stop(self) -> None:
        """Stop background tasks and flush remaining events."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining events
        if self._event_buffer:
            await self._flush_to_db()
        
        logger.info("AuditLogger stopped")
    
    async def log(
        self,
        event_type: AuditEventType,
        action: str,
        description: str,
        actor_id: str = "system",
        actor_type: str = "system",
        target_type: str = "system",
        target_id: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event
            action: Short action name
            description: Human-readable description
            actor_id: Who performed the action
            actor_type: Type of actor (user, system, strategy)
            target_type: Type of target (strategy, config, order)
            target_id: ID of target object
            severity: Event severity
            old_value: Previous state (for changes)
            new_value: New state (for changes)
            session_id: Session identifier
            metadata: Additional context
            
        Returns:
            The created audit event
        """
        import hashlib
        import uuid
        
        event_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()
        
        # Create event
        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type,
            severity=severity,
            actor_id=actor_id,
            actor_type=actor_type,
            target_type=target_type,
            target_id=target_id,
            action=action,
            description=description,
            old_value=old_value,
            new_value=new_value,
            session_id=session_id,
            metadata=metadata or {},
        )
        
        # Calculate checksum for integrity
        event_data = f"{event_id}:{timestamp.isoformat()}:{event_type.value}:{target_id}"
        event.checksum = hashlib.sha256(event_data.encode()).hexdigest()[:16]
        
        # Add to buffer
        self._event_buffer.append(event)
        
        # Trim buffer if needed
        if len(self._event_buffer) > self.max_memory_buffer:
            self._event_buffer = self._event_buffer[-self.max_memory_buffer:]
        
        # Log to stdout
        if self.log_to_stdout:
            self._log_to_stdout(event)
        
        # Notify subscribers
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception as e:
                logger.error(f"Audit subscriber error: {e}")
        
        # Critical events flush immediately
        if severity in (AuditSeverity.ERROR, AuditSeverity.CRITICAL):
            if self.db_pool:
                await self._flush_single_event(event)
        
        return event
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    async def log_strategy_lifecycle(
        self,
        strategy_id: UUID,
        transition: str,  # activated, deactivated, paused, resumed
        actor_id: str = "system",
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
    ) -> AuditEvent:
        """Log strategy lifecycle event."""
        event_type_map = {
            "activated": AuditEventType.STRATEGY_ACTIVATED,
            "deactivated": AuditEventType.STRATEGY_DEACTIVATED,
            "paused": AuditEventType.STRATEGY_PAUSED,
            "resumed": AuditEventType.STRATEGY_RESUMED,
        }
        
        event_type = event_type_map.get(transition, AuditEventType.STRATEGY_UPDATED)
        
        return await self.log(
            event_type=event_type,
            action=f"strategy_{transition}",
            description=f"Strategy {strategy_id} {transition}",
            actor_id=actor_id,
            target_type="strategy",
            target_id=str(strategy_id),
            severity=AuditSeverity.INFO,
            old_value={"status": old_status} if old_status else None,
            new_value={"status": new_status} if new_status else None,
        )
    
    async def log_config_change(
        self,
        strategy_id: UUID,
        version: int,
        actor_id: str,
        old_config: Optional[Dict[str, Any]],
        new_config: Dict[str, Any],
        change_summary: str,
    ) -> AuditEvent:
        """Log configuration change."""
        return await self.log(
            event_type=AuditEventType.CONFIG_UPDATED,
            action="config_update",
            description=f"Config updated: {change_summary}",
            actor_id=actor_id,
            target_type="config",
            target_id=str(strategy_id),
            severity=AuditSeverity.INFO,
            old_value={"version": version - 1, "config": old_config} if old_config else None,
            new_value={"version": version, "config": new_config},
        )
    
    async def log_guardrail_breach(
        self,
        guardrail_type: str,
        strategy_id: Optional[UUID],
        details: Dict[str, Any],
        action_taken: str,
    ) -> AuditEvent:
        """Log guardrail breach event."""
        return await self.log(
            event_type=AuditEventType.GUARDRAIL_BREACH,
            action="guardrail_breach",
            description=f"Guardrail {guardrail_type} breached: {action_taken}",
            actor_id="risk_guardrail",
            target_type="strategy" if strategy_id else "system",
            target_id=str(strategy_id) if strategy_id else None,
            severity=AuditSeverity.WARNING,
            new_value={
                "guardrail_type": guardrail_type,
                "action_taken": action_taken,
                "details": details,
            },
        )
    
    async def log_kill_switch(
        self,
        triggered: bool,
        reason: str,
        strategy_id: Optional[UUID] = None,
        triggered_by: str = "system",
    ) -> AuditEvent:
        """Log kill switch activation/release."""
        event_type = (
            AuditEventType.KILL_SWITCH_TRIGGERED if triggered
            else AuditEventType.KILL_SWITCH_RELEASED
        )
        
        return await self.log(
            event_type=event_type,
            action="kill_switch_triggered" if triggered else "kill_switch_released",
            description=f"Kill switch {'activated' if triggered else 'released'}: {reason}",
            actor_id=triggered_by,
            target_type="strategy" if strategy_id else "system",
            target_id=str(strategy_id) if strategy_id else None,
            severity=AuditSeverity.CRITICAL if triggered else AuditSeverity.INFO,
            new_value={"reason": reason},
        )
    
    async def log_emergency_stop(
        self,
        reason: str,
        triggered_by: str,
        affected_strategies: List[UUID],
    ) -> AuditEvent:
        """Log emergency stop event."""
        return await self.log(
            event_type=AuditEventType.EMERGENCY_STOP,
            action="emergency_stop",
            description=f"EMERGENCY STOP: {reason}",
            actor_id=triggered_by,
            target_type="system",
            severity=AuditSeverity.CRITICAL,
            new_value={
                "reason": reason,
                "affected_strategies": [str(s) for s in affected_strategies],
                "strategy_count": len(affected_strategies),
            },
        )
    
    async def log_order_event(
        self,
        order_id: str,
        strategy_id: UUID,
        symbol: str,
        side: str,
        quantity: float,
        event_subtype: str,  # submitted, filled, rejected, cancelled, error
        price: Optional[float] = None,
        error_message: Optional[str] = None,
        actor_id: str = "system",
    ) -> AuditEvent:
        """Log order event."""
        event_type_map = {
            "submitted": AuditEventType.ORDER_SUBMITTED,
            "filled": AuditEventType.ORDER_FILLED,
            "rejected": AuditEventType.ORDER_REJECTED,
            "cancelled": AuditEventType.ORDER_CANCELLED,
            "error": AuditEventType.ORDER_ERROR,
        }
        
        event_type = event_type_map.get(event_subtype, AuditEventType.ORDER_ERROR)
        severity = AuditSeverity.ERROR if event_subtype in ("rejected", "error") else AuditSeverity.INFO
        
        return await self.log(
            event_type=event_type,
            action=f"order_{event_subtype}",
            description=f"Order {order_id} {event_subtype}: {side} {quantity} {symbol}",
            actor_id=actor_id,
            target_type="order",
            target_id=order_id,
            severity=severity,
            new_value={
                "order_id": order_id,
                "strategy_id": str(strategy_id),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "error_message": error_message,
            },
        )
    
    async def log_llm_request(
        self,
        request_type: str,  # generate, modify, suggest
        strategy_id: Optional[UUID],
        actor_id: str,
        prompt_length: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log LLM request event."""
        event_type = (
            AuditEventType.LLM_GENERATE_REQUEST if request_type == "generate"
            else AuditEventType.LLM_MODIFY_REQUEST
        )
        
        return await self.log(
            event_type=event_type,
            action=f"llm_{request_type}",
            description=f"LLM {request_type} request from {actor_id}",
            actor_id=actor_id,
            target_type="strategy" if strategy_id else "system",
            target_id=str(strategy_id) if strategy_id else None,
            severity=AuditSeverity.INFO,
            metadata={
                "prompt_length": prompt_length,
                **(metadata or {}),
            },
        )
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_recent_events(
        self,
        count: int = 100,
        event_types: Optional[List[AuditEventType]] = None,
        target_id: Optional[str] = None,
        min_severity: Optional[AuditSeverity] = None,
    ) -> List[AuditEvent]:
        """Get recent events from memory buffer."""
        events = list(self._event_buffer)
        
        # Filter
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        
        if target_id:
            events = [e for e in events if e.target_id == target_id]
        
        if min_severity:
            severity_order = [AuditSeverity.INFO, AuditSeverity.WARNING, AuditSeverity.ERROR, AuditSeverity.CRITICAL]
            min_idx = severity_order.index(min_severity)
            allowed = severity_order[min_idx:]
            events = [e for e in events if e.severity in allowed]
        
        # Return most recent
        return sorted(events, key=lambda e: e.timestamp, reverse=True)[:count]
    
    async def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        target_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Query events from database."""
        if not self.db_pool:
            return []
        
        # Build query
        conditions = ["1=1"]
        params = []
        
        if start_time:
            conditions.append("timestamp >= $1")
            params.append(start_time)
        
        if end_time:
            conditions.append("timestamp <= $2")
            params.append(end_time)
        
        if event_types:
            placeholders = [f"${i+len(params)+1}" for i in range(len(event_types))]
            conditions.append(f"event_type IN ({','.join(placeholders)})")
            params.extend([e.value for e in event_types])
        
        if target_id:
            conditions.append(f"target_id = ${len(params)+1}")
            params.append(target_id)
        
        if actor_id:
            conditions.append(f"actor_id = ${len(params)+1}")
            params.append(actor_id)
        
        query = f"""
            SELECT * FROM audit_log
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                
                events = []
                for row in rows:
                    events.append(AuditEvent(
                        event_id=row['event_id'],
                        timestamp=row['timestamp'],
                        event_type=AuditEventType(row['event_type']),
                        severity=AuditSeverity(row['severity']),
                        actor_id=row['actor_id'],
                        actor_type=row['actor_type'],
                        target_type=row['target_type'],
                        target_id=row['target_id'],
                        action=row['action'],
                        description=row['description'],
                        old_value=row['old_value'],
                        new_value=row['new_value'],
                        metadata=row.get('metadata', {}),
                        checksum=row.get('checksum'),
                    ))
                
                return events
        except Exception as e:
            logger.error(f"Failed to query audit events: {e}")
            return []
    
    def subscribe(self, callback: Callable[[AuditEvent], None]) -> None:
        """Subscribe to real-time audit events."""
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[AuditEvent], None]) -> None:
        """Unsubscribe from audit events."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _log_to_stdout(self, event: AuditEvent) -> None:
        """Log event to stdout."""
        log_level = {
            AuditSeverity.INFO: logging.INFO,
            AuditSeverity.WARNING: logging.WARNING,
            AuditSeverity.ERROR: logging.ERROR,
            AuditSeverity.CRITICAL: logging.CRITICAL,
        }.get(event.severity, logging.INFO)
        
        logger.log(
            log_level,
            f"AUDIT: {event.event_type.value} | {event.action} | "
            f"{event.target_type}:{event.target_id} | {event.description}"
        )
    
    async def _flush_single_event(self, event: AuditEvent) -> None:
        """Flush a single event to database."""
        if not self.db_pool or not self.log_to_db:
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log (
                        event_id, timestamp, event_type, severity,
                        actor_id, actor_type, target_type, target_id,
                        action, description, old_value, new_value,
                        session_id, metadata, checksum
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    """,
                    event.event_id,
                    event.timestamp,
                    event.event_type.value,
                    event.severity.value,
                    event.actor_id,
                    event.actor_type,
                    event.target_type,
                    event.target_id,
                    event.action,
                    event.description,
                    json.dumps(event.old_value) if event.old_value else None,
                    json.dumps(event.new_value) if event.new_value else None,
                    event.session_id,
                    json.dumps(event.metadata),
                    event.checksum,
                )
        except Exception as e:
            logger.error(f"Failed to persist audit event {event.event_id}: {e}")
    
    async def _flush_to_db(self) -> None:
        """Flush buffered events to database."""
        if not self.db_pool or not self.log_to_db or not self._event_buffer:
            return
        
        # Batch insert
        null_placeholder = '\\N'
        try:
            import io
            
            buffer = io.StringIO()
            for event in self._event_buffer:
                old_val = json.dumps(event.old_value) if event.old_value else null_placeholder
                new_val = json.dumps(event.new_value) if event.new_value else null_placeholder
                session_val = event.session_id or null_placeholder
                checksum_val = event.checksum or null_placeholder
                
                buffer.write(
                    f"{event.event_id}\t{event.timestamp.isoformat()}\t"
                    f"{event.event_type.value}\t{event.severity.value}\t"
                    f"{event.actor_id}\t{event.actor_type}\t"
                    f"{event.target_type}\t{event.target_id or ''}\t"
                    f"{event.action}\t{event.description}\t"
                    f"{old_val}\t{new_val}\t{session_val}\t"
                    f"{json.dumps(event.metadata)}\t{checksum_val}\n"
                )
            
            buffer.seek(0)
            
            async with self.db_pool.acquire() as conn:
                await conn.copy_to_table(
                    'audit_log',
                    source=buffer,
                    columns=[
                        'event_id', 'timestamp', 'event_type', 'severity',
                        'actor_id', 'actor_type', 'target_type', 'target_id',
                        'action', 'description', 'old_value', 'new_value',
                        'session_id', 'metadata', 'checksum'
                    ],
                    format='text',
                )
            
            # Clear buffer
            self._event_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush audit events: {e}")
    
    async def _periodic_flush(self) -> None:
        """Periodic background flush task."""
        while True:
            try:
                await asyncio.sleep(30)  # Flush every 30 seconds
                
                if self._event_buffer:
                    await self._flush_to_db()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in audit flush: {e}")


# Singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(
    db_pool=None,
    log_to_stdout: bool = True,
    log_to_db: bool = True,
) -> AuditLogger:
    """Get or create the global audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(db_pool, log_to_stdout, log_to_db)
    elif db_pool and not _audit_logger.db_pool:
        _audit_logger.db_pool = db_pool
    return _audit_logger


def set_audit_logger(logger: AuditLogger) -> None:
    """Set the global audit logger (for testing)."""
    global _audit_logger
    _audit_logger = logger
