"""
Indicator management service.

This service manages indicator registration, activation, and configuration.

Architecture: Application Layer (orchestration)
Dependencies: Domain layer + Infrastructure (asyncpg)
"""

import json
import logging
from typing import Any, Optional

import asyncpg

from src.domain.models.config import IndicatorConfig

logger = logging.getLogger(__name__)


class IndicatorManager:
    """
    Manage indicator registration and activation.

    Responsibilities:
        - List all indicators
        - Register new indicators
        - Activate/deactivate indicators
        - Update indicator parameters

    Example:
        >>> manager = IndicatorManager(db_pool)
        >>> indicators = await manager.list_indicators()
        >>> await manager.register_indicator(
        ...     name='rsi_14',
        ...     class_name='RSIIndicator',
        ...     module_path='src.indicators.momentum',
        ...     category='momentum',
        ...     params={'period': 14},
        ... )
    """

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.

        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool

    async def list_indicators(
        self,
        active_only: bool = False,
        category: Optional[str] = None,
    ) -> list[IndicatorConfig]:
        """
        List indicators with optional filters.

        Args:
            active_only: If True, return only active indicators
            category: Filter by category (momentum, trend, volatility, volume)

        Returns:
            List of indicator configurations
        """
        async with self.db_pool.acquire() as conn:
            # Build query with optional filters
            query = """
                SELECT
                    name, class_name, module_path, category,
                    params, is_active, created_at, updated_at
                FROM indicator_definitions
                WHERE 1=1
            """

            params: list[Any] = []
            param_count = 1

            if active_only:
                query += f" AND is_active = ${param_count}"
                params.append(True)
                param_count += 1

            if category:
                query += f" AND category = ${param_count}"
                params.append(category)
                param_count += 1

            query += " ORDER BY category, name"

            rows = await conn.fetch(query, *params)

            return [self._row_to_indicator(row) for row in rows]

    def _row_to_indicator(self, row: asyncpg.Record) -> IndicatorConfig:
        """
        Convert database row to IndicatorConfig.

        Args:
            row: Database record

        Returns:
            Indicator configuration
        """
        # Parse params (JSONB)
        raw_params = row["params"]
        if isinstance(raw_params, str):
            params = json.loads(raw_params)
        elif isinstance(raw_params, dict):
            params = raw_params
        else:
            params = raw_params or {}

        return IndicatorConfig(
            name=row["name"],
            class_name=row["class_name"],
            module_path=row["module_path"],
            category=row["category"],
            params=params,
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_by_name(self, name: str) -> Optional[IndicatorConfig]:
        """
        Get indicator by name.

        Args:
            name: Indicator name (e.g., 'rsi_14')

        Returns:
            Indicator configuration or None if not found
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    name, class_name, module_path, category,
                    params, is_active, created_at, updated_at
                FROM indicator_definitions
                WHERE name = $1
                """,
                name,
            )

            return self._row_to_indicator(row) if row else None

    async def register_indicator(
        self,
        name: str,
        class_name: str,
        module_path: str,
        category: str,
        params: Optional[dict[str, Any]] = None,
        is_active: bool = True,
    ) -> bool:
        """
        Register a new indicator.

        Args:
            name: Unique indicator name (e.g., 'rsi_14')
            class_name: Python class name (e.g., 'RSIIndicator')
            module_path: Python module path (e.g., 'src.indicators.momentum')
            category: Category (momentum, trend, volatility, volume)
            params: Indicator parameters (default: empty dict)
            is_active: Whether indicator is active (default: True)

        Returns:
            True if registered successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO indicator_definitions (
                        name, class_name, module_path, category,
                        params, is_active, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
                    """,
                    name,
                    class_name,
                    module_path,
                    category,
                    json.dumps(params or {}),
                    is_active,
                )

            logger.info(f"Registered indicator: {name}")
            return True

        except asyncpg.UniqueViolationError:
            logger.error(f"Indicator already exists: {name}")
            return False
        except Exception as e:
            logger.error(f"Failed to register indicator {name}: {e}")
            return False

    async def activate_indicator(self, name: str) -> bool:
        """
        Activate an indicator.

        Args:
            name: Indicator name

        Returns:
            True if activated successfully
        """
        return await self._update_active(name, True)

    async def deactivate_indicator(self, name: str) -> bool:
        """
        Deactivate an indicator.

        Args:
            name: Indicator name

        Returns:
            True if deactivated successfully
        """
        return await self._update_active(name, False)

    async def _update_active(self, name: str, is_active: bool) -> bool:
        """
        Update indicator active status.

        Args:
            name: Indicator name
            is_active: New active status

        Returns:
            True if updated successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE indicator_definitions
                    SET is_active = $2, updated_at = NOW()
                    WHERE name = $1
                    """,
                    name,
                    is_active,
                )

            status = "activated" if is_active else "deactivated"
            logger.info(f"{status.capitalize()} indicator: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update indicator {name}: {e}")
            return False

    async def update_indicator(
        self,
        name: str,
        params: Optional[dict[str, Any]] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """
        Update indicator configuration.

        Args:
            name: Indicator name
            params: New parameters (optional)
            is_active: New active status (optional)

        Returns:
            True if updated successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                # Build dynamic update query
                updates = ["updated_at = NOW()"]
                values: list[Any] = [name]
                param_count = 2

                if params is not None:
                    updates.append(f"params = ${param_count}")
                    values.append(json.dumps(params))
                    param_count += 1

                if is_active is not None:
                    updates.append(f"is_active = ${param_count}")
                    values.append(is_active)
                    param_count += 1

                query = f"""
                    UPDATE indicator_definitions
                    SET {', '.join(updates)}
                    WHERE name = $1
                """

                await conn.execute(query, *values)

            logger.info(f"Updated indicator: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update indicator {name}: {e}")
            return False

    async def unregister_indicator(self, name: str) -> bool:
        """
        Unregister an indicator (soft delete - set is_active=false).

        Args:
            name: Indicator name

        Returns:
            True if unregistered successfully
        """
        # Soft delete - just deactivate
        return await self.deactivate_indicator(name)

    async def hard_delete_indicator(self, name: str) -> bool:
        """
        Hard delete an indicator from database.

        WARNING: This permanently removes the indicator!

        Args:
            name: Indicator name

        Returns:
            True if deleted successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    DELETE FROM indicator_definitions
                    WHERE name = $1
                    """,
                    name,
                )

            logger.info(f"Hard deleted indicator: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete indicator {name}: {e}")
            return False

    async def get_categories(self) -> list[str]:
        """
        Get all indicator categories.

        Returns:
            List of unique categories
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT category
                FROM indicator_definitions
                ORDER BY category
                """)

            return [row["category"] for row in rows]

    async def count_indicators(self, active_only: bool = False) -> int:
        """
        Count indicators.

        Args:
            active_only: If True, count only active indicators

        Returns:
            Number of indicators
        """
        async with self.db_pool.acquire() as conn:
            if active_only:
                row = await conn.fetchrow("""
                    SELECT COUNT(*) as count
                    FROM indicator_definitions
                    WHERE is_active = true
                    """)
            else:
                row = await conn.fetchrow("""
                    SELECT COUNT(*) as count
                    FROM indicator_definitions
                    """)

            return row["count"] or 0
