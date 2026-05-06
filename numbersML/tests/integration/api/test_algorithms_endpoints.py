"""
Integration tests for Algorithms API endpoints with real database.

Tests that the endpoints work correctly with the actual database schema.
Validates that the algorithm_versions and algorithm_events tables exist and work correctly.
"""

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

# Set environment variables BEFORE importing app
os.environ["API_KEY_ADMIN"] = "admin-secret-key"
os.environ["API_KEY_TRADER"] = "trader-secret-key"
os.environ["API_KEY_READ"] = "read-secret-key"

from src.infrastructure.api.app import app
from src.infrastructure.api.routes.algorithms import get_algorithm_repo, get_event_repo


def get_db_connection():
    """Get database connection directly using asyncpg."""
    async def connect():
        return await asyncpg.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER", "crypto"),
            password=os.environ.get("DB_PASS", "crypto_secret"),
            database=os.environ.get("DB_NAME", "crypto_trading"),
        )
    return asyncio.run(connect())


def setup_algorithm():
    """Create a test algorithm and return its ID."""
    async def setup():
        conn = await asyncpg.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER", "crypto"),
            password=os.environ.get("DB_PASS", "crypto_secret"),
            database=os.environ.get("DB_NAME", "crypto_trading"),
        )
        try:
            # Create test algorithm with unique name
            import time
            unique_name = f'Test Algorithm {time.time()}'
            alg_row = await conn.fetchrow(
                """
                INSERT INTO algorithms (name, description, status)
                VALUES ($1, 'For testing', 'draft')
                RETURNING id
                """
            , unique_name)
            return alg_row["id"]
        finally:
            await conn.close()
    return asyncio.run(setup())


def cleanup_algorithm(algorithm_id):
    """Clean up test algorithm and related data."""
    async def cleanup():
        conn = await asyncpg.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER", "crypto"),
            password=os.environ.get("DB_PASS", "crypto_secret"),
            database=os.environ.get("DB_NAME", "crypto_trading"),
        )
        try:
            await conn.execute("DELETE FROM algorithm_events WHERE algorithm_id = $1", algorithm_id)
            await conn.execute("DELETE FROM algorithm_versions WHERE algorithm_id = $1", algorithm_id)
            await conn.execute("DELETE FROM algorithm_runs WHERE algorithm_id = $1", algorithm_id)
            await conn.execute("DELETE FROM algorithm_backtests WHERE strategy_id = $1", algorithm_id)
            await conn.execute("DELETE FROM algorithms WHERE id = $1", algorithm_id)
        finally:
            await conn.close()
    asyncio.run(cleanup())


def setup_algorithm_version(algorithm_id):
    """Create a test algorithm version and return its ID."""
    async def setup():
        conn = await asyncpg.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER", "crypto"),
            password=os.environ.get("DB_PASS", "crypto_secret"),
            database=os.environ.get("DB_NAME", "crypto_trading"),
        )
        try:
            version_row = await conn.fetchrow(
                """
                INSERT INTO algorithm_versions (algorithm_id, version, schema_version, config, is_active)
                VALUES ($1, 1, 1, '{}', true)
                RETURNING id
                """
            , algorithm_id)
            return version_row["id"]
        finally:
            await conn.close()
    return asyncio.run(setup())


class TestAlgorithmsDatabaseSchemaValidation:
    """Validate that database schema matches code expectations."""

    def test_algorithm_versions_table_exists(self):
        """Test that algorithm_versions table exists."""
        async def check_table():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            try:
                row = await conn.fetchrow(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'algorithm_versions'
                    """
                )
                return row is not None
            finally:
                await conn.close()
        has_table = asyncio.run(check_table())
        assert has_table, "algorithm_versions table does not exist"

    def test_algorithm_events_table_exists(self):
        """Test that algorithm_events table exists."""
        async def check_table():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            try:
                row = await conn.fetchrow(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'algorithm_events'
                    """
                )
                return row is not None
            finally:
                await conn.close()
        has_table = asyncio.run(check_table())
        assert has_table, "algorithm_events table does not exist"

    def test_algorithm_runs_table_exists(self):
        """Test that algorithm_runs table exists."""
        async def check_table():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            try:
                row = await conn.fetchrow(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'algorithm_runs'
                    """
                )
                return row is not None
            finally:
                await conn.close()
        has_table = asyncio.run(check_table())
        assert has_table, "algorithm_runs table does not exist"


class TestAlgorithmsEndpointsWithRealDB:
    """Test Algorithms API with real database."""

    def setup_method(self):
        """Set up test client and database."""
        self.algorithm_id = setup_algorithm()

        # Override the dependencies to use real database
        async def get_real_algo_repo():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            from src.infrastructure.repositories.algorithm_repository_pg import AlgorithmRepositoryPG
            repo = AlgorithmRepositoryPG(conn)
            yield repo
            await conn.close()

        async def get_real_event_repo():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            from src.infrastructure.repositories.runtime_event_repository_pg import AlgorithmRuntimeEventRepositoryPG
            repo = AlgorithmRuntimeEventRepositoryPG(conn)
            yield repo
            await conn.close()

        app.dependency_overrides[get_algorithm_repo] = get_real_algo_repo
        app.dependency_overrides[get_event_repo] = get_real_event_repo
        self.client = TestClient(app)

    def teardown_method(self):
        """Clean up after test."""
        cleanup_algorithm(self.algorithm_id)
        app.dependency_overrides.clear()

    def test_get_algorithm_versions_empty(self):
        """Test getting versions when none exist."""
        response = self.client.get(
            f"/api/algorithms/{self.algorithm_id}/versions",
            headers={"X-API-Key": "read-secret-key"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_get_algorithm_events_empty(self):
        """Test getting events when none exist."""
        response = self.client.get(
            f"/api/algorithms/{self.algorithm_id}/events",
            headers={"X-API-Key": "read-secret-key"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_create_and_get_version(self):
        """Test creating and getting algorithm versions."""
        # Create a version via the API (if endpoint exists) or directly in DB
        version_id = setup_algorithm_version(self.algorithm_id)

        # Get versions
        response = self.client.get(
            f"/api/algorithms/{self.algorithm_id}/versions",
            headers={"X-API-Key": "read-secret-key"}
        )
        assert response.status_code == 200
        versions = response.json()
        assert len(versions) >= 1
        # Check that the version we created is in the list
        # The response uses 'version' field (not 'id') to identify versions
        assert any(v["version"] == 1 for v in versions)

    def test_create_and_get_events(self):
        """Test creating and getting algorithm events."""
        # Create a version first
        version_id = setup_algorithm_version(self.algorithm_id)

        # Add an event directly to DB
        async def add_event():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            try:
                await conn.execute(
                    """
                    INSERT INTO algorithm_events (algorithm_id, algorithm_version_id, event_type, event_payload)
                    VALUES ($1, $2, 'created', '{}')
                    """
                , self.algorithm_id, version_id)
            finally:
                await conn.close()
        asyncio.run(add_event())

        # Get events
        response = self.client.get(
            f"/api/algorithms/{self.algorithm_id}/events",
            headers={"X-API-Key": "read-secret-key"}
        )
        assert response.status_code == 200
        events = response.json()
        assert len(events) >= 1
