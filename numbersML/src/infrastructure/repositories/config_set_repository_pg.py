"""
ConfigurationSet repository PostgreSQL implementation.

Uses asyncpg for async database access.
Follows DDD: Infrastructure layer implements Domain interface.
"""

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from src.domain.repositories.config_set_repository import ConfigSetRepository
from src.domain.strategies.config_set import ConfigurationSet

logger = logging.getLogger(__name__)


def _parse_json(value: Any) -> dict[str, Any]:
    """Parse JSONB column value to dict.

    asyncpg may return JSONB as dict or str depending on codec.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)  # fallback for other types (e.g., asyncpg.Record)


class ConfigSetRepositoryPG(ConfigSetRepository):
    """
    PostgreSQL implementation of ConfigSetRepository using asyncpg.

    Architecture: Infrastructure Layer
    Dependencies: asyncpg connection from pool
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        """
        Initialize with database connection.

        Args:
            conn: asyncpg connection from pool
        """
        self._conn = conn

    async def get_by_id(self, entity_id: UUID) -> ConfigurationSet | None:
        """
        Get ConfigurationSet by ID.

        Args:
            entity_id: UUID of the configuration set

        Returns:
            ConfigurationSet if found, None otherwise
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, name, description, config, is_active, created_by,
                   created_at, updated_at, version
            FROM configuration_sets
            WHERE id = $1
            """,
            entity_id,
        )

        if not row:
            return None

        return self._row_to_entity(row)

    async def get_all(self) -> list[ConfigurationSet]:
        """
        Get all ConfigurationSets.

        Returns:
            List of all ConfigurationSet entities
        """
        rows = await self._conn.fetch(
            """
            SELECT id, name, description, config, is_active, created_by,
                   created_at, updated_at, version
            FROM configuration_sets
            ORDER BY created_at DESC
            """,
        )

        return [self._row_to_entity(row) for row in rows]

    async def save(self, entity: ConfigurationSet) -> ConfigurationSet:
        """
        Save (insert or update) a ConfigurationSet.

        Uses upsert (INSERT ... ON CONFLICT) for idempotency.

        Args:
            entity: ConfigurationSet entity to save

        Returns:
            Saved ConfigurationSet with updated timestamps

        Raises:
            ValueError: If config_set is invalid
        """
        try:
            row = await self._conn.fetchrow(
                """
                INSERT INTO configuration_sets
                    (id, name, description, config, is_active, created_by, version)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    config = EXCLUDED.config,
                    is_active = EXCLUDED.is_active,
                    version = EXCLUDED.version,
                    updated_at = NOW()
                RETURNING id, name, description, config, is_active, created_by,
                          created_at, updated_at, version
                """,
                entity.id,
                entity.name,
                entity.description,
                json.dumps(entity.to_dict()["config"]),
                entity.is_active,
                entity.created_by,
                entity.version,
            )

            return self._row_to_entity(row)

        except asyncpg.UniqueViolationError as e:
            logger.error(f"Unique violation saving ConfigurationSet: {e}")
            raise ValueError("ConfigurationSet with this name already exists") from e
        except Exception as e:
            logger.error(f"Failed to save ConfigurationSet: {e}")
            raise

    async def delete(self, entity_id: UUID) -> bool:
        """
        Soft delete by deactivating.

        Args:
            entity_id: UUID of the configuration set

        Returns:
            True if deleted, False if not found

        Note:
            This performs a soft delete by setting is_active=False.
        """
        result = await self._conn.execute(
            """
            UPDATE configuration_sets
            SET is_active = false, updated_at = NOW()
            WHERE id = $1
            """,
            entity_id,
        )

        return "UPDATE 1" in result

    async def get_by_name(self, name: str) -> ConfigurationSet | None:
        """
        Get ConfigurationSet by name.

        Args:
            name: Unique name of the configuration set

        Returns:
            ConfigurationSet if found, None otherwise
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, name, description, config, is_active, created_by,
                   created_at, updated_at, version
            FROM configuration_sets
            WHERE name = $1
            """,
            name,
        )

        if not row:
            return None

        return self._row_to_entity(row)

    async def list_all(
        self,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConfigurationSet]:
        """
        List ConfigurationSets with optional filtering.

        Args:
            active_only: If True, return only active config sets
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of ConfigurationSet entities
        """
        if active_only:
            rows = await self._conn.fetch(
                """
                SELECT id, name, description, config, is_active, created_by,
                       created_at, updated_at, version
                FROM configuration_sets
                WHERE is_active = true
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        else:
            rows = await self._conn.fetch(
                """
                SELECT id, name, description, config, is_active, created_by,
                       created_at, updated_at, version
                FROM configuration_sets
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

        return [self._row_to_entity(row) for row in rows]

    async def update_config(
        self,
        config_set_id: UUID,
        new_config: dict[str, Any],
        updated_by: str = "system",
    ) -> ConfigurationSet | None:
        """
        Update configuration and increment version.

        Args:
            config_set_id: UUID of the configuration set
            new_config: New configuration dictionary
            updated_by: User making the change

        Returns:
            Updated ConfigurationSet if found, None otherwise
        """
        result = await self._conn.execute(
            """
            UPDATE configuration_sets
            SET config = $2, version = version + 1, updated_at = NOW()
            WHERE id = $1
            """,
            config_set_id,
            json.dumps(new_config),
        )

        if "UPDATE 1" not in result:
            return None

        return await self.get_by_id(config_set_id)

    def _row_to_entity(self, row: asyncpg.Record) -> ConfigurationSet:
        """
        Convert database row to ConfigurationSet entity.

        Args:
            row: asyncpg Record from SELECT query

        Returns:
            ConfigurationSet entity
        """
        config_set = ConfigurationSet(
            name=row["name"],
            config=_parse_json(row["config"]),  # Handle JSONB column
            description=row["description"],
            id=row["id"],
            is_active=row["is_active"],
            created_by=row["created_by"],
        )
        # Override version from database
        config_set._version = row["version"]
        # Set timestamps from database
        config_set.created_at = row["created_at"]
        config_set.updated_at = row["updated_at"]
        return config_set
