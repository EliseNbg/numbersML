#!/usr/bin/env python3
"""
Quick test to verify DB trigger calculates indicators on insert.
"""

import asyncio
import asyncpg
import json
from datetime import datetime

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

async def test_trigger():
    """Test that trigger calculates indicators on insert."""
    print("=" * 70)
    print("Testing DB Trigger: Indicator Calculation on INSERT")
    print("=" * 70)
    
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    
    try:
        async with pool.acquire() as conn:
            # Get test symbol ID
            symbol_row = await conn.fetchrow(
                "SELECT id FROM symbols WHERE symbol = $1",
                "ts1/USDC"
            )
            
            if not symbol_row:
                print("ERROR: Test symbol ts1/USDC not found!")
                return
            
            symbol_id = symbol_row['id']
            print(f"✓ Found test symbol: ts1/USDC (ID: {symbol_id})")
            
            # Insert 60 tickers to build up price history
            print("\nInserting 60 tickers to build price history...")
            base_price = 100.0
            
            for i in range(60):
                # Linear up pattern (+1% per tick)
                price = base_price * (1.0 + i * 0.01)
                
                await conn.execute(
                    """
                    INSERT INTO ticker_24hr_stats (
                        time, symbol_id, symbol,
                        last_price, open_price, high_price, low_price,
                        total_volume, total_quote_volume,
                        price_change, price_change_pct, total_trades
                    ) VALUES (
                        NOW() - INTERVAL '60 seconds' + INTERVAL '{} seconds',
                        $1, 'ts1/USDC', $2, $3, $4, $5, $6, $7, $8, $9, 100
                    )
                    """.format(i),
                    symbol_id, price,
                    price * 0.99,  # open
                    price * 1.02,  # high
                    price * 0.98,  # low
                    1000.0 + i * 50,  # volume
                    (1000.0 + i * 50) * price,  # quote volume
                    price * 0.01,  # change
                    1.0  # change pct
                )
            
            print(f"✓ Inserted 60 tickers")
            
            # Check if indicators were calculated
            print("\nChecking for calculated indicators...")
            
            indicators = await conn.fetch(
                """
                SELECT time, values, indicator_keys
                FROM tick_indicators
                WHERE symbol_id = $1
                ORDER BY time DESC
                LIMIT 5
                """,
                symbol_id
            )
            
            if indicators:
                print(f"✓ Found {len(indicators)} indicator records!")
                print("\nLatest indicators:")
                
                for ind in indicators[:3]:
                    print(f"\n  Time: {ind['time']}")
                    print(f"  Keys: {list(ind['indicator_keys'])}")
                    print(f"  Values:")
                    for key, value in ind['values'].items():
                        if isinstance(value, float):
                            print(f"    {key}: {value:.4f}")
                        else:
                            print(f"    {key}: {value}")
            else:
                print("⚠ WARNING: No indicators found!")
                print("\nChecking if trigger exists...")
                
                trigger_check = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count
                    FROM information_schema.triggers
                    WHERE trigger_name = 'calculate_indicators_trigger'
                    """
                )
                
                if trigger_check['count'] > 0:
                    print("✓ Trigger exists in database")
                else:
                    print("✗ Trigger NOT found in database!")
            
            # Summary
            print("\n" + "=" * 70)
            print("TEST SUMMARY")
            print("=" * 70)
            
            ticker_count = await conn.fetchval(
                "SELECT COUNT(*) FROM ticker_24hr_stats WHERE symbol_id = $1",
                symbol_id
            )
            
            indicator_count = await conn.fetchval(
                "SELECT COUNT(*) FROM tick_indicators WHERE symbol_id = $1",
                symbol_id
            )
            
            print(f"Tickers inserted: {ticker_count}")
            print(f"Indicators calculated: {indicator_count}")
            
            if indicator_count > 0:
                print("\n✅ SUCCESS: Trigger is working!")
            else:
                print("\n⚠ WARNING: No indicators calculated")
                print("Check PostgreSQL logs for errors")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await pool.close()

if __name__ == '__main__':
    asyncio.run(test_trigger())
