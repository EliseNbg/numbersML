"""
Pytest fixtures for unit test suite.
"""

import asyncio
import os
import sys

# Ensure user site-packages are disabled FIRST before any imports
sys.path = [p for p in sys.path if 'local/lib/python' not in p.replace('\\', '/')]

import pytest

# Add src to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.infrastructure.database.config import get_test_db_url

# Use the same test database as the main test suite
DB_URL = get_test_db_url()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool():
    """Create a database connection pool for the test session."""
    import asyncpg

    # For unit tests that actually hit the database, we need a pool
    # But many tests mock the repository, so we'll make this optional
    try:
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
        yield pool
        await pool.close()
    except Exception:
        # If we can't connect to DB, yield None - tests should mock dependencies
        yield None


@pytest.fixture
async def db_connection(db_pool):
    """Get a database connection from the pool."""
    if db_pool is None:
        # Return a mock connection if pool is not available
        from unittest.mock import AsyncMock

        conn = AsyncMock()
        # Mock common connection methods
        conn.fetchrow = AsyncMock()
        conn.fetch = AsyncMock()
        conn.execute = AsyncMock()
        conn.acquire = AsyncMock()
        yield conn
    else:
        async with db_pool.acquire() as connection:
            yield connection