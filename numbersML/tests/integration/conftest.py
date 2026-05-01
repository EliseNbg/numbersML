"""
Pytest configuration for integration tests.
Sets up test data in the database before tests run.
"""
import asyncio
import logging
import os
import sys

import asyncpg
import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))

from src.infrastructure.database.config import get_test_db_url  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_db_url(db_url: str) -> dict:
    """Parse postgresql:// URL into connection parameters."""
    import re

    match = re.match(
        r"postgresql://(?P<user>[^:]+):(?P<pass>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<db>\w+)",
        db_url,
    )
    if not match:
        pytest.fail(f"Invalid TEST_DB_URL format: {db_url}")
    return {
        "host": match.group("host"),
        "port": int(match.group("port")),
        "user": match.group("user"),
        "password": match.group("pass"),
        "database": match.group("db"),
    }


@pytest.fixture(scope="session", autouse=True)
def setup_test_data():
    """Set up test data in the database for integration tests.

    This fixture runs once per test session and loads the test data SQL script.
    It is idempotent - safe to run even if data is already loaded.
    """
    # Skip if running in CI and test data already loaded via workflow
    if os.environ.get("CI") and os.environ.get("TEST_DATA_LOADED"):
        logger.info("Skipping test data setup - already loaded in CI workflow")
        yield
        return

    db_url = get_test_db_url()
    db_params = _parse_db_url(db_url)

    async def load_test_data():
        # Run migrations first
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        migrations_dir = os.path.join(project_root, "migrations")

        # Connect to database with retry logic
        conn = None
        for attempt in range(5):
            try:
                conn = await asyncpg.connect(**db_params)
                break
            except asyncpg.exceptions.InvalidPasswordError:
                pytest.fail(
                    f"Password authentication failed for user '{db_params['user']}'. "
                    f"Check TEST_DB_URL environment variable."
                )
            except Exception:
                if attempt < 4:
                    await asyncio.sleep(1)
                else:
                    raise

        if conn is None:
            pytest.fail("Failed to connect to database after retries")

        try:
            # Run each migration (except test_data.sql)
            for filename in sorted(os.listdir(migrations_dir)):
                if filename.endswith(".sql") and filename != "test_data.sql":
                    filepath = os.path.join(migrations_dir, filename)
                    with open(filepath) as f:
                        sql = f.read()
                    try:
                        await conn.execute(sql)
                    except Exception as e:
                        # Ignore errors for migrations that were already applied
                        if "already exists" not in str(e):
                            print(f"Warning: Migration {filename} failed: {e}")

            # Run test_data.sql (idempotent - uses ON CONFLICT or IF NOT EXISTS)
            test_data_path = os.path.join(migrations_dir, "test_data.sql")
            if os.path.exists(test_data_path):
                with open(test_data_path) as f:
                    sql = f.read()
                try:
                    await conn.execute(sql)
                except Exception as e:
                    # Log but don't fail - test data might already be loaded
                    print(f"Warning: test_data.sql loading issue: {e}")

        finally:
            await conn.close()

    # Run the async setup using asyncio.run() for Python 3.11+ compatibility
    asyncio.run(load_test_data())

    yield
