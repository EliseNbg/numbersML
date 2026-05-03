"""PostgreSQL implementation of strategy runtime event repository."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from src.domain.repositories.runtime_event_repository import StrategyRuntimeEventRepository
from src.domain.strategies.runtime import StrategyLifecycleEvent


class StrategyRuntimeEventRepositoryPG(StrategyRuntimeEventRepository):
    """PostgreSQL-backed runtime event repository.

    Persists strategy lifecycle events to the strategy_events table.
    Events are append-only and never updated.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self.conn = connection

    async def save(self, entity: StrategyLifecycleEvent) -> StrategyLifecycleEvent:
        """Persist a lifecycle event.

        Args:
            entity: The lifecycle event to persist

        Returns:
            The persisted event (unchanged)
        """
        await self.conn.fetchrow(
            """
            INSERT INTO strategy_events (
                id, strategy_id, strategy_version_id, event_type,
                event_payload, actor, created_at
            ) VALUES (
                $1, $2,
                (SELECT id FROM strategy_versions
                 WHERE strategy_id = $2 AND version = $3),
                $4, $5, $6, $7
            )
            """,
            entity.event_id,
            entity.strategy_id,
            entity.strategy_version,
            entity.event_type,
            json.dumps(entity.details),
            entity.trigger if hasattr(entity, "trigger") else "system",
            entity.occurred_at,
        )
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        """Delete an event (soft delete not supported - events are immutable).

        Note: This is generally discouraged as events form an audit trail.
        """
        result = await self.conn.execute("DELETE FROM strategy_events WHERE id = $1", entity_id)
        return result == "DELETE 1"

    async def get_events_for_strategy(
        self,
        strategy_id: UUID,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        event_types: list[str] | None = None,
        limit: int = 1000,
    ) -> list[StrategyLifecycleEvent]:
        """Fetch lifecycle events for a specific strategy."""
        query = """
            SELECT e.*, s.name as strategy_name, sv.version as strategy_version
            FROM strategy_events e
            JOIN strategies s ON e.strategy_id = s.id
            LEFT JOIN strategy_versions sv ON e.strategy_version_id = sv.id
            WHERE e.strategy_id = $1
        """
        params = [strategy_id]
        param_count = 1

        if from_time is not None:
            param_count += 1
            query += f" AND e.created_at >= ${param_count}"
            params.append(from_time)

        if to_time is not None:
            param_count += 1
            query += f" AND e.created_at < ${param_count}"
            params.append(to_time)

        if event_types:
            param_count += 1
            query += f" AND e.event_type = ANY(${param_count})"
            params.append(event_types)

        query += " ORDER BY e.created_at DESC LIMIT $"
        param_count += 1
        query += str(param_count)
        params.append(limit)

        rows = await self.conn.fetch(query, *params)
        return [self._map_event(row) for row in rows]

    async def get_events_by_type(
        self,
        event_type: str,
        from_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[StrategyLifecycleEvent]:
        """Fetch events of a specific type across all strategies."""
        query = """
            SELECT e.*, s.name as strategy_name, sv.version as strategy_version
            FROM strategy_events e
            JOIN strategies s ON e.strategy_id = s.id
            LEFT JOIN strategy_versions sv ON e.strategy_version_id = sv.id
            WHERE e.event_type = $1
        """
        params = [event_type]

        if from_time is not None:
            query += " AND e.created_at >= $2"
            params.append(from_time)

        query += " ORDER BY e.created_at DESC LIMIT $"
        if from_time is not None:
            query += "3"
            params.append(limit)
        else:
            query += "2"
            params.append(limit)

        rows = await self.conn.fetch(query, *params)
        return [self._map_event(row) for row in rows]

    async def get_current_states(self) -> list[dict[str, Any]]:
        """Get the most recent state for each strategy."""
        rows = await self.conn.fetch("""
            SELECT DISTINCT ON (e.strategy_id)
                e.strategy_id,
                s.name as strategy_name,
                sv.version as strategy_version,
                e.event_type,
                e.event_payload,
                e.created_at as last_state_change
            FROM strategy_events e
            JOIN strategies s ON e.strategy_id = s.id
            LEFT JOIN strategy_versions sv ON e.strategy_version_id = sv.id
            WHERE e.event_type = 'StrategyLifecycleEvent'
            ORDER BY e.strategy_id, e.created_at DESC
        """)
        return [dict(r) for r in rows]

    async def get_error_events(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[StrategyLifecycleEvent]:
        """Get recent error state transitions."""
        query = """
            SELECT e.*, s.name as strategy_name, sv.version as strategy_version
            FROM strategy_events e
            JOIN strategies s ON e.strategy_id = s.id
            LEFT JOIN strategy_versions sv ON e.strategy_version_id = sv.id
            WHERE e.event_type = 'StrategyLifecycleEvent'
              AND (e.event_payload->>'to_state') = '"ERROR"'
        """
        params: list[Any] = []

        if since is not None:
            query += " AND e.created_at >= $"
            params.append(1)
            params.append(since)

        query += " ORDER BY e.created_at DESC LIMIT $"
        if since is not None:
            query += "2"
            params.append(limit)
        else:
            query = query.replace(
                "WHERE e.event_type = 'StrategyLifecycleEvent'",
                "WHERE e.event_type = 'StrategyLifecycleEvent'",
            )
            query += "1"
            params = [limit]

        rows = (
            await self.conn.fetch(query, *params) if since else await self.conn.fetch(query, limit)
        )
        return [self._map_event(row) for row in rows]

    async def get_by_id(self, entity_id: UUID) -> StrategyLifecycleEvent | None:
        """Get a single event by ID."""
        row = await self.conn.fetchrow(
            """
            SELECT e.*, s.name as strategy_name, sv.version as strategy_version
            FROM strategy_events e
            JOIN strategies s ON e.strategy_id = s.id
            LEFT JOIN strategy_versions sv ON e.strategy_version_id = sv.id
            WHERE e.id = $1
        """,
            entity_id,
        )
        if row is None:
            return None
        return self._map_event(row)

    async def get_all(self) -> list[StrategyLifecycleEvent]:
        """Get all events (most recent first)."""
        rows = await self.conn.fetch("""
            SELECT e.*, s.name as strategy_name, sv.version as strategy_version
            FROM strategy_events e
            JOIN strategies s ON e.strategy_id = s.id
            LEFT JOIN strategy_versions sv ON e.strategy_version_id = sv.id
            ORDER BY e.created_at DESC
        """)
        return [self._map_event(row) for row in rows]

    @staticmethod
    def _map_event(row: asyncpg.Record) -> StrategyLifecycleEvent:
        """Map a database row to a StrategyLifecycleEvent."""
        payload = row["event_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        from_state = StrategyInstanceState(payload.get("from_state", "STOPPED"))
        to_state = StrategyInstanceState(payload.get("to_state", "STOPPED"))
        return StrategyLifecycleEvent(
            event_id=row["id"],
            strategy_id=row["strategy_id"],
            strategy_name=row["strategy_name"],
            strategy_version=row["strategy_version"] or 1,
            from_state=from_state,
            to_state=to_state,
            trigger=payload.get("trigger", "system"),
            details=payload.get("details", {}),
            occurred_at=_coerce_datetime(row["created_at"]),
        )


def _coerce_datetime(value: datetime) -> datetime:
    """Normalize datetime values from asyncpg records."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
