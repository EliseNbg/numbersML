"""
Configuration management service.

This service manages system configuration tables.

Architecture: Application Layer (orchestration)
Dependencies: Domain layer + Infrastructure (asyncpg)
"""

import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg

from src.domain.models.config import ConfigEntry

logger = logging.getLogger(__name__)


# Allowed configuration tables
ALLOWED_TABLES = {
    'system_config': ['id', 'key', 'value', 'description', 'is_sensitive', 'is_editable'],
    'collection_config': ['symbol_id', 'collect_ticks', 'collect_24hr_ticker', 'collect_orderbook'],
    'symbols': ['id', 'symbol', 'base_asset', 'quote_asset', 'is_active', 'is_allowed'],
    'indicator_definitions': ['name', 'class_name', 'module_path', 'category', 'params', 'is_active'],
}


class ConfigManager:
    """
    Manage system configuration tables.
    
    Responsibilities:
        - Load configuration tables
        - Update configuration entries
        - Validate configuration changes
    
    Example:
        >>> manager = ConfigManager(db_pool)
        >>> data = await manager.get_table_data('system_config')
        >>> await manager.update_entry('system_config', 1, {'value': {'new': 'value'}})
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.
        
        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
    
    async def get_table_data(
        self,
        table_name: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get data from configuration table.
        
        Args:
            table_name: Table name (must be in ALLOWED_TABLES)
            limit: Maximum rows to return
        
        Returns:
            List of row dictionaries
        
        Raises:
            ValueError: If table_name is not allowed
        """
        self._validate_table(table_name)
        
        async with self.db_pool.acquire() as conn:
            # Get column names
            columns = await conn.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = $1
                ORDER BY ordinal_position
                """,
                table_name,
            )
            
            column_names = [col['column_name'] for col in columns]
            
            # Get data
            rows = await conn.fetch(
                f"SELECT * FROM {table_name} LIMIT $1",
                limit,
            )
            
            # Convert to list of dicts
            result = []
            for row in rows:
                row_dict = {}
                for col_name in column_names:
                    value = row[col_name]
                    # Convert JSONB to dict
                    if isinstance(value, dict):
                        row_dict[col_name] = value
                    else:
                        row_dict[col_name] = value
                result.append(row_dict)
            
            return result
    
    async def update_entry(
        self,
        table_name: str,
        entry_id: int,
        data: Dict[str, Any],
    ) -> bool:
        """
        Update configuration entry.
        
        Args:
            table_name: Table name
            entry_id: Entry ID (id, symbol_id, or name depending on table)
            data: Data to update
        
        Returns:
            True if updated successfully
        
        Raises:
            ValueError: If table_name is not allowed
        """
        self._validate_table(table_name)
        
        try:
            async with self.db_pool.acquire() as conn:
                # Build dynamic update query
                updates = []
                values: List[Any] = []
                param_count = 2
                
                for key, value in data.items():
                    if key in ['id', 'symbol_id', 'name']:  # Skip primary keys
                        continue
                    
                    # Convert dict to JSON for JSONB columns
                    if isinstance(value, dict):
                        value = json.dumps(value)
                    
                    updates.append(f"{key} = ${param_count}")
                    values.append(value)
                    param_count += 1
                
                if not updates:
                    logger.warning("No fields to update")
                    return False
                
                # Determine ID column
                id_column = self._get_id_column(table_name)
                
                query = f"""
                    UPDATE {table_name}
                    SET {', '.join(updates)}
                    WHERE {id_column} = $1
                """
                
                values.insert(0, entry_id)
                
                await conn.execute(query, *values)
            
            logger.info(f"Updated entry in {table_name} (ID: {entry_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update entry in {table_name}: {e}")
            return False
    
    async def insert_entry(
        self,
        table_name: str,
        data: Dict[str, Any],
    ) -> Optional[int]:
        """
        Insert new configuration entry.
        
        Args:
            table_name: Table name
            data: Entry data
        
        Returns:
            New entry ID or None if failed
        
        Raises:
            ValueError: If table_name is not allowed
        """
        self._validate_table(table_name)
        
        try:
            async with self.db_pool.acquire() as conn:
                # Get column names (exclude auto-generated)
                columns = []
                values = []
                
                for key, value in data.items():
                    if key in ['id', 'created_at', 'updated_at']:  # Skip auto-generated
                        continue
                    
                    columns.append(key)
                    
                    # Convert dict to JSON for JSONB columns
                    if isinstance(value, dict):
                        values.append(json.dumps(value))
                    else:
                        values.append(value)
                
                if not columns:
                    logger.warning("No fields to insert")
                    return None
                
                # Build insert query
                placeholders = ', '.join(f'${i}' for i in range(2, len(values) + 2))
                query = f"""
                    INSERT INTO {table_name} ({', '.join(columns)})
                    VALUES ({placeholders})
                    RETURNING {self._get_id_column(table_name)}
                """
                
                result = await conn.fetchval(query, *values)
            
            logger.info(f"Inserted entry in {table_name} (ID: {result})")
            return result
            
        except Exception as e:
            logger.error(f"Failed to insert entry in {table_name}: {e}")
            return None
    
    async def delete_entry(
        self,
        table_name: str,
        entry_id: int,
    ) -> bool:
        """
        Delete configuration entry.
        
        Args:
            table_name: Table name
            entry_id: Entry ID
        
        Returns:
            True if deleted successfully
        
        Raises:
            ValueError: If table_name is not allowed
        """
        self._validate_table(table_name)
        
        try:
            async with self.db_pool.acquire() as conn:
                id_column = self._get_id_column(table_name)
                
                await conn.execute(
                    f"DELETE FROM {table_name} WHERE {id_column} = $1",
                    entry_id,
                )
            
            logger.info(f"Deleted entry from {table_name} (ID: {entry_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete entry from {table_name}: {e}")
            return False
    
    def _validate_table(self, table_name: str) -> None:
        """
        Validate table name is allowed.
        
        Args:
            table_name: Table name to validate
        
        Raises:
            ValueError: If table is not allowed
        """
        if table_name not in ALLOWED_TABLES:
            raise ValueError(
                f"Table '{table_name}' not allowed. "
                f"Allowed tables: {', '.join(ALLOWED_TABLES.keys())}"
            )
    
    def _get_id_column(self, table_name: str) -> str:
        """
        Get ID column name for table.
        
        Args:
            table_name: Table name
        
        Returns:
            ID column name
        """
        id_columns = {
            'system_config': 'id',
            'collection_config': 'symbol_id',
            'symbols': 'id',
            'indicator_definitions': 'name',
        }
        return id_columns.get(table_name, 'id')
    
    async def get_entry(
        self,
        table_name: str,
        entry_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get single configuration entry.
        
        Args:
            table_name: Table name
            entry_id: Entry ID
        
        Returns:
            Entry dictionary or None if not found
        """
        self._validate_table(table_name)
        
        async with self.db_pool.acquire() as conn:
            id_column = self._get_id_column(table_name)
            
            row = await conn.fetchrow(
                f"SELECT * FROM {table_name} WHERE {id_column} = $1",
                entry_id,
            )
            
            if not row:
                return None
            
            # Convert to dict
            return dict(row)
    
    async def get_config_value(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Get configuration value by key from system_config.
        
        Args:
            key: Configuration key
            default: Default value if not found
        
        Returns:
            Configuration value or default
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT value FROM system_config
                WHERE key = $1
                """,
                key,
            )
            
            if row:
                return dict(row['value']) if row['value'] else default
            
            return default
    
    async def set_config_value(
        self,
        key: str,
        value: Any,
        description: Optional[str] = None,
    ) -> bool:
        """
        Set configuration value in system_config.
        
        Args:
            key: Configuration key
            value: Configuration value
            description: Optional description
        
        Returns:
            True if set successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO system_config (key, value, description, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        description = EXCLUDED.description,
                        updated_at = NOW()
                    """,
                    key,
                    json.dumps(value) if isinstance(value, dict) else value,
                    description,
                )
            
            logger.info(f"Set config value: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set config value {key}: {e}")
            return False
