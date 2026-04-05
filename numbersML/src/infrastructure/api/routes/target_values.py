"""
Target Value API endpoints.

Provides REST API for ML target value calculation and retrieval:
- GET /api/target-values?symbol=BTC/USDC&hours=2&response_time=200 - Get target data
- POST /api/target-values/calculate - Trigger batch calculation
"""

import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from src.infrastructure.database import get_db_pool_async
from src.pipeline.target_value import batch_calculate_target_data

router = APIRouter(prefix="/api/target-values", tags=["target-values"])


@router.get(
    "",
    summary="Get target values",
    description="Get candle data with filtered trends and market state",
)
async def get_target_values(
    symbol: str = Query(..., description="Symbol name (e.g., 'BTC/USDC')"),
    hours: int = Query(default=2, ge=1, le=168),
    response_time: float = Query(default=200.0, ge=1.0, le=1000.0),
    use_kalman: bool = Query(default=True, description="Use Kalman Filter (True) or Hanning (False)"),
) -> List[Dict[str, Any]]:
    """
    Get candle data with target values.

    Returns candles with close price and calculated market state.
    Target data includes filtered_value (smooth wave), diff, trend direction, velocity.
    """
    db_pool = await get_db_pool_async()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

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

    # Extract prices and compute target data
    prices = [float(r['close']) for r in rows]
    target_data_list = batch_calculate_target_data(prices, response_time=response_time, use_kalman=use_kalman)

    return [
        {
            'time': int(r['time'].timestamp()),
            'open': float(r['open']),
            'high': float(r['high']),
            'low': float(r['low']),
            'close': float(r['close']),
            'volume': float(r['volume']),
            'target_value': target_data_list[i] if i < len(target_data_list) else None,
            'filter': 'kalman' if use_kalman else 'hanning',
            'response_time': response_time if use_kalman else None,
        }
        for i, r in enumerate(rows)
    ]


@router.post(
    "/calculate",
    summary="Calculate and store target values",
    description="Batch calculate target data for a symbol and store in candles_1s as JSONB",
)
async def calculate_target_values(
    symbol: str = Query(..., description="Symbol name"),
    response_time: float = Query(default=200.0, ge=1.0, le=1000.0),
    use_kalman: bool = Query(default=True, description="Use Kalman Filter (True) or Hanning (False)"),
    from_time: Optional[str] = Query(default=None, description="Start time (YYYY-MM-DD HH:MM:SS)"),
    to_time: Optional[str] = Query(default=None, description="End time (YYYY-MM-DD HH:MM:SS)"),
    hours: Optional[int] = Query(default=None, ge=1, le=168, description="Calculate last N hours"),
) -> Dict[str, Any]:
    """
    Calculate and store target values in candles_1s.target_value as JSONB.

    Processes candles for the symbol. Kalman Filter (default) needs the full
    history for optimal smoothing. Only candles in the time range are
    stored with target_value.

    Stores JSONB structure:
    {
        "filtered_value": 105.5,  // Smooth Kalman trend (WAVES)
        "close": 103.2,           // Current candle close
        "diff": -2.3,             // Deviation from trend
        "trend": "up",            // or "down", "flat"
        "velocity": 0.15          // Rate of change
    }
    """
    db_pool = await get_db_pool_async()

    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval(
            "SELECT id FROM symbols WHERE symbol = $1", symbol
        )
        if not symbol_id:
            return {'error': f'Symbol not found: {symbol}', 'updated': 0}

        # Build time range
        now = datetime.now(timezone.utc)
        if hours is not None:
            from_dt = now - timedelta(hours=hours)
            to_dt = now
        elif from_time:
            from_dt = datetime.strptime(from_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            to_dt = datetime.strptime(to_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc) if to_time else now
        else:
            from_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
            to_dt = now

        # Load ALL candles for this symbol (need history for Kalman)
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

        # Calculate target data (JSON structures)
        prices = [float(r['close']) for r in rows]
        target_data_list = batch_calculate_target_data(prices, response_time=response_time, use_kalman=use_kalman)

        # Update in batches
        batch_size = 5000
        updated = 0
        for i in range(0, len(rows), batch_size):
            batch = [
                (json.dumps(target_data_list[j]), rows[j]['time'])
                for j in range(i, min(i + batch_size, len(rows)))
                if from_dt <= rows[j]['time'] <= to_dt and target_data_list[j] is not None
            ]
            if batch:
                await conn.executemany(
                    """
                    UPDATE candles_1s SET target_value = $1::jsonb
                    WHERE symbol_id = $2 AND time = $3
                    """,
                    [(b[0], symbol_id, b[1]) for b in batch],
                )
                updated += len(batch)

        return {
            'symbol': symbol,
            'filter': 'kalman' if use_kalman else 'hanning',
            'response_time': response_time if use_kalman else None,
            'updated': updated,
            'total_candles': len(rows),
        }
