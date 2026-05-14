"""PostgreSQL implementation of strategy lifecycle repository."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition


class StrategyRepositoryPG(StrategyRepository):
    """Persist and query strategy definitions and versioned configs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_by_id(self, entity_id: UUID) -> StrategyDefinition | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM strategies WHERE id = $1", entity_id)
            if row is None:
                return None
            return self._map_strategy(row)

    async def get_by_name(self, name: str) -> StrategyDefinition | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM strategies WHERE name = $1", name)
            if row is None:
                return None
            return self._map_strategy(row)

    async def get_all(self) -> list[StrategyDefinition]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM strategies ORDER BY created_at DESC")
            return [self._map_strategy(row) for row in rows]

    async def save(self, entity: StrategyDefinition) -> StrategyDefinition:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"[REPO SAVE] Saving strategy {entity.id} with status='{entity.status}', type='{entity.strategy_type}'"
        )
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategies (
                    id, name, description, mode, status, strategy_type, class_path,
                    current_version, created_by, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    mode = EXCLUDED.mode,
                    status = EXCLUDED.status,
                    strategy_type = EXCLUDED.strategy_type,
                    class_path = EXCLUDED.class_path,
                    current_version = EXCLUDED.current_version,
                    updated_at = NOW()
                RETURNING *
                """,
                entity.id,
                entity.name,
                entity.description,
                entity.mode,
                entity.status,
                entity.strategy_type,
                entity.class_path,
                entity.current_version,
                entity.created_by,
                entity.created_at,
            )
            logger.warning(
                f"[REPO SAVE] Saved strategy {entity.id}, returned status='{row['status']}', type='{row.get('strategy_type', 'config')}'"
            )
        return self._map_strategy(row)

    async def delete(self, entity_id: UUID) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM strategies WHERE id = $1", entity_id)
            return result == "DELETE 1"

    async def list_versions(self, strategy_id: UUID) -> list[StrategyConfigVersion]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
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
        import logging
        from asyncpg import UniqueViolationError

        logger = logging.getLogger(__name__)
        strategy = await self.get_by_id(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} does not exist.")

        max_retries = 5
        for attempt in range(max_retries):
            # Refresh the strategy to get the latest current_version
            strategy = await self.get_by_id(strategy_id)
            next_version = strategy.current_version + 1
            logger.debug(
                f"Attempt {attempt}: strategy {strategy_id} current_version={strategy.current_version}, "
                f"next_version to insert={next_version}"
            )
            async with self.pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        row = await conn.fetchrow(
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
                        # Update the strategy's current_version
                        await conn.execute(
                            """
                            UPDATE strategies
                            SET current_version = $2, updated_at = NOW()
                            WHERE id = $1
                            """,
                            strategy_id,
                            next_version,
                        )
                        return self._map_version(row)
                except UniqueViolationError:
                    logger.warning(
                        f"Duplicate key for version {next_version} on strategy {strategy_id}, retrying... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    continue
                except Exception as e:
                    logger.error(f"Failed to create version: {e}", exc_info=True)
                    raise
        # If we exhausted retries, raise an error.
        raise RuntimeError(
            f"Failed to create version for strategy {strategy_id} after {max_retries} attempts"
        )

    async def set_active_version(self, strategy_id: UUID, version: int) -> bool:
        async with self.pool.acquire() as conn:
            target = await conn.fetchrow(
                """
                SELECT id FROM strategy_versions
                WHERE strategy_id = $1 AND version = $2
                """,
                strategy_id,
                version,
            )
            if target is None:
                return False

            await conn.execute(
                "UPDATE strategy_versions SET is_active = false WHERE strategy_id = $1",
                strategy_id,
            )
            await conn.execute(
                "UPDATE strategy_versions SET is_active = true WHERE id = $1",
                target["id"],
            )
            await conn.execute(
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
            strategy_type=row.get("strategy_type", "config"),
            class_path=row.get("class_path"),
            current_version=row["current_version"],
            created_by=row["created_by"],
            created_at=_coerce_datetime(row["created_at"]),
            updated_at=_coerce_datetime(row["updated_at"]),
        )

    @staticmethod
    def _map_version(row: asyncpg.Record) -> StrategyConfigVersion:
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"_map_version called with row: {row}")
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
            id=row.get("id"),
        )


def _coerce_datetime(value: datetime) -> datetime:
    """Normalize datetime values from asyncpg records."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
