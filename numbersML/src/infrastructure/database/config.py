"""Database configuration for the project.

Provides a centralized way to get database URLs for different environments.
Uses environment variables with sensible defaults matching the project's Docker setup.
"""

import os


def get_test_db_url() -> str:
    """Get the database URL for tests.

    Priority:
    1. TEST_DB_URL environment variable (explicit override)
    2. Construct from individual DB_* environment variables
    3. Default: postgresql://crypto:crypto_secret@localhost:5432/crypto_trading

    Returns:
        Database connection URL string
    """
    # If TEST_DB_URL is explicitly set, use it
    if "TEST_DB_URL" in os.environ:
        return os.environ["TEST_DB_URL"]

    # Construct from individual environment variables
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    user = os.environ.get("DB_USER", "crypto")
    password = os.environ.get("DB_PASS", "crypto_secret")
    database = os.environ.get("DB_NAME", "crypto_trading")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def get_db_url() -> str:
    """Get the database URL for production/development use.

    Returns:
        Database connection URL string
    """
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    user = os.environ.get("DB_USER", "crypto")
    password = os.environ.get("DB_PASS", "crypto_secret")
    database = os.environ.get("DB_NAME", "crypto_trading")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
