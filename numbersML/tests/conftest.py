"""
Pytest fixtures for test suite.

Provides TEST/USDT setup and cleanup for database tests.
"""

import asyncio
import os
import sys

import asyncpg
import pytest

# Add src to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.infrastructure.database.config import get_test_db_url

DB_URL = get_test_db_url()


@pytest.fixture
async def db_pool():
    """Create a database connection pool for the test session."""
    last_error = None
    for attempt in range(30):  # Retry up to 30 times (30 seconds)
        try:
            pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
            print(f"DB connected successfully on attempt {attempt + 1}")
            yield pool
            await pool.close()
            return
        except Exception as e:
            last_error = e
            print(f"DB connection attempt {attempt + 1}/30 failed: {e}")
            await asyncio.sleep(1)

    raise last_error or Exception(
        f"Failed to connect to database after 30 attempts. DB_URL: {DB_URL}"
    )


@pytest.fixture
async def allow_test_usdt(db_pool):
    """
    Fixture to allow TEST/USDT for testing purposes.

    Activates TEST/USDT before test and disables it after.

    Yields:
        int: The symbol ID for TEST/USDT
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM symbols WHERE symbol = 'TEST/USDT'")

        if not row:
            row = await conn.fetchrow(
                "INSERT INTO symbols (symbol, is_active, is_allowed) "
                "VALUES ('TEST/USDT', true, true) RETURNING id"
            )
            symbol_id = row["id"]
        else:
            symbol_id = row["id"]
            await conn.execute(
                "UPDATE symbols SET is_active = true, is_allowed = true WHERE id = $1", symbol_id
            )

    yield symbol_id

    # After test: always disallow TEST/USDT
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE symbols SET is_active = false, is_allowed = false "
                "WHERE symbol = 'TEST/USDT'"
            )
    except Exception:
        pass


@pytest.fixture
def test_usdt_symbol():
    """Get TEST/USDT symbol name."""
    return "TEST/USDT"
