"""
Pytest fixtures for test suite.

Provides automatic TEST/USDT disallowing after each test.
"""
import pytest
import asyncio
import asyncpg
import os

DB_URL = os.getenv("TEST_DB_URL", "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool():
    """Create a database connection pool for the test session."""
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    yield pool
    await pool.close()


@pytest.fixture(autouse=True)
async def cleanup_test_usdt(db_pool):
    """
    Autouse fixture that ensures TEST/USDT is disallowed after every test.
    
    This runs automatically for all tests, providing a safety net to ensure
    TEST/USDT is never left in an active/allowed state after test execution.
    """
    yield
    
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
async def allow_test_usdt(db_pool):
    """
    Fixture to allow TEST/USDT for testing purposes.
    
    Activates TEST/USDT before test. The autouse cleanup_test_usdt
    fixture will disallow it after the test.
    
    Yields:
        int: The symbol ID for TEST/USDT
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM symbols WHERE symbol = 'TEST/USDT'"
        )
        
        if not row:
            row = await conn.fetchrow(
                "INSERT INTO symbols (symbol, is_active, is_allowed) "
                "VALUES ('TEST/USDT', true, true) RETURNING id"
            )
            symbol_id = row['id']
        else:
            symbol_id = row['id']
            await conn.execute(
                "UPDATE symbols SET is_active = true, is_allowed = true WHERE id = $1",
                symbol_id
            )
    
    yield symbol_id


@pytest.fixture
def test_usdt_symbol():
    """Get TEST/USDT symbol name."""
    return "TEST/USDT"
