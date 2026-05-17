"""
Strategy management GUI API endpoints.

Provides REST API for the strategy dashboard:
- Full dashboard state (strategies, status, signals count)
- Strategy statistics
- Cleanup operations

Architecture: Infrastructure Layer (API)
Dependencies: Application services, Pipeline components
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.pipeline.signal_aggregator import SignalAggregator
from src.pipeline.stdout_collector import StdoutCollector

router = APIRouter(prefix="/api/strategies/gui", tags=["strategies-gui"])

logger = logging.getLogger(__name__)


# ============================================================================
# Dependencies
# ============================================================================


def get_stdout_collector() -> StdoutCollector:
    """Get or create StdoutCollector singleton."""
    if not hasattr(get_stdout_collector, "_instance"):
        get_stdout_collector._instance = StdoutCollector()
    return get_stdout_collector._instance


def get_signal_aggregator() -> SignalAggregator:
    """Get or create SignalAggregator singleton."""
    if not hasattr(get_signal_aggregator, "_instance"):
        get_signal_aggregator._instance = SignalAggregator()
    return get_signal_aggregator._instance


async def get_cleanup_service():
    """Get CleanupService instance."""
    from src.application.services.cleanup_service import CleanupService
    from src.infrastructure.database import get_db_pool_async

    db_pool = await get_db_pool_async()
    return CleanupService(db_pool=db_pool)


# ============================================================================
# Dashboard Endpoints
# ============================================================================


@router.get("/dashboard", response_model=dict[str, Any])
async def get_dashboard(
    aggregator: SignalAggregator = Depends(get_signal_aggregator),
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Get full dashboard state (strategies, status, signals count)."""
    strategy_ids = aggregator.get_all_strategy_ids()
    strategies = []

    for sid in strategy_ids:
        stats = aggregator.get_stats(sid)
        stdout_info = collector.to_dict(sid)
        strategies.append({
            "id": str(sid),
            "signals_today": stats.total_signals,
            "buy_count": stats.buy_count,
            "sell_count": stats.sell_count,
            "executed_count": stats.executed_count,
            "stdout_lines": stdout_info["line_count"],
        })

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_strategies": len(strategies),
        "total_signals": aggregator.get_signal_count(),
        "strategies": strategies,
        "recent_signals": [
            {
                "signal_id": str(s.signal_id),
                "strategy_id": str(s.strategy_id),
                "strategy_name": s.strategy_name,
                "symbol": s.symbol,
                "side": s.side,
                "price": float(s.price) if s.price else None,
                "quantity": float(s.quantity),
                "status": s.status.value,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in aggregator.get_recent(limit=20)
        ],
    }


@router.get("/{strategy_id}/stats", response_model=dict[str, Any])
async def get_strategy_stats(
    strategy_id: UUID,
    aggregator: SignalAggregator = Depends(get_signal_aggregator),
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Get strategy statistics."""
    stats = aggregator.get_stats(strategy_id)
    stdout_info = collector.to_dict(strategy_id)

    return {
        "strategy_id": str(strategy_id),
        "signals": stats.to_dict(),
        "stdout": stdout_info,
    }


@router.get("/{strategy_id}/signals", response_model=list[dict[str, Any]])
async def get_strategy_signals(
    strategy_id: UUID,
    limit: int = Query(50, ge=1, le=500, description="Maximum signals to return"),
    aggregator: SignalAggregator = Depends(get_signal_aggregator),
) -> list[dict[str, Any]]:
    """Get signals for a strategy."""
    signals = aggregator.get_recent(strategy_id=strategy_id, limit=limit)
    return [
        {
            "signal_id": str(s.signal_id),
            "strategy_name": s.strategy_name,
            "symbol": s.symbol,
            "side": s.side,
            "order_type": s.order_type,
            "price": float(s.price) if s.price else None,
            "quantity": float(s.quantity),
            "status": s.status.value,
            "timestamp": s.timestamp.isoformat(),
            "metadata": s.metadata,
        }
        for s in signals
    ]


@router.get("/{strategy_id}/stdout", response_model=dict[str, Any])
async def get_strategy_stdout(
    strategy_id: UUID,
    limit: int = Query(100, ge=1, le=1000, description="Maximum lines to return"),
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Get stdout for a strategy."""
    lines = collector.get_output(strategy_id, limit=limit)
    return {
        "strategy_id": str(strategy_id),
        "lines": lines,
        "line_count": len(lines),
    }


@router.post("/{strategy_id}/stdout/clear", response_model=dict[str, Any])
async def clear_strategy_stdout(
    strategy_id: UUID,
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Clear stdout buffer for a strategy."""
    collector.clear(strategy_id)
    return {
        "message": f"Stdout cleared for strategy {strategy_id}",
        "strategy_id": str(strategy_id),
    }


# ============================================================================
# Cleanup Endpoints
# ============================================================================


@router.post("/cleanup", response_model=dict[str, Any])
async def cleanup_strategy(
    strategy_id: UUID,
    delete_signals: bool = Query(True, description="Delete signal records"),
    delete_backtests: bool = Query(True, description="Delete backtest records"),
    delete_events: bool = Query(True, description="Delete event records"),
    delete_versions: bool = Query(False, description="Delete version records"),
    cleanup_svc=Depends(get_cleanup_service),
) -> dict[str, Any]:
    """Clean up artifacts for a strategy."""
    result = await cleanup_svc.cleanup_strategy(
        strategy_id=strategy_id,
        delete_signals=delete_signals,
        delete_backtests=delete_backtests,
        delete_events=delete_events,
        delete_versions=delete_versions,
    )
    return result.to_dict()


@router.post("/cleanup-all-stopped", response_model=dict[str, Any])
async def cleanup_all_stopped(
    older_than_hours: int = Query(24, ge=1, description="Clean strategies older than N hours"),
    cleanup_svc=Depends(get_cleanup_service),
) -> dict[str, Any]:
    """Clean up all stopped/archived strategies."""
    results = await cleanup_svc.cleanup_all_stopped(older_than_hours=older_than_hours)
    return {
        "strategies_cleaned": len(results),
        "results": {
            str(sid): result.to_dict() for sid, result in results.items()
        },
    }


@router.get("/cleanup-stats", response_model=dict[str, Any])
async def get_cleanup_stats(
    cleanup_svc=Depends(get_cleanup_service),
) -> dict[str, Any]:
    """Get statistics about cleanup candidates."""
    return await cleanup_svc.get_cleanup_stats()
