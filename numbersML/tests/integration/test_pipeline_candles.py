"""
Integration test: Pipeline produces candles and indicators for all active symbols.

Verifies after 10 minutes of pipeline runtime:
1. All 4 active symbols have candles in candles_1s table
2. All 4 active symbols have indicators in candle_indicators table
3. Candles and indicators are valid (non-zero prices, correct schema)
"""

import asyncio
import pytest
import asyncpg
import json
import logging

from src.pipeline.service import PipelineManager

logger = logging.getLogger(__name__)

ACTIVE_SYMBOLS = ['BTC/USDC', 'ETH/USDC', 'DOGE/USDC', 'ADA/USDC']
RUN_SECONDS = 600  # 10 minutes


@pytest.fixture
async def db_pool():
    """Create database connection pool."""
    pool = await asyncpg.create_pool(
        'postgresql://crypto:crypto_secret@localhost:5432/crypto_trading',
        min_size=1,
        max_size=2,
    )
    yield pool
    await pool.close()


@pytest.fixture(autouse=True)
async def cleanup():
    """Clean state before test."""
    pool = await asyncpg.create_pool(
        'postgresql://crypto:crypto_secret@localhost:5432/crypto_trading',
        min_size=1,
        max_size=2,
    )
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM candles_1s')
        await conn.execute('DELETE FROM candle_indicators')
        await conn.execute('DELETE FROM pipeline_state')
    await pool.close()
    yield


class TestPipelineFullRun:
    """Test pipeline produces data for all active symbols over 10 minutes."""

    @pytest.mark.asyncio
    async def test_all_symbols_have_candles(self, db_pool: asyncpg.Pool) -> None:
        """
        Run pipeline 10 minutes, verify all 4 symbols have candles.

        Each active symbol (BTC/USDC, ETH/USDC, DOGE/USDC, ADA/USDC)
        must produce at least 5 candles.
        """
        manager = PipelineManager(db_pool)

        # Start pipeline
        started = await manager.start_pipeline(symbols=[])
        assert started, "Pipeline failed to start"

        # Wait for first trade (up to 10s)
        for i in range(20):
            await asyncio.sleep(0.5)
            status = manager.get_pipeline_status('default')
            if status and status['trades_processed'] > 0:
                logger.info(f"First trade after {i * 0.5}s")
                break
        else:
            await manager.stop_pipeline('default')
            pytest.fail("Pipeline never received a trade from Binance")

        # Run for RUN_SECONDS
        await asyncio.sleep(RUN_SECONDS)

        # Stop pipeline
        await manager.stop_pipeline('default')

        # Verify candles per symbol
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT s.symbol, count(*) as cnt, '
                'min(c.time) as first_time, max(c.time) as last_time '
                'FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id '
                'GROUP BY s.symbol ORDER BY s.symbol'
            )

        results = {r['symbol']: r['cnt'] for r in rows}
        total = sum(results.values())

        print(f"\nCandles: {results} (total={total})")
        for r in rows:
            print(f"  {r['symbol']}: {r['cnt']} candles from {r['first_time']} to {r['last_time']}")

        # All 4 symbols must have candles
        for sym in ACTIVE_SYMBOLS:
            count = results.get(sym, 0)
            assert count >= 5, (
                f"{sym}: expected >= 5 candles, got {count}"
            )

        # Total should be significant (10 minutes at ~0.5 candles/sec/symbol)
        assert total >= 40, f"Expected >= 40 total candles, got {total}"

    @pytest.mark.asyncio
    async def test_all_symbols_have_indicators(self, db_pool: asyncpg.Pool) -> None:
        """
        Run pipeline 10 minutes, verify all 4 symbols have indicators.

        IndicatorCalculator must run on each completed candle and write
        results to candle_indicators table.
        """
        manager = PipelineManager(db_pool)

        # Start pipeline
        started = await manager.start_pipeline(symbols=[])
        assert started, "Pipeline failed to start"

        # Wait for first trade
        for i in range(20):
            await asyncio.sleep(0.5)
            status = manager.get_pipeline_status('default')
            if status and status['trades_processed'] > 0:
                break
        else:
            await manager.stop_pipeline('default')
            pytest.fail("Pipeline never received a trade")

        # Run for RUN_SECONDS
        await asyncio.sleep(RUN_SECONDS)

        # Stop pipeline
        await manager.stop_pipeline('default')

        # Verify indicators per symbol
        async with db_pool.acquire() as conn:
            candle_rows = await conn.fetch(
                'SELECT s.symbol, count(*) as cnt '
                'FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id '
                'GROUP BY s.symbol ORDER BY s.symbol'
            )
            indicator_rows = await conn.fetch(
                'SELECT s.symbol, count(*) as cnt '
                'FROM candle_indicators ci JOIN symbols s ON s.id = ci.symbol_id '
                'GROUP BY s.symbol ORDER BY s.symbol'
            )
            # Get sample indicator to verify structure
            sample = await conn.fetchrow(
                'SELECT ci.values, ci.indicator_keys, ci.price, ci.volume '
                'FROM candle_indicators ci ORDER BY ci.time DESC LIMIT 1'
            )

        candle_counts = {r['symbol']: r['cnt'] for r in candle_rows}
        indicator_counts = {r['symbol']: r['cnt'] for r in indicator_rows}

        print(f"\nCandles: {candle_counts} (total={sum(candle_counts.values())})")
        print(f"Indicators: {indicator_counts} (total={sum(indicator_counts.values())})")

        # All 4 symbols must have indicators
        for sym in ACTIVE_SYMBOLS:
            candles = candle_counts.get(sym, 0)
            indicators = indicator_counts.get(sym, 0)
            assert indicators >= 1, (
                f"{sym}: no indicators despite {candles} candles"
            )
            # Most candles should have indicators (allow some gap for first candle + errors)
            assert indicators >= candles - 10, (
                f"{sym}: expected indicators >= candles-10, got {indicators} vs {candles} candles"
            )

        # Verify indicator structure
        assert sample is not None, "No indicators found"
        values = json.loads(sample['values']) if isinstance(sample['values'], str) else sample['values']
        keys = sample['indicator_keys']
        assert len(values) > 0, "Indicator values dict is empty"
        assert len(keys) > 0, "Indicator keys list is empty"
        assert float(sample['price']) > 0, "Indicator price is 0"
        print(f"\nSample indicators: keys={keys}, values={list(values.keys())}")
