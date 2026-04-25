"""PostgreSQL implementation of strategy lifecycle repository."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition


class StrategyRepositoryPG(StrategyRepository):
    """Persist and query strategy definitions and versioned configs."""

    def __init__(self, connection: asyncpg.Connection) -> None:
        self.conn = connection

    async def get_by_id(self, entity_id: UUID) -> StrategyDefinition | None:
        row = await self.conn.fetchrow("SELECT * FROM strategies WHERE id = $1", entity_id)
        if row is None:
            return None
        return self._map_strategy(row)

    async def get_by_name(self, name: str) -> StrategyDefinition | None:
        row = await self.conn.fetchrow("SELECT * FROM strategies WHERE name = $1", name)
        if row is None:
            return None
        return self._map_strategy(row)

    async def get_all(self) -> list[StrategyDefinition]:
        rows = await self.conn.fetch("SELECT * FROM strategies ORDER BY created_at DESC")
        return [self._map_strategy(row) for row in rows]

    async def save(self, entity: StrategyDefinition) -> StrategyDefinition:
        row = await self.conn.fetchrow(
            """
            INSERT INTO strategies (
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
        return self._map_strategy(row)

    async def delete(self, entity_id: UUID) -> bool:
        result = await self.conn.execute("DELETE FROM strategies WHERE id = $1", entity_id)
        return result == "DELETE 1"

    async def list_versions(self, strategy_id: UUID) -> list[StrategyConfigVersion]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM strategy_versions
            WHERE strategy_id = $1
            ORDER BY version DESC
            """,
            strategy_id,
        )
        return [self._map_version(row) for row in rows]

    async def create_version(
        self,
        strategy_id: UUID,
        config: dict[str, Any],
        schema_version: int,
        created_by: str = "system",
    ) -> StrategyConfigVersion:
        strategy = await self.get_by_id(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} does not exist.")

        next_version = strategy.current_version + 1
        row = await self.conn.fetchrow(
            """
            INSERT INTO strategy_versions (strategy_id, version, schema_version, config, created_by)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            strategy_id,
            next_version,
            schema_version,
            json.dumps(config),
            created_by,
        )
        await self.conn.execute(
            "UPDATE strategies SET current_version = $2, updated_at = NOW() WHERE id = $1",
            strategy_id,
            next_version,
        )
        return self._map_version(row)

    async def set_active_version(self, strategy_id: UUID, version: int) -> bool:
        target = await self.conn.fetchrow(
            """
            SELECT id FROM strategy_versions
            WHERE strategy_id = $1 AND version = $2
            """,
            strategy_id,
            version,
        )
        if target is None:
            return False

        await self.conn.execute(
            "UPDATE strategy_versions SET is_active = false WHERE strategy_id = $1",
            strategy_id,
        )
        await self.conn.execute(
            "UPDATE strategy_versions SET is_active = true WHERE id = $1",
            target["id"],
        )
        await self.conn.execute(
            """
            UPDATE strategies
            SET status = 'active', current_version = $2, updated_at = NOW()
            WHERE id = $1
            """,
            strategy_id,
            version,
        )
        return True

    @staticmethod
    def _map_strategy(row: asyncpg.Record) -> StrategyDefinition:
        return StrategyDefinition(
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
    def _map_version(row: asyncpg.Record) -> StrategyConfigVersion:
        config_payload = row["config"]
        if isinstance(config_payload, str):
            config_payload = json.loads(config_payload)
        return StrategyConfigVersion(
            strategy_id=row["strategy_id"],
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
        return value.replace(tzinfo=timezone.utc)
    return value
