"""
Integration test: Grid Algorithm on TEST/USDT noised sin wave.

Verifies that Grid Algorithm generates positive PnL.
Uses consolidated fixtures from conftest.py.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestGridAlgorithmPnL:
    """Test that Grid Algorithm shows positive PnL on synthetic data."""

    @pytest.mark.asyncio
    async def test_grid_backtest_positive_pnl(self, test_usdt_with_sin_wave_data):
        """Test running Grid Algorithm backtest on TEST/USDT.

        Prerequisites:
            - TEST/USDT symbol exists with noised sin wave data (provided by fixture)
            - Grid Algorithm ConfigurationSet exists
            - GridAlgorithm implementation exists

        Expected:
            - PnL > 0 (positive)
            - At least some trades executed
        """
        symbol_id = test_usdt_with_sin_wave_data

        # This test requires:
        # 1. Database with test data (provided by fixture)
        # 2. GridAlgorithm registered/loadable
        # 3. BacktestService working

        # For now, this is a placeholder
        # In full implementation:
        # - Load GridAlgorithm
        # - Create AlgorithmInstance with Grid config
        # - Run backtest
        # - Assert PnL > 0

        pytest.skip("Requires GridAlgorithm implementation and BacktestService")

    @pytest.mark.asyncio
    async def test_sin_wave_data_exists(self, db_pool, test_usdt_with_sin_wave_data):
        """Test that TEST/USDT has sin wave data."""
        symbol_id = test_usdt_with_sin_wave_data

        async with db_pool.acquire() as conn:
            # Check symbol exists (already verified by fixture, but double-check)
            db_symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = 'TEST/USDT'")
            assert db_symbol_id == symbol_id, "Symbol ID mismatch"
            assert symbol_id is not None, "TEST/USDT symbol not found"

            # Check candles exist (should have 5000 from fixture)
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id
            )
            assert count == 5000, f"Expected 5000 candles, got {count}"

            # Check price range (should be ~$98-$102)
            row = await conn.fetchrow(
                "SELECT MIN(close) as min_p, MAX(close) as max_p FROM candles_1s WHERE symbol_id = $1",
                symbol_id,
            )
            assert 97.0 < float(row["min_p"]) < 103.0, f"Min price out of range: {row['min_p']}"
            assert 97.0 < float(row["max_p"]) < 103.0, f"Max price out of range: {row['max_p']}"

        logger.info("Sin wave data validation passed")
