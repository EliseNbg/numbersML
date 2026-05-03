"""
Integration test: Grid Algorithm on TEST/USDT noised sin wave.

Verifies that Grid Algorithm generates positive PnL.
"""

import pytest


@pytest.mark.integration
class TestGridAlgorithmPnL:
    """Test that Grid Algorithm shows positive PnL on synthetic data."""

    @pytest.mark.asyncio
    async def test_grid_backtest_positive_pnl(self):
        """
        Test running Grid Algorithm backtest on TEST/USDT.

        Prerequisites:
            - TEST/USDT symbol exists with noised sin wave data
            - Grid Algorithm ConfigurationSet exists
            - GridAlgorithm implementation exists

        Expected:
            - PnL > 0 (positive)
            - At least some trades executed
        """

        # This test requires:
        # 1. Database with test data
        # 2. GridAlgorithm registered/loadable
        # 3. BacktestService working

        # For now, this is a placeholder
        # In full implementation:
        # - Load GridAlgorithm
        # - Create StrategyInstance with Grid config
        # - Run backtest
        # - Assert PnL > 0

        pytest.skip("Requires database with generated test data")

    @pytest.mark.asyncio
    async def test_sin_wave_data_exists(self):
        """Test that TEST/USDT has sin wave data."""
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="crypto",
            password="crypto_secret",
            database="crypto_trading",
        )

        try:
            # Check symbol exists
            symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = 'TEST/USDT'")
            assert symbol_id is not None, "TEST/USDT symbol not found"

            # Check candles exist
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1",
                symbol_id,
            )
            assert count > 1000, f"Expected >1000 candles, got {count}"

            # Check price range (should be ~$98-$102)
            row = await conn.fetchrow(
                "SELECT MIN(close) as min_p, MAX(close) as max_p FROM candles_1s WHERE symbol_id = $1",
                symbol_id,
            )
            assert 97.0 < float(row["min_p"]) < 99.0, f"Min price too low/high: {row['min_p']}"
            assert 101.0 < float(row["max_p"]) < 103.0, f"Max price too low/high: {row['max_p']}"

        finally:
            await conn.close()
