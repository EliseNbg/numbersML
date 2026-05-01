"""
Pytest configuration for integration tests.
Sets up test data in the database before tests run.
"""
import asyncio
import os

import asyncpg
import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_data():
    """Set up test data in the database for integration tests.

    This fixture runs once per test session and loads the test data SQL script.
    """
    db_url = os.environ.get(
        "TEST_DB_URL", "postgresql://test:test@localhost:5432/test"
    )

    # Parse URL
    # postgresql://user:pass@host:port/dbname
    import re

    match = re.match(
        r"postgresql://(?P<user>[^:]+):(?P<pass>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<db>\w+)",
        db_url,
    )
    if not match:
        pytest.fail(f"Invalid TEST_DB_URL format: {db_url}")

    db_host = match.group("host")
    db_port = match.group("port")
    db_name = match.group("db")
    db_user = match.group("user")
    db_pass = match.group("pass")

    async def load_test_data():
        # Run migrations first
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        migrations_dir = os.path.join(project_root, "migrations")

        # Connect to database
        conn = await asyncpg.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_pass,
            database=db_name,
        )

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

            # Run test_data.sql
            test_data_path = os.path.join(migrations_dir, "test_data.sql")
            if os.path.exists(test_data_path):
                with open(test_data_path) as f:
                    sql = f.read()
                await conn.execute(sql)

        finally:
            await conn.close()

    # Run the async setup
    asyncio.get_event_loop().run_until_complete(load_test_data())

    yield
