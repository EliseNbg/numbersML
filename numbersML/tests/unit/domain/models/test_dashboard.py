"""
Unit tests for dashboard domain models.

Tests:
    - Entity creation
    - Field types
    - Default values
    - Property methods
"""

import pytest
from datetime import datetime, timedelta, timezone

from src.domain.models.dashboard import (
    CollectorStatus,
    SLAMetric,
    DashboardStats,
)


class TestCollectorStatus:
    """Test CollectorStatus entity."""
    
    def test_create_with_defaults(self) -> None:
        """Test creating status with default values."""
        status = CollectorStatus()
        
        assert status.is_running is False
        assert status.pid is None
        assert status.uptime_seconds is None
        assert status.last_tick_time is None
        assert status.ticks_processed == 0
        assert status.errors == 0
    
    def test_create_with_values(self) -> None:
        """Test creating status with specific values."""
        now = datetime.now(timezone.utc)
        status = CollectorStatus(
            is_running=True,
            pid=12345,
            uptime_seconds=3600.0,
            last_tick_time=now,
            ticks_processed=86400,
            errors=0,
        )
        
        assert status.is_running is True
        assert status.pid == 12345
        assert status.uptime_seconds == 3600.0
        assert status.last_tick_time == now
        assert status.ticks_processed == 86400
        assert status.errors == 0
    
    def test_is_healthy_running(self) -> None:
        """Test health check when running."""
        status = CollectorStatus(
            is_running=True,
            errors=0,
        )
        assert status.is_healthy is True
    
    def test_is_healthy_not_running(self) -> None:
        """Test health check when not running."""
        status = CollectorStatus(
            is_running=False,
            errors=0,
        )
        assert status.is_healthy is False
    
    def test_is_healthy_with_errors(self) -> None:
        """Test health check with errors."""
        status = CollectorStatus(
            is_running=True,
            errors=1,
        )
        assert status.is_healthy is False
    
    def test_uptime_formatted_none(self) -> None:
        """Test uptime formatting when None."""
        status = CollectorStatus(uptime_seconds=None)
        assert status.uptime_formatted == "N/A"
    
    def test_uptime_formatted_seconds(self) -> None:
        """Test uptime formatting in seconds."""
        status = CollectorStatus(uptime_seconds=45.0)
        assert status.uptime_formatted == "45s"
    
    def test_uptime_formatted_minutes(self) -> None:
        """Test uptime formatting in minutes."""
        status = CollectorStatus(uptime_seconds=125.0)
        assert status.uptime_formatted == "2m 5s"
    
    def test_uptime_formatted_hours(self) -> None:
        """Test uptime formatting in hours."""
        status = CollectorStatus(uptime_seconds=3665.0)
        assert status.uptime_formatted == "1h 1m 5s"


class TestSLAMetric:
    """Test SLAMetric entity."""
    
    def test_create_with_defaults(self) -> None:
        """Test creating metric with default values."""
        now = datetime.now(timezone.utc)
        metric = SLAMetric(timestamp=now)
        
        assert metric.timestamp == now
        assert metric.avg_time_ms == 0.0
        assert metric.max_time_ms == 0.0
        assert metric.sla_violations == 0
        assert metric.ticks_processed == 0
    
    def test_create_with_values(self) -> None:
        """Test creating metric with specific values."""
        now = datetime.now(timezone.utc)
        metric = SLAMetric(
            timestamp=now,
            avg_time_ms=150.5,
            max_time_ms=450.0,
            sla_violations=2,
            ticks_processed=60,
        )
        
        assert metric.avg_time_ms == 150.5
        assert metric.max_time_ms == 450.0
        assert metric.sla_violations == 2
        assert metric.ticks_processed == 60
    
    def test_is_compliant_true(self) -> None:
        """Test compliance check when compliant."""
        metric = SLAMetric(
            timestamp=datetime.utcnow(),
            sla_violations=0,
            avg_time_ms=150.0,
        )
        assert metric.is_compliant is True
    
    def test_is_compliant_false_violations(self) -> None:
        """Test compliance check with violations."""
        metric = SLAMetric(
            timestamp=datetime.utcnow(),
            sla_violations=1,
            avg_time_ms=150.0,
        )
        assert metric.is_compliant is False
    
    def test_is_compliant_false_slow(self) -> None:
        """Test compliance check when too slow."""
        metric = SLAMetric(
            timestamp=datetime.utcnow(),
            sla_violations=0,
            avg_time_ms=1500.0,
        )
        assert metric.is_compliant is False
    
    def test_compliance_pct_100(self) -> None:
        """Test compliance percentage when 100%."""
        metric = SLAMetric(
            timestamp=datetime.utcnow(),
            ticks_processed=60,
            sla_violations=0,
        )
        assert metric.compliance_pct == 100.0
    
    def test_compliance_pct_partial(self) -> None:
        """Test compliance percentage when partial."""
        metric = SLAMetric(
            timestamp=datetime.utcnow(),
            ticks_processed=100,
            sla_violations=5,
        )
        assert metric.compliance_pct == 95.0
    
    def test_compliance_pct_zero_ticks(self) -> None:
        """Test compliance percentage with zero ticks."""
        metric = SLAMetric(
            timestamp=datetime.utcnow(),
            ticks_processed=0,
        )
        assert metric.compliance_pct == 100.0


class TestDashboardStats:
    """Test DashboardStats entity."""
    
    def test_create_with_defaults(self) -> None:
        """Test creating stats with default values."""
        stats = DashboardStats()
        
        assert stats.ticks_per_minute == 0
        assert stats.avg_processing_time_ms == 0.0
        assert stats.sla_compliance_pct == 100.0
        assert stats.active_symbols_count == 0
        assert stats.active_indicators_count == 0
    
    def test_create_with_values(self) -> None:
        """Test creating stats with specific values."""
        stats = DashboardStats(
            ticks_per_minute=60,
            avg_processing_time_ms=150.5,
            sla_compliance_pct=99.5,
            active_symbols_count=20,
            active_indicators_count=6,
        )
        
        assert stats.ticks_per_minute == 60
        assert stats.avg_processing_time_ms == 150.5
        assert stats.sla_compliance_pct == 99.5
        assert stats.active_symbols_count == 20
        assert stats.active_indicators_count == 6
    
    def test_performance_level_excellent(self) -> None:
        """Test performance level when excellent."""
        stats = DashboardStats(sla_compliance_pct=99.5)
        assert stats.performance_level == "excellent"
    
    def test_performance_level_good(self) -> None:
        """Test performance level when good."""
        stats = DashboardStats(sla_compliance_pct=97.0)
        assert stats.performance_level == "good"
    
    def test_performance_level_fair(self) -> None:
        """Test performance level when fair."""
        stats = DashboardStats(sla_compliance_pct=92.0)
        assert stats.performance_level == "fair"
    
    def test_performance_level_poor(self) -> None:
        """Test performance level when poor."""
        stats = DashboardStats(sla_compliance_pct=85.0)
        assert stats.performance_level == "poor"
    
    def test_performance_color_excellent(self) -> None:
        """Test performance color when excellent."""
        stats = DashboardStats(sla_compliance_pct=99.5)
        assert stats.performance_color == "success"
    
    def test_performance_color_good(self) -> None:
        """Test performance color when good."""
        stats = DashboardStats(sla_compliance_pct=97.0)
        assert stats.performance_color == "info"
    
    def test_performance_color_fair(self) -> None:
        """Test performance color when fair."""
        stats = DashboardStats(sla_compliance_pct=92.0)
        assert stats.performance_color == "warning"
    
    def test_performance_color_poor(self) -> None:
        """Test performance color when poor."""
        stats = DashboardStats(sla_compliance_pct=85.0)
        assert stats.performance_color == "danger"
