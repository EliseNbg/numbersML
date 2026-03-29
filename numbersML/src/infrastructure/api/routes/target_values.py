"""
Target Value API endpoints.

Provides REST API for ML target value calculation and retrieval:
- GET /api/target-values?symbol=BTC/USDC&hours=2&window_size=300 - Get target values
- POST /api/target-values/calculate - Trigger batch calculation
"""

import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from src.infrastructure.database import get_db_pool_async
from src.pipeline.target_value import batch_calculate_numpy

router = APIRouter(prefix="/api/target-values", tags=["target-values"])


@router.get(
    "",
    summary="Get target values",
    description="Get candle close prices and calculated target values for a symbol",
)
async def get_target_values(
    symbol: str = Query(..., description="Symbol name (e.g., 'BTC/USDC')"),
    hours: int = Query(default=2, ge=1, le=168),
    window_size: int = Query(default=300, ge=1, le=5000),
) -> List[Dict[str, Any]]:
    """
    Get candle data with target values.

    Returns candles with close price and calculated target value.
    Target values are computed on-the-fly using the Hanning filter.
    """
    db_pool = await get_db_pool_async()
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval(
            "SELECT id FROM symbols WHERE symbol = $1", symbol
        )
        if not symbol_id:
            return []

        rows = await conn.fetch(
            """
            SELECT time, open, high, low, close, volume
            FROM candles_1s
            WHERE symbol_id = $1 AND time >= $2
            ORDER BY time
            """,
            symbol_id, since,
        )

    if not rows:
        return []

    # Extract prices and compute target values
    prices = [float(r['close']) for r in rows]
    targets = batch_calculate_numpy(prices, window_size)

    return [
        {
            'time': int(r['time'].timestamp()),
            'open': float(r['open']),
            'high': float(r['high']),
            'low': float(r['low']),
            'close': float(r['close']),
            'volume': float(r['volume']),
            'target_value': round(float(targets[i]), 8) if i < len(targets) else None,
        }
        for i, r in enumerate(rows)
    ]


@router.post(
    "/calculate",
    summary="Calculate and store target values",
    description="Batch calculate target values for a symbol and store in candles_1s",
)
async def calculate_target_values(
    symbol: str = Query(..., description="Symbol name"),
    window_size: int = Query(default=300, ge=1, le=5000),
    from_time: Optional[str] = Query(default=None, description="Start time (YYYY-MM-DD HH:MM:SS)"),
    to_time: Optional[str] = Query(default=None, description="End time (YYYY-MM-DD HH:MM:SS)"),
) -> Dict[str, Any]:
    """
    Calculate and store target values in candles_1s.target_value.

    Processes all candles for the symbol in the time range.
    Uses Hanning filter with given window_size.
    """
    db_pool = await get_db_pool_async()

    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval(
            "SELECT id FROM symbols WHERE symbol = $1", symbol
        )
        if not symbol_id:
            return {'error': f'Symbol not found: {symbol}', 'updated': 0}

        # Build query
        if from_time:
            from_dt = datetime.strptime(from_time, '%Y-%m-%d %H:%M:%S')
        else:
            from_dt = datetime(2020, 1, 1)

        if to_time:
            to_dt = datetime.strptime(to_time, '%Y-%m-%d %H:%M:%S')
        else:
            to_dt = datetime(2100, 1, 1)

        # Load ALL candles for this symbol (need history for edges)
        rows = await conn.fetch(
            """
            SELECT time, close
            FROM candles_1s
            WHERE symbol_id = $1
            ORDER BY time
            """,
            symbol_id,
        )

        if not rows:
            return {'error': 'No candles found', 'updated': 0}

        # Calculate target values
        prices = [float(r['close']) for r in rows]
        targets = batch_calculate_numpy(prices, window_size)

        # Update in batches
        batch_size = 5000
        updated = 0
        for i in range(0, len(rows), batch_size):
            batch = [
                (targets[j], rows[j]['time'].replace(tzinfo=None))
                for j in range(i, min(i + batch_size, len(rows)))
                if from_dt <= rows[j]['time'] <= to_dt
            ]
            if batch:
                await conn.executemany(
                    """
                    UPDATE candles_1s SET target_value = $1
                    WHERE symbol_id = $2 AND time = $3
                    """,
                    [(b[0], symbol_id, b[1]) for b in batch],
                )
                updated += len(batch)

        return {
            'symbol': symbol,
            'window_size': window_size,
            'updated': updated,
            'total_candles': len(rows),
        }
