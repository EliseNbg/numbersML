#!/usr/bin/env python3
"""
Generate 24 hours of synthetic sine wave data for T01/USDC.

This script:
1. Creates T01/USDC symbol (if not exists)
2. Generates 24 hours of sine wave candles (86,400 candles)
3. Calculates technical indicators
4. Generates wide vectors
5. Keeps all data in database (no cleanup)

Usage:
    python3 generate_synthetic_24h.py
"""

import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

from src.pipeline.service import TradePipeline
from src.pipeline.database_writer import MultiSymbolDatabaseWriter as DatabaseWriter
from src.pipeline.indicator_calculator import IndicatorCalculator
from src.pipeline.wide_vector_service import WideVectorService
from src.pipeline.aggregator import TradeAggregation


async def init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


def generate_sine_candles(
    base_time: datetime,
    duration_hours: int = 24,
    period_minutes: int = 15,
    base_price: float = 100.0,
    amplitude: float = 5.0,
    noise_std: float = 0.1
) -> List[TradeAggregation]:
    """
    Generate candles with noised sine wave price pattern.

    Args:
        base_time: Start time
        duration_hours: Total duration (default 24 hours)
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
    print(f"Generating {total_seconds:,} candles for {duration_hours} hours...")

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

        candles.append(TradeAggregation(
            time=time,
            symbol="",
            open=Decimal(str(round(open_price, 5))),
            high=Decimal(str(round(high_price, 5))),
            low=Decimal(str(round(low_price, 5))),
            close=Decimal(str(round(close_price, 5))),
            volume=Decimal(str(round(np.random.uniform(0.1, 10.0), 6))),
            quote_volume=Decimal(0),
            trade_count=1
        ))

        # Progress update
        if (i + 1) % 10000 == 0:
            print(f"  Generated {i + 1:,}/{total_seconds:,} candles ({(i+1)/total_seconds*100:.1f}%)")

    return candles


async def main():
    """Generate 24 hours of synthetic data for T01/USDC."""
    print()
    print("="*60)
    print("Generating 24 Hours of Synthetic Data for T01/USDC")
    print("="*60)
    print()

    # Create database connection pool
    print("Creating database connection pool...")
    db_pool = await asyncpg.create_pool(
        'postgresql://crypto:crypto_secret@localhost:5432/crypto_trading',
        min_size=2,
        max_size=10,
        init=init_utc,
    )

    try:
        # Step 1: Create symbol
        print("\nStep 1: Creating T01/USDC symbol...")
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO symbols (
                    symbol, base_asset, quote_asset,
                    tick_size, step_size, min_notional,
                    is_active, is_allowed
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol) DO UPDATE
                SET is_active = true, is_allowed = true
            ''',
                'T01/USDC', 'T01', 'USDC',
                Decimal('0.00001'), Decimal('0.000001'), Decimal('1.0'),
                True, True
            )

            # Get symbol ID
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1", 'T01/USDC'
            )
            print(f"  ✅ Symbol created with ID: {symbol_id}")

        # Step 2: Generate synthetic candles
        print("\nStep 2: Generating 24 hours of sine wave candles...")
        base_time = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=24)
        t01_candles = generate_sine_candles(
            base_time,
            duration_hours=24,  # 24 hours
            period_minutes=15,
            base_price=100.0,
            amplitude=5.0,
            noise_std=0.1
        )
        print(f"  ✅ Generated {len(t01_candles):,} candles")

        # Step 3: Initialize pipeline components
        print("\nStep 3: Initializing pipeline components...")
        db_writer = DatabaseWriter(db_pool)
        indicator_calc = IndicatorCalculator(db_pool)
        wide_vector_service = WideVectorService(db_pool)

        await db_writer.start()
        await indicator_calc.load_definitions()
        await wide_vector_service.load_symbols()
        print("  ✅ Components initialized")

        # Step 4: Insert candles and calculate indicators
        print("\nStep 4: Inserting candles and calculating indicators...")
        insert_count = 0

        for i in range(len(t01_candles)):
            candle = t01_candles[i]

            # Write candle to database
            await db_writer.write_candle('T01/USDC', candle)

            # Calculate indicators for this candle
            await indicator_calc.calculate('T01/USDC')

            insert_count += 1

            # Flush database writer every 100 candles
            if insert_count % 100 == 0:
                await db_writer.flush_all()
                await wide_vector_service.generate(candle.time)

            # Progress update
            if (i + 1) % 5000 == 0:
                print(f"  Inserted {i + 1:,}/{len(t01_candles):,} candles ({(i+1)/len(t01_candles)*100:.1f}%)")
                await asyncio.sleep(0.1)

            # Small delay every 1000 to prevent database overload
            if i % 1000 == 0 and i > 0:
                await asyncio.sleep(0.1)

        # Final flush
        print("\n  Final flush and wide vector generation...")
        await db_writer.flush_all()

        # Force run indicator calculation for all timestamps
        await indicator_calc.calculate('T01/USDC', symbol_id=symbol_id)

        await wide_vector_service.generate(t01_candles[-1].time)

        # Allow processing to complete
        print("  Waiting for processing to complete...")
        await asyncio.sleep(30)

        # Stop components
        await db_writer.stop()

        # Step 5: Verification
        print("\nStep 5: Verifying data...")
        async with db_pool.acquire() as conn:
            # Count candles
            candle_count = await conn.fetchval('''
                SELECT COUNT(*)
                FROM candles_1s c
                JOIN symbols s ON c.symbol_id = s.id
                WHERE s.symbol = 'T01/USDC'
            ''')
            print(f"  Candles in database: {candle_count:,}")

            # Count wide vectors
            vector_count = await conn.fetchval('''
                SELECT COUNT(*)
                FROM wide_vectors wv
                WHERE wv.vector_size >= 50
            ''')
            print(f"  Wide vectors: {vector_count:,}")

            # Check wide vector features
            sample_vector = await conn.fetchval('''
                SELECT vector_size
                FROM wide_vectors
                WHERE vector_size >= 50
                LIMIT 1
            ''')
            if sample_vector:
                print(f"  Features per wide vector: {sample_vector}")

            # Time range
            time_range = await conn.fetchrow('''
                SELECT
                    MIN(time) as start_time,
                    MAX(time) as end_time
                FROM candles_1s c
                JOIN symbols s ON c.symbol_id = s.id
                WHERE s.symbol = 'T01/USDC'
            ''')
            if time_range['start_time'] and time_range['end_time']:
                duration = time_range['end_time'] - time_range['start_time']
                hours = duration.total_seconds() / 3600
                print(f"  Time range: {time_range['start_time']} to {time_range['end_time']}")
                print(f"  Duration: {hours:.2f} hours")

        print()
        print("="*60)
        print("✅ Synthetic Data Generation Complete!")
        print("="*60)
        print()
        print(f"Symbol: T01/USDC")
        print(f"Duration: 24 hours")
        print(f"Candles: {len(t01_candles):,}")
        print()
        print("Next steps:")
        print("  1. Train CNN+GRU model with 24 hours of data:")
        print("     python3 -m ml.train --model cnn_gru --train-hours 24 --symbol T01/USDC")
        print()
        print("  2. View predictions in dashboard:")
        print("     http://localhost:8000/dashboard/prediction.html")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
