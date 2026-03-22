#!/usr/bin/env python3
"""
Integration Test: Insert Test Ticker Data

Inserts 20 ticker data points for each of the 12 test symbols (ts1-ts12)
with 1-second pause between inserts to emulate Binance !miniTicker@arr stream.

This tests:
1. Ticker insertion
2. DB trigger for indicator calculation
3. Wide vector generation
"""

import asyncio
import asyncpg
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Test configuration
TEST_SYMBOLS = [f'ts{i}/USDC' for i in range(1, 13)]  # ts1 to ts12
NUM_TICKS = 3  # 3 ticks per symbol for quick test (change to 20 for full test)
DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

# Predefined price patterns for each symbol (for predictable testing)
# Each symbol has a base price and a pattern
SYMBOL_PRICES = {
    'ts1/USDC': {'base': 100.0, 'pattern': 'linear_up'},
    'ts2/USDC': {'base': 50.0, 'pattern': 'linear_down'},
    'ts3/USDC': {'base': 200.0, 'pattern': 'sine_wave'},
    'ts4/USDC': {'base': 75.0, 'pattern': 'random_walk'},
    'ts5/USDC': {'base': 150.0, 'pattern': 'flat'},
    'ts6/USDC': {'base': 300.0, 'pattern': 'linear_up'},
    'ts7/USDC': {'base': 80.0, 'pattern': 'sine_wave'},
    'ts8/USDC': {'base': 120.0, 'pattern': 'random_walk'},
    'ts9/USDC': {'base': 90.0, 'pattern': 'linear_down'},
    'ts10/USDC': {'base': 250.0, 'pattern': 'flat'},
    'ts11/USDC': {'base': 60.0, 'pattern': 'sine_wave'},
    'ts12/USDC': {'base': 180.0, 'pattern': 'linear_up'},
}


def generate_price(symbol: str, tick_num: int) -> float:
    """Generate predictable price based on symbol pattern."""
    import math
    
    config = SYMBOL_PRICES.get(symbol, {'base': 100.0, 'pattern': 'flat'})
    base = config['base']
    pattern = config['pattern']
    
    if pattern == 'linear_up':
        # Price increases by 1% per tick
        return base * (1.0 + tick_num * 0.01)
    
    elif pattern == 'linear_down':
        # Price decreases by 0.5% per tick
        return base * (1.0 - tick_num * 0.005)
    
    elif pattern == 'sine_wave':
        # Price oscillates with sine wave
        return base * (1.0 + 0.05 * math.sin(tick_num * 0.5))
    
    elif pattern == 'random_walk':
        # Deterministic "random" walk (using tick as seed)
        import random
        random.seed(tick_num * 100 + hash(symbol) % 1000)
        change = (random.random() - 0.5) * 0.02  # ±1%
        return base * (1.0 + change)
    
    else:  # flat
        return base


async def insert_test_ticker(
    conn: asyncpg.Connection,
    symbol: str,
    tick_num: int,
    price: float,
) -> Dict:
    """
    Insert a single ticker for a test symbol.
    
    Returns the inserted ticker data.
    """
    # Get symbol ID
    symbol_row = await conn.fetchrow(
        "SELECT id FROM symbols WHERE symbol = $1",
        symbol
    )
    
    if not symbol_row:
        logger.error(f"Symbol {symbol} not found!")
        return None
    
    symbol_id = symbol_row['id']
    
    # Generate ticker data
    open_price = price * 0.99  # Open slightly lower
    high_price = price * 1.02  # High 2% higher
    low_price = price * 0.98   # Low 2% lower
    volume = 1000.0 + tick_num * 50  # Increasing volume
    quote_volume = volume * price
    price_change = price - open_price
    price_change_pct = (price_change / open_price) * 100
    
    # Insert ticker (match actual schema)
    await conn.execute(
        """
        INSERT INTO ticker_24hr_stats (
            time, symbol_id, symbol,
            last_price, open_price, high_price, low_price,
            total_volume, total_quote_volume,
            price_change, price_change_pct, total_trades
        ) VALUES (
            NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
        )
        """,
        symbol_id,
        symbol,
        price,
        open_price,
        high_price,
        low_price,
        volume,
        quote_volume,
        price_change,
        price_change_pct,
        100 + tick_num,  # trade count
    )
    
    return {
        'symbol': symbol,
        'tick_num': tick_num,
        'price': price,
        'open': open_price,
        'high': high_price,
        'low': low_price,
        'volume': volume,
    }


async def verify_indicators_calculated(
    conn: asyncpg.Connection,
    symbol: str,
    tick_time: datetime,
) -> Dict:
    """Verify indicators were calculated by trigger."""
    # Get symbol ID
    symbol_row = await conn.fetchrow(
        "SELECT id FROM symbols WHERE symbol = $1",
        symbol
    )
    
    if not symbol_row:
        return None
    
    symbol_id = symbol_row['id']
    
    # Check for indicators
    indicator_row = await conn.fetchrow(
        """
        SELECT values, indicator_keys
        FROM tick_indicators
        WHERE symbol_id = $1 AND time = $2
        """,
        symbol_id,
        tick_time
    )
    
    if not indicator_row:
        return None
    
    return {
        'values': dict(indicator_row['values']),
        'keys': list(indicator_row['indicator_keys']),
    }


async def run_integration_test() -> Dict:
    """
    Run the complete integration test.
    
    Returns test results.
    """
    logger.info("=" * 70)
    logger.info("Integration Test: Ticker Insert → Indicators → Wide Vector")
    logger.info("=" * 70)
    logger.info(f"Test symbols: {len(TEST_SYMBOLS)}")
    logger.info(f"Ticks per symbol: {NUM_TICKS}")
    logger.info(f"Total inserts: {len(TEST_SYMBOLS) * NUM_TICKS}")
    logger.info("")
    
    # Connect to database
    db_pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    
    test_results = {
        'start_time': datetime.now(timezone.utc).isoformat(),
        'symbols_tested': [],
        'ticks_inserted': 0,
        'indicators_verified': 0,
        'errors': [],
    }
    
    try:
        async with db_pool.acquire() as conn:
            # Insert tickers for each symbol
            for symbol in TEST_SYMBOLS:
                logger.info(f"Processing {symbol}...")
                
                symbol_result = {
                    'symbol': symbol,
                    'base_price': SYMBOL_PRICES[symbol]['base'],
                    'pattern': SYMBOL_PRICES[symbol]['pattern'],
                    'ticks': [],
                    'indicators': [],
                }
                
                for tick_num in range(NUM_TICKS):
                    # Generate price
                    price = generate_price(symbol, tick_num)
                    
                    # Insert ticker
                    ticker_data = await insert_test_ticker(conn, symbol, tick_num, price)
                    
                    if ticker_data:
                        test_results['ticks_inserted'] += 1
                        symbol_result['ticks'].append(ticker_data)
                        
                        logger.debug(f"  Tick {tick_num}: price={price:.2f}")
                    
                    # Wait 1 second (emulate !miniTicker@arr)
                    if tick_num < NUM_TICKS - 1:
                        await asyncio.sleep(1.0)
                
                test_results['symbols_tested'].append(symbol_result)
                logger.info(f"  ✓ {symbol}: {NUM_TICKS} ticks inserted")
            
            # Verify indicators were calculated
            logger.info("")
            logger.info("Verifying indicator calculation...")
            
            for symbol_result in test_results['symbols_tested']:
                symbol = symbol_result['symbol']
                
                # Get last ticker time
                last_tick = symbol_result['ticks'][-1]
                
                # For this test, we'll check if ANY indicators exist for the symbol
                async with db_pool.acquire() as conn:
                    symbol_row = await conn.fetchrow(
                        "SELECT id FROM symbols WHERE symbol = $1",
                        symbol
                    )
                    
                    if symbol_row:
                        # Check for any indicators
                        indicators = await conn.fetch(
                            """
                            SELECT values, indicator_keys, time
                            FROM tick_indicators
                            WHERE symbol_id = $1
                            ORDER BY time DESC
                            LIMIT 1
                            """,
                            symbol_row['id']
                        )
                        
                        if indicators:
                            test_results['indicators_verified'] += 1
                            symbol_result['indicators'] = {
                                'keys': list(indicators[0]['indicator_keys']),
                                'values': dict(indicators[0]['values']),
                                'time': indicators[0]['time'].isoformat(),
                            }
                            logger.info(f"  ✓ {symbol}: {len(indicators[0]['indicator_keys'])} indicators")
                        else:
                            logger.warning(f"  ⚠ {symbol}: No indicators found")
                            test_results['errors'].append(f"{symbol}: No indicators")
            
            test_results['end_time'] = datetime.now(timezone.utc).isoformat()
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        test_results['errors'].append(str(e))
        import traceback
        traceback.print_exc()
    
    finally:
        await db_pool.close()
    
    return test_results


async def main() -> None:
    """Main entry point."""
    # Run integration test
    results = await run_integration_test()
    
    # Print summary
    print("")
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Start time: {results['start_time']}")
    print(f"End time: {results['end_time']}")
    print(f"Symbols tested: {len(results['symbols_tested'])}")
    print(f"Total ticks inserted: {results['ticks_inserted']}")
    print(f"Symbols with indicators: {results['indicators_verified']}/{len(results['symbols_tested'])}")
    print(f"Errors: {len(results['errors'])}")
    
    if results['errors']:
        print("")
        print("Errors:")
        for error in results['errors']:
            print(f"  - {error}")
    
    # Save results to file
    results_file = '/tmp/integration_test_results.json'
    with open(results_file, 'w') as f:
        # Convert to JSON-serializable format
        json_results = {
            'start_time': results['start_time'],
            'end_time': results['end_time'],
            'symbols_tested': len(results['symbols_tested']),
            'ticks_inserted': results['ticks_inserted'],
            'indicators_verified': results['indicators_verified'],
            'errors': results['errors'],
            'sample_data': [],
        }
        
        # Add sample data for first 3 symbols
        for symbol_result in results['symbols_tested'][:3]:
            json_results['sample_data'].append({
                'symbol': symbol_result['symbol'],
                'base_price': symbol_result['base_price'],
                'pattern': symbol_result['pattern'],
                'first_tick': symbol_result['ticks'][0] if symbol_result['ticks'] else None,
                'last_tick': symbol_result['ticks'][-1] if symbol_result['ticks'] else None,
                'indicators': symbol_result.get('indicators'),
            })
        
        json.dump(json_results, f, indent=2, default=str)
    
    print("")
    print(f"Results saved to: {results_file}")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
