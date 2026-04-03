#!/usr/bin/env python3
"""
Fast synthetic data generation for T01/USDC (24 hours).

Directly inserts data in batches for speed.
"""

import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import time

async def main():
    print("="*60)
    print("Generating 24 Hours Synthetic Data for T01/USDC")
    print("="*60)
    
    pool = await asyncpg.create_pool(
        'postgresql://crypto:crypto_secret@localhost:5432/crypto_trading'
    )
    
    async with pool.acquire() as conn:
        await conn.execute("SET timezone = 'UTC'")
        
        # 1. Create symbol
        print("\n1. Creating symbol T01/USDC...")
        await conn.execute("""
            INSERT INTO symbols (symbol, base_asset, quote_asset, tick_size, step_size, min_notional, is_active, is_allowed)
            VALUES ('T01/USDC', 'T01', 'USDC', 0.00001, 0.000001, 1.0, true, true)
            ON CONFLICT (symbol) DO UPDATE SET is_active = true, is_allowed = true
        """)
        symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = 'T01/USDC'")
        print(f"   Symbol ID: {symbol_id}")
        
        # 2. Generate candles (24 hours = 86400 seconds)
        print("\n2. Generating 86,400 candles (24 hours)...")
        duration = 24 * 3600
        base_time = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=24)
        
        # Generate all at once with numpy
        indices = np.arange(duration)
        prices = 100.0 + 5.0 * np.sin(2 * np.pi * indices / (15 * 60))
        prices += np.random.normal(0, 0.1, duration)
        
        opens = prices + np.random.uniform(-0.05, 0.05, duration)
        highs = np.maximum(opens, prices) + np.random.uniform(0, 0.1, duration)
        lows = np.minimum(opens, prices) - np.random.uniform(0, 0.1, duration)
        closes = prices
        volumes = np.random.uniform(0.1, 10.0, duration)
        timestamps = [base_time + timedelta(seconds=i) for i in range(duration)]
        
        print(f"   Generated {len(closes):,} candles")
        
        # 3. Batch insert candles
        print("\n3. Inserting candles in batches...")
        batch_size = 1000
        start = time.time()
        
        for i in range(0, duration, batch_size):
            end = min(i + batch_size, duration)
            rows = []
            for j in range(i, end):
                rows.append((
                    symbol_id,
                    timestamps[j],
                    Decimal(str(round(opens[j], 5))),
                    Decimal(str(round(highs[j], 5))),
                    Decimal(str(round(lows[j], 5))),
                    Decimal(str(round(closes[j], 5))),
                    Decimal(str(round(volumes[j], 6))),
                    Decimal(str(round(volumes[j] * closes[j], 6))),
                    1
                ))
            
            await conn.executemany("""
                INSERT INTO candles_1s (symbol_id, time, open, high, low, close, volume, quote_volume, trade_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (symbol_id, time) DO NOTHING
            """, rows)
            
            if (i + batch_size) % 10000 == 0:
                elapsed = time.time() - start
                pct = (i + batch_size) / duration * 100
                print(f"   Inserted {i + batch_size:,}/{duration:,} ({pct:.0f}%) - {elapsed:.1f}s")
        
        elapsed = time.time() - start
        print(f"   ✅ Inserted {duration:,} candles in {elapsed:.1f}s")
        
        # 4. Calculate indicators - use actual candle_indicators schema
        print("\n4. Calculating indicators...")
        
        # Calculate indicators and store in candle_indicators
        await conn.execute("""
            INSERT INTO candle_indicators (
                symbol_id, time, price, volume, 
                values, indicator_keys, indicator_version
            )
            SELECT
                c.symbol_id,
                c.time,
                c.close,
                c.volume,
                jsonb_build_object(
                    'atr_14', AVG(ABS(c.high - c.low)) OVER w,
                    'ema_10', AVG(c.close) OVER w10,
                    'ema_20', AVG(c.close) OVER w20,
                    'ema_50', AVG(c.close) OVER w50,
                    'macd', (AVG(c.close) OVER w12 - AVG(c.close) OVER w26),
                    'rsi_14', 50.0,
                    'sma_10', AVG(c.close) OVER w10,
                    'sma_20', AVG(c.close) OVER w20,
                    'sma_50', AVG(c.close) OVER w50,
                    'bb_upper', AVG(c.close) OVER w20 + 2.0 * STDDEV(c.close) OVER w20,
                    'bb_middle', AVG(c.close) OVER w20,
                    'bb_lower', AVG(c.close) OVER w20 - 2.0 * STDDEV(c.close) OVER w20
                ),
                ARRAY['atr_14', 'ema_10', 'ema_20', 'ema_50', 'macd', 'rsi_14', 'sma_10', 'sma_20', 'sma_50', 'bb_upper', 'bb_middle', 'bb_lower'],
                1
            FROM candles_1s c
            WHERE c.symbol_id = $1
            WINDOW 
                w AS (ORDER BY c.time ROWS BETWEEN 14 PRECEDING AND CURRENT ROW),
                w10 AS (ORDER BY c.time ROWS BETWEEN 9 PRECEDING AND CURRENT ROW),
                w20 AS (ORDER BY c.time ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
                w50 AS (ORDER BY c.time ROWS BETWEEN 49 PRECEDING AND CURRENT ROW),
                w12 AS (ORDER BY c.time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
                w26 AS (ORDER BY c.time ROWS BETWEEN 25 PRECEDING AND CURRENT ROW)
            ON CONFLICT (symbol_id, time) DO UPDATE SET
                values = EXCLUDED.values,
                indicator_keys = EXCLUDED.indicator_keys,
                updated_at = NOW()
        """, symbol_id)
        
        indicator_count = await conn.fetchval(
            "SELECT COUNT(*) FROM candle_indicators WHERE symbol_id = $1", symbol_id
        )
        print(f"   ✅ Calculated {indicator_count:,} indicator rows")
        
        # 5. Generate wide vectors
        print("\n5. Generating wide vectors...")
        
        vectors = await conn.fetch("""
            SELECT
                c.time,
                ARRAY[
                    COALESCE((ci.values->>'sma_10')::float, c.close::float),
                    COALESCE((ci.values->>'sma_20')::float, c.close::float),
                    COALESCE((ci.values->>'sma_50')::float, c.close::float),
                    COALESCE((ci.values->>'ema_10')::float, c.close::float),
                    COALESCE((ci.values->>'ema_20')::float, c.close::float),
                    COALESCE((ci.values->>'ema_50')::float, c.close::float),
                    COALESCE((ci.values->>'rsi_14')::float, 50.0),
                    COALESCE((ci.values->>'macd')::float, 0.0),
                    COALESCE((ci.values->>'atr_14')::float, 0.0),
                    COALESCE((ci.values->>'bb_upper')::float, c.close::float),
                    COALESCE((ci.values->>'bb_middle')::float, c.close::float),
                    COALESCE((ci.values->>'bb_lower')::float, c.close::float),
                    c.close::float,
                    c.volume::float,
                    c.open::float,
                    c.high::float,
                    c.low::float,
                    -- Add padding features to reach 50+ features
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                ] as features
            FROM candles_1s c
            LEFT JOIN candle_indicators ci ON ci.symbol_id = c.symbol_id AND ci.time = c.time
            WHERE c.symbol_id = $1
            ORDER BY c.time
        """, symbol_id)
        
        # Insert wide vectors in batches
        print(f"   Processing {len(vectors):,} vectors...")
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i+batch_size]
            rows = []
            feature_names = ['sma_10', 'sma_20', 'sma_50', 'ema_10', 'ema_20', 'ema_50',
                           'rsi_14', 'macd', 'atr_14', 'bb_upper', 'bb_middle', 'bb_lower',
                           'close', 'volume', 'open', 'high', 'low'] + \
                          [f'pad_{i}' for i in range(34)]  # Padding to reach 51 features
            for v in batch:
                vector_json = json.dumps([float(x) if x else 0.0 for x in v['features']])
                rows.append((
                    v['time'], 
                    vector_json, 
                    len(v['features']),
                    feature_names,
                    ['T01/USDC'],
                    1,
                    0
                ))
            
            await conn.executemany("""
                INSERT INTO wide_vectors (time, vector, vector_size, column_names, symbols, symbol_count, indicator_count)
                VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7)
                ON CONFLICT (time) DO UPDATE SET vector = EXCLUDED.vector, vector_size = EXCLUDED.vector_size
            """, rows)
            
            if (i + batch_size) % 20000 == 0:
                print(f"   Inserted {min(i + batch_size, len(vectors)):,}/{len(vectors):,} vectors")
        
        print(f"   ✅ Generated {len(vectors):,} wide vectors with {len(vectors[0]['features'])} features each")
        
        # 6. Summary
        print("\n" + "="*60)
        print("✅ Synthetic Data Generation Complete!")
        print("="*60)
        
        candle_count = await conn.fetchval("SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1", symbol_id)
        vector_count = await conn.fetchval("SELECT COUNT(*) FROM wide_vectors")
        time_range = await conn.fetchrow("""
            SELECT MIN(time) as start_time, MAX(time) as end_time
            FROM candles_1s WHERE symbol_id = $1
        """, symbol_id)
        
        hours = (time_range['end_time'] - time_range['start_time']).total_seconds() / 3600
        
        print(f"\nSymbol: T01/USDC")
        print(f"Candles: {candle_count:,}")
        print(f"Indicators: {indicator_count:,}")
        print(f"Wide Vectors: {vector_count:,}")
        print(f"Features: {len(vectors[0]['features'])}")
        print(f"Time Range: {time_range['start_time']} to {time_range['end_time']}")
        print(f"Duration: {hours:.1f} hours")
        print(f"\nNext step:")
        print(f"  python3 -m ml.train --model cnn_gru --train-hours 24 --symbol T01/USDC")

if __name__ == "__main__":
    asyncio.run(main())
