"""
Signal and stdout API endpoints.

Provides REST API for:
- Querying recent trade signals
- Retrieving strategy stdout output
- Signal statistics and aggregation

Architecture: Infrastructure Layer (API)
Dependencies: Pipeline components (StdoutCollector, SignalAggregator)
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.domain.strategies.signal import SignalStatus, TradeSignal
from src.pipeline.signal_aggregator import SignalAggregator
from src.pipeline.stdout_collector import StdoutCollector

router = APIRouter(prefix="/api/signals", tags=["signals", "stdout"])

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


# ============================================================================
# Pydantic Response Models (dict-based for speed)
# ============================================================================


def _signal_to_dict(signal: TradeSignal) -> dict[str, Any]:
    """Convert TradeSignal to API response dict."""
    return {
        "signal_id": str(signal.signal_id),
        "strategy_id": str(signal.strategy_id),
        "strategy_name": signal.strategy_name,
        "symbol": signal.symbol,
        "side": signal.side,
        "order_type": signal.order_type,
        "quantity": float(signal.quantity),
        "price": float(signal.price) if signal.price is not None else None,
        "timestamp": signal.timestamp.isoformat(),
        "metadata": signal.metadata,
        "status": signal.status.value if isinstance(signal.status, SignalStatus) else signal.status,
    }


# ============================================================================
# Signal Endpoints
# ============================================================================


@router.get("", response_model=list[dict[str, Any]])
async def get_signals(
    strategy_id: UUID | None = Query(None, description="Filter by strategy ID"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=500, description="Maximum signals to return"),
    aggregator: SignalAggregator = Depends(get_signal_aggregator),
) -> list[dict[str, Any]]:
    """Get recent trade signals with optional filters."""
    signals = aggregator.get_recent(
        strategy_id=strategy_id,
        symbol=symbol,
        limit=limit,
    )
    return [_signal_to_dict(s) for s in signals]


@router.get("/stats", response_model=dict[str, Any])
async def get_signal_stats(
    strategy_id: UUID | None = Query(None, description="Filter by strategy ID"),
    aggregator: SignalAggregator = Depends(get_signal_aggregator),
) -> dict[str, Any]:
    """Get signal statistics."""
    if strategy_id is not None:
        stats = aggregator.get_stats(strategy_id)
        return {
            "strategy_id": str(strategy_id),
            "stats": stats.to_dict(),
        }
    return aggregator.to_dict()


@router.get("/count", response_model=dict[str, int])
async def get_signal_count(
    strategy_id: UUID | None = Query(None, description="Filter by strategy ID"),
    aggregator: SignalAggregator = Depends(get_signal_aggregator),
) -> dict[str, int]:
    """Get signal count."""
    count = aggregator.get_signal_count(strategy_id)
    return {"count": count}


# ============================================================================
# Stdout Endpoints
# ============================================================================


@router.get("/stdout/{strategy_id}", response_model=dict[str, Any])
async def get_strategy_stdout(
    strategy_id: UUID,
    limit: int = Query(100, ge=1, le=1000, description="Maximum lines to return"),
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Get captured stdout for a strategy."""
    lines = collector.get_output(strategy_id, limit=limit)
    return {
        "strategy_id": str(strategy_id),
        "lines": lines,
        "line_count": len(lines),
        "total_lines": collector.get_line_count(strategy_id),
        "buffer_size": collector.get_buffer_size(strategy_id),
    }


@router.post("/stdout/{strategy_id}/clear", response_model=dict[str, Any])
async def clear_strategy_stdout(
    strategy_id: UUID,
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Clear stdout buffer for a strategy."""
    collector.clear(strategy_id)
    return {
        "message": f"Stdout buffer cleared for strategy {strategy_id}",
        "strategy_id": str(strategy_id),
    }


@router.get("/stdout", response_model=list[dict[str, Any]])
async def list_stdout_strategies(
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> list[dict[str, Any]]:
    """List all strategies with stdout buffers."""
    strategy_ids = collector.get_all_strategy_ids()
    return [collector.to_dict(sid) for sid in strategy_ids]


@router.post("/stdout/clear-all", response_model=dict[str, Any])
async def clear_all_stdout(
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Clear all stdout buffers."""
    collector.clear_all()
    return {"message": "All stdout buffers cleared"}


# ============================================================================
# Combined Dashboard Endpoint
# ============================================================================


@router.get("/dashboard", response_model=dict[str, Any])
async def get_signal_dashboard(
    strategy_id: UUID | None = Query(None, description="Filter by strategy ID"),
    aggregator: SignalAggregator = Depends(get_signal_aggregator),
    collector: StdoutCollector = Depends(get_stdout_collector),
) -> dict[str, Any]:
    """Get combined signal and stdout dashboard data."""
    result: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "signals": aggregator.to_dict(strategy_id),
    }

    if strategy_id is not None:
        result["stdout"] = collector.to_dict(strategy_id)
    else:
        result["stdout_strategies"] = [
            collector.to_dict(sid) for sid in collector.get_all_strategy_ids()
        ]

    return result
