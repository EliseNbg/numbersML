# Step 2: ConfigurationSet Database Migration & Repository

## Objective
Create database migration and repository implementation for ConfigurationSet following DDD and TDD practices.

## Context
- Step 1 completed: `ConfigurationSet` domain entity created
- Existing pattern: `src/infrastructure/repositories/strategy_repository_pg.py`
- Database migrations in `migrations/` directory
- Repository pattern: Interface in `src/domain/repositories/`, PG implementation in `src/infrastructure/repositories/`

## DDD Architecture Decision (ADR)

**Decision**: Repository pattern for data access
- **Domain layer**: `ConfigSetRepository` abstract base class (interface)
- **Infrastructure layer**: `ConfigSetRepositoryPG` asyncpg implementation
- **Lifecycle**: `ConfigSetRepository` is registered in domain layer, implemented in infrastructure

**Database Schema**:
```sql
CREATE TABLE configuration_sets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1 NOT NULL
);

CREATE INDEX idx_config_sets_active ON configuration_sets(is_active) WHERE is_active = true;
```

## TDD Approach

1. **Red**: Write failing repository tests first (mocking asyncpg)
2. **Green**: Implement repository to pass tests
3. **Refactor**: Add error handling, logging, optimization

## Implementation Files

### 1. `migrations/003_configuration_sets.sql`

```sql
--
-- Migration: Create configuration_sets table
-- Phase 4 Step 2
--

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--
-- Create configuration_sets table
--
CREATE TABLE configuration_sets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    version INTEGER DEFAULT 1 NOT NULL,
    
    CONSTRAINT chk_version_positive CHECK (version > 0)
);

--
-- Indexes
--
CREATE INDEX idx_config_sets_active ON configuration_sets(is_active) WHERE is_active = true;
CREATE INDEX idx_config_sets_created_at ON configuration_sets(created_at DESC);

--
-- Auto-update updated_at trigger
--
CREATE OR REPLACE FUNCTION update_config_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_config_sets_updated_at
    BEFORE UPDATE ON configuration_sets
    FOR EACH ROW
    EXECUTE FUNCTION update_config_set_updated_at();

--
-- Comments
--
COMMENT ON TABLE configuration_sets IS 'Reusable configuration parameter sets for strategies';
COMMENT ON COLUMN configuration_sets.name IS 'Human-readable name (unique)';
COMMENT ON COLUMN configuration_sets.config IS 'JSONB with symbols, thresholds, risk, execution params';
COMMENT ON COLUMN configuration_sets.is_active IS 'Whether available for new strategy instances';
COMMENT ON COLUMN configuration_sets.version IS 'Incremented on each config update';
```

### 2. `src/domain/repositories/config_set_repository.py`

```python
"""
ConfigurationSet repository interface (Domain Layer).

Defines the contract for ConfigurationSet persistence.
Follows DDD Repository pattern - interface in domain, implementation in infrastructure.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from src.domain.strategies.config_set import ConfigurationSet


class ConfigSetRepository(ABC):
    """
    Abstract base class for ConfigurationSet repository.
    
    Defines the contract for persisting ConfigurationSet entities.
    Implementation is in infrastructure layer (asyncpg, etc.).
    
    Example:
        >>> from src.infrastructure.repositories.config_set_repository_pg import ConfigSetRepositoryPG
        >>> repo = ConfigSetRepositoryPG(connection)
        >>> config_set = await repo.save(config_set)
    """
    
    @abstractmethod
    async def save(self, config_set: ConfigurationSet) -> ConfigurationSet:
        """
        Save (insert or update) a ConfigurationSet.
        
        Args:
            config_set: ConfigurationSet entity to save
            
        Returns:
            Saved ConfigurationSet (may have updated ID/timestamps)
            
        Raises:
            ValueError: If config_set is invalid
        """
        pass
    
    @abstractmethod
    async def get_by_id(self, config_set_id: UUID) -> Optional[ConfigurationSet]:
        """
        Get ConfigurationSet by ID.
        
        Args:
            config_set_id: UUID of the configuration set
            
        Returns:
            ConfigurationSet if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[ConfigurationSet]:
        """
        Get ConfigurationSet by name.
        
        Args:
            name: Unique name of the configuration set
            
        Returns:
            ConfigurationSet if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def list_all(
        self,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ConfigurationSet]:
        """
        List ConfigurationSets with optional filtering.
        
        Args:
            active_only: If True, return only active config sets
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of ConfigurationSet entities
        """
        pass
    
    @abstractmethod
    async def delete(self, config_set_id: UUID) -> bool:
        """
        Delete a ConfigurationSet (soft delete by deactivating).
        
        Args:
            config_set_id: UUID of the configuration set
            
        Returns:
            True if deleted, False if not found
            
        Note:
            This performs a soft delete by setting is_active=False.
            Hard delete can be implemented if needed with a separate method.
        """
        pass
    
    @abstractmethod
    async def update_config(
        self,
        config_set_id: UUID,
        new_config: dict,
        updated_by: str = "system",
    ) -> Optional[ConfigurationSet]:
        """
        Update configuration and increment version.
        
        Args:
            config_set_id: UUID of the configuration set
            new_config: New configuration dictionary
            updated_by: User making the change
            
        Returns:
            Updated ConfigurationSet if found, None otherwise
        """
        pass
```

### 3. `src/infrastructure/repositories/config_set_repository_pg.py`

```python
"""
ConfigurationSet repository PostgreSQL implementation.

Uses asyncpg for async database access.
Follows DDD: Infrastructure layer implements Domain interface.
"""

import logging
from typing import List, Optional
from uuid import UUID

import asyncpg

from src.domain.repositories.config_set_repository import ConfigSetRepository
from src.domain.strategies.config_set import ConfigurationSet

logger = logging.getLogger(__name__)


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
    
    async def save(self, config_set: ConfigurationSet) -> ConfigurationSet:
        """
        Save (insert or update) a ConfigurationSet.
        
        Uses upsert (INSERT ... ON CONFLICT) for idempotency.
        
        Args:
            config_set: ConfigurationSet entity to save
            
        Returns:
            Saved ConfigurationSet with updated timestamps
        """
        try:
            # Check if exists
            existing = await self._conn.fetchrow(
                "SELECT id FROM configuration_sets WHERE id = $1",
                config_set.id,
            )
            
            if existing:
                # Update
                await self._conn.execute(
                    """
                    UPDATE configuration_sets
                    SET name = $2, description = $3, config = $4, 
                        is_active = $5, updated_at = NOW(), version = $6
                    WHERE id = $1
                    """,
                    config_set.id,
                    config_set.name,
                    config_set.description,
                    config_set.to_dict()["config"],  # Serialize config
                    config_set.is_active,
                    config_set.version,
                )
            else:
                # Insert
                await self._conn.execute(
                    """
                    INSERT INTO configuration_sets 
                        (id, name, description, config, is_active, created_by, version)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    config_set.id,
                    config_set.name,
                    config_set.description,
                    config_set.to_dict()["config"],
                    config_set.is_active,
                    config_set.created_by,
                    config_set.version,
                )
            
            # Fetch updated entity
            return await self.get_by_id(config_set.id)
            
        except asyncpg.UniqueViolationError as e:
            logger.error(f"Unique violation saving ConfigurationSet: {e}")
            raise ValueError(f"ConfigurationSet with this name already exists")
        except Exception as e:
            logger.error(f"Failed to save ConfigurationSet: {e}")
            raise
    
    async def get_by_id(self, config_set_id: UUID) -> Optional[ConfigurationSet]:
        """
        Get ConfigurationSet by ID.
        
        Args:
            config_set_id: UUID of the configuration set
            
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
            config_set_id,
        )
        
        if not row:
            return None
        
        return self._row_to_entity(row)
    
    async def get_by_name(self, name: str) -> Optional[ConfigurationSet]:
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
    ) -> List[ConfigurationSet]:
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
    
    async def delete(self, config_set_id: UUID) -> bool:
        """
        Soft delete by deactivating.
        
        Args:
            config_set_id: UUID of the configuration set
            
        Returns:
            True if deleted, False if not found
        """
        result = await self._conn.execute(
            """
            UPDATE configuration_sets
            SET is_active = false, updated_at = NOW()
            WHERE id = $1 AND is_active = true
            """,
            config_set_id,
        )
        
        return "UPDATE 1" in result
    
    async def update_config(
        self,
        config_set_id: UUID,
        new_config: dict,
        updated_by: str = "system",
    ) -> Optional[ConfigurationSet]:
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
            new_config,
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
        from src.domain.strategies.config_set import ConfigurationSet
        
        return ConfigurationSet(
            name=row["name"],
            config=dict(row["config"]),  # JSONB comes as dict
            description=row["description"],
            id=row["id"],
            is_active=row["is_active"],
            created_by=row["created_by"],
        )
```

### 4. `tests/unit/infrastructure/repositories/test_config_set_repository_pg.py`

```python
"""
Unit tests for ConfigSetRepositoryPG.

Uses unittest.mock to mock asyncpg.Connection.
Follows TDD: tests first, then implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID
from datetime import datetime, timezone

from src.domain.strategies.config_set import ConfigurationSet
from src.infrastructure.repositories.config_set_repository_pg import ConfigSetRepositoryPG


@pytest.fixture
def mock_connection():
    """Create a mock asyncpg connection."""
    conn = AsyncMock(spec=asyncpg.Connection)
    return conn


@pytest.fixture
def repository(mock_connection):
    """Create repository with mock connection."""
    return ConfigSetRepositoryPG(mock_connection)


@pytest.fixture
def sample_config_set():
    """Create a sample ConfigurationSet for testing."""
    return ConfigurationSet(
        name="Test Config",
        config={"symbols": ["BTC/USDT"], "risk": {"max_position_size_pct": 10}},
        description="Test description",
        created_by="test",
    )


class TestConfigSetRepositoryPGSave:
    """Tests for save method."""
    
    @pytest.mark.asyncio
    async def test_save_new_config_set(self, repository, mock_connection, sample_config_set):
        """Test saving a new ConfigurationSet."""
        # Mock no existing record (new insert)
        mock_connection.fetchrow.return_value = None
        mock_connection.execute.return_value = "INSERT 0 1"
        
        # Mock the get_by_id call after save
        mock_connection.fetchrow.side_effect = [
            None,  # First call: check if exists
            {   # Second call: fetch after insert
                "id": sample_config_set.id,
                "name": sample_config_set.name,
                "description": sample_config_set.description,
                "config": sample_config_set.to_dict()["config"],
                "is_active": sample_config_set.is_active,
                "created_by": sample_config_set.created_by,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "version": 1,
            },
        ]
        
        result = await repository.save(sample_config_set)
        
        assert result is not None
        assert result.id == sample_config_set.id
        assert result.name == sample_config_set.name
        assert mock_connection.execute.called
    
    @pytest.mark.asyncio
    async def test_save_existing_config_set(self, repository, mock_connection, sample_config_set):
        """Test updating an existing ConfigurationSet."""
        # Mock existing record
        mock_connection.fetchrow.return_value = {"id": sample_config_set.id}
        mock_connection.execute.return_value = "UPDATE 1"
        
        mock_connection.fetchrow.side_effect = [
            {"id": sample_config_set.id},  # Check exists
            {   # Fetch updated
                "id": sample_config_set.id,
                "name": sample_config_set.name,
                "description": sample_config_set.description,
                "config": sample_config_set.to_dict()["config"],
                "is_active": sample_config_set.is_active,
                "created_by": sample_config_set.created_by,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "version": 1,
            },
        ]
        
        result = await repository.save(sample_config_set)
        
        assert result is not None
        # Verify UPDATE was called, not INSERT
        update_call = mock_connection.execute.call_args
        assert "UPDATE" in update_call[0][0] or "UPDATE" in str(update_call)
    
    @pytest.mark.asyncio
    async def test_save_duplicate_name_raises_error(self, repository, mock_connection, sample_config_set):
        """Test that duplicate name raises ValueError."""
        mock_connection.execute.side_effect = asyncpg.UniqueViolationError("unique_violation")
        
        with pytest.raises(ValueError, match="already exists"):
            await repository.save(sample_config_set)


class TestConfigSetRepositoryPGGetById:
    """Tests for get_by_id method."""
    
    @pytest.mark.asyncio
    async def test_get_existing_config_set(self, repository, mock_connection, sample_config_set):
        """Test getting an existing ConfigurationSet by ID."""
        mock_connection.fetchrow.return_value = {
            "id": sample_config_set.id,
            "name": sample_config_set.name,
            "description": sample_config_set.description,
            "config": sample_config_set.to_dict()["config"],
            "is_active": True,
            "created_by": "test",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "version": 1,
        }
        
        result = await repository.get_by_id(sample_config_set.id)
        
        assert result is not None
        assert result.id == sample_config_set.id
        assert result.name == sample_config_set.name
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, repository, mock_connection):
        """Test that getting non-existent ID returns None."""
        mock_connection.fetchrow.return_value = None
        
        result = await repository.get_by_id(uuid4())
        
        assert result is None


class TestConfigSetRepositoryPGListAll:
    """Tests for list_all method."""
    
    @pytest.mark.asyncio
    async def test_list_all_config_sets(self, repository, mock_connection):
        """Test listing all ConfigurationSets."""
        mock_connection.fetch.return_value = [
            {
                "id": uuid4(),
                "name": "Config 1",
                "description": "Desc 1",
                "config": {"key": "value1"},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "version": 1,
            },
            {
                "id": uuid4(),
                "name": "Config 2",
                "description": "Desc 2",
                "config": {"key": "value2"},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "version": 1,
            },
        ]
        
        results = await repository.list_all()
        
        assert len(results) == 2
        assert results[0].name == "Config 1"
        assert results[1].name == "Config 2"
    
    @pytest.mark.asyncio
    async def test_list_active_only(self, repository, mock_connection):
        """Test listing only active ConfigurationSets."""
        mock_connection.fetch.return_value = [
            {
                "id": uuid4(),
                "name": "Active Config",
                "description": None,
                "config": {},
                "is_active": True,
                "created_by": "test",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "version": 1,
            },
        ]
        
        results = await repository.list_all(active_only=True)
        
        assert len(results) == 1
        assert results[0].is_active is True
        # Verify query included WHERE is_active = true
        call_args = mock_connection.fetch.call_args
        assert "is_active" in call_args[0][0]


class TestConfigSetRepositoryPGDelete:
    """Tests for delete method (soft delete)."""
    
    @pytest.mark.asyncio
    async def test_delete_existing_config_set(self, repository, mock_connection):
        """Test soft deleting an existing ConfigurationSet."""
        mock_connection.execute.return_value = "UPDATE 1"
        
        result = await repository.delete(uuid4())
        
        assert result is True
        # Verify UPDATE was called with is_active = false
        call_args = mock_connection.execute.call_args
        assert "is_active" in call_args[0][0] or "UPDATE" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, repository, mock_connection):
        """Test that deleting non-existent returns False."""
        mock_connection.execute.return_value = "UPDATE 0"
        
        result = await repository.delete(uuid4())
        
        assert result is False


class TestConfigSetRepositoryPGUpdateConfig:
    """Tests for update_config method."""
    
    @pytest.mark.asyncio
    async def test_update_config_success(self, repository, mock_connection):
        """Test successfully updating configuration."""
        config_set_id = uuid4()
        new_config = {"symbols": ["ETH/USDT"], "risk": {"max_position_size_pct": 20}}
        
        # Mock get_by_id after update
        mock_connection.execute.return_value = "UPDATE 1"
        mock_connection.fetchrow.return_value = {
            "id": config_set_id,
            "name": "Test",
            "description": None,
            "config": new_config,
            "is_active": True,
            "created_by": "test",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "version": 2,  # Incremented
        }
        
        result = await repository.update_config(config_set_id, new_config)
        
        assert result is not None
        assert result.version == 2
        # Verify UPDATE was called with version increment
        call_args = mock_connection.execute.call_args
        assert "version = version + 1" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_update_config_nonexistent_returns_none(self, repository, mock_connection):
        """Test updating non-existent config set returns None."""
        mock_connection.execute.return_value = "UPDATE 0"
        
        result = await repository.update_config(uuid4(), {"new": "config"})
        
        assert result is None
```

## LLM Implementation Prompt

```text
You are implementing Step 2 of Phase 4: ConfigurationSet Database Migration & Repository.

## Your Task

Create the database migration and repository implementation for ConfigurationSet.

## Context

- Step 1 is complete: ConfigurationSet domain entity exists in src/domain/strategies/config_set.py
- Follow DDD: Repository interface in domain, implementation in infrastructure
- Existing pattern: See src/infrastructure/repositories/strategy_repository_pg.py
- Database migrations go in migrations/ directory

## Requirements

1. Create `migrations/003_configuration_sets.sql` with:
   - CREATE TABLE configuration_sets with all columns (id, name, description, config JSONB, is_active, etc.)
   - UNIQUE constraint on name
   - CHECK constraint on version > 0
   - Index on is_active for filtered queries
   - Trigger to auto-update updated_at column
   - Comments on table and key columns

2. Create `src/domain/repositories/config_set_repository.py` with:
   - Abstract base class ConfigSetRepository(ABC)
   - Methods: save, get_by_id, get_by_name, list_all, delete, update_config
   - Full type annotations (UUID, ConfigurationSet, etc.)
   - Google-style docstrings
   - Matching existing repository patterns in src/domain/repositories/

3. Create `src/infrastructure/repositories/config_set_repository_pg.py` with:
   - ConfigSetRepositoryPG implementing ConfigSetRepository
   - Uses asyncpg for async database access
   - save(): upsert (INSERT ON CONFLICT) for idempotency
   - get_by_id(), get_by_name(): SELECT by respective fields
   - list_all(): SELECT with optional active_only filter, pagination
   - delete(): Soft delete (UPDATE is_active = false)
   - update_config(): UPDATE config and increment version
   - _row_to_entity(): Convert asyncpg Record to ConfigurationSet

4. Create `tests/unit/infrastructure/repositories/test_config_set_repository_pg.py` with TDD:
   - TestConfigSetRepositoryPGSave: new, existing, duplicate name error
   - TestConfigSetRepositoryPGGetById: existing, non-existent
   - TestConfigSetRepositoryPGListAll: all, active_only filter
   - TestConfigSetRepositoryPGDelete: existing, non-existent
   - TestConfigSetRepositoryPGUpdateConfig: success, non-existent
   - Use unittest.mock.AsyncMock to mock asyncpg.Connection
   - Mark async tests with @pytest.mark.asyncio

## Constraints

- Follow AGENTS.md coding standards
- Use type hints on all public methods (mypy strict)
- Use Google-style docstrings
- Use relative imports within package
- Line length max 100 characters
- Log errors with logger.error(f"message: {e}")
- Use asyncpg for PostgreSQL access (not psycopg2)
- Repository must be async (all methods async def)

## Acceptance Criteria

1. Migration 003 creates table with correct schema
2. ConfigSetRepository interface defines all required methods
3. ConfigSetRepositoryPG implements all interface methods
4. Soft delete sets is_active=False (not DELETE FROM)
5. update_config() increments version by 1
6. All unit tests pass with mocked connection
7. mypy passes with no errors
8. ruff check passes with no errors
9. black formatting applied

## Commands to Run

```bash
# Format and lint
black src/domain/repositories/config_set_repository.py src/infrastructure/repositories/config_set_repository_pg.py tests/unit/infrastructure/repositories/test_config_set_repository_pg.py
ruff check src/domain/repositories/config_set_repository.py src/infrastructure/repositories/config_set_repository_pg.py tests/unit/infrastructure/repositories/test_config_set_repository_pg.py
mypy src/domain/repositories/config_set_repository.py src/infrastructure/repositories/config_set_repository_pg.py

# Run tests
.venv/bin/python -m pytest tests/unit/infrastructure/repositories/test_config_set_repository_pg.py -v
```

## Output

1. List of files created/modified
2. Test results (passed/failed count)
3. mypy/ruff output (no errors)
4. Any issues encountered and how resolved
```

## Success Criteria

- [ ] Migration file creates configuration_sets table correctly
- [ ] ConfigSetRepository abstract base class created
- [ ] ConfigSetRepositoryPG implements all interface methods
- [ ] save() handles both insert and update (upsert)
- [ ] Soft delete implemented (is_active = false)
- [ ] update_config() increments version
- [ ] All unit tests pass (mocked asyncpg)
- [ ] mypy strict mode passes
- [ ] ruff check passes (rules: E, W, F, I, N, UP, B, C4)
- [ ] black formatting applied
- [ ] Google-style docstrings on all public methods
