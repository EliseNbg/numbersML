"""
Integration tests for StrategyInstance API endpoint with real database.

Tests that the endpoint works correctly with the actual database schema.
Validates that the strategy_instances table has the correct columns.
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
from src.infrastructure.api.routes.strategy_instances import get_instance_repository


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


def setup_test_data():
    """Set up test data: create algorithm and config set."""
    async def setup():
        conn = await asyncpg.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER", "crypto"),
            password=os.environ.get("DB_PASS", "crypto_secret"),
            database=os.environ.get("DB_NAME", "crypto_trading"),
        )
        try:
            import time
            # Create test algorithm with unique name
            alg_row = await conn.fetchrow(
                """
                INSERT INTO algorithms (name, description, status)
                VALUES ($1, 'For testing', 'validated')
                RETURNING id
                """
            , f'Test Algorithm {time.time()}')
            algorithm_id = alg_row["id"]

            # Create test config set
            config_row = await conn.fetchrow(
                """
                INSERT INTO configuration_sets (name, description, config)
                VALUES ($1, 'For testing', '{}')
                RETURNING id
                """
            , f'Test Config {time.time()}')
            config_set_id = config_row["id"]

            return algorithm_id, config_set_id
        finally:
            await conn.close()
    return asyncio.run(setup())


def cleanup_test_data(algorithm_id, config_set_id):
    """Clean up test data."""
    async def cleanup():
        conn = await asyncpg.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            user=os.environ.get("DB_USER", "crypto"),
            password=os.environ.get("DB_PASS", "crypto_secret"),
            database=os.environ.get("DB_NAME", "crypto_trading"),
        )
        try:
            await conn.execute(
                "DELETE FROM strategy_instances WHERE algorithm_id = $1", algorithm_id
            )
            await conn.execute(
                "DELETE FROM configuration_sets WHERE id = $1", config_set_id
            )
            await conn.execute("DELETE FROM algorithms WHERE id = $1", algorithm_id)
        finally:
            await conn.close()

    asyncio.run(cleanup())


class TestDatabaseSchemaValidation:
    """Validate that database schema matches code expectations."""

    def test_strategy_instances_table_has_algorithm_id_column(self):
        """Test that strategy_instances table has algorithm_id column."""
        async def check_column():
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
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'strategy_instances'
                    AND column_name = 'algorithm_id'
                    """
                )
                return row is not None
            finally:
                await conn.close()

        has_column = asyncio.run(check_column())
        assert has_column, "strategy_instances table missing algorithm_id column"

    def test_strategy_instances_table_has_all_required_columns(self):
        """Test that strategy_instances table has all required columns."""
        required_columns = [
            "id", "algorithm_id", "config_set_id", "status",
            "runtime_stats", "started_at", "stopped_at",
            "created_at", "updated_at"
        ]

        async def check_columns():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            try:
                rows = await conn.fetch(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'strategy_instances'
                    """
                )
                return {row["column_name"] for row in rows}
            finally:
                await conn.close()

        columns = asyncio.run(check_columns())
        for col in required_columns:
            assert col in columns, f"strategy_instances table missing column: {col}"


class TestStrategyInstancesEndpointWithRealDB:
    """Test StrategyInstance API with real database."""

    def setup_method(self):
        """Set up test client and database."""
        self.algorithm_id, self.config_set_id = setup_test_data()

        # Override the dependency to use real database
        async def get_real_repo():
            conn = await asyncpg.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ.get("DB_USER", "crypto"),
                password=os.environ.get("DB_PASS", "crypto_secret"),
                database=os.environ.get("DB_NAME", "crypto_trading"),
            )
            from src.infrastructure.repositories.strategy_instance_repository_pg import (
                StrategyInstanceRepositoryPG,
            )
            repo = StrategyInstanceRepositoryPG(conn)
            yield repo
            await conn.close()

        app.dependency_overrides[get_instance_repository] = get_real_repo
        self.client = TestClient(app)

    def teardown_method(self):
        """Clean up after test."""
        cleanup_test_data(self.algorithm_id, self.config_set_id)
        app.dependency_overrides.clear()

    def test_list_instances_empty(self):
        """Test listing instances when none exist."""
        response = self.client.get(
            "/api/algorithm-instances",
            headers={"X-API-Key": "read-secret-key"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_create_and_list_instance(self):
        """Test creating and listing instances."""
        # Create an instance
        response = self.client.post(
            "/api/algorithm-instances",
            headers={"X-API-Key": "trader-secret-key"},
            json={
                "algorithm_id": str(self.algorithm_id),
                "config_set_id": str(self.config_set_id),
            },
        )
        assert response.status_code == 201
        instance_id = response.json()["id"]

        # List instances
        list_response = self.client.get(
            "/api/algorithm-instances",
            headers={"X-API-Key": "read-secret-key"}
        )
        assert list_response.status_code == 200
        instances = list_response.json()
        assert len(instances) >= 1
        assert any(inst["id"] == instance_id for inst in instances)

    def test_get_instance(self):
        """Test getting a specific instance."""
        # Create an instance
        response = self.client.post(
            "/api/algorithm-instances",
            headers={"X-API-Key": "trader-secret-key"},
            json={
                "algorithm_id": str(self.algorithm_id),
                "config_set_id": str(self.config_set_id),
            },
        )
        assert response.status_code == 201
        instance_id = response.json()["id"]

        # Get the instance
        get_response = self.client.get(
            f"/api/algorithm-instances/{instance_id}",
            headers={"X-API-Key": "read-secret-key"}
        )
        assert get_response.status_code == 200
        assert get_response.json()["id"] == instance_id

    def test_create_duplicate_instance(self):
        """Test creating duplicate instance returns 400."""
        # Create first instance
        response1 = self.client.post(
            "/api/algorithm-instances",
            headers={"X-API-Key": "trader-secret-key"},
            json={
                "algorithm_id": str(self.algorithm_id),
                "config_set_id": str(self.config_set_id),
            },
        )
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = self.client.post(
            "/api/algorithm-instances",
            headers={"X-API-Key": "trader-secret-key"},
            json={
                "algorithm_id": str(self.algorithm_id),
                "config_set_id": str(self.config_set_id),
            },
        )
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"]
