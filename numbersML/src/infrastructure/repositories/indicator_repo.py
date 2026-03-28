"""
Indicator data access repository.

This repository provides data access for indicator_definitions table.

Architecture: Infrastructure Layer (data access)
Dependencies: Domain layer + asyncpg
"""

import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg

from src.domain.models.config import IndicatorConfig

logger = logging.getLogger(__name__)


class IndicatorRepository:
    """
    Repository for indicator_definitions table.
    
    Responsibilities:
        - List indicators with filtering
        - Get indicator by name
        - Register new indicators
        - Update indicator configuration
        - Activate/deactivate indicators
    
    Example:
        >>> repo = IndicatorRepository(db_pool)
        >>> indicators = await repo.list_all()
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.
        
        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
    
    async def list_all(
        self,
        active_only: bool = False,
        category: Optional[str] = None,
    ) -> List[IndicatorConfig]:
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
            
            params: List[Any] = []
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
    
    async def insert(
        self,
        name: str,
        class_name: str,
        module_path: str,
        category: str,
        params: Optional[Dict[str, Any]] = None,
        params_schema: Optional[Dict[str, Any]] = None,
        code_hash: str = 'manual',
        is_active: bool = True,
    ) -> bool:
        """
        Register new indicator.
        
        Args:
            name: Unique indicator name
            class_name: Python class name
            module_path: Python module path
            category: Category (momentum, trend, volatility, volume)
            params: Indicator parameters (default: empty dict)
            params_schema: Parameters schema (default: empty dict)
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
                        params, params_schema, is_active, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
                    """,
                    name,
                    class_name,
                    module_path,
                    category,
                    json.dumps(params or {}),
                    json.dumps(params_schema or {}),
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
    
    async def update_active(
        self,
        name: str,
        is_active: bool,
    ) -> bool:
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
    
    async def update(
        self,
        name: str,
        params: Optional[Dict[str, Any]] = None,
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
                values: List[Any] = [name]
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
    
    async def delete(self, name: str) -> bool:
        """
        Soft delete indicator (set is_active=false).
        
        Args:
            name: Indicator name
        
        Returns:
            True if deleted successfully
        """
        return await self.update_active(name, False)
    
    async def hard_delete(self, name: str) -> bool:
        """
        Hard delete indicator from database.
        
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
    
    async def get_categories(self) -> List[str]:
        """
        Get all indicator categories.
        
        Returns:
            List of unique categories
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT category
                FROM indicator_definitions
                ORDER BY category
                """
            )
            
            return [row['category'] for row in rows]
    
    async def count(self, active_only: bool = False) -> int:
        """
        Count indicators.
        
        Args:
            active_only: If True, count only active indicators
        
        Returns:
            Number of indicators
        """
        async with self.db_pool.acquire() as conn:
            if active_only:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count
                    FROM indicator_definitions
                    WHERE is_active = true
                    """
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count
                    FROM indicator_definitions
                    """
                )
            
            return row['count'] or 0
    
    def _row_to_indicator(self, row: asyncpg.Record) -> IndicatorConfig:
        """
        Convert database row to IndicatorConfig.
        
        Args:
            row: Database record
        
        Returns:
            Indicator configuration
        """
        # Parse params (JSONB)
        raw_params = row['params']
        if isinstance(raw_params, str):
            params = json.loads(raw_params)
        elif isinstance(raw_params, dict):
            params = raw_params
        else:
            params = raw_params or {}
        
        return IndicatorConfig(
            name=row['name'],
            class_name=row['class_name'],
            module_path=row['module_path'],
            category=row['category'],
            params=params,
            is_active=row['is_active'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
