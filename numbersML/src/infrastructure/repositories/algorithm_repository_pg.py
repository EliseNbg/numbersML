"""PostgreSQL implementation of algorithm lifecycle repository."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from src.domain.repositories.algorithm_repository import AlgorithmRepository
from src.domain.algorithms.algorithm_config import AlgorithmConfigVersion, AlgorithmDefinition


class AlgorithmRepositoryPG(AlgorithmRepository):
    """Persist and query algorithm definitions and versioned configs."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        self.conn = connection

    async def get_by_id(self, entity_id: UUID) -> AlgorithmDefinition | None:
        row = await self.conn.fetchrow("SELECT * FROM algorithms WHERE id = $1", entity_id)
        if row is None:
            return None
        return self._map_algorithm(row)

    async def get_by_name(self, name: str) -> AlgorithmDefinition | None:
        row = await self.conn.fetchrow("SELECT * FROM algorithms WHERE name = $1", name)
        if row is None:
            return None
        return self._map_algorithm(row)

    async def get_all(self) -> list[AlgorithmDefinition]:
        rows = await self.conn.fetch("SELECT * FROM algorithms ORDER BY created_at DESC")
        return [self._map_algorithm(row) for row in rows]

    async def save(self, entity: AlgorithmDefinition) -> AlgorithmDefinition:
        row = await self.conn.fetchrow(
            """
            INSERT INTO algorithms (
                id, name, description, mode, status, current_version, created_by, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                mode = EXCLUDED.mode,
                status = EXCLUDED.status,
                current_version = EXCLUDED.current_version,
                updated_at = NOW()
            RETURNING *
            """,
            entity.id,
            entity.name,
            entity.description,
            entity.mode,
            entity.status,
            entity.current_version,
            entity.created_by,
            entity.created_at,
        )
        return self._map_algorithm(row)

    async def delete(self, entity_id: UUID) -> bool:
        result = await self.conn.execute("DELETE FROM algorithms WHERE id = $1", entity_id)
        return result == "DELETE 1"

    async def list_versions(self, algorithm_id: UUID) -> list[AlgorithmConfigVersion]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM algorithm_versions
            WHERE algorithm_id = $1
            ORDER BY version DESC
            """,
            algorithm_id,
        )
        return [self._map_version(row) for row in rows]

    async def create_version(
        self,
        algorithm_id: UUID,
        config: dict[str, Any],
        schema_version: int,
        created_by: str = "system",
    ) -> AlgorithmConfigVersion:
        algorithm = await self.get_by_id(algorithm_id)
        if algorithm is None:
            raise ValueError(f"Algorithm {algorithm_id} does not exist.")

        next_version = algorithm.current_version + 1
        row = await self.conn.fetchrow(
            """
            INSERT INTO algorithm_versions (algorithm_id, version, schema_version, config, created_by)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            algorithm_id,
            next_version,
            schema_version,
            json.dumps(config),
            created_by,
        )
        await self.conn.execute(
            "UPDATE algorithms SET current_version = $2, updated_at = NOW() WHERE id = $1",
            algorithm_id,
            next_version,
        )
        return self._map_version(row)

    async def set_active_version(self, algorithm_id: UUID, version: int) -> bool:
        target = await self.conn.fetchrow(
            """
            SELECT id FROM algorithm_versions
            WHERE algorithm_id = $1 AND version = $2
            """,
            algorithm_id,
            version,
        )
        if target is None:
            return False

        await self.conn.execute(
            "UPDATE algorithm_versions SET is_active = false WHERE algorithm_id = $1",
            algorithm_id,
        )
        await self.conn.execute(
            "UPDATE algorithm_versions SET is_active = true WHERE id = $1",
            target["id"],
        )
        await self.conn.execute(
            """
            UPDATE algorithms
            SET status = 'active', current_version = $2, updated_at = NOW()
            WHERE id = $1
            """,
            algorithm_id,
            version,
        )
        return True

    @staticmethod
    def _map_algorithm(row: asyncpg.Record) -> AlgorithmDefinition:
        return AlgorithmDefinition(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            mode=row["mode"],
            status=row["status"],
            current_version=row["current_version"],
            created_by=row["created_by"],
            created_at=_coerce_datetime(row["created_at"]),
            updated_at=_coerce_datetime(row["updated_at"]),
        )

    @staticmethod
    def _map_version(row: asyncpg.Record) -> AlgorithmConfigVersion:
        config_payload = row["config"]
        if isinstance(config_payload, str):
            config_payload = json.loads(config_payload)
        return AlgorithmConfigVersion(
            algorithm_id=row["algorithm_id"],
            version=row["version"],
            schema_version=row["schema_version"],
            config=dict(config_payload),
            is_active=row["is_active"],
            created_by=row["created_by"],
            created_at=_coerce_datetime(row["created_at"]),
        )


def _coerce_datetime(value: datetime) -> datetime:
    """Normalize datetime values from asyncpg records."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
