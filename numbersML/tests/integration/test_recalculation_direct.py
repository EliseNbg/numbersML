#!/usr/bin/env python3
"""
Direct integration test for recalculation service.

Tests the recalculation by directly calling the functions instead of subprocess.
"""

import asyncio
import asyncpg
import numpy as np
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List
import logging

logger = logging.getLogger(__name__)

# Test configuration
TEST_SYMBOL = "TEST/USDT"
TEST_CANDLE_COUNT = 1000  # Reduced for faster testing
DETERMINISTIC_SEED = 42


@pytest.mark.integration
async def test_recalculation_direct_integration():
    """Test the recalculation service with direct function calls."""
    # Create database connection
    pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=2,
        max_size=10,
    )
    
    try:
        async with pool.acquire() as conn:
            # 1. Clean up any existing data
            await cleanup_existing_data(conn)
            
            # 2. Set up test symbol
            symbol_id = await setup_test_symbol(conn)
            
            # 3. Generate and insert synthetic candles
            min_time = await insert_synthetic_candles(conn, symbol_id)
            
            # 4. Run recalculation directly
            await run_recalculation_direct(pool, [symbol_id], min_time)
            
            # 5. Validate results
            await validate_results(conn, symbol_id)
            
            logger.info("Direct integration test completed successfully")
    
    finally:
        # Clean up
        async with pool.acquire() as conn:
            await cleanup_existing_data(conn)
            await conn.execute(
                "UPDATE symbols SET is_active = false, is_allowed = false WHERE symbol = $1",
                TEST_SYMBOL,
            )
        await pool.close()


async def cleanup_existing_data(conn: asyncpg.Connection):
    """Clean up any existing test data."""
    symbol_id = await conn.fetchval(
        "SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL
    )
    
    if symbol_id:
        await conn.execute(
            "DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id
        )
        await conn.execute(
            "DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id
        )


async def setup_test_symbol(conn: asyncpg.Connection) -> int:
    """Set up TEST/USDT symbol for testing."""
    await conn.execute(
        """
        INSERT INTO symbols (symbol, base_asset, quote_asset, tick_size, step_size, min_notional, is_active, is_allowed)
        VALUES ($1, 'TEST', 'USDT', 0.00001, 0.000001, 1.0, true, true)
        ON CONFLICT (symbol) DO UPDATE SET is_active = true, is_allowed = true
        """,
        TEST_SYMBOL,
    )
    
    symbol_id = await conn.fetchval(
        "SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL
    )
    
    if not symbol_id:
        raise ValueError(f"Failed to create symbol {TEST_SYMBOL}")
    
    return symbol_id


def generate_deterministic_candles(symbol_id: int, start_time: datetime) -> List[tuple]:
    """Generate deterministic synthetic candle data."""
    np.random.seed(DETERMINISTIC_SEED)
    
    # Generate candles going backward from start_time
    indices = np.arange(TEST_CANDLE_COUNT)
    
    # Base price with sine wave oscillation
    prices = 100.0 + 5.0 * np.sin(2 * np.pi * indices / (15 * 60))
    prices += np.random.normal(0, 0.1, TEST_CANDLE_COUNT)
    
    # Generate OHLCV values
    opens = prices + np.random.uniform(-0.05, 0.05, TEST_CANDLE_COUNT)
    highs = np.maximum(opens, prices) + np.random.uniform(0, 0.1, TEST_CANDLE_COUNT)
    lows = np.minimum(opens, prices) - np.random.uniform(0, 0.1, TEST_CANDLE_COUNT)
    closes = prices
    volumes = np.random.uniform(0.1, 10.0, TEST_CANDLE_COUNT)
    
    # Create rows for insertion (going backward in time)
    rows = []
    for i in range(TEST_CANDLE_COUNT):
        timestamp = start_time - timedelta(seconds=i)
        rows.append((
            symbol_id,
            timestamp,
            Decimal(str(round(opens[i], 5))),
            Decimal(str(round(highs[i], 5))),
            Decimal(str(round(lows[i], 5))),
            Decimal(str(round(closes[i], 5))),
            Decimal(str(round(volumes[i], 6))),
            Decimal(str(round(volumes[i] * closes[i], 6))),
            1,  # trade_count
        ))
    
    return rows


async def insert_synthetic_candles(conn: asyncpg.Connection, symbol_id: int) -> datetime:
    """Insert synthetic candles into database."""
    start_time = datetime.now(timezone.utc).replace(microsecond=0)
    rows = generate_deterministic_candles(symbol_id, start_time)
    
    # Insert in batches
    batch_size = 1000
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
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
    assert count == TEST_CANDLE_COUNT, f"Expected {TEST_CANDLE_COUNT} candles, got {count}"
    
    # Get time range
    time_range = await conn.fetchrow(
        """
        SELECT MIN(time) as min_time, MAX(time) as max_time 
        FROM candles_1s WHERE symbol_id = $1
        """,
        symbol_id,
    )
    
    logger.info(f"Inserted {count} candles from {time_range['min_time']} to {time_range['max_time']}")
    return time_range['min_time']


async def run_recalculation_direct(pool, symbol_ids: List[int], from_time: datetime):
    """Run recalculation by directly importing and calling the function."""
    # Import the recalculation function
    from src.cli.recalculate import recalculate_indicators
    
    # Run recalculation
    count = await recalculate_indicators(
        pool, symbol_ids, from_time, None, with_quality_guard=True
    )
    
    logger.info(f"Recalculated {count} indicators")
    assert count > 0, "No indicators were recalculated"


async def validate_results(conn: asyncpg.Connection, symbol_id: int):
    """Validate the recalculation results."""
    # Get candle count
    candle_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
    )
    
    # Get indicator row count
    indicator_count = await conn.fetchval(
        "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1", symbol_id
    )
    
    # Should have 1:1 mapping
    assert indicator_count == candle_count, (
        f"Expected {candle_count} indicator rows, got {indicator_count}"
    )
    
    # Check time alignment
    candle_times = await conn.fetch(
        "SELECT time FROM candles_1s WHERE symbol_id = $1 ORDER BY time LIMIT 10", symbol_id
    )
    indicator_times = await conn.fetch(
        "SELECT time FROM candle_indicators WHERE symbol_id = $1 ORDER BY time LIMIT 10", symbol_id
    )
    
    assert len(candle_times) == len(indicator_times), "Time count mismatch"
    
    for i, (candle, indicator) in enumerate(zip(candle_times, indicator_times)):
        assert candle['time'] == indicator['time'], f"Time mismatch at index {i}"
    
    # Check indicator values exist
    sample_row = await conn.fetchrow(
        "SELECT values FROM candle_indicators WHERE symbol_id = $1 LIMIT 1", symbol_id
    )
    
    assert sample_row is not None, "No indicator data found"
    values = sample_row['values']
    assert len(values) > 0, "No indicator values found"
    
    logger.info(f"Validation passed: {candle_count} candles, {indicator_count} indicators, {len(values)} values per candle")
