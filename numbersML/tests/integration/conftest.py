"""
Pytest configuration for integration tests.
Sets up test data in the database before tests run.
"""

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
import asyncpg

# Add src to path for imports
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"
    ),
)

from src.infrastructure.database.config import get_test_db_url  # noqa: E402

logger = logging.getLogger(__name__)

TEST_SYMBOL = "TEST/USDT"
DETERMINISTIC_SEED = 42


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
    # Skip if running in GitHub Actions (test data loaded via workflow)
    if os.environ.get("GITHUB_ACTIONS"):
        logger.info("Running in GitHub Actions - skipping test data setup (loaded via workflow)")
        yield
        return

    db_url = get_test_db_url()
    db_params = _parse_db_url(db_url)

    async def load_test_data():
        # Run migrations first
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        migrations_dir = os.path.join(project_root, "migrations")

        # Connect to database with retry logic
        conn = None
        for attempt in range(5):
            try:
                conn = await asyncpg.connect(**db_params)
                break
            except asyncpg.exceptions.InvalidPasswordError:
                # Only fail immediately if not retrying
                if attempt == 4:
                    pytest.fail(
                        f"Password authentication failed for user '{db_params['user']}'. "
                        f"Check TEST_DB_URL environment variable."
                    )
                await asyncio.sleep(1)
            except Exception:
                if attempt < 4:
                    await asyncio.sleep(1)
                else:
                    raise

        if conn is None:
            pytest.fail("Failed to connect to database after retries")

        try:
            # Run each migration (except test_data.sql and CLEAN_SCHEMA.sql)
            for filename in sorted(os.listdir(migrations_dir)):
                if filename.endswith(".sql") and filename != "test_data.sql" and not filename.startswith("CLEAN"):
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


@pytest.fixture
async def test_usdt_symbol(db_pool):
    """Ensure TEST/USDT symbol exists with correct parameters.

    Creates the symbol if it doesn't exist, or updates it if it does.
    Sets is_active=True, is_allowed=True for testing.

    Yields:
        int: The symbol ID for TEST/USDT
    """
    async with db_pool.acquire() as conn:
        # Insert or update TEST/USDT symbol with consistent parameters
        row = await conn.fetchrow(
            """
            INSERT INTO symbols (
                symbol, base_asset, quote_asset, status, is_active, is_allowed,
                price_precision, quantity_precision, tick_size, step_size,
                min_notional, is_test
            ) VALUES ($1, 'TEST', 'USDT', 'TRADING', true, true,
                2, 6, 0.01, 0.000001, 10.0, true)
            ON CONFLICT (symbol) DO UPDATE SET
                is_active = EXCLUDED.is_active,
                is_allowed = EXCLUDED.is_allowed,
                is_test = EXCLUDED.is_test
            RETURNING id
            """,
            TEST_SYMBOL,
        )
        symbol_id = row["id"]

    yield symbol_id

    # After test: disable the symbol
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE symbols SET is_active = false, is_allowed = false WHERE symbol = $1",
                TEST_SYMBOL,
            )
    except Exception:
        pass


def generate_deterministic_candles(
    symbol_id: int, start_time: datetime, count: int = 3000
) -> list[tuple]:
    """Generate deterministic synthetic candle data.

    Args:
        symbol_id: Database symbol ID
        start_time: Starting timestamp (candles go backward from this time)
        count: Number of candles to generate

    Returns:
        List of tuples ready for database insertion
    """
    np.random.seed(DETERMINISTIC_SEED)

    # Generate candles going backward from start_time
    indices = np.arange(count)

    # Base price with sine wave oscillation (period = 15 minutes)
    prices = 100.0 + 5.0 * np.sin(2 * np.pi * indices / (15 * 60))
    prices += np.random.normal(0, 0.1, count)

    # Generate OHLCV values
    opens = prices + np.random.uniform(-0.05, 0.05, count)
    highs = np.maximum(opens, prices) + np.random.uniform(0, 0.1, count)
    lows = np.minimum(opens, prices) - np.random.uniform(0, 0.1, count)
    closes = prices
    volumes = np.random.uniform(0.1, 10.0, count)

    # Create rows for insertion (going backward in time)
    rows = []
    for i in range(count):
        timestamp = start_time - timedelta(seconds=i)
        rows.append(
            (
                symbol_id,
                timestamp,
                Decimal(str(round(opens[i], 5))),
                Decimal(str(round(highs[i], 5))),
                Decimal(str(round(lows[i], 5))),
                Decimal(str(round(closes[i], 5))),
                Decimal(str(round(volumes[i], 6))),
                Decimal(str(round(volumes[i] * closes[i], 6))),
                1,  # trade_count
            )
        )

    return rows


@pytest.fixture
async def test_usdt_with_candles(db_pool, test_usdt_symbol):
    """Provide TEST/USDT symbol with synthetic candles for recalculation tests.

    Creates deterministic synthetic candles (noised sine wave around 100.0).
    Cleans up candles after the test.

    Yields:
        tuple: (symbol_id, min_time) where min_time is the earliest candle timestamp
    """
    symbol_id = test_usdt_symbol
    candle_count = 100  # Use 3000 for full integration tests (takes 10+ min)

    async with db_pool.acquire() as conn:
        # Clean up any existing data
        await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
        await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)

        # Generate and insert candles
        start_time = datetime.now(UTC).replace(microsecond=0)
        rows = generate_deterministic_candles(symbol_id, start_time, candle_count)

        # Insert in batches
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            await conn.executemany(
                """
                INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (symbol_id, time) DO NOTHING
                """,
                batch,
            )

        # Verify count
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
        )
        assert count == candle_count, f"Expected {candle_count} candles, got {count}"

        # Get time range
        time_range = await conn.fetchrow(
            "SELECT MIN(time) as min_time FROM candles_1s WHERE symbol_id = $1", symbol_id
        )
        min_time = time_range["min_time"]

    yield symbol_id, min_time

    # Cleanup after test
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
            await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
    except Exception:
        pass


@pytest.fixture
async def test_usdt_with_sin_wave_data(db_pool, test_usdt_symbol):
    """Provide TEST/USDT with noised sin wave data for grid strategy tests.

    Uses fixed timestamp (2024-01-01) to match generate_test_data.py output.
    Cleans up after the test.

    Yields:
        int: The symbol ID for TEST/USDT
    """
    import math
    import random

    symbol_id = test_usdt_symbol
    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    num_candles = 5000

    async with db_pool.acquire() as conn:
        # Clean up existing data
        await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
        await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)

        # Generate noised sin wave data (matching generate_test_data.py)
        candles = []
        for i in range(num_candles):
            t = i / 1000.0 * 2 * math.pi
            pure_price = 100.0 + 2.0 * math.sin(t)  # AMPLITUDE = 2.0
            noise = random.uniform(-0.3, 0.3)  # NOISE_LEVEL = 0.3
            price = pure_price + noise

            spread = random.uniform(0.01, 0.05)
            candle_time = base_time + timedelta(seconds=i)
            candles.append(
                (
                    candle_time,
                    symbol_id,
                    Decimal(str(price - spread / 2)),
                    Decimal(str(price + spread)),
                    Decimal(str(price - spread)),
                    Decimal(str(price + spread / 2)),
                    Decimal(str(random.uniform(1.0, 10.0))),
                    Decimal(str(price * random.uniform(1.0, 10.0))),
                    random.randint(1, 100),
                )
            )

        # Batch insert
        await conn.copy_records_to_table(
            "candles_1s",
            records=candles,
            columns=["time", "symbol_id", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"],
        )

        logger.info(f"Inserted {len(candles)} sin wave candles for TEST/USDT")

    yield symbol_id

    # Cleanup after test
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
            await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
    except Exception:
        pass
