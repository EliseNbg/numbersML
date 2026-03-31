"""
Database dependency management.

Provides database pool access for dependency injection.
All connections enforce UTC timezone for consistent datetime handling.
"""

import asyncpg
from typing import Optional


async def _init_utc(conn: asyncpg.Connection) -> None:
    """Initialize connection to use UTC timezone."""
    await conn.execute("SET timezone = 'UTC'")


# Database pool (managed by lifespan)
_db_pool: Optional[asyncpg.Pool] = None


def set_db_pool(pool: asyncpg.Pool) -> None:
    """Set the database pool."""
    global _db_pool
    _db_pool = pool


def get_db_pool() -> asyncpg.Pool:
    """
    Get database pool.
    
    Returns:
        Database pool instance
    
    Raises:
        RuntimeError: If pool is not initialized
    """
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized")
    return _db_pool


async def get_db_pool_async() -> asyncpg.Pool:
    """
    Async dependency for getting database pool.
    
    Returns:
        Database pool instance
    """
    return get_db_pool()
