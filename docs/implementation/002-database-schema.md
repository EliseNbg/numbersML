# Step 002: Database Schema

## Context

**Phase**: 1 - Foundation  
**Effort**: 4 hours  
**Dependencies**: Step 001 (Project Setup) completed

---

## Goal

Implement PostgreSQL database schema with migrations, focusing on:
- Core tables (symbols, trades, indicator definitions, tick_indicators)
- **Binance asset metadata fields** (synced daily from Binance API)
- Helper functions and triggers
- Proper indexing for time-series data

---

## Domain Model

### Entities

```python
# Domain layer preview (will be implemented in Step 003)

class Symbol(Entity):
    id: int
    symbol: str              # e.g., "BTC/USDT"
    base_asset: str          # e.g., "BTC"
    quote_asset: str         # e.g., "USDT"
    
    # Trading parameters
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal
    
    # Binance metadata (synced daily)
    binance_asset_code: str  # e.g., "BNB"
    binance_asset_name: str  # e.g., "Bitcoin Cash SV"
    binance_id: int          # Binance asset ID
    logo_url: str
    tags: List[str]          # e.g., ["Layer1_Layer2", "BSC", "NFT"]
    is_trading: bool         # Binance trading flag
    is_delisted: bool        # Binance delisted flag
    plate_type: str          # "MAINWEB", "DEX"
    etf: bool
    
    # Status
    is_active: bool          # Our flag: collect data for this symbol
    last_synced_at: datetime
    
    ...
```

### Value Objects

```python
class SymbolId(ValueObject):
    value: int

class TradeId(ValueObject):
    value: str

class IndicatorName(ValueObject):
    value: str
```

### Domain Events

```python
class IndicatorChangedEvent(DomainEvent):
    indicator_id: int
    indicator_name: str
    change_type: str         # 'code_changed' or 'params_changed'
    occurred_at: datetime
```

---

## Implementation Tasks

### Task 2.1: Database Connection Module

**File**: `src/infrastructure/database/connection.py`

```python
"""PostgreSQL database connection management."""

import asyncpg
from typing import Optional, AsyncContextManager
from contextlib import asynccontextmanager


class DatabaseConnection:
    """Manages PostgreSQL connection pool."""
    
    def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20):
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self._pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Create connection pool."""
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=self.min_size,
            max_size=self.max_size,
            command_timeout=60,
        )
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool."""
        if not self._pool:
            raise RuntimeError("Database not connected")
        
        async with self._pool.acquire() as conn:
            yield conn
    
    @property
    def pool(self) -> asyncpg.Pool:
        """Get connection pool."""
        if not self._pool:
            raise RuntimeError("Database not connected")
        return self._pool
```

**File**: `src/infrastructure/database/__init__.py`

```python
"""Database infrastructure module."""

from .connection import DatabaseConnection

__all__ = ["DatabaseConnection"]
```

---

### Task 2.2: Schema Migration System

**File**: `src/infrastructure/database/migrations.py`

```python
"""Database migration management."""

import asyncpg
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self, connection: asyncpg.Connection):
        self.conn = connection
    
    async def ensure_migrations_table(self) -> None:
        """Create migrations tracking table if not exists."""
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
    
    async def get_applied_migrations(self) -> List[str]:
        """Get list of already applied migrations."""
        rows = await self.conn.fetch(
            "SELECT migration_name FROM schema_migrations ORDER BY applied_at"
        )
        return [row['migration_name'] for row in rows]
    
    async def mark_migration_applied(self, migration_name: str) -> None:
        """Mark a migration as applied."""
        await self.conn.execute(
            "INSERT INTO schema_migrations (migration_name) VALUES ($1)",
            migration_name
        )
    
    async def run_migration(self, migration_name: str, sql: str) -> bool:
        """Run a single migration."""
        applied = await self.get_applied_migrations()
        
        if migration_name in applied:
            logger.info(f"Migration {migration_name} already applied, skipping")
            return False
        
        logger.info(f"Applying migration: {migration_name}")
        
        async with self.conn.transaction():
            await self.conn.execute(sql)
            await self.mark_migration_applied(migration_name)
        
        return True
```

---

### Task 2.3: Initial Schema Migration

**File**: `migrations/001_initial_schema.sql`

```sql
-- Migration: 001_initial_schema
-- Description: Create core tables for crypto trading system

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- REFERENCE DATA
-- =============================================================================

CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    
    -- Basic identification
    symbol TEXT NOT NULL UNIQUE,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'binance',
    
    -- Trading parameters
    tick_size NUMERIC(20,10) NOT NULL DEFAULT 0.00000001,
    step_size NUMERIC(20,10) NOT NULL DEFAULT 0.00000001,
    min_notional NUMERIC(20,10) NOT NULL DEFAULT 10,
    price_precision INTEGER NOT NULL DEFAULT 8,
    quantity_precision INTEGER NOT NULL DEFAULT 8,
    
    -- Binance asset metadata (synced daily from Binance API)
    binance_asset_code TEXT,
    binance_asset_name TEXT,
    binance_id INTEGER,
    logo_url TEXT,
    tags TEXT[] DEFAULT '{}',
    is_trading BOOLEAN NOT NULL DEFAULT true,
    is_delisted BOOLEAN NOT NULL DEFAULT false,
    plate_type TEXT,
    etf BOOLEAN NOT NULL DEFAULT false,
    
    -- Withdrawal/fee info
    commission_rate NUMERIC(20,10) NOT NULL DEFAULT 0,
    free_audit_withdraw_amt NUMERIC(30,10) NOT NULL DEFAULT 0,
    asset_digit INTEGER NOT NULL DEFAULT 8,
    fee_digit INTEGER NOT NULL DEFAULT 2,
    
    -- Status flags
    is_active BOOLEAN NOT NULL DEFAULT false,
    
    -- Sync metadata
    last_synced_at TIMESTAMP,
    sync_source TEXT DEFAULT 'binance_api',
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_symbols_active ON symbols(is_active);
CREATE INDEX idx_symbols_exchange ON symbols(exchange);
CREATE INDEX idx_symbols_binance_id ON symbols(binance_id);
CREATE INDEX idx_symbols_trading ON symbols(is_trading);
CREATE INDEX idx_symbols_delisted ON symbols(is_delisted);
CREATE INDEX idx_symbols_plate_type ON symbols(plate_type);

-- Index for finding symbols that need sync (not synced in last 24h)
CREATE INDEX idx_symbols_needs_sync ON symbols(last_synced_at) 
    WHERE last_synced_at IS NULL OR last_synced_at < NOW() - INTERVAL '24 hours';
CREATE INDEX idx_symbols_exchange ON symbols(exchange);

-- =============================================================================
-- RAW TICK DATA
-- =============================================================================

CREATE TABLE IF NOT EXISTS trades (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    trade_id TEXT NOT NULL,
    price NUMERIC(20,10) NOT NULL,
    quantity NUMERIC(20,10) NOT NULL,
    side TEXT NOT NULL,
    is_buyer_maker BOOLEAN NOT NULL,
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_time_symbol ON trades(time DESC, symbol_id);
CREATE INDEX idx_trades_symbol_time ON trades(symbol_id, time DESC);
CREATE UNIQUE INDEX idx_trades_unique ON trades(trade_id, symbol_id);

-- =============================================================================
-- DYNAMIC INDICATOR DEFINITIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS indicator_definitions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    class_name TEXT NOT NULL,
    module_path TEXT NOT NULL,
    category TEXT NOT NULL,
    params_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    code_hash TEXT NOT NULL,
    code_version INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    input_fields JSONB NOT NULL DEFAULT '["price", "volume"]'::jsonb,
    output_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_calculated_at TIMESTAMP
);

CREATE INDEX idx_indicators_category ON indicator_definitions(category);
CREATE INDEX idx_indicators_active ON indicator_definitions(is_active);

-- =============================================================================
-- INDICATOR VALUES (JSONB Storage)
-- =============================================================================

CREATE TABLE IF NOT EXISTS tick_indicators (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    price NUMERIC(20,10) NOT NULL,
    volume NUMERIC(20,10) NOT NULL,
    values JSONB NOT NULL DEFAULT '{}'::jsonb,
    indicator_keys TEXT[] NOT NULL DEFAULT '{}',
    indicator_version INTEGER NOT NULL DEFAULT 1,
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (time, symbol_id)
);

CREATE INDEX idx_tick_ind_time_symbol ON tick_indicators(time DESC, symbol_id);
CREATE INDEX idx_tick_ind_symbol_time ON tick_indicators(symbol_id, time DESC);
CREATE INDEX idx_tick_ind_values_gin ON tick_indicators USING GIN (values);
CREATE INDEX idx_tick_ind_keys ON tick_indicators USING GIN (indicator_keys);

-- =============================================================================
-- RECALCULATION JOBS
-- =============================================================================

CREATE TABLE IF NOT EXISTS recalculation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_id INTEGER REFERENCES indicator_definitions(id),
    indicator_name TEXT NOT NULL,
    symbol_id INTEGER REFERENCES symbols(id),
    time_start TIMESTAMP,
    time_end TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending',
    progress_percent NUMERIC(5,2) DEFAULT 0,
    ticks_processed BIGINT DEFAULT 0,
    ticks_total BIGINT,
    errors_count INTEGER DEFAULT 0,
    last_error TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTERVAL,
    triggered_by TEXT NOT NULL DEFAULT 'manual',
    triggered_by_user TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recalc_status ON recalculation_jobs(status);
CREATE INDEX idx_recalc_indicator ON recalculation_jobs(indicator_id);

-- =============================================================================
-- COLLECTION STATE & MONITORING
-- =============================================================================

CREATE TABLE IF NOT EXISTS collection_state (
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    data_type TEXT NOT NULL,
    last_collected_time TIMESTAMP,
    last_processed_time TIMESTAMP,
    last_trade_id TEXT,
    is_collecting BOOLEAN NOT NULL DEFAULT false,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol_id, data_type)
);

CREATE TABLE IF NOT EXISTS service_health (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL,
    records_processed BIGINT DEFAULT 0,
    indicators_calculated BIGINT DEFAULT 0,
    recalculation_jobs_run BIGINT DEFAULT 0,
    errors_last_hour INTEGER DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL,
    service TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    log_date DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX idx_event_log_timestamp ON event_log(timestamp);
CREATE INDEX idx_event_log_service ON event_log(service);
CREATE INDEX idx_event_log_date ON event_log(log_date);

-- =============================================================================
-- HELPER VIEWS
-- =============================================================================

CREATE OR REPLACE VIEW active_symbols AS
SELECT id, symbol, base_asset, quote_asset, exchange
FROM symbols
WHERE is_active = true;

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

CREATE OR REPLACE FUNCTION get_or_create_symbol(
    p_symbol TEXT,
    p_base_asset TEXT,
    p_quote_asset TEXT,
    p_exchange TEXT DEFAULT 'binance',
    p_tick_size NUMERIC DEFAULT 0.00000001,
    p_step_size NUMERIC DEFAULT 0.00000001,
    p_min_notional NUMERIC DEFAULT 10
) RETURNS INTEGER AS $$
DECLARE v_symbol_id INTEGER;
BEGIN
    SELECT id INTO v_symbol_id FROM symbols
    WHERE symbol = p_symbol AND exchange = p_exchange;
    
    IF v_symbol_id IS NULL THEN
        INSERT INTO symbols (symbol, base_asset, quote_asset, exchange, tick_size, step_size, min_notional)
        VALUES (p_symbol, p_base_asset, p_quote_asset, p_exchange, p_tick_size, p_step_size, p_min_notional)
        RETURNING id INTO v_symbol_id;
    END IF;
    
    RETURN v_symbol_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_active_symbols() 
RETURNS TABLE (
    id INTEGER,
    symbol TEXT,
    base_asset TEXT,
    quote_asset TEXT,
    exchange TEXT
) AS $$
BEGIN
    RETURN QUERY SELECT s.id, s.symbol, s.base_asset, s.quote_asset, s.exchange
    FROM symbols s
    WHERE s.is_active = true;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION is_symbol_active(p_symbol TEXT) 
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM symbols 
        WHERE symbol = p_symbol AND is_active = true
    );
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER symbols_update_updated_at
    BEFORE UPDATE ON symbols
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER indicator_definitions_update_updated_at
    BEFORE UPDATE ON indicator_definitions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tick_indicators_update_updated_at
    BEFORE UPDATE ON tick_indicators
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

### Task 2.4: Migration Runner Script

**File**: `scripts/migrate.py`

```python
#!/usr/bin/env python3
"""Run database migrations."""

import asyncio
import sys
from pathlib import Path
import asyncpg

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from infrastructure.database.migrations import MigrationManager


MIGRATIONS = [
    ("001_initial_schema", "migrations/001_initial_schema.sql"),
    # Add future migrations here
]


async def main():
    """Run all pending migrations."""
    dsn = "postgresql://user:password@localhost/crypto_trading"
    
    print(f"Connecting to database: {dsn}")
    conn = await asyncpg.connect(dsn)
    
    try:
        manager = MigrationManager(conn)
        await manager.ensure_migrations_table()
        
        applied = await manager.get_applied_migrations()
        print(f"Already applied: {applied}")
        
        for migration_name, migration_file in MIGRATIONS:
            migration_path = Path(__file__).parent.parent / migration_file
            
            if not migration_path.exists():
                print(f"ERROR: Migration file not found: {migration_path}")
                continue
            
            sql = migration_path.read_text()
            
            result = await manager.run_migration(migration_name, sql)
            
            if result:
                print(f"✓ Applied: {migration_name}")
            else:
                print(f"- Skipped: {migration_name}")
        
        print("\nMigration complete!")
    
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

### Task 2.5: Database Configuration

**File**: `config/database.yaml`

```yaml
development:
  dsn: "postgresql://crypto:crypto@localhost:5432/crypto_trading_dev"
  min_size: 5
  max_size: 10

test:
  dsn: "postgresql://crypto:crypto@localhost:5432/crypto_trading_test"
  min_size: 2
  max_size: 5

production:
  dsn: "postgresql://crypto:crypto@localhost:5432/crypto_trading"
  min_size: 10
  max_size: 50
```

**File**: `src/infrastructure/database/config.py`

```python
"""Database configuration."""

import yaml
from pathlib import Path
from typing import Dict


def load_database_config(environment: str = "development") -> Dict:
    """Load database configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent / "config" / "database.yaml"
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    return config.get(environment, config["development"])
```

---

## Test Requirements

### Test Coverage Target: **80%**

### Unit Tests

**File**: `tests/unit/infrastructure/database/test_connection.py`

```python
"""Test database connection management."""

import pytest
from src.infrastructure.database.connection import DatabaseConnection


class TestDatabaseConnection:
    """Test DatabaseConnection class."""
    
    def test_connection_initialization(self):
        """Test connection initializes with correct parameters."""
        conn = DatabaseConnection(
            dsn="postgresql://test:test@localhost/test",
            min_size=2,
            max_size=10
        )
        
        assert conn.dsn == "postgresql://test:test@localhost/test"
        assert conn.min_size == 2
        assert conn.max_size == 10
        assert conn._pool is None
    
    @pytest.mark.asyncio
    async def test_connect_creates_pool(self, mock_asyncpg):
        """Test connect creates connection pool."""
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        
        await conn.connect()
        
        assert conn._pool is not None
        mock_asyncpg.create_pool.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_disconnect_closes_pool(self, mock_asyncpg):
        """Test disconnect closes connection pool."""
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        await conn.connect()
        
        await conn.disconnect()
        
        conn._pool.close.assert_called_once()
    
    def test_acquire_without_connect_raises_error(self):
        """Test acquire raises error if not connected."""
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        
        with pytest.raises(RuntimeError, match="Database not connected"):
            async with conn.acquire():
                pass
    
    def test_pool_property_without_connect_raises_error(self):
        """Test pool property raises error if not connected."""
        conn = DatabaseConnection(dsn="postgresql://test:test@localhost/test")
        
        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = conn.pool
```

**File**: `tests/unit/infrastructure/database/test_migrations.py`

```python
"""Test migration management."""

import pytest
from src.infrastructure.database.migrations import MigrationManager


class TestMigrationManager:
    """Test MigrationManager class."""
    
    @pytest.mark.asyncio
    async def test_ensure_migrations_table(self, mock_conn):
        """Test migrations table is created."""
        manager = MigrationManager(mock_conn)
        
        await manager.ensure_migrations_table()
        
        mock_conn.execute.assert_called_once()
        assert "CREATE TABLE IF NOT EXISTS schema_migrations" in \
               mock_conn.execute.call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_get_applied_migrations(self, mock_conn):
        """Test getting applied migrations."""
        mock_conn.fetch.return_value = [
            {'migration_name': '001_initial_schema'},
            {'migration_name': '002_add_indexes'},
        ]
        
        manager = MigrationManager(mock_conn)
        result = await manager.get_applied_migrations()
        
        assert result == ['001_initial_schema', '002_add_indexes']
    
    @pytest.mark.asyncio
    async def test_run_migration_applies_new_migration(self, mock_conn):
        """Test running a new migration."""
        mock_conn.fetch.return_value = []  # No migrations applied yet
        
        manager = MigrationManager(mock_conn)
        result = await manager.run_migration(
            "001_test",
            "CREATE TABLE test (id INT)"
        )
        
        assert result is True
        mock_conn.execute.assert_called()
    
    @pytest.mark.asyncio
    async def test_run_migration_skips_already_applied(self, mock_conn):
        """Test skipping already applied migration."""
        mock_conn.fetch.return_value = [
            {'migration_name': '001_test'}
        ]
        
        manager = MigrationManager(mock_conn)
        result = await manager.run_migration(
            "001_test",
            "CREATE TABLE test (id INT)"
        )
        
        assert result is False
```

### Integration Tests

**File**: `tests/integration/database/test_schema.py`

```python
"""Test database schema with real PostgreSQL."""

import pytest
import asyncpg
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def postgres_container():
    """Create PostgreSQL test container."""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.mark.integration
@pytest.mark.asyncio
async def test_initial_schema_migration(postgres_container):
    """Test initial schema migration creates all tables."""
    dsn = postgres_container.get_connection_url()
    conn = await asyncpg.connect(dsn)
    
    try:
        # Run migration
        migration_sql = Path("migrations/001_initial_schema.sql").read_text()
        await conn.execute(migration_sql)
        
        # Verify tables exist
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        
        table_names = [t['table_name'] for t in tables]
        
        assert 'symbols' in table_names
        assert 'trades' in table_names
        assert 'indicator_definitions' in table_names
        assert 'tick_indicators' in table_names
        assert 'recalculation_jobs' in table_names
    
    finally:
        await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_helper_functions_work(postgres_container):
    """Test helper functions work correctly."""
    dsn = postgres_container.get_connection_url()
    conn = await asyncpg.connect(dsn)
    
    try:
        # Run migration
        migration_sql = Path("migrations/001_initial_schema.sql").read_text()
        await conn.execute(migration_sql)
        
        # Test get_or_create_symbol
        symbol_id = await conn.fetchval(
            "SELECT get_or_create_symbol($1, $2, $3)",
            "BTC/USDT", "BTC", "USDT"
        )
        
        assert symbol_id == 1
        
        # Test is_symbol_active
        is_active = await conn.fetchval(
            "SELECT is_symbol_active($1)",
            "BTC/USDT"
        )
        
        assert is_active is False  # Default is inactive
    
    finally:
        await conn.close()
```

---

## Acceptance Criteria

- [ ] Database connection module implemented
- [ ] Migration system implemented
- [ ] Initial schema migration created
- [ ] All tables created successfully
- [ ] Indexes created for performance
- [ ] Helper functions implemented
- [ ] Triggers for updated_at working
- [ ] Migration runner script works
- [ ] Unit tests pass (80%+ coverage)
- [ ] Integration tests pass with Testcontainers
- [ ] Documentation updated

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
psql postgresql://crypto:crypto@localhost/crypto_trading_dev
\dt  # List tables
\d symbols  # Describe table
```

---

## Next Step

After completing this step, proceed to **[003-domain-models.md](003-domain-models.md)**
