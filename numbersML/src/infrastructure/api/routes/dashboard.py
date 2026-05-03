"""
Dashboard API endpoints.

Provides REST API for dashboard monitoring:
- Collector service status
- SLA metrics
- Dashboard statistics

Architecture: Infrastructure Layer (API)
Dependencies: Application services
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.pipeline_monitor import PipelineMonitor
from src.domain.models.dashboard import CollectorStatus, DashboardStats, SLAMetric
from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def get_pipeline_monitor() -> PipelineMonitor:
    """Get PipelineMonitor instance with database pool."""
    db_pool = await get_db_pool_async()
    return PipelineMonitor(db_pool)


@router.get(
    "/status",
    response_model=CollectorStatus,
    summary="Get collector status",
    description="Get current status of the ticker collector service",
)
async def get_collector_status(
    monitor: PipelineMonitor = Depends(get_pipeline_monitor),
) -> CollectorStatus:
    """
    Get collector service status.

    Returns:
        Current collector status including:
        - is_running: Whether collector is running
        - pid: Process ID
        - uptime_seconds: How long it's been running
        - last_tick_time: Last processed tick
        - ticks_processed: Total ticks processed
        - errors: Error count

    Example:
        {
            "is_running": true,
            "pid": 12345,
            "uptime_seconds": 3600.0,
            "last_tick_time": "2026-03-24T12:00:00Z",
            "ticks_processed": 86400,
            "errors": 0
        }
    """
    return await monitor.get_collector_status()


@router.post(
    "/collector/start",
    summary="Start collector",
    description="Start the ticker collector service",
)
async def start_collector(
    monitor: PipelineMonitor = Depends(get_pipeline_monitor),
) -> dict:
    """
    Start collector service.

    Returns:
        Success message

    Example:
        {"message": "Collector started", "pid": 12345}
    """
    success = await monitor.start_collector()

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start collector",
        )

    return {"message": "Collector started"}


@router.post(
    "/collector/stop",
    summary="Stop collector",
    description="Stop the ticker collector service",
)
async def stop_collector(
    monitor: PipelineMonitor = Depends(get_pipeline_monitor),
) -> dict:
    """
    Stop collector service.

    Returns:
        Success message

    Example:
        {"message": "Collector stopped"}
    """
    success = await monitor.stop_collector()

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop collector",
        )

    return {"message": "Collector stopped"}


@router.get(
    "/metrics",
    response_model=list[SLAMetric],
    summary="Get SLA metrics",
    description="Get SLA metrics for the last N seconds",
)
async def get_sla_metrics(
    seconds: int = 60,
    monitor: PipelineMonitor = Depends(get_pipeline_monitor),
) -> list[SLAMetric]:
    """
    Get SLA metrics for last N seconds.

    Args:
        seconds: Number of seconds to fetch (default: 60)

    Returns:
        List of SLA metrics, one per second

    Example:
        [
            {
                "timestamp": "2026-03-24T12:00:00Z",
                "avg_time_ms": 150.5,
                "max_time_ms": 450.0,
                "sla_violations": 0,
                "ticks_processed": 60
            }
        ]
    """
    if seconds < 1 or seconds > 300:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seconds must be between 1 and 300",
        )

    return await monitor.get_sla_metrics(seconds=seconds)


@router.get(
    "/stats",
    response_model=DashboardStats,
    summary="Get dashboard stats",
    description="Get quick dashboard statistics",
)
async def get_dashboard_stats(
    monitor: PipelineMonitor = Depends(get_pipeline_monitor),
) -> DashboardStats:
    """
    Get quick dashboard statistics.

    Returns:
        Dashboard statistics including:
        - ticks_per_minute: Throughput
        - avg_processing_time_ms: Average latency
        - sla_compliance_pct: Compliance percentage
        - active_symbols_count: Active symbols
        - active_indicators_count: Active indicators

    Example:
        {
            "ticks_per_minute": 60,
            "avg_processing_time_ms": 150.5,
            "sla_compliance_pct": 99.5,
            "active_symbols_count": 20,
            "active_indicators_count": 6
        }
    """
    return await monitor.get_dashboard_stats()
