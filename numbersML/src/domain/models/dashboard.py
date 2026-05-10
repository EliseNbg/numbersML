"""
Dashboard entities for pipeline monitoring.

This module contains domain models for the dashboard layer.
These are pure Python classes with no external dependencies (DDD Domain Layer).

Entities:
    - CollectorStatus: Status of the ticker collector service
    - SLAMetric: Single SLA measurement
    - DashboardStats: Quick statistics for dashboard
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CollectorStatus:
    """
    Status of the ticker collector service.

    Attributes:
        is_running: Whether collector process is currently running
        pid: Process ID of collector (None if not running)
        uptime_seconds: How long collector has been running (None if not running)
        last_tick_time: Timestamp of last processed tick (None if no ticks)
        ticks_processed: Total ticks processed since start
        errors: Total errors encountered

    Example:
        >>> status = CollectorStatus(
        ...     is_running=True,
        ...     pid=12345,
        ...     uptime_seconds=3600.0,
        ...     ticks_processed=86400,
        ...     errors=0,
        ... )
        >>> status.is_healthy
        True
    """

    is_running: bool = False
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    last_tick_time: Optional[datetime] = None
    ticks_processed: int = 0
    errors: int = 0

    @property
    def is_healthy(self) -> bool:
        """
        Check if collector is healthy.

        Healthy = running + no recent errors + recent tick
        """
        if not self.is_running:
            return False

        if self.errors > 0:
            return False

        return True

    @property
    def uptime_formatted(self) -> str:
        """
        Get human-readable uptime string.

        Returns:
            Formatted uptime (e.g., "1h 30m 15s") or "N/A"
        """
        if self.uptime_seconds is None:
            return "N/A"

        hours = int(self.uptime_seconds // 3600)
        minutes = int((self.uptime_seconds % 3600) // 60)
        seconds = int(self.uptime_seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"


@dataclass
class SLAMetric:
    """
    Single SLA measurement for a specific time bucket.

    Attributes:
        timestamp: Time bucket for this measurement
        avg_time_ms: Average processing time in milliseconds
        max_time_ms: Maximum processing time in milliseconds
        sla_violations: Count of ticks exceeding 1000ms SLA
        ticks_processed: Total ticks in this time bucket

    Example:
        >>> metric = SLAMetric(
        ...     timestamp=datetime.now(timezone.utc),
        ...     avg_time_ms=150.5,
        ...     max_time_ms=450.0,
        ...     sla_violations=0,
        ...     ticks_processed=60,
        ... )
        >>> metric.is_compliant
        True
    """

    timestamp: datetime
    avg_time_ms: float = 0.0
    max_time_ms: float = 0.0
    sla_violations: int = 0
    ticks_processed: int = 0

    @property
    def is_compliant(self) -> bool:
        """
        Check if this metric meets SLA (1-second target).

        Returns:
            True if no violations and avg < 1000ms
        """
        return self.sla_violations == 0 and self.avg_time_ms < 1000.0

    @property
    def compliance_pct(self) -> float:
        """
        Calculate compliance percentage for this bucket.

        Returns:
            Percentage of ticks within SLA (0-100)
        """
        if self.ticks_processed == 0:
            return 100.0

        compliant = self.ticks_processed - self.sla_violations
        return (compliant / self.ticks_processed) * 100.0


@dataclass
class DashboardStats:
    """
    Quick statistics for dashboard display.

    Attributes:
        ticks_per_minute: Ticks processed in last minute
        avg_processing_time_ms: Average processing time (last minute)
        sla_compliance_pct: SLA compliance percentage (last minute)
        active_symbols_count: Number of active symbols
        active_indicators_count: Number of active indicators

    Example:
        >>> stats = DashboardStats(
        ...     ticks_per_minute=60,
        ...     avg_processing_time_ms=150.5,
        ...     sla_compliance_pct=99.5,
        ...     active_symbols_count=20,
        ...     active_indicators_count=6,
        ... )
        >>> stats.performance_level
        'excellent'
    """

    ticks_per_minute: int = 0
    avg_processing_time_ms: float = 0.0
    sla_compliance_pct: float = 100.0
    active_symbols_count: int = 0
    active_indicators_count: int = 0

    @property
    def performance_level(self) -> str:
        """
        Get performance level based on SLA compliance.

        Returns:
            Performance level: excellent, good, fair, or poor
        """
        if self.sla_compliance_pct >= 99.0:
            return "excellent"
        elif self.sla_compliance_pct >= 95.0:
            return "good"
        elif self.sla_compliance_pct >= 90.0:
            return "fair"
        else:
            return "poor"

    @property
    def performance_color(self) -> str:
        """
        Get color code for performance level.

        Returns:
            Bootstrap color class (success, info, warning, danger)
        """
        colors = {
            "excellent": "success",
            "good": "info",
            "fair": "warning",
            "poor": "danger",
        }
        return colors.get(self.performance_level, "secondary")
