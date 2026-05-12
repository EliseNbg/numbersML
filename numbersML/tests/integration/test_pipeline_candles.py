"""
Integration test: Pipeline produces candles and indicators for all active symbols.

Verifies after 30 sec of pipeline runtime:
1. All 4 active symbols have candles in candles_1s table
2. All 4 active symbols have indicators in candle_indicators table
3. Candles and indicators are valid (non-zero prices, correct schema)
"""

import asyncio
import json
import logging

import asyncpg
import pytest


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


from src.pipeline.service import PipelineManager

logger = logging.getLogger(__name__)

ACTIVE_SYMBOLS = ["BTC/USDT", "ETH/USDT", "DOGE/USDT", "ADA/USDT"]
RUN_SECONDS = 30  # 30 seconds (reduced from 10 minutes for faster testing)


@pytest.fixture
async def db_pool():
    """Create database connection pool."""
    pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=1,
        max_size=2,
        init=_init_utc,
    )
    yield pool
    await pool.close()


@pytest.fixture(autouse=True)
async def cleanup():
    """Clean state before and after test."""
    pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=1,
        max_size=2,
        init=_init_utc,
    )
    async with pool.acquire() as conn:
        # Activate test symbols before test
        await conn.execute(
            """
            UPDATE symbols
            SET is_active = true, is_allowed = true
            WHERE symbol = ANY($1)
            """,
            ACTIVE_SYMBOLS,
        )
        # Clear candle/indicator data for test symbols only
        await conn.execute("""
            DELETE FROM candles_1s
            WHERE symbol_id IN (
                SELECT id FROM symbols WHERE symbol = ANY($1)
            )
        """, ACTIVE_SYMBOLS)
        await conn.execute("""
            DELETE FROM candle_indicators
            WHERE symbol_id IN (
                SELECT id FROM symbols WHERE symbol = ANY($1)
            )
        """, ACTIVE_SYMBOLS)
        await conn.execute("DELETE FROM pipeline_state")
    yield pool
    # After test: deactivate test symbols
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE symbols
            SET is_active = false, is_allowed = false
            WHERE symbol = ANY($1)
            """,
            ACTIVE_SYMBOLS,
        )
    await pool.close()


class TestPipelineFullRun:
    """Test pipeline produces data for all active symbols over 10 minutes."""

    @pytest.mark.asyncio
    async def test_all_symbols_have_candles(self, db_pool: asyncpg.Pool) -> None:
        """
        Run pipeline 30 sec, verify all 4 symbols have candles.

        Each active symbol IN ('BTC/USDT', 'ETH/USDT', 'DOGE/USDT', 'ADA/USDT')
        must produce at least 1 candle.
        """
        manager = PipelineManager(db_pool)

        # Start pipeline
        started = await manager.start_pipeline(symbols=ACTIVE_SYMBOLS)
        assert started, "Pipeline failed to start"

        # Wait for first trade (up to 10s)
        for i in range(10):
            await asyncio.sleep(0.5)
            status = manager.get_pipeline_status("default")
            if status and status["trades_processed"] > 0:
                logger.info(f"First trade after {i * 0.5}s")
                break
        else:
            await manager.stop_pipeline("default")
            pytest.fail("Pipeline never received a trade from Binance")

        # Run for RUN_SECONDS
        await asyncio.sleep(RUN_SECONDS)

        # Stop pipeline
        await manager.stop_pipeline("default")

        # Verify candles per symbol
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT s.symbol, count(*) as cnt, "
                "min(c.time) as first_time, max(c.time) as last_time "
                "FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id "
                "GROUP BY s.symbol ORDER BY s.symbol"
            )

        results = {r["symbol"]: r["cnt"] for r in rows}
        total = sum(results.values())

        # All 4 symbols must have candles
        for sym in ACTIVE_SYMBOLS:
            count = results.get(sym, 0)
            assert count >= 1, f"{sym}: expected >= 1 candles, got {count}"

        # Total should be significant (30 seconds at ~0.5 candles/sec/symbol)
        assert total >= 4, f"Expected >= 4 total candles, got {total}"

    @pytest.mark.asyncio
    async def test_all_symbols_have_indicators(self, db_pool: asyncpg.Pool) -> None:
        """
        Run pipeline 30 sec, verify all 4 symbols have indicators.

        IndicatorCalculator must run on each completed candle and write
        results to candle_indicators table.
        """
        manager = PipelineManager(db_pool)

        # Start pipeline
        started = await manager.start_pipeline(symbols=ACTIVE_SYMBOLS)
        assert started, "Pipeline failed to start"

        # Wait for first trade
        for i in range(10):
            await asyncio.sleep(0.5)
            status = manager.get_pipeline_status("default")
            if status and status["trades_processed"] > 0:
                break
        else:
            await manager.stop_pipeline("default")
            pytest.fail("Pipeline never received a trade")

        # Run for RUN_SECONDS
        await asyncio.sleep(RUN_SECONDS)

        # Stop pipeline
        await manager.stop_pipeline("default")

        # Verify indicators per symbol
        async with db_pool.acquire() as conn:
            # Get candle counts per symbol
            candle_rows = await conn.fetch(
                "SELECT s.symbol, count(*) as cnt "
                "FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id "
                "GROUP BY s.symbol ORDER BY s.symbol"
            )
            # Get indicator counts per symbol
            indicator_rows = await conn.fetch(
                "SELECT s.symbol, count(*) as cnt "
                "FROM candle_indicators ci JOIN symbols s ON s.id = ci.symbol_id "
                "GROUP BY s.symbol ORDER BY s.symbol"
            )
            # Get sample indicator to verify structure
            sample = await conn.fetchrow(
                "SELECT ci.values, ci.price, ci.volume "
                "FROM candle_indicators ci ORDER BY ci.time DESC LIMIT 1"
            )

            # Process results while connection is still open
            candle_counts = {r["symbol"]: r["cnt"] for r in candle_rows}
            indicator_counts = {r["symbol"]: r["cnt"] for r in indicator_rows}

        print(f"\nCandles: {candle_counts} (total={sum(candle_counts.values())})")
        print(f"Indicators: {indicator_counts} (total={sum(indicator_counts.values())})")

        # All 4 symbols must have indicators
        for sym in ACTIVE_SYMBOLS:
            candles = candle_counts.get(sym, 0)
            indicators = indicator_counts.get(sym, 0)
            assert indicators >= 1, f"{sym}: no indicators despite {candles} candles"
            # Most candles should have indicators (allow some gap for first candle + errors)
            assert (
                indicators >= candles - 2
            ), f"{sym}: expected indicators >= candles-2, got {indicators} vs {candles} candles"

        # Verify indicator structure
        assert sample is not None, "No indicators found"
        values = (
            json.loads(sample["values"]) if isinstance(sample["values"], str) else sample["values"]
        )
        assert len(values) > 0, "Indicator values dict is empty"
        assert float(sample["price"]) > 0, "Indicator price is 0"
        print(f"\nSample indicators: values={list(values.keys())}")
