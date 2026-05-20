"""
Candles API endpoints.

Provides REST API for candle data:
- GET /api/candles?symbol=BTC/USDC&seconds=60
- GET /api/candles/indicators?symbol=BTC/USDC&seconds=60
- GET /api/candles/range?symbol=BTC/USDC&start=ISO&end=ISO
- GET /api/candles/indicators/range?symbol=BTC/USDC&start=ISO&end=ISO
"""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/candles", tags=["candles"])


@router.get(
    "",
    summary="Get candle history",
    description="Get 1-second candle data for a symbol",
)
async def get_candles(
    symbol: str = Query(..., description="Symbol name (e.g., 'BTC/USDC')"),
    seconds: int = Query(default=60, ge=1, le=86400),
) -> list[dict[str, Any]]:
    """
    Get candle history for a symbol.
    """
    db_pool = await get_db_pool_async()

    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
        if not symbol_id:
            return []

        rows = await conn.fetch(
            """
            SELECT time, open, high, low, close, volume, trade_count
            FROM candles_1s
            WHERE symbol_id = $1
            ORDER BY time DESC
            LIMIT $2
            """,
            symbol_id,
            seconds,
        )

    return [
        {
            "time": int(r["time"].timestamp()),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]),
            "trades": r["trade_count"],
        }
        for r in reversed(rows)
    ]


@router.get(
    "/indicators",
    summary="Get indicator values per candle",
    description="Get calculated indicator values for chart overlays",
)
async def get_candle_indicators(
    symbol: str = Query(..., description="Symbol name"),
    seconds: int = Query(default=60, ge=1, le=86400),
) -> list[dict[str, Any]]:
    """
    Get indicator values for a symbol.
    """
    db_pool = await get_db_pool_async()

    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
        if not symbol_id:
            return []

        rows = await conn.fetch(
            """
            SELECT time, price, values
            FROM candle_indicators
            WHERE symbol_id = $1
            ORDER BY time DESC
            LIMIT $2
            """,
            symbol_id,
            seconds,
        )

    return [
        {
            "time": int(r["time"].timestamp()),
            "price": float(r["price"]),
            "values": (
                r["values"]
                if isinstance(r["values"], dict)
                else (json.loads(r["values"]) if r["values"] else {})
            ),
            "keys": (
                list(r["values"].keys())
                if isinstance(r["values"], dict)
                else (list(json.loads(r["values"]).keys()) if r["values"] else [])
            ),
        }
        for r in reversed(rows)
    ]


@router.get(
    "/range",
    summary="Get candle history for a time range",
    description="Get 1-second candle data for a symbol within a specific time range",
)
async def get_candles_range(
    symbol: str = Query(..., description="Symbol name (e.g., 'BTC/USDC')"),
    start: str = Query(..., description="Start time in ISO format"),
    end: str = Query(..., description="End time in ISO format"),
) -> list[dict[str, Any]]:
    """
    Get candle history for a symbol within a time range.
    """
    db_pool = await get_db_pool_async()

    try:
        start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return []

    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
        if not symbol_id:
            return []

        rows = await conn.fetch(
            """
            SELECT time, open, high, low, close, volume, trade_count
            FROM candles_1s
            WHERE symbol_id = $1 AND time >= $2 AND time <= $3
            ORDER BY time ASC
            """,
            symbol_id,
            start_time,
            end_time,
        )

    return [
        {
            "time": int(r["time"].timestamp()),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]),
            "trades": r["trade_count"],
        }
        for r in rows
    ]


@router.get(
    "/indicators/range",
    summary="Get indicator values for a time range",
    description="Get calculated indicator values for chart overlays within a specific time range",
)
async def get_candle_indicators_range(
    symbol: str = Query(..., description="Symbol name"),
    start: str = Query(..., description="Start time in ISO format"),
    end: str = Query(..., description="End time in ISO format"),
) -> list[dict[str, Any]]:
    """
    Get indicator values for a symbol within a time range.
    """
    db_pool = await get_db_pool_async()

    try:
        start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return []

    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
        if not symbol_id:
            return []

        rows = await conn.fetch(
            """
            SELECT time, price, values
            FROM candle_indicators
            WHERE symbol_id = $1 AND time >= $2 AND time <= $3
            ORDER BY time ASC
            """,
            symbol_id,
            start_time,
            end_time,
        )

    return [
        {
            "time": int(r["time"].timestamp()),
            "price": float(r["price"]),
            "values": (
                r["values"]
                if isinstance(r["values"], dict)
                else (json.loads(r["values"]) if r["values"] else {})
            ),
            "keys": (
                list(r["values"].keys())
                if isinstance(r["values"], dict)
                else (list(json.loads(r["values"]).keys()) if r["values"] else [])
            ),
        }
        for r in rows
    ]
