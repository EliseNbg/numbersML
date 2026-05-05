"""PostgreSQL implementation of algorithm backtest repository."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg


class AlgorithmBacktestRepositoryPG:
    """Repository for algorithm backtest results."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        self.conn = connection

    async def save(
        self,
        algorithm_id: UUID,
        algorithm_version_id: UUID | None,
        time_range_start: datetime,
        time_range_end: datetime,
        initial_balance: float,
        final_balance: float | None,
        metrics: dict[str, Any],
        trades: list[dict[str, Any]] | None = None,
        equity_curve: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        """Save a backtest result.

        Args:
            algorithm_id: Algorithm ID this backtest belongs to
            algorithm_version_id: Optional version ID used for backtest
            time_range_start: Backtest start time
            time_range_end: Backtest end time
            initial_balance: Starting capital
            final_balance: Ending capital
            metrics: Performance metrics dictionary
            trades: List of individual trades
            equity_curve: Equity curve data points
            metadata: Additional metadata
            created_by: User/actor who created this backtest

        Returns:
            Saved backtest record as dictionary
        """

        def _json_serializable(v):
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, (int, float, str, bool, type(None))):
                return v
            return str(v)

        trades_json = json.dumps(
            [{k: _json_serializable(v) for k, v in t.items()} for t in (trades or [])]
        )
        equity_json = json.dumps(
            [{k: _json_serializable(v) for k, v in p.items()} for p in (equity_curve or [])]
        )
        metrics_json = json.dumps(metrics)

        row = await self.conn.fetchrow(
            """
            INSERT INTO algorithm_backtests (
                algorithm_id,
                algorithm_version_id,
                time_range_start,
                time_range_end,
                initial_balance,
                final_balance,
                metrics,
                trades,
                equity_curve,
                created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            algorithm_id,
            algorithm_version_id,
            time_range_start,
            time_range_end,
            initial_balance,
            final_balance,
            metrics_json,
            trades_json,
            equity_json,
            created_by,
        )
        return self._map_backtest(row)

    async def get(self, backtest_id: UUID) -> dict[str, Any] | None:
        """Get a backtest result by ID.

        Args:
            backtest_id: Backtest record ID

        Returns:
            Backtest result or None if not found
        """
        row = await self.conn.fetchrow(
            "SELECT * FROM algorithm_backtests WHERE id = $1",
            backtest_id,
        )
        if row is None:
            return None
        return self._map_backtest(row)

    async def list_for_algorithm(
        self,
        algorithm_id: UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List all backtests for a algorithm.

        Args:
            algorithm_id: Algorithm ID to filter by
            limit: Maximum number of results to return

        Returns:
            List of backtest results
        """
        rows = await self.conn.fetch(
            """
            SELECT * FROM algorithm_backtests
            WHERE algorithm_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            algorithm_id,
            limit,
        )
        return [self._map_backtest(row) for row in rows]

    @staticmethod
    def _map_backtest(row: asyncpg.Record) -> dict[str, Any]:
        """Map a database row to a backtest result dictionary.

        Args:
            row: Database record

        Returns:
            Backtest result as serializable dict
        """
        config_payload = row["metrics"]
        if isinstance(config_payload, str):
            config_payload = json.loads(config_payload)

        trades_payload = row["trades"]
        if isinstance(trades_payload, str):
            trades_payload = json.loads(trades_payload)

        equity_payload = row["equity_curve"]
        if isinstance(equity_payload, str):
            equity_payload = json.loads(equity_payload)

        return {
            "id": row["id"],
            "algorithm_id": row["algorithm_id"],
            "algorithm_version_id": row["algorithm_version_id"],
            "time_range_start": _coerce_datetime(row["time_range_start"]),
            "time_range_end": _coerce_datetime(row["time_range_end"]),
            "initial_balance": float(row["initial_balance"]),
            "final_balance": float(row["final_balance"]) if row["final_balance"] else None,
            "metrics": dict(config_payload),
            "trades": list(trades_payload),
            "equity_curve": list(equity_payload),
            "created_by": row["created_by"],
            "created_at": _coerce_datetime(row["created_at"]),
        }


def _coerce_datetime(value: datetime) -> datetime:
    """Normalize datetime values from asyncpg records."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
