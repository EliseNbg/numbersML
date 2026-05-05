"""
AlgorithmInstance repository PostgreSQL implementation.

Uses asyncpg for async database access.
Follows DDD: Infrastructure layer implements Domain interface.
"""

import logging
from typing import Any
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from src.domain.repositories.algorithm_instance_repository import AlgorithmInstanceRepository
from src.domain.algorithms.algorithm_instance import AlgorithmInstance, AlgorithmInstanceState

logger = logging.getLogger(__name__)


class AlgorithmInstanceRepositoryPG(AlgorithmInstanceRepository):
    """
    PostgreSQL implementation of AlgorithmInstanceRepository.

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

    async def get_by_id(self, entity_id: UUID) -> AlgorithmInstance | None:
        """
        Get AlgorithmInstance by ID.

        Args:
            entity_id: UUID of the instance

        Returns:
            AlgorithmInstance if found, None otherwise
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, algorithm_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM algorithm_instances
            WHERE id = $1
            """,
            entity_id,
        )
        return self._row_to_entity(row) if row else None

    async def get_all(self) -> list[AlgorithmInstance]:
        """
        Get all AlgorithmInstances.

        Returns:
            List of all AlgorithmInstance entities
        """
        rows = await self._conn.fetch(
            """
            SELECT id, algorithm_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM algorithm_instances
            ORDER BY created_at DESC
            """,
        )
        return [self._row_to_entity(row) for row in rows]

    async def save(self, entity: AlgorithmInstance) -> AlgorithmInstance:
        """
        Save (insert or update) a AlgorithmInstance.

        Args:
            entity: AlgorithmInstance entity to save

        Returns:
            Saved AlgorithmInstance with updated timestamps

        Raises:
            ValueError: If entity is invalid
        """
        try:
            row = await self._conn.fetchrow(
                """
                INSERT INTO algorithm_instances
                    (id, algorithm_id, config_set_id, status, runtime_stats,
                     started_at, stopped_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    algorithm_id = EXCLUDED.algorithm_id,
                    config_set_id = EXCLUDED.config_set_id,
                    status = EXCLUDED.status,
                    runtime_stats = EXCLUDED.runtime_stats,
                    started_at = EXCLUDED.started_at,
                    stopped_at = EXCLUDED.stopped_at,
                    updated_at = NOW()
                RETURNING id, algorithm_id, config_set_id, status, runtime_stats,
                          started_at, stopped_at, created_at, updated_at
                """,
                entity.id,
                entity.algorithm_id,
                entity.config_set_id,
                entity.status.value,
                entity.runtime_stats.to_dict(),
                entity.started_at,
                entity.stopped_at,
            )
            return self._row_to_entity(row)
        except asyncpg.UniqueViolationError as e:
            logger.error(f"Unique violation saving AlgorithmInstance: {e}")
            raise ValueError("Instance with this algorithm and config set already exists") from e
        except Exception as e:
            logger.error(f"Failed to save AlgorithmInstance: {e}")
            raise

    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete a AlgorithmInstance.

        Args:
            entity_id: UUID of the instance

        Returns:
            True if deleted, False if not found
        """
        result = await self._conn.execute("DELETE FROM algorithm_instances WHERE id = $1", entity_id)
        return "DELETE 1" in result

    async def get_by_algorithm_and_config(
        self, algorithm_id: UUID, config_set_id: UUID
    ) -> AlgorithmInstance | None:
        """
        Get instance by algorithm + config_set combination.

        Args:
            algorithm_id: UUID of the algorithm
            config_set_id: UUID of the configuration set

        Returns:
            AlgorithmInstance if found, None otherwise
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, algorithm_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM algorithm_instances
            WHERE algorithm_id = $1 AND config_set_id = $2
            """,
            algorithm_id,
            config_set_id,
        )
        return self._row_to_entity(row) if row else None

    async def list_all(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AlgorithmInstance]:
        """
        List instances with optional status filter.

        Args:
            status: Optional status filter (stopped, running, paused, error)
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of AlgorithmInstance entities
        """
        if status:
            rows = await self._conn.fetch(
                """
                SELECT id, algorithm_id, config_set_id, status, runtime_stats,
                       started_at, stopped_at, created_at, updated_at
                FROM algorithm_instances
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
                SELECT id, algorithm_id, config_set_id, status, runtime_stats,
                       started_at, stopped_at, created_at, updated_at
                FROM algorithm_instances
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [self._row_to_entity(row) for row in rows]

    async def list_by_algorithm(self, algorithm_id: UUID) -> list[AlgorithmInstance]:
        """
        List all instances for a specific algorithm.

        Args:
            algorithm_id: UUID of the algorithm

        Returns:
            List of AlgorithmInstance entities for the algorithm
        """
        rows = await self._conn.fetch(
            """
            SELECT id, algorithm_id, config_set_id, status, runtime_stats,
                   started_at, stopped_at, created_at, updated_at
            FROM algorithm_instances
            WHERE algorithm_id = $1
            ORDER BY created_at DESC
            """,
            algorithm_id,
        )
        return [self._row_to_entity(row) for row in rows]

    async def update_status(
        self, instance_id: UUID, status: str, runtime_stats: dict[str, Any] | None = None
    ) -> AlgorithmInstance | None:
        """
        Update instance status and optionally runtime stats.

        Args:
            instance_id: UUID of the instance
            status: New status value
            runtime_stats: Optional runtime stats dict to update

        Returns:
            Updated AlgorithmInstance if found, None otherwise
        """
        if runtime_stats:
            result = await self._conn.execute(
                """
                UPDATE algorithm_instances
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
                UPDATE algorithm_instances
                SET status = $2, updated_at = NOW()
                WHERE id = $1
                """,
                instance_id,
                status,
            )

        if "UPDATE 1" not in result:
            return None
        return await self.get_by_id(instance_id)

    def _row_to_entity(self, row: asyncpg.Record) -> AlgorithmInstance:
        """
        Convert database row to AlgorithmInstance entity.

        Args:
            row: asyncpg Record from SELECT query

        Returns:
            AlgorithmInstance entity
        """
        from src.domain.algorithms.algorithm_instance import RuntimeStats

        if row["runtime_stats"]:
            stats_dict = dict(row["runtime_stats"]) if row["runtime_stats"] else {}
            # Filter out keys not in RuntimeStats.__init__ parameters
            init_params = RuntimeStats.__init__.__code__.co_varnames[1:]  # Skip self
            filtered_stats = {k: v for k, v in stats_dict.items() if k in init_params}
            runtime_stats = RuntimeStats(**filtered_stats)
        else:
            runtime_stats = RuntimeStats()

        instance = AlgorithmInstance(
            algorithm_id=row["algorithm_id"],
            config_set_id=row["config_set_id"],
            id=row["id"],
            status=AlgorithmInstanceState(row["status"]),
            runtime_stats=runtime_stats,
            started_at=row["started_at"],
            stopped_at=row["stopped_at"],
        )
        # Set timestamps from DB
        instance.created_at = row["created_at"]
        instance.updated_at = row["updated_at"]
        return instance
