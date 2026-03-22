"""
PostgreSQL database connection management.

This module provides a connection pool manager for PostgreSQL
using asyncpg. It handles connection lifecycle, pooling, and
health checks.

Example:
    >>> async def main():
    ...     db = DatabaseConnection(
    ...         dsn="postgresql://crypto:crypto@localhost/crypto_trading",
    ...         min_size=5,
    ...         max_size=20,
    ...     )
    ...     await db.connect()
    ...     async with db.acquire() as conn:
    ...         await conn.execute("SELECT 1")
    ...     await db.disconnect()
"""

import asyncpg
from typing import Optional, AsyncContextManager
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Manages PostgreSQL connection pool.

    This class provides a high-level interface for managing
    PostgreSQL connections with connection pooling, health checks,
    and graceful shutdown.

    Attributes:
        dsn: Database connection string
        min_size: Minimum number of connections in pool
        max_size: Maximum number of connections in pool
        _pool: Internal connection pool (asyncpg.Pool)

    Example:
        >>> db = DatabaseConnection(
        ...     dsn="postgresql://user:pass@localhost/db",
        ...     min_size=5,
        ...     max_size=20,
        ... )
        >>> await db.connect()
        >>> # Use db.acquire() to get connections
        >>> await db.disconnect()
    """

    def __init__(
        self,
        dsn: str,
        min_size: int = 5,
        max_size: int = 20,
        command_timeout: int = 60,
    ) -> None:
        """
        Initialize database connection manager.

        Args:
            dsn: PostgreSQL connection string
                Format: postgresql://user:password@host:port/database
            min_size: Minimum connections in pool (default: 5)
            max_size: Maximum connections in pool (default: 20)
            command_timeout: Default command timeout in seconds (default: 60)

        Raises:
            ValueError: If min_size or max_size are invalid
        """
        if min_size < 1:
            raise ValueError(f"min_size must be >= 1, got {min_size}")
        if max_size < min_size:
            raise ValueError(f"max_size must be >= min_size")

        self.dsn: str = dsn
        self.min_size: int = min_size
        self.max_size: int = max_size
        self.command_timeout: int = command_timeout
        self._pool: Optional[asyncpg.Pool] = None

        logger.info(
            f"DatabaseConnection initialized (min={min_size}, max={max_size})"
        )

    async def connect(self) -> None:
        """
        Create connection pool.

        Establishes connections to PostgreSQL and creates a pool
        for efficient connection reuse.

        Raises:
            RuntimeError: If already connected
            asyncpg.PostgresError: If connection fails

        Example:
            >>> db = DatabaseConnection(dsn="...")
            >>> await db.connect()
            >>> print(f"Connected: {db.is_connected}")
        """
        if self._pool is not None:
            raise RuntimeError("Database already connected")

        logger.info(f"Connecting to PostgreSQL: {self.dsn}")

        try:
            self._pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=self.command_timeout,
            )

            logger.info(
                f"Database connected successfully "
                f"(pool size: {self._pool.get_size()})"
            )

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """
        Close connection pool.

        Gracefully closes all connections in the pool.

        Raises:
            RuntimeError: If not connected

        Example:
            >>> await db.connect()
            >>> # ... use database ...
            >>> await db.disconnect()
        """
        if self._pool is None:
            raise RuntimeError("Database not connected")

        logger.info("Disconnecting from database...")

        await self._pool.close()
        self._pool = None

        logger.info("Database disconnected")

    @asynccontextmanager
    async def acquire(
        self
    ) -> AsyncContextManager[asyncpg.Connection]:
        """
        Acquire connection from pool.

        Context manager for safely acquiring and releasing
        database connections.

        Yields:
            asyncpg.Connection: Database connection

        Raises:
            RuntimeError: If not connected

        Example:
            >>> async with db.acquire() as conn:
            ...     await conn.execute("SELECT 1")
        """
        if self._pool is None:
            raise RuntimeError("Database not connected")

        async with self._pool.acquire() as conn:
            yield conn

    @property
    def pool(self) -> asyncpg.Pool:
        """
        Get connection pool.

        Returns:
            asyncpg.Pool: The connection pool

        Raises:
            RuntimeError: If not connected
        """
        if self._pool is None:
            raise RuntimeError("Database not connected")
        return self._pool

    @property
    def is_connected(self) -> bool:
        """
        Check if database is connected.

        Returns:
            bool: True if connected, False otherwise
        """
        return self._pool is not None

    async def health_check(self) -> bool:
        """
        Perform database health check.

        Tests if database is responsive by executing a simple query.

        Returns:
            bool: True if healthy, False otherwise

        Example:
            >>> if await db.health_check():
            ...     print("Database is healthy")
        """
        if self._pool is None:
            return False

        try:
            async with self.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False
