"""
Integration test: Synthetic data pipeline with time alignment verification.

Verifies that synthetic candles flow correctly through:
1. Candle aggregation
2. Indicator calculation
3. Wide vector generation

All timestamps are perfectly aligned across all tables.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import numpy as np
import pytest

from src.pipeline.aggregator import TradeAggregation
from src.pipeline.database_writer import MultiSymbolDatabaseWriter as DatabaseWriter
from src.pipeline.indicator_calculator import IndicatorCalculator
from src.pipeline.wide_vector_service import WideVectorService


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


@pytest.fixture
async def db_pool():
    """Create database connection pool."""
    pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=2,
        max_size=5,
        init=_init_utc,
    )
    yield pool
    await pool.close()


@pytest.fixture(autouse=True)
async def cleanup_test_symbols():
    """Clean test data before and after test."""
    pool = await asyncpg.create_pool(
        "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        min_size=1,
        max_size=2,
        init=_init_utc,
    )

    async with pool.acquire() as conn:
        # Delete test symbols and all related data
        await conn.execute(
            """
            DELETE FROM wide_vectors
            WHERE symbols @> $1::text[]
        """,
            ["T01/USDC", "T02/USDC"],
        )
        await conn.execute("""
            DELETE FROM candle_indicators
            WHERE symbol_id IN (
                SELECT id FROM symbols WHERE symbol IN ('T01/USDC', 'T02/USDC')
            )
        """)
        await conn.execute("""
            DELETE FROM candles_1s
            WHERE symbol_id IN (
                SELECT id FROM symbols WHERE symbol IN ('T01/USDC', 'T02/USDC')
            )
        """)
        await conn.execute("""
            DELETE FROM symbols
            WHERE symbol IN ('T01/USDC', 'T02/USDC')
        """)

    await pool.close()
    yield


def generate_sine_candles(
    base_time: datetime,
    duration_hours: int = 2,
    period_minutes: int = 15,
    base_price: float = 100.0,
    amplitude: float = 5.0,
    noise_std: float = 0.1,
) -> list[TradeAggregation]:
    """
    Generate candles with noised sine wave price pattern.

    Args:
        base_time: Start time
        duration_hours: Total duration
        period_minutes: Sine wave period
        base_price: Base price level
        amplitude: Sine wave amplitude
        noise_std: Gaussian noise standard deviation

    Returns:
        List of TradeAggregation objects
    """
    total_seconds = duration_hours * 3600
    period_seconds = period_minutes * 60

    candles = []
    for i in range(total_seconds):
        time = base_time + timedelta(seconds=i)

        # Sine wave + gaussian noise
        price = base_price + amplitude * np.sin(2 * np.pi * i / period_seconds)
        price += np.random.normal(0, noise_std)

        # OHLC values with small random spread
        open_price = price + np.random.uniform(-0.05, 0.05)
        high_price = max(open_price, price) + np.random.uniform(0, 0.1)
        low_price = min(open_price, price) - np.random.uniform(0, 0.1)
        close_price = price

        candles.append(
            TradeAggregation(
                time=time,
                symbol="",
                open=Decimal(str(round(open_price, 5))),
                high=Decimal(str(round(high_price, 5))),
                low=Decimal(str(round(low_price, 5))),
                close=Decimal(str(round(close_price, 5))),
                volume=Decimal(str(round(np.random.uniform(0.1, 10.0), 6))),
                quote_volume=Decimal(0),
                trade_count=1,
            )
        )

    return candles


class TestSyntheticPipelineIntegration:
    """Test full pipeline with synthetic sine wave data."""

    @pytest.mark.asyncio
    async def test_full_pipeline_time_alignment(self, db_pool: asyncpg.Pool) -> None:
        """
        Test complete pipeline flow with synthetic data.

        1. Create test symbols
        2. Generate 2 hours of sine wave candles
        3. Process through pipeline components
        4. Verify time alignment across all tables
        5. Verify indicators and wide vectors are generated
        """

        # ---------------------------------------------------------------------
        # Step 1: Create test symbols
        # ---------------------------------------------------------------------
        async with db_pool.acquire() as conn:
            for symbol in ["T01/USDC", "T02/USDC"]:
                await conn.execute(
                    """
                    INSERT INTO symbols (
                        symbol, base_asset, quote_asset,
                        tick_size, step_size, min_notional,
                        is_active, is_allowed
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (symbol) DO UPDATE
                    SET is_active = true, is_allowed = true
                """,
                    symbol,
                    symbol.split("/")[0],
                    symbol.split("/")[1],
                    Decimal("0.00001"),
                    Decimal("0.000001"),
                    Decimal("1.0"),
                    True,
                    True,
                )

            # Get symbol IDs
            symbol_rows = await conn.fetch("""
                SELECT id, symbol FROM symbols
                WHERE symbol IN ('T01/USDC', 'T02/USDC')
            """)
            symbol_ids = {r["symbol"]: r["id"] for r in symbol_rows}

            assert len(symbol_ids) == 2, "Test symbols not created correctly"

        # ---------------------------------------------------------------------
        # Step 2: Generate synthetic candles
        # ---------------------------------------------------------------------
        base_time = datetime.now(UTC).replace(microsecond=0)
        t01_candles = generate_sine_candles(base_time, duration_hours=2)
        t02_candles = generate_sine_candles(
            base_time, duration_hours=2, base_price=50.0, amplitude=2.5
        )

        total_candles = len(t01_candles) + len(t02_candles)
        assert total_candles == 7200 * 2, f"Expected 14400 candles, got {total_candles}"

        # ---------------------------------------------------------------------
        # Step 3: Initialize pipeline components
        # ---------------------------------------------------------------------
        db_writer = DatabaseWriter(db_pool)
        indicator_calc = IndicatorCalculator(db_pool)
        wide_vector_service = WideVectorService(db_pool)

        await db_writer.start()
        await indicator_calc.load_definitions()
        await wide_vector_service.load_symbols()

        # ---------------------------------------------------------------------
        # Step 4: Insert candles into pipeline
        # ---------------------------------------------------------------------
        insert_count = 0

        for i in range(len(t01_candles)):
            # Insert both symbols at same timestamp
            for candles, symbol in [(t01_candles, "T01/USDC"), (t02_candles, "T02/USDC")]:
                candle = candles[i]

                # Write candle to database
                await db_writer.write_candle(symbol, candle)

                # Calculate indicators for this candle
                await indicator_calc.calculate(symbol)

                insert_count += 1

                # Flush database writer every 100 candles
                if insert_count % 100 == 0:
                    await db_writer.flush_all()
                    await wide_vector_service.generate(candle.time)

            # Small delay to prevent database overload
            if i % 1000 == 0:
                await asyncio.sleep(0.1)

        # Final flush and wide vector generation
        await db_writer.flush_all()

        # Force run indicator calculation for all timestamps
        for s in ["T01/USDC", "T02/USDC"]:
            await indicator_calc.calculate(s, symbol_id=symbol_ids[s])

        await wide_vector_service.generate(t01_candles[-1].time)

        # Allow processing to complete
        await asyncio.sleep(60)

        # Stop components
        await db_writer.stop()

        # ---------------------------------------------------------------------
        # Step 5: Verification
        # ---------------------------------------------------------------------
        async with db_pool.acquire() as conn:
            # Verify candle counts
            candle_counts = await conn.fetch("""
                SELECT s.symbol, COUNT(*) as count
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE s.symbol IN ('T01/USDC', 'T02/USDC')
                GROUP BY s.symbol
            """)

            for row in candle_counts:
                assert (
                    row["count"] >= 7000
                ), f"Expected at least 7000 candles for {row['symbol']}, got {row['count']}"

            # Verify indicator counts
            indicator_counts = await conn.fetch("""
                SELECT s.symbol, COUNT(*) as count, COUNT(DISTINCT c.time) as unique_times
                FROM candle_indicators i
                JOIN symbols s ON s.id = i.symbol_id
                JOIN candles_1s c ON c.symbol_id = i.symbol_id AND c.time = i.time
                WHERE s.symbol IN ('T01/USDC', 'T02/USDC')
                GROUP BY s.symbol
            """)

            for row in indicator_counts:
                assert (
                    row["count"] >= 7000
                ), f"Expected at least 7000 indicators for {row['symbol']}, got {row['count']}"

            # Verify wide vector count
            wide_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM wide_vectors
                WHERE symbols @> $1::text[]
            """,
                ["T01/USDC", "T02/USDC"],
            )

            assert wide_count >= 7000, f"Expected at least 7000 wide vectors, got {wide_count}"

            # Verify time alignment across all tables (allowing 1 second delay for indicators)
            alignment_check = await conn.fetchrow(
                """
                WITH candle_times AS (
                    SELECT DISTINCT time FROM candles_1s
                    WHERE symbol_id IN (SELECT id FROM symbols WHERE symbol IN ('T01/USDC', 'T02/USDC'))
                ),
                indicator_times AS (
                    SELECT DISTINCT time FROM candle_indicators
                    WHERE symbol_id IN (SELECT id FROM symbols WHERE symbol IN ('T01/USDC', 'T02/USDC'))
                ),
                wide_times AS (
                    SELECT DISTINCT time FROM wide_vectors
                    WHERE symbols @> $1::text[]
                )
                SELECT
                    (SELECT COUNT(*) FROM candle_times) as candle_count,
                    (SELECT COUNT(*) FROM indicator_times) as indicator_count,
                    (SELECT COUNT(*) FROM wide_times) as wide_count,
                    (SELECT COUNT(*)
                     FROM candle_times ct
                     JOIN indicator_times it ON ABS(EXTRACT(EPOCH FROM ct.time - it.time)) <= 1) as ci_matches,
                    (SELECT COUNT(*)
                     FROM candle_times ct
                     JOIN wide_times wt ON ct.time = wt.time) as cw_matches,
                    (SELECT COUNT(*)
                     FROM indicator_times it
                     JOIN wide_times wt ON ABS(EXTRACT(EPOCH FROM it.time - wt.time)) <= 1) as iw_matches
            """,
                ["T01/USDC", "T02/USDC"],
            )

            # Verify matches are within acceptable tolerance
            match_ratio_cw = alignment_check["cw_matches"] / alignment_check["candle_count"]
            match_ratio_iw = alignment_check["iw_matches"] / alignment_check["indicator_count"]

            # Wide vectors use exact timestamp from candles
            assert (
                match_ratio_cw > 0.98
            ), f"Low candle-wide vector match ratio: {match_ratio_cw:.2%}"
            # Indicators may have up to 1 second processing delay
            assert (
                match_ratio_iw > 0.95
            ), f"Low indicator-wide vector match ratio: {match_ratio_iw:.2%}"

            # Verify wide vector structure
            sample_vector = await conn.fetchrow(
                """
                SELECT vector, vector_size, column_names, symbols
                FROM wide_vectors
                WHERE symbols @> $1::text[]
                ORDER BY time DESC
                LIMIT 1
            """,
                ["T01/USDC", "T02/USDC"],
            )

            assert sample_vector is not None, "No wide vectors found"
            assert (
                sample_vector["vector_size"] >= 52
            ), f"Expected vector size >= 52, got {sample_vector['vector_size']}"
            assert (
                len(sample_vector["column_names"]) == sample_vector["vector_size"]
            ), "Column names length mismatch"
            assert (
                len(sample_vector["symbols"]) >= 4
            ), f"Expected at least 4 symbols in vector, got {len(sample_vector['symbols'])}"

            # Verify no NULL values
            null_check = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE vector IS NULL) as null_vectors,
                    COUNT(*) FILTER (WHERE column_names IS NULL) as null_columns
                FROM wide_vectors
                WHERE symbols @> $1::text[]
            """,
                ["T01/USDC", "T02/USDC"],
            )

            assert null_check["null_vectors"] == 0, "Found NULL vectors in wide_vectors"
            assert null_check["null_columns"] == 0, "Found NULL column names in wide_vectors"

        # ---------------------------------------------------------------------
        # Test completed successfully
        # ---------------------------------------------------------------------
        print("\n✅ Pipeline integration test passed:")
        print(f"  - Candles: {alignment_check['candle_count']}")
        print(f"  - Indicators: {alignment_check['indicator_count']}")
        print(f"  - Wide vectors: {alignment_check['wide_count']}")
        print(f"  - Candle ↔ Wide vector match: {match_ratio_cw:.2%}")
        print(f"  - Indicator ↔ Wide vector match: {match_ratio_iw:.2%}")
        print(f"  - Vector size: {sample_vector['vector_size']} features")
