# Step 002: Database Schema - Implementation Guide

**Phase**: 1 - Foundation  
**Effort**: 4 hours  
**Dependencies**: Step 001 (Project Setup) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements the complete PostgreSQL database schema with:
- Core tables (symbols, trades, ticker stats, indicators)
- Configuration tables (system_config, collection_config)
- Helper functions and triggers
- Migration system
- Comprehensive tests

---

## Implementation Tasks

### Task 1: Database Connection Module

**File**: `src/infrastructure/database/connection.py`

```python
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
```

---

### Task 2: Database Configuration

**File**: `src/infrastructure/database/config.py`

```python
"""
Database configuration management.

This module provides configuration loading from YAML files
and environment variables.

Example:
    >>> config = load_database_config("development")
    >>> print(config['dsn'])
"""

import yaml
from pathlib import Path
from typing import Dict, Any
import os


def load_database_config(environment: str = "development") -> Dict[str, Any]:
    """
    Load database configuration from YAML file.
    
    Loads configuration for the specified environment from
    config/database.yaml. Falls back to environment variables
    if file is not found.
    
    Args:
        environment: Environment name (development, test, production)
    
    Returns:
        Dictionary with database configuration:
        - dsn: Connection string
        - min_size: Minimum pool size
        - max_size: Maximum pool size
    
    Raises:
        FileNotFoundError: If config file not found and no env vars
        ValueError: If environment not found in config
    
    Example:
        >>> config = load_database_config("development")
        >>> print(config['dsn'])
        'postgresql://crypto:crypto@localhost/crypto_trading_dev'
    """
    config_path = Path(__file__).parent.parent.parent / "config" / "database.yaml"
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if environment not in config:
            raise ValueError(f"Environment '{environment}' not found in config")
        
        return config[environment]
    
    # Fallback to environment variables
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        raise FileNotFoundError(
            "Config file not found and DATABASE_URL not set. "
            "Please create config/database.yaml or set DATABASE_URL environment variable."
        )
    
    return {
        'dsn': dsn,
        'min_size': int(os.getenv('DB_MIN_SIZE', '5')),
        'max_size': int(os.getenv('DB_MAX_SIZE', '20')),
    }
```

---

### Task 3: Migration System

**File**: `src/infrastructure/database/migrations.py`

```python
"""
Database migration management.

This module provides a simple migration system for managing
database schema changes with version tracking.

Example:
    >>> async with db.acquire() as conn:
    ...     manager = MigrationManager(conn)
    ...     await manager.run_migration("001_initial_schema", sql)
"""

import asyncpg
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class MigrationManager:
    """
    Manages database schema migrations.
    
    This class handles migration execution, tracking, and
    rollback capabilities.
    
    Attributes:
        conn: Database connection
        migrations_table: Name of migrations tracking table
    
    Example:
        >>> async with db.acquire() as conn:
        ...     manager = MigrationManager(conn)
        ...     await manager.ensure_migrations_table()
        ...     await manager.run_migration("001_initial", sql)
    """
    
    def __init__(self, connection: asyncpg.Connection) -> None:
        """
        Initialize migration manager.
        
        Args:
            connection: Database connection
        """
        self.conn: asyncpg.Connection = connection
        self.migrations_table: str = "schema_migrations"
    
    async def ensure_migrations_table(self) -> None:
        """
        Create migrations tracking table if not exists.
        
        Creates the schema_migrations table to track which
        migrations have been applied.
        
        Example:
            >>> await manager.ensure_migrations_table()
        """
        logger.info("Ensuring migrations table exists...")
        
        await self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.migrations_table} (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        
        logger.info("Migrations table ready")
    
    async def get_applied_migrations(self) -> List[str]:
        """
        Get list of already applied migrations.
        
        Returns:
            List of migration names that have been applied
        
        Example:
            >>> applied = await manager.get_applied_migrations()
            >>> print(applied)
            ['001_initial_schema', '002_add_indexes']
        """
        rows = await self.conn.fetch(
            f"SELECT migration_name FROM {self.migrations_table} ORDER BY applied_at"
        )
        return [row['migration_name'] for row in rows]
    
    async def mark_migration_applied(self, migration_name: str) -> None:
        """
        Mark a migration as applied.
        
        Args:
            migration_name: Name of the migration
        
        Example:
            >>> await manager.mark_migration_applied("001_initial_schema")
        """
        await self.conn.execute(
            f"INSERT INTO {self.migrations_table} (migration_name) VALUES ($1)",
            migration_name
        )
    
    async def is_migration_applied(self, migration_name: str) -> bool:
        """
        Check if a migration has been applied.
        
        Args:
            migration_name: Name of the migration
        
        Returns:
            True if migration has been applied, False otherwise
        
        Example:
            >>> if await manager.is_migration_applied("001_initial"):
            ...     print("Migration already applied")
        """
        result = await self.conn.fetchval(
            f"SELECT 1 FROM {self.migrations_table} WHERE migration_name = $1",
            migration_name
        )
        return result is not None
    
    async def run_migration(
        self,
        migration_name: str,
        sql: str,
    ) -> bool:
        """
        Run a single migration.
        
        Executes the migration SQL within a transaction and
        marks it as applied.
        
        Args:
            migration_name: Name of the migration
            sql: SQL to execute
        
        Returns:
            True if migration was applied, False if already applied
        
        Raises:
            asyncpg.PostgresError: If migration fails
        
        Example:
            >>> sql = open("migrations/001_initial.sql").read()
            >>> applied = await manager.run_migration("001_initial", sql)
            >>> if applied:
            ...     print("Migration applied successfully")
        """
        # Check if already applied
        if await self.is_migration_applied(migration_name):
            logger.info(f"Migration {migration_name} already applied, skipping")
            return False
        
        logger.info(f"Applying migration: {migration_name}")
        
        # Execute migration in transaction
        async with self.conn.transaction():
            await self.conn.execute(sql)
            await self.mark_migration_applied(migration_name)
        
        logger.info(f"Migration {migration_name} applied successfully")
        return True
    
    async def run_all_migrations(self, migrations_dir: Path) -> List[str]:
        """
        Run all pending migrations from directory.
        
        Args:
            migrations_dir: Path to migrations directory
        
        Returns:
            List of migration names that were applied
        
        Example:
            >>> migrations_dir = Path("migrations")
            >>> applied = await manager.run_all_migrations(migrations_dir)
        """
        await self.ensure_migrations_table()
        
        applied = await self.get_applied_migrations()
        logger.info(f"Already applied migrations: {applied}")
        
        newly_applied = []
        
        # Get all SQL files in order
        migration_files = sorted(migrations_dir.glob("*.sql"))
        
        for migration_file in migration_files:
            migration_name = migration_file.stem
            
            if migration_name in applied:
                continue
            
            sql = migration_file.read_text()
            
            if await self.run_migration(migration_name, sql):
                newly_applied.append(migration_name)
        
        logger.info(f"Applied {len(newly_applied)} new migrations")
        return newly_applied
```

---

### Task 4: Initial Schema Migration

**File**: `migrations/001_initial_schema.sql`

```sql
-- Migration: 001_initial_schema
-- Description: Create core tables for crypto trading system
-- Date: 2026-03-18
-- Author: Trading System Team

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- CONFIGURATION TABLES
-- =============================================================================

-- System-wide configuration
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    is_sensitive BOOLEAN NOT NULL DEFAULT false,
    is_editable BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    version INTEGER NOT NULL DEFAULT 1
);

-- Per-symbol collection configuration
CREATE TABLE IF NOT EXISTS collection_config (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- Data collection flags
    collect_ticks BOOLEAN NOT NULL DEFAULT false,
    collect_24hr_ticker BOOLEAN NOT NULL DEFAULT true,
    collect_orderbook BOOLEAN NOT NULL DEFAULT false,
    collect_candles BOOLEAN NOT NULL DEFAULT true,
    
    -- Collection frequency (seconds)
    tick_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    ticker_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    orderbook_snapshot_interval_sec INTEGER DEFAULT 1,
    candle_intervals TEXT[] NOT NULL DEFAULT '{"1m", "5m", "15m", "1h"}',
    
    -- Order book configuration (future)
    orderbook_levels INTEGER DEFAULT 10,
    orderbook_storage_mode TEXT DEFAULT 'arrays',
    
    -- Retention policies (days)
    tick_retention_days INTEGER NOT NULL DEFAULT 30,
    ticker_retention_days INTEGER NOT NULL DEFAULT 180,
    orderbook_retention_days INTEGER DEFAULT 30,
    candle_retention_days INTEGER NOT NULL DEFAULT 365,
    
    -- Quality thresholds
    max_price_move_pct NUMERIC(10,4) DEFAULT 10.0,
    max_quantity_move_pct NUMERIC(10,4) DEFAULT 50.0,
    max_gap_seconds INTEGER DEFAULT 5,
    
    -- Regional (EU compliance)
    is_allowed BOOLEAN NOT NULL DEFAULT true,
    last_region_check TIMESTAMP DEFAULT NOW(),
    
    -- Status
    is_collecting BOOLEAN NOT NULL DEFAULT false,
    last_config_change TIMESTAMP NOT NULL DEFAULT NOW(),
    config_version INTEGER NOT NULL DEFAULT 1,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_tick_interval CHECK (tick_snapshot_interval_sec >= 1),
    CONSTRAINT chk_ticker_interval CHECK (ticker_snapshot_interval_sec >= 1),
    CONSTRAINT chk_orderbook_levels CHECK (
        orderbook_levels IS NULL OR 
        (orderbook_levels >= 5 AND orderbook_levels <= 20)
    ),
    CONSTRAINT chk_retention_days CHECK (tick_retention_days >= 0)
);

-- Audit trail for configuration changes
CREATE TABLE IF NOT EXISTS config_change_log (
    id BIGSERIAL PRIMARY KEY,
    config_type TEXT NOT NULL,
    config_key TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'system',
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'applied',
    reason TEXT
);

-- Service status tracking
CREATE TABLE IF NOT EXISTS service_status (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    pid INTEGER,
    host TEXT,
    port INTEGER,
    is_healthy BOOLEAN NOT NULL DEFAULT false,
    last_health_check TIMESTAMP,
    health_check_error TEXT,
    uptime_seconds BIGINT DEFAULT 0,
    records_processed BIGINT DEFAULT 0,
    errors_last_hour INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMP,
    config_version INTEGER DEFAULT 1,
    started_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- =============================================================================
-- MARKET DATA TABLES
-- =============================================================================

-- 24hr ticker statistics (low storage, all symbols)
CREATE TABLE IF NOT EXISTS ticker_24hr_stats (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    symbol TEXT NOT NULL,
    pair TEXT,
    
    -- Price changes
    price_change NUMERIC(20,10),
    price_change_pct NUMERIC(10,6),
    
    -- Prices
    last_price NUMERIC(20,10) NOT NULL,
    open_price NUMERIC(20,10),
    high_price NUMERIC(20,10),
    low_price NUMERIC(20,10),
    weighted_avg_price NUMERIC(20,10),
    
    -- Volumes
    last_quantity NUMERIC(20,10),
    total_volume NUMERIC(30,10),
    total_quote_volume NUMERIC(40,10),
    
    -- Trade IDs
    first_trade_id BIGINT,
    last_trade_id BIGINT,
    total_trades INTEGER,
    
    -- Times
    stats_open_time TIMESTAMP,
    stats_close_time TIMESTAMP,
    
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (time, symbol_id)
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Configuration indexes
CREATE INDEX IF NOT EXISTS idx_system_config_key ON system_config(key);
CREATE INDEX IF NOT EXISTS idx_collection_config_collecting 
    ON collection_config(is_collecting) WHERE is_collecting = true;
CREATE INDEX IF NOT EXISTS idx_config_change_log_type_key 
    ON config_change_log(config_type, config_key);
CREATE INDEX IF NOT EXISTS idx_config_change_log_changed_at 
    ON config_change_log(changed_at DESC);

-- Market data indexes
CREATE INDEX IF NOT EXISTS idx_ticker_stats_time_symbol 
    ON ticker_24hr_stats(time DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_ticker_stats_symbol_time 
    ON ticker_24hr_stats(symbol_id, time DESC);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to configuration tables
CREATE TRIGGER IF NOT EXISTS system_config_update_timestamp
    BEFORE UPDATE ON system_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER IF NOT EXISTS collection_config_update_timestamp
    BEFORE UPDATE ON collection_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER IF NOT EXISTS service_status_update_timestamp
    BEFORE UPDATE ON service_status
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- INITIAL DATA
-- =============================================================================

-- Insert default system configuration
INSERT INTO system_config (key, value, description) VALUES
('app.name', '{"value": "Crypto Trading System"}'::jsonb, 'Application name'),
('app.version', '{"value": "0.1.0"}'::jsonb, 'Application version'),
('app.environment', '{"value": "development"}'::jsonb, 'Environment'),
('app.region', '{"value": "EU"}'::jsonb, 'Operating region'),

-- Regional settings (EU compliance)
('region.allowed_quote_assets', 
 '{"value": ["USDC", "BTC", "ETH"]}'::jsonb, 
 'Allowed quote assets for EU region'),
('region.enable_auto_filter', 
 '{"value": true}'::jsonb, 
 'Enable auto-filtering by region'),

-- Data collection settings
('data_collection.enabled', '{"value": true}'::jsonb, 'Enable data collection'),
('data_collection.batch_size', '{"value": 500}'::jsonb, 'Batch size for inserts'),
('data_collection.batch_interval_ms', '{"value": 500}'::jsonb, 'Batch interval'),

-- Data quality settings
('data_quality.enabled', '{"value": true}'::jsonb, 'Enable quality validation'),
('data_quality.max_price_move_pct', '{"value": 10.0}'::jsonb, 'Max price move %'),
('data_quality.max_gap_seconds', '{"value": 5}'::jsonb, 'Max gap seconds'),

-- Enrichment settings
('enrichment.enabled', '{"value": true}'::jsonb, 'Enable enrichment'),
('enrichment.window_size', '{"value": 1000}'::jsonb, 'Window size'),
('enrichment.indicators', 
 '{"value": ["rsi_14", "macd", "sma_20", "ema_20", "bollinger"]}'::jsonb, 
 'Active indicators'),

-- Monitoring settings
('monitoring.enabled', '{"value": true}'::jsonb, 'Enable monitoring'),
('monitoring.log_level', '{"value": "INFO"}'::jsonb, 'Log level')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE system_config IS 'Global system configuration';
COMMENT ON TABLE collection_config IS 'Per-symbol collection configuration';
COMMENT ON TABLE config_change_log IS 'Audit trail for configuration changes';
COMMENT ON TABLE service_status IS 'Real-time service status';
COMMENT ON TABLE ticker_24hr_stats IS '24hr ticker statistics';

COMMENT ON COLUMN collection_config.collect_ticks IS 'Collect individual trades';
COMMENT ON COLUMN collection_config.collect_24hr_ticker IS 'Collect 24hr ticker stats';
COMMENT ON COLUMN collection_config.is_allowed IS 'EU compliance flag';
```

---

### Task 5: Repository Pattern

**File**: `src/domain/repositories/base.py`

```python
"""
Base repository interface.

This module defines the repository pattern for data access.
Repositories are ports in the hexagonal architecture.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List
from src.domain.models.base import Entity

T = TypeVar('T', bound=Entity)


class Repository(ABC, Generic[T]):
    """
    Base repository interface.
    
    Repositories provide a collection-like interface for
    accessing domain entities from storage.
    
    Type Parameters:
        T: Type of entity this repository manages
    
    Example:
        >>> class SymbolRepository(Repository[Symbol]):
        ...     async def get_by_id(self, id: int) -> Optional[Symbol]:
        ...         pass
    """
    
    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[T]:
        """
        Get entity by ID.
        
        Args:
            id: Entity ID
        
        Returns:
            Entity if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def get_all(self) -> List[T]:
        """
        Get all entities.
        
        Returns:
            List of all entities
        """
        pass
    
    @abstractmethod
    async def save(self, entity: T) -> T:
        """
        Save entity.
        
        Args:
            entity: Entity to save
        
        Returns:
            Saved entity with updated ID
        """
        pass
    
    @abstractmethod
    async def delete(self, id: int) -> bool:
        """
        Delete entity by ID.
        
        Args:
            id: Entity ID
        
        Returns:
            True if deleted, False if not found
        """
        pass
```

---

### Task 6: Test Infrastructure

**File**: `tests/conftest.py`

```python
"""
Pytest configuration and fixtures.

This module provides shared fixtures for all tests.
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from pathlib import Path


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create event loop for async tests.
    
    Yields:
        asyncio event loop
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def project_root() -> Path:
    """
    Get project root directory.
    
    Returns:
        Path to project root
    """
    return Path(__file__).parent.parent


@pytest.fixture
def migrations_dir(project_root: Path) -> Path:
    """
    Get migrations directory.
    
    Args:
        project_root: Project root path
    
    Returns:
        Path to migrations directory
    """
    return project_root / "migrations"
```

---

### Task 7: Test Database Connection

**File**: `tests/unit/infrastructure/database/test_connection.py`

```python
"""
Tests for database connection module.

Tests cover connection lifecycle, pooling, and error handling.
"""

import pytest
from src.infrastructure.database.connection import DatabaseConnection


class TestDatabaseConnection:
    """Test DatabaseConnection class."""
    
    def test_connection_initialization(self) -> None:
        """Test connection initializes with correct parameters."""
        # Arrange
        dsn = "postgresql://test:test@localhost/test"
        
        # Act
        conn = DatabaseConnection(
            dsn=dsn,
            min_size=5,
            max_size=20,
        )
        
        # Assert
        assert conn.dsn == dsn
        assert conn.min_size == 5
        assert conn.max_size == 20
        assert conn.is_connected is False
    
    def test_invalid_min_size_raises_error(self) -> None:
        """Test that invalid min_size raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="min_size must be >= 1"):
            DatabaseConnection(
                dsn="postgresql://test:test@localhost/test",
                min_size=0,
            )
    
    def test_max_size_less_than_min_size_raises_error(self) -> None:
        """Test that max_size < min_size raises ValueError."""
        # Arrange & Act & Assert
        with pytest.raises(ValueError, match="max_size must be >= min_size"):
            DatabaseConnection(
                dsn="postgresql://test:test@localhost/test",
                min_size=10,
                max_size=5,
            )
    
    @pytest.mark.asyncio
    async def test_connect_creates_pool(self, mocker) -> None:
        """Test connect creates connection pool."""
        # Arrange
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        mock_pool = mocker.AsyncMock()
        mocker.patch('asyncpg.create_pool', return_value=mock_pool)
        
        # Act
        await conn.connect()
        
        # Assert
        assert conn.is_connected is True
        assert conn._pool is not None
    
    @pytest.mark.asyncio
    async def test_disconnect_closes_pool(self, mocker) -> None:
        """Test disconnect closes connection pool."""
        # Arrange
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        mock_pool = mocker.AsyncMock()
        mocker.patch('asyncpg.create_pool', return_value=mock_pool)
        await conn.connect()
        
        # Act
        await conn.disconnect()
        
        # Assert
        assert conn.is_connected is False
        mock_pool.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_acquire_without_connect_raises_error(self) -> None:
        """Test acquire raises error if not connected."""
        # Arrange
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="Database not connected"):
            async with conn.acquire():
                pass
    
    @pytest.mark.asyncio
    async def test_pool_property_without_connect_raises_error(self) -> None:
        """Test pool property raises error if not connected."""
        # Arrange
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = conn.pool
    
    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_healthy(self, mocker) -> None:
        """Test health check returns True when database is healthy."""
        # Arrange
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        mock_pool = mocker.AsyncMock()
        mocker.patch('asyncpg.create_pool', return_value=mock_pool)
        await conn.connect()
        
        # Mock the execute call
        mock_conn = mocker.AsyncMock()
        mock_conn.execute = mocker.AsyncMock()
        
        # Mock the acquire context manager
        async def mock_acquire():
            yield mock_conn
        
        conn._pool.acquire = mock_acquire
        
        # Act
        result = await conn.health_check()
        
        # Assert
        assert result is True
```

---

## Acceptance Criteria

- [ ] Database connection module implemented
- [ ] Configuration loading works
- [ ] Migration system implemented
- [ ] Initial schema migration created
- [ ] All tables created successfully
- [ ] Indexes created for performance
- [ ] Helper functions implemented
- [ ] Triggers for updated_at working
- [ ] Repository pattern implemented
- [ ] Unit tests pass (80%+ coverage)
- [ ] Integration tests pass with Testcontainers

---

## Verification Commands

```bash
# Run unit tests
pytest tests/unit/infrastructure/database/ -v --cov

# Run integration tests (requires Docker)
pytest tests/integration/database/ -v --cov

# Run migrations
python scripts/migrate.py

# Verify schema
psql postgresql://crypto:crypto@localhost/crypto_trading
\dt  # List tables
\d symbols  # Describe table
```

---

## Next Step

After completing this step, proceed to **[003-domain-models.md](003-domain-models.md)**
