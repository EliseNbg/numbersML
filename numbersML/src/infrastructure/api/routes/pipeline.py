"""
Pipeline API endpoints.

Provides REST API for pipeline control:
- Start/Stop pipeline
- Get status
- Manage active symbols
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional

from src.pipeline.service import PipelineManager, _pipeline_manager

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def get_pipeline_manager() -> PipelineManager:
    """Get pipeline manager instance."""
    if _pipeline_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline manager not initialized",
        )
    return _pipeline_manager


def set_pipeline_manager(manager: PipelineManager) -> None:
    """Set pipeline manager instance."""
    global _pipeline_manager
    _pipeline_manager = manager


@router.get(
    "/status",
    response_model=Dict[str, Any],
    summary="Get pipeline status",
    description="Get current status of the trade pipeline",
)
async def get_status(
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> Dict[str, Any]:
    """
    Get pipeline status.
    
    Returns:
        Status dictionary with:
        - is_running: Whether pipeline is running
        - symbols: List of active symbols
        - uptime_seconds: Pipeline uptime
        - trades_per_second: Current trade rate
        - trades_processed: Total trades processed
        - candles_written: Total candles written
        - recovery_events: Number of gap recoveries
    """
    statuses = manager.get_all_statuses()
    
    if not statuses:
        return {
            'is_running': False,
            'symbols': [],
            'message': 'Pipeline not started',
        }
    
    # Aggregate statuses
    all_symbols = []
    total_trades = 0
    total_candles = 0
    
    for pid, status_dict in statuses.items():
        if status_dict:
            all_symbols.extend(status_dict.get('symbols', []))
            total_trades += status_dict.get('trades_processed', 0)
            total_candles += status_dict.get('candles_written', 0)
    
    return {
        'is_running': any(s.get('is_running', False) for s in statuses.values()),
        'symbols': list(set(all_symbols)),
        'trades_processed': total_trades,
        'candles_written': total_candles,
        'pipelines': len(statuses),
    }


@router.post(
    "/start",
    summary="Start pipeline",
    description="Start the trade pipeline for active symbols",
)
async def start_pipeline(
    symbols: Optional[List[str]] = None,
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> Dict[str, Any]:
    """
    Start pipeline.
    
    Args:
        symbols: Optional list of symbols (default: all active symbols)
    
    Returns:
        Start result
    """
    if symbols is None:
        # Use default pipeline
        symbols = []
    
    pipeline_id = 'default'
    
    success = await manager.start_pipeline(
        symbols=symbols or [],
        pipeline_id=pipeline_id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to start pipeline (already running or no active symbols)",
        )
    
    return {
        'message': 'Pipeline started',
        'pipeline_id': pipeline_id,
        'symbols': symbols or 'all active symbols',
    }


@router.post(
    "/stop",
    summary="Stop pipeline",
    description="Stop the trade pipeline gracefully",
)
async def stop_pipeline(
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> Dict[str, Any]:
    """
    Stop pipeline.
    
    Returns:
        Stop result
    """
    pipeline_id = 'default'
    
    success = await manager.stop_pipeline(pipeline_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pipeline not running",
        )
    
    return {
        'message': 'Pipeline stopped',
        'pipeline_id': pipeline_id,
    }


@router.get(
    "/symbols",
    response_model=List[str],
    summary="Get active symbols",
    description="Get list of symbols being processed",
)
async def get_symbols(
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> List[str]:
    """
    Get active symbols.
    
    Returns:
        List of symbol names
    """
    status = manager.get_pipeline_status()
    
    if not status:
        return []
    
    return status.get('symbols', [])


@router.get(
    "/stats",
    response_model=Dict[str, Any],
    summary="Get detailed statistics",
    description="Get detailed pipeline statistics",
)
async def get_stats(
    manager: PipelineManager = Depends(get_pipeline_manager),
) -> Dict[str, Any]:
    """
    Get detailed statistics.
    
    Returns:
        Statistics dictionary with:
        - pipeline: Overall pipeline stats
        - aggregator: Aggregation stats
        - database_writer: Database write stats
        - recovery: Per-symbol recovery stats
        - websocket: WebSocket stats
    """
    statuses = manager.get_all_statuses()
    
    if not statuses:
        return {
            'message': 'Pipeline not running',
        }
    
    # Get detailed stats from first pipeline
    for pipeline in manager._pipelines.values():
        return pipeline.get_detailed_stats()
    
    return {}
