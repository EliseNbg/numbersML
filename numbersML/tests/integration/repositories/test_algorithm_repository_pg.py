"""Integration tests for AlgorithmRepositoryPG against real PostgreSQL."""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest

from src.domain.algorithms.algorithm_config import AlgorithmDefinition
from src.infrastructure.repositories.algorithm_repository_pg import AlgorithmRepositoryPG

DB_URL = os.getenv("TEST_DB_URL", "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading")


async def _init_utc(conn: asyncpg.Connection) -> None:
    await conn.execute("SET timezone = 'UTC'")


async def _ensure_phase3_schema(conn: asyncpg.Connection) -> None:
    migration_path = (
        Path(__file__).resolve().parents[3] / "migrations" / "003_phase3_algorithm_foundation.sql"
    )
    await conn.execute(migration_path.read_text(encoding="utf-8"))


@pytest.mark.integration
class TestAlgorithmRepositoryPGIntegration:
    """Repository integration tests with actual database."""

    @pytest.fixture
    async def db_conn(self) -> asyncpg.Connection:
        try:
            conn = await asyncpg.connect(DB_URL)
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable for integration test: {exc}")
        await _init_utc(conn)
        await _ensure_phase3_schema(conn)
        yield conn
        await conn.close()

    @pytest.mark.asyncio
    async def test_save_create_version_and_activate(self, db_conn: asyncpg.Connection) -> None:
        repo = AlgorithmRepositoryPG(db_conn)
        unique_name = f"it_algorithm_{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        algorithm = AlgorithmDefinition(
            name=unique_name,
            description="integration test algorithm",
            created_by="pytest",
            created_at=now,
            updated_at=now,
        )

        saved = await repo.save(algorithm)
        assert saved.name == unique_name

        version = await repo.create_version(
            algorithm_id=saved.id,
            schema_version=1,
            config={"meta": {"name": unique_name, "schema_version": 1}},
            created_by="pytest",
        )
        assert version.version == 2

        activated = await repo.set_active_version(saved.id, version.version)
        assert activated is True

        versions = await repo.list_versions(saved.id)
        assert len(versions) >= 1
        assert any(v.version == 2 and v.is_active for v in versions)
