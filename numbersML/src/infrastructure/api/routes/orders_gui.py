"""Order dashboard API endpoints."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from src.infrastructure.database import get_db_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/dashboard")
async def get_order_dashboard() -> dict:
    """Full order dashboard state.

    Returns:
        Dict with orders, stats, and active keys.
    """
    pool = get_db_pool()

    async with pool.acquire() as conn:
        orders = await conn.fetch(
            """
            SELECT o.*, s.name as strategy_name
            FROM orders o
            LEFT JOIN strategies s ON o.strategy_id = s.id
            ORDER BY o.created_at DESC
            LIMIT 100
            """
        )

        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') as total_today,
                COUNT(*) FILTER (WHERE status = 'FILLED' AND created_at >= NOW() - INTERVAL '24 hours') as filled_today,
                COUNT(*) FILTER (WHERE status = 'REJECTED' AND created_at >= NOW() - INTERVAL '24 hours') as rejected_today,
                COUNT(*) FILTER (WHERE status = 'CANCELED' AND created_at >= NOW() - INTERVAL '24 hours') as cancelled_today,
                AVG(COALESCE(latency_ms, 0)) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') as avg_latency
            FROM orders
            """
        )

    total_today = stats["total_today"] or 0
    filled_today = stats["filled_today"] or 0
    fill_rate = (filled_today / total_today * 100) if total_today > 0 else 0

    return {
        "orders": [dict(o) for o in orders],
        "stats": {
            "total_orders_today": total_today,
            "filled": filled_today,
            "rejected": stats["rejected_today"] or 0,
            "cancelled": stats["cancelled_today"] or 0,
            "fill_rate_pct": round(fill_rate, 1),
            "avg_latency_ms": round(stats["avg_latency"] or 0, 1),
        },
    }


@router.get("/stats")
async def get_order_stats() -> dict:
    """Order statistics (fill rate, avg latency, etc.).

    Returns:
        Statistics dict.
    """
    pool = get_db_pool()

    async with pool.acquire() as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'FILLED') as filled,
                COUNT(*) FILTER (WHERE status = 'REJECTED') as rejected,
                COUNT(*) FILTER (WHERE status = 'CANCELED') as canceled,
                AVG(COALESCE(latency_ms, 0)) as avg_latency,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') as today
            FROM orders
            """
        )

    total = stats["total"] or 0
    filled = stats["filled"] or 0
    fill_rate = (filled / total * 100) if total > 0 else 0

    return {
        "total": total,
        "filled": filled,
        "rejected": stats["rejected"] or 0,
        "canceled": stats["canceled"] or 0,
        "fill_rate_pct": round(fill_rate, 1),
        "avg_latency_ms": round(stats["avg_latency"] or 0, 1),
        "today": stats["today"] or 0,
    }


@router.get("/export")
async def export_orders_csv(
    limit: int = Query(default=1000, le=10000),
) -> str:
    """Export orders as CSV.

    Args:
        limit: Maximum number of orders to export.

    Returns:
        CSV formatted string.
    """
    pool = get_db_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT $1",
            limit,
        )

    if not rows:
        return ""

    headers = list(rows[0].keys())
    lines = [",".join(headers)]

    for row in rows:
        values = []
        for h in headers:
            val = row[h]
            if val is None:
                values.append("")
            elif isinstance(val, str) and ("," in val or '"' in val):
                values.append(f'"{val.replace(chr(34), chr(34)+chr(34))}"')
            else:
                values.append(str(val))
        lines.append(",".join(values))

    return "\n".join(lines)


@router.get("/{order_id}")
async def get_order_details(order_id: UUID) -> dict:
    """Order details with execution history.

    Args:
        order_id: Order UUID.

    Returns:
        Order details dict.

    Raises:
        HTTPException: 404 if not found.
    """
    pool = get_db_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return dict(row)


@router.post("/{order_id}/cancel")
async def cancel_order(order_id: UUID) -> dict:
    """Cancel an order.

    Args:
        order_id: Order UUID.

    Returns:
        Cancel result.

    Raises:
        HTTPException: 404 if not found.
    """
    pool = get_db_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status FROM orders WHERE id = $1",
            order_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if row["status"] in ("FILLED", "CANCELED", "REJECTED"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status: {row['status']}",
        )

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET status = 'CANCELED', updated_at = NOW() WHERE id = $1",
            order_id,
        )

    return {"status": "canceled", "order_id": str(order_id)}
