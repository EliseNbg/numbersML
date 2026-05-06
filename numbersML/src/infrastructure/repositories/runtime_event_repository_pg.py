"""PostgreSQL implementation of algorithm runtime event repository."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from src.domain.repositories.runtime_event_repository import AlgorithmRuntimeEventRepository
from src.domain.algorithms.runtime import AlgorithmLifecycleEvent
from src.domain.algorithms.strategy_instance import StrategyInstanceState


class AlgorithmRuntimeEventRepositoryPG(AlgorithmRuntimeEventRepository):
    """PostgreSQL-backed runtime event repository.

    Persists algorithm lifecycle events to the algorithm_events table.
    Events are append-only and never updated.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self.conn = connection

    async def save(self, entity: AlgorithmLifecycleEvent) -> AlgorithmLifecycleEvent:
        """Persist a lifecycle event.

        Args:
            entity: The lifecycle event to persist

        Returns:
            The persisted event (unchanged)
        """
        await self.conn.fetchrow(
            """
            INSERT INTO algorithm_events (
                id, algorithm_id, algorithm_version_id, event_type,
                event_payload, actor, created_at
            ) VALUES (
                $1, $2,
                (SELECT id FROM algorithm_versions
                 WHERE algorithm_id = $2 AND version = $3),
                $4, $5, $6, $7
            )
            """,
            entity.event_id,
            entity.algorithm_id,
            entity.algorithm_version,
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
        result = await self.conn.execute("DELETE FROM algorithm_events WHERE id = $1", entity_id)
        return result == "DELETE 1"

    async def get_events_for_algorithm(
        self,
        algorithm_id: UUID,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        event_types: list[str] | None = None,
        limit: int = 1000,
    ) -> list[AlgorithmLifecycleEvent]:
        """Fetch lifecycle events for a specific algorithm."""
        query = """
            SELECT e.*, s.name as algorithm_name, sv.version as algorithm_version
            FROM algorithm_events e
            JOIN algorithms s ON e.algorithm_id = s.id
            LEFT JOIN algorithm_versions sv ON e.algorithm_version_id = sv.id
            WHERE e.algorithm_id = $1
        """
        params = [algorithm_id]
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
    ) -> list[AlgorithmLifecycleEvent]:
        """Fetch events of a specific type across all algorithms."""
        query = """
            SELECT e.*, s.name as algorithm_name, sv.version as algorithm_version
            FROM algorithm_events e
            JOIN algorithms s ON e.algorithm_id = s.id
            LEFT JOIN algorithm_versions sv ON e.algorithm_version_id = sv.id
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
        """Get the most recent state for each algorithm."""
        rows = await self.conn.fetch("""
            SELECT DISTINCT ON (e.algorithm_id)
                e.algorithm_id,
                s.name as algorithm_name,
                sv.version as algorithm_version,
                e.event_type,
                e.event_payload,
                e.created_at as last_state_change
            FROM algorithm_events e
            JOIN algorithms s ON e.algorithm_id = s.id
            LEFT JOIN algorithm_versions sv ON e.algorithm_version_id = sv.id
            WHERE e.event_type = 'AlgorithmLifecycleEvent'
            ORDER BY e.algorithm_id, e.created_at DESC
        """)
        return [dict(r) for r in rows]

    async def get_error_events(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AlgorithmLifecycleEvent]:
        """Get recent error state transitions."""
        query = """
            SELECT e.*, s.name as algorithm_name, sv.version as algorithm_version
            FROM algorithm_events e
            JOIN algorithms s ON e.algorithm_id = s.id
            LEFT JOIN algorithm_versions sv ON e.algorithm_version_id = sv.id
            WHERE e.event_type = 'AlgorithmLifecycleEvent'
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
                "WHERE e.event_type = 'AlgorithmLifecycleEvent'",
                "WHERE e.event_type = 'AlgorithmLifecycleEvent'",
            )
            query += "1"
            params = [limit]

        rows = (
            await self.conn.fetch(query, *params) if since else await self.conn.fetch(query, limit)
        )
        return [self._map_event(row) for row in rows]

    async def get_by_id(self, entity_id: UUID) -> AlgorithmLifecycleEvent | None:
        """Get a single event by ID."""
        row = await self.conn.fetchrow(
            """
            SELECT e.*, s.name as algorithm_name, sv.version as algorithm_version
            FROM algorithm_events e
            JOIN algorithms s ON e.algorithm_id = s.id
            LEFT JOIN algorithm_versions sv ON e.algorithm_version_id = sv.id
            WHERE e.id = $1
        """,
            entity_id,
        )
        if row is None:
            return None
        return self._map_event(row)

    async def get_all(self) -> list[AlgorithmLifecycleEvent]:
        """Get all events (most recent first)."""
        rows = await self.conn.fetch("""
            SELECT e.*, s.name as algorithm_name, sv.version as algorithm_version
            FROM algorithm_events e
            JOIN algorithms s ON e.algorithm_id = s.id
            LEFT JOIN algorithm_versions sv ON e.algorithm_version_id = sv.id
            ORDER BY e.created_at DESC
        """)
        return [self._map_event(row) for row in rows]

    @staticmethod
    def _map_event(row: asyncpg.Record) -> AlgorithmLifecycleEvent:
        """Map a database row to a AlgorithmLifecycleEvent."""
        payload = row["event_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        from_state = StrategyInstanceState(payload.get("from_state", "stopped"))
        to_state = StrategyInstanceState(payload.get("to_state", "stopped"))
        return AlgorithmLifecycleEvent(
            event_id=row["id"],
            algorithm_id=row["algorithm_id"],
            algorithm_name=row["algorithm_name"],
            algorithm_version=row["algorithm_version"] or 1,
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
