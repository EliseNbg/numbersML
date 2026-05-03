"""
StrategyInstance repository PostgreSQL implementation.

Uses asyncpg for async database access.
Follows DDD: Infrastructure layer implements Domain interface.
"""

import logging
from typing import Any
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from src.domain.repositories.strategy_instance_repository import StrategyInstanceRepository
from src.domain.strategies.strategy_instance import StrategyInstance, StrategyInstanceState

logger = logging.getLogger(__name__)


class StrategyInstanceRepositoryPG(StrategyInstanceRepository):
    """
    PostgreSQL implementation of StrategyInstanceRepository.

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

    async def get_by_id(self, entity_id: UUID) -> StrategyInstance | None:
        """
        Get StrategyInstance by ID.

        Args:
            entity_id: UUID of the instance

        Returns:
            StrategyInstance if found, None otherwise
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, strategy_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM strategy_instances
            WHERE id = $1
            """,
            entity_id,
        )
        return self._row_to_entity(row) if row else None

    async def get_all(self) -> list[StrategyInstance]:
        """
        Get all StrategyInstances.

        Returns:
            List of all StrategyInstance entities
        """
        rows = await self._conn.fetch(
            """
            SELECT id, strategy_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM strategy_instances
            ORDER BY created_at DESC
            """,
        )
        return [self._row_to_entity(row) for row in rows]

    async def save(self, entity: StrategyInstance) -> StrategyInstance:
        """
        Save (insert or update) a StrategyInstance.

        Args:
            entity: StrategyInstance entity to save

        Returns:
            Saved StrategyInstance with updated timestamps

        Raises:
            ValueError: If entity is invalid
        """
        try:
            row = await self._conn.fetchrow(
                """
                INSERT INTO strategy_instances
                    (id, strategy_id, config_set_id, status, runtime_stats,
                     started_at, stopped_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    strategy_id = EXCLUDED.strategy_id,
                    config_set_id = EXCLUDED.config_set_id,
                    status = EXCLUDED.status,
                    runtime_stats = EXCLUDED.runtime_stats,
                    started_at = EXCLUDED.started_at,
                    stopped_at = EXCLUDED.stopped_at,
                    updated_at = NOW()
                RETURNING id, strategy_id, config_set_id, status, runtime_stats,
                          started_at, stopped_at, created_at, updated_at
                """,
                entity.id,
                entity.strategy_id,
                entity.config_set_id,
                entity.status.value,
                entity.runtime_stats.to_dict(),
                entity.started_at,
                entity.stopped_at,
            )
            return self._row_to_entity(row)
        except asyncpg.UniqueViolationError as e:
            logger.error(f"Unique violation saving StrategyInstance: {e}")
            raise ValueError("Instance with this strategy and config set already exists") from e
        except Exception as e:
            logger.error(f"Failed to save StrategyInstance: {e}")
            raise

    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete a StrategyInstance.

        Args:
            entity_id: UUID of the instance

        Returns:
            True if deleted, False if not found
        """
        result = await self._conn.execute("DELETE FROM strategy_instances WHERE id = $1", entity_id)
        return "DELETE 1" in result

    async def get_by_strategy_and_config(
        self, strategy_id: UUID, config_set_id: UUID
    ) -> StrategyInstance | None:
        """
        Get instance by strategy + config_set combination.

        Args:
            strategy_id: UUID of the strategy
            config_set_id: UUID of the configuration set

        Returns:
            StrategyInstance if found, None otherwise
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, strategy_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM strategy_instances
            WHERE strategy_id = $1 AND config_set_id = $2
            """,
            strategy_id,
            config_set_id,
        )
        return self._row_to_entity(row) if row else None

    async def list_all(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StrategyInstance]:
        """
        List instances with optional status filter.

        Args:
            status: Optional status filter (stopped, running, paused, error)
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of StrategyInstance entities
        """
        if status:
            rows = await self._conn.fetch(
                """
                SELECT id, strategy_id, config_set_id, status, runtime_stats,
                       started_at, stopped_at, created_at, updated_at
                FROM strategy_instances
                WHERE status = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status,
                limit,
                offset,
            )
        else:
            rows = await self._conn.fetch(
                """
                SELECT id, strategy_id, config_set_id, status, runtime_stats,
                       started_at, stopped_at, created_at, updated_at
                FROM strategy_instances
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [self._row_to_entity(row) for row in rows]

    async def list_by_strategy(self, strategy_id: UUID) -> list[StrategyInstance]:
        """
        List all instances for a specific strategy.

        Args:
            strategy_id: UUID of the strategy

        Returns:
            List of StrategyInstance entities for the strategy
        """
        rows = await self._conn.fetch(
            """
            SELECT id, strategy_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM strategy_instances
            WHERE strategy_id = $1
            ORDER BY created_at DESC
            """,
            strategy_id,
        )
        return [self._row_to_entity(row) for row in rows]

    async def update_status(
        self, instance_id: UUID, status: str, runtime_stats: dict[str, Any] | None = None
    ) -> StrategyInstance | None:
        """
        Update instance status and optionally runtime stats.

        Args:
            instance_id: UUID of the instance
            status: New status value
            runtime_stats: Optional runtime stats dict to update

        Returns:
            Updated StrategyInstance if found, None otherwise
        """
        if runtime_stats:
            result = await self._conn.execute(
                """
                UPDATE strategy_instances
                SET status = $2, runtime_stats = $3, updated_at = NOW()
                WHERE id = $1
                """,
                instance_id,
                status,
                runtime_stats,
            )
        else:
            result = await self._conn.execute(
                """
                UPDATE strategy_instances
                SET status = $2, updated_at = NOW()
                WHERE id = $1
                """,
                instance_id,
                status,
            )

        if "UPDATE 1" not in result:
            return None
        return await self.get_by_id(instance_id)

    def _row_to_entity(self, row: asyncpg.Record) -> StrategyInstance:
        """
        Convert database row to StrategyInstance entity.

        Args:
            row: asyncpg Record from SELECT query

        Returns:
            StrategyInstance entity
        """
        from src.domain.strategies.strategy_instance import RuntimeStats

        if row["runtime_stats"]:
            stats_dict = dict(row["runtime_stats"]) if row["runtime_stats"] else {}
            # Filter out keys not in RuntimeStats.__init__ parameters
            init_params = RuntimeStats.__init__.__code__.co_varnames[1:]  # Skip self
            filtered_stats = {k: v for k, v in stats_dict.items() if k in init_params}
            runtime_stats = RuntimeStats(**filtered_stats)
        else:
            runtime_stats = RuntimeStats()

        instance = StrategyInstance(
            strategy_id=row["strategy_id"],
            config_set_id=row["config_set_id"],
            id=row["id"],
            status=StrategyInstanceState(row["status"]),
            runtime_stats=runtime_stats,
            started_at=row["started_at"],
            stopped_at=row["stopped_at"],
        )
        # Set timestamps from DB
        instance.created_at = row["created_at"]
        instance.updated_at = row["updated_at"]
        return instance
