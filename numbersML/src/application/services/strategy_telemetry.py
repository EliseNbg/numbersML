"""
Strategy Telemetry Service - Comprehensive observability for strategy execution.

Provides:
- Per-strategy health metrics
- Order execution statistics (success/failure ratios, latency)
- Signal generation tracking
- Error and exception counters
- Backtest vs live drift indicators
- Performance profiling
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Deque, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class OrderStatus(Enum):
    """Order execution status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL_FILL = "partial_fill"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class OrderMetrics:
    """Metrics for a single order."""
    order_id: str
    strategy_id: UUID
    symbol: str
    side: str
    quantity: float
    price: float
    status: OrderStatus
    created_at: datetime
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    error_message: Optional[str] = None
    latency_ms: Optional[float] = None
    slippage_bps: Optional[float] = None


@dataclass
class SignalMetrics:
    """Metrics for a signal generation event."""
    signal_id: str
    strategy_id: UUID
    symbol: str
    signal_type: str
    confidence: float
    generated_at: datetime
    indicators_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorEvent:
    """Error or exception event."""
    timestamp: datetime
    strategy_id: UUID
    error_type: str
    error_message: str
    context: Dict[str, Any] = field(default_factory=dict)
    severity: str = "error"  # error, warning, critical


@dataclass
class StrategyHealth:
    """Health metrics for a strategy."""
    strategy_id: UUID
    is_healthy: bool = True
    last_tick_processed: Optional[datetime] = None
    ticks_per_minute: float = 0.0
    signals_per_minute: float = 0.0
    orders_per_minute: float = 0.0
    error_rate_5m: float = 0.0
    avg_signal_latency_ms: float = 0.0
    avg_order_latency_ms: float = 0.0
    uptime_seconds: float = 0.0
    last_health_check: Optional[datetime] = None
    
    # Status flags
    data_fresh: bool = True
    processing_lag_seconds: float = 0.0
    memory_usage_mb: float = 0.0


@dataclass
class ExecutionStatistics:
    """Order execution statistics."""
    total_orders: int = 0
    filled_orders: int = 0
    rejected_orders: int = 0
    cancelled_orders: int = 0
    error_orders: int = 0
    timeout_orders: int = 0
    partial_fills: int = 0
    
    # Ratios
    fill_rate: float = 0.0
    reject_rate: float = 0.0
    error_rate: float = 0.0
    
    # Latency
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    
    # Slippage
    avg_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0


@dataclass
class DriftIndicator:
    """Backtest vs live performance drift indicator."""
    strategy_id: UUID
    metric_name: str
    backtest_value: float
    live_value: float
    drift_pct: float
    drift_threshold_pct: float
    is_significant: bool
    calculated_at: datetime
    
    @classmethod
    def calculate(
        cls,
        strategy_id: UUID,
        metric_name: str,
        backtest_value: float,
        live_value: float,
        threshold_pct: float = 20.0,
    ) -> "DriftIndicator":
        """Calculate drift between backtest and live performance."""
        if backtest_value == 0:
            drift_pct = 0.0 if live_value == 0 else float('inf')
        else:
            drift_pct = abs((live_value - backtest_value) / backtest_value) * 100
        
        return cls(
            strategy_id=strategy_id,
            metric_name=metric_name,
            backtest_value=backtest_value,
            live_value=live_value,
            drift_pct=drift_pct,
            drift_threshold_pct=threshold_pct,
            is_significant=drift_pct > threshold_pct,
            calculated_at=datetime.utcnow(),
        )


class StrategyTelemetryService:
    """
    Service for collecting and aggregating strategy execution telemetry.
    
    Features:
    - Real-time metrics collection
    - Sliding window statistics
    - Health monitoring
    - Performance drift detection
    - Structured logging
    """
    
    def __init__(
        self,
        window_minutes: int = 5,
        max_history: int = 10000,
    ) -> None:
        self.window_minutes = window_minutes
        self.max_history = max_history
        
        # Per-strategy metrics stores
        self._orders: Dict[UUID, Deque[OrderMetrics]] = {}
        self._signals: Dict[UUID, Deque[SignalMetrics]] = {}
        self._errors: Dict[UUID, Deque[ErrorEvent]] = {}
        self._health: Dict[UUID, StrategyHealth] = {}
        
        # Global counters
        self._global_counters: Dict[str, int] = {
            "total_signals": 0,
            "total_orders": 0,
            "total_errors": 0,
            "total_guardrail_blocks": 0,
        }
        
        # Start time for uptime tracking
        self._start_time = datetime.utcnow()
        
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info(f"StrategyTelemetryService initialized (window={window_minutes}m)")
    
    async def start(self) -> None:
        """Start background maintenance tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("StrategyTelemetryService started")
    
    async def stop(self) -> None:
        """Stop background tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("StrategyTelemetryService stopped")
    
    def register_strategy(self, strategy_id: UUID) -> StrategyHealth:
        """Register a strategy for telemetry collection."""
        now = datetime.utcnow()
        
        if strategy_id not in self._orders:
            self._orders[strategy_id] = deque(maxlen=self.max_history)
        if strategy_id not in self._signals:
            self._signals[strategy_id] = deque(maxlen=self.max_history)
        if strategy_id not in self._errors:
            self._errors[strategy_id] = deque(maxlen=self.max_history)
        
        if strategy_id not in self._health:
            self._health[strategy_id] = StrategyHealth(
                strategy_id=strategy_id,
                last_health_check=now,
            )
        
        logger.info(f"Registered strategy {strategy_id} for telemetry")
        return self._health[strategy_id]
    
    def unregister_strategy(self, strategy_id: UUID) -> None:
        """Unregister a strategy and clean up data."""
        self._orders.pop(strategy_id, None)
        self._signals.pop(strategy_id, None)
        self._errors.pop(strategy_id, None)
        self._health.pop(strategy_id, None)
        logger.info(f"Unregistered strategy {strategy_id} from telemetry")
    
    # =========================================================================
    # Order Tracking
    # =========================================================================
    
    def record_order_created(
        self,
        strategy_id: UUID,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> OrderMetrics:
        """Record order creation."""
        self._ensure_strategy(strategy_id)
        
        order = OrderMetrics(
            order_id=order_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        
        self._orders[strategy_id].append(order)
        self._global_counters["total_orders"] += 1
        
        return order
    
    def record_order_submitted(
        self,
        strategy_id: UUID,
        order_id: str,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Record order submission to exchange."""
        order = self._find_order(strategy_id, order_id)
        if order:
            order.submitted_at = datetime.utcnow()
            order.status = OrderStatus.SUBMITTED
            if latency_ms:
                order.latency_ms = latency_ms
    
    def record_order_filled(
        self,
        strategy_id: UUID,
        order_id: str,
        fill_price: float,
        latency_ms: Optional[float] = None,
        slippage_bps: Optional[float] = None,
    ) -> None:
        """Record order fill."""
        order = self._find_order(strategy_id, order_id)
        if order:
            order.filled_at = datetime.utcnow()
            order.status = OrderStatus.FILLED
            if latency_ms:
                order.latency_ms = latency_ms
            if slippage_bps:
                order.slippage_bps = slippage_bps
    
    def record_order_rejected(
        self,
        strategy_id: UUID,
        order_id: str,
        reason: str,
    ) -> None:
        """Record order rejection."""
        order = self._find_order(strategy_id, order_id)
        if order:
            order.rejected_at = datetime.utcnow()
            order.status = OrderStatus.REJECTED
            order.error_message = reason
    
    def record_order_error(
        self,
        strategy_id: UUID,
        order_id: str,
        error: Exception,
    ) -> None:
        """Record order error."""
        order = self._find_order(strategy_id, order_id)
        if order:
            order.status = OrderStatus.ERROR
            order.error_message = str(error)
        
        self.record_error(
            strategy_id=strategy_id,
            error_type=type(error).__name__,
            error_message=str(error),
            context={"order_id": order_id},
        )
    
    def record_order_timeout(
        self,
        strategy_id: UUID,
        order_id: str,
    ) -> None:
        """Record order timeout."""
        order = self._find_order(strategy_id, order_id)
        if order:
            order.status = OrderStatus.TIMEOUT
    
    # =========================================================================
    # Signal Tracking
    # =========================================================================
    
    def record_signal(
        self,
        strategy_id: UUID,
        signal_id: str,
        symbol: str,
        signal_type: str,
        confidence: float,
        indicators_used: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SignalMetrics:
        """Record signal generation."""
        self._ensure_strategy(strategy_id)
        
        signal = SignalMetrics(
            signal_id=signal_id,
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            generated_at=datetime.utcnow(),
            indicators_used=indicators_used or [],
            metadata=metadata or {},
        )
        
        self._signals[strategy_id].append(signal)
        self._global_counters["total_signals"] += 1
        
        return signal
    
    # =========================================================================
    # Error Tracking
    # =========================================================================
    
    def record_error(
        self,
        strategy_id: UUID,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
        severity: str = "error",
    ) -> ErrorEvent:
        """Record an error event."""
        self._ensure_strategy(strategy_id)
        
        error = ErrorEvent(
            timestamp=datetime.utcnow(),
            strategy_id=strategy_id,
            error_type=error_type,
            error_message=error_message,
            context=context or {},
            severity=severity,
        )
        
        self._errors[strategy_id].append(error)
        self._global_counters["total_errors"] += 1
        
        # Log critical errors immediately
        if severity == "critical":
            logger.critical(
                f"CRITICAL ERROR in strategy {strategy_id}: "
                f"{error_type}: {error_message}"
            )
        
        return error
    
    # =========================================================================
    # Health Tracking
    # =========================================================================
    
    def record_tick_processed(
        self,
        strategy_id: UUID,
        tick_time: datetime,
        processing_time_ms: float,
    ) -> None:
        """Record tick processing."""
        health = self._ensure_strategy(strategy_id)
        health.last_tick_processed = tick_time
    
    def record_guardrail_block(
        self,
        strategy_id: UUID,
        guardrail_type: str,
        reason: str,
    ) -> None:
        """Record guardrail blocking an action."""
        self._global_counters["total_guardrail_blocks"] += 1
        
        logger.warning(
            f"Guardrail block: {guardrail_type} for strategy {strategy_id}: {reason}"
        )
    
    # =========================================================================
    # Statistics Queries
    # =========================================================================
    
    def get_execution_statistics(
        self,
        strategy_id: UUID,
        window_minutes: Optional[int] = None,
    ) -> ExecutionStatistics:
        """Get order execution statistics for a strategy."""
        orders = self._get_recent_orders(strategy_id, window_minutes)
        
        if not orders:
            return ExecutionStatistics()
        
        total = len(orders)
        filled = sum(1 for o in orders if o.status == OrderStatus.FILLED)
        rejected = sum(1 for o in orders if o.status == OrderStatus.REJECTED)
        cancelled = sum(1 for o in orders if o.status == OrderStatus.CANCELLED)
        errors = sum(1 for o in orders if o.status == OrderStatus.ERROR)
        timeouts = sum(1 for o in orders if o.status == OrderStatus.TIMEOUT)
        partial = sum(1 for o in orders if o.status == OrderStatus.PARTIAL_FILL)
        
        # Latency stats (for filled orders)
        latencies = [
            o.latency_ms for o in orders
            if o.latency_ms is not None and o.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED)
        ]
        
        stats = ExecutionStatistics(
            total_orders=total,
            filled_orders=filled,
            rejected_orders=rejected,
            cancelled_orders=cancelled,
            error_orders=errors,
            timeout_orders=timeouts,
            partial_fills=partial,
            fill_rate=filled / total if total > 0 else 0,
            reject_rate=rejected / total if total > 0 else 0,
            error_rate=errors / total if total > 0 else 0,
        )
        
        if latencies:
            sorted_latencies = sorted(latencies)
            stats.avg_latency_ms = sum(latencies) / len(latencies)
            stats.p50_latency_ms = sorted_latencies[int(len(sorted_latencies) * 0.5)]
            stats.p95_latency_ms = sorted_latencies[min(int(len(sorted_latencies) * 0.95), len(sorted_latencies) - 1)]
            stats.p99_latency_ms = sorted_latencies[min(int(len(sorted_latencies) * 0.99), len(sorted_latencies) - 1)]
            stats.max_latency_ms = max(latencies)
        
        return stats
    
    def get_signal_statistics(
        self,
        strategy_id: UUID,
        window_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get signal generation statistics."""
        signals = self._get_recent_signals(strategy_id, window_minutes)
        
        if not signals:
            return {
                "total_signals": 0,
                "avg_confidence": 0,
                "signals_by_type": {},
            }
        
        total = len(signals)
        avg_confidence = sum(s.confidence for s in signals) / total
        
        by_type: Dict[str, int] = {}
        for s in signals:
            by_type[s.signal_type] = by_type.get(s.signal_type, 0) + 1
        
        return {
            "total_signals": total,
            "avg_confidence": avg_confidence,
            "signals_by_type": by_type,
            "signals_per_minute": total / (window_minutes or self.window_minutes),
        }
    
    def get_error_summary(
        self,
        strategy_id: UUID,
        window_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get error summary for a strategy."""
        errors = self._get_recent_errors(strategy_id, window_minutes)
        
        if not errors:
            return {
                "total_errors": 0,
                "errors_by_type": {},
                "critical_count": 0,
            }
        
        by_type: Dict[str, int] = {}
        critical = 0
        
        for e in errors:
            by_type[e.error_type] = by_type.get(e.error_type, 0) + 1
            if e.severity == "critical":
                critical += 1
        
        return {
            "total_errors": len(errors),
            "errors_by_type": by_type,
            "critical_count": critical,
            "error_rate_per_minute": len(errors) / (window_minutes or self.window_minutes),
        }
    
    def get_health_summary(self, strategy_id: UUID) -> StrategyHealth:
        """Get current health summary for a strategy."""
        health = self._ensure_strategy(strategy_id)
        
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=self.window_minutes)
        
        # Calculate rates
        recent_signals = [
            s for s in self._signals.get(strategy_id, [])
            if s.generated_at > window_start
        ]
        recent_orders = [
            o for o in self._orders.get(strategy_id, [])
            if o.created_at > window_start
        ]
        
        health.signals_per_minute = len(recent_signals) / self.window_minutes
        health.orders_per_minute = len(recent_orders) / self.window_minutes
        health.uptime_seconds = (now - self._start_time).total_seconds()
        health.last_health_check = now
        
        # Error rate
        recent_errors = [
            e for e in self._errors.get(strategy_id, [])
            if e.timestamp > window_start
        ]
        health.error_rate_5m = len(recent_errors) / self.window_minutes
        
        # Determine health status
        health.is_healthy = (
            health.error_rate_5m < 1.0 and  # Less than 1 error per minute
            health.data_fresh and
            not health.kill_switch_active if hasattr(health, 'kill_switch_active') else True
        )
        
        return health
    
    def calculate_drift(
        self,
        strategy_id: UUID,
        backtest_metrics: Dict[str, float],
        live_metrics: Dict[str, float],
        threshold_pct: float = 20.0,
    ) -> List[DriftIndicator]:
        """Calculate drift between backtest and live performance."""
        indicators = []
        
        common_metrics = set(backtest_metrics.keys()) & set(live_metrics.keys())
        
        for metric_name in common_metrics:
            bt_val = backtest_metrics[metric_name]
            live_val = live_metrics[metric_name]
            
            # Skip non-numeric metrics
            if not isinstance(bt_val, (int, float)) or not isinstance(live_val, (int, float)):
                continue
            
            indicator = DriftIndicator.calculate(
                strategy_id=strategy_id,
                metric_name=metric_name,
                backtest_value=bt_val,
                live_value=live_val,
                threshold_pct=threshold_pct,
            )
            
            indicators.append(indicator)
        
        # Sort by drift significance
        indicators.sort(key=lambda x: x.drift_pct, reverse=True)
        
        return indicators
    
    def get_global_metrics(self) -> Dict[str, Any]:
        """Get global telemetry summary."""
        return {
            "uptime_seconds": (datetime.utcnow() - self._start_time).total_seconds(),
            "monitored_strategies": len(self._health),
            "total_signals_issued": self._global_counters["total_signals"],
            "total_orders_submitted": self._global_counters["total_orders"],
            "total_errors": self._global_counters["total_errors"],
            "total_guardrail_blocks": self._global_counters["total_guardrail_blocks"],
        }
    
    def get_all_health(self) -> Dict[UUID, StrategyHealth]:
        """Get health for all strategies."""
        return {
            sid: self.get_health_summary(sid)
            for sid in self._health.keys()
        }
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _ensure_strategy(self, strategy_id: UUID) -> StrategyHealth:
        """Ensure strategy is registered and return health."""
        if strategy_id not in self._health:
            return self.register_strategy(strategy_id)
        return self._health[strategy_id]
    
    def _find_order(self, strategy_id: UUID, order_id: str) -> Optional[OrderMetrics]:
        """Find an order by ID."""
        orders = self._orders.get(strategy_id, deque())
        for order in orders:
            if order.order_id == order_id:
                return order
        return None
    
    def _get_recent_orders(
        self,
        strategy_id: UUID,
        window_minutes: Optional[int] = None,
    ) -> List[OrderMetrics]:
        """Get orders within time window."""
        minutes = window_minutes or self.window_minutes
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        
        orders = self._orders.get(strategy_id, deque())
        return [o for o in orders if o.created_at > cutoff]
    
    def _get_recent_signals(
        self,
        strategy_id: UUID,
        window_minutes: Optional[int] = None,
    ) -> List[SignalMetrics]:
        """Get signals within time window."""
        minutes = window_minutes or self.window_minutes
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        
        signals = self._signals.get(strategy_id, deque())
        return [s for s in signals if s.generated_at > cutoff]
    
    def _get_recent_errors(
        self,
        strategy_id: UUID,
        window_minutes: Optional[int] = None,
    ) -> List[ErrorEvent]:
        """Get errors within time window."""
        minutes = window_minutes or self.window_minutes
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        
        errors = self._errors.get(strategy_id, deque())
        return [e for e in errors if e.timestamp > cutoff]
    
    async def _cleanup_loop(self) -> None:
        """Background task for periodic maintenance."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                # Cleanup is handled by deque maxlen, but we can do additional pruning
                now = datetime.utcnow()
                cutoff = now - timedelta(minutes=self.window_minutes * 2)
                
                for strategy_id in list(self._health.keys()):
                    # Update health status
                    health = self._health.get(strategy_id)
                    if health and health.last_tick_processed:
                        lag = (now - health.last_tick_processed).total_seconds()
                        health.processing_lag_seconds = lag
                        health.data_fresh = lag < 60  # Data older than 60s is stale
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry cleanup: {e}")


# Singleton instance
_telemetry_service: Optional[StrategyTelemetryService] = None


def get_telemetry_service() -> StrategyTelemetryService:
    """Get or create the global telemetry service."""
    global _telemetry_service
    if _telemetry_service is None:
        _telemetry_service = StrategyTelemetryService()
    return _telemetry_service


def set_telemetry_service(service: StrategyTelemetryService) -> None:
    """Set the global telemetry service (for testing)."""
    global _telemetry_service
    _telemetry_service = service
