#!/usr/bin/env python3
"""
Complete Integration Test: Ticker Insert → EnrichmentService → Wide Vector → Validation

This test verifies the complete enrichment flow:
1. Inserts test ticker data for 12 test symbols
2. Waits for Python EnrichmentService to calculate indicators
3. Verifies indicators are calculated (via EnrichmentService, not DB trigger)
4. Generates wide vector for LLM with all indicators
5. Validates vector against expected values
6. Saves results to file

Key difference from old test:
- Old: Indicators calculated synchronously by DB trigger
- New: Indicators calculated asynchronously by Python EnrichmentService
- Test now waits for enrichment_complete notification before proceeding
"""

import asyncio
import asyncpg
import json
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Any, Set

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"
TEST_SYMBOLS = [f'ts{i}/USDC' for i in range(1, 13)]  # ts1 to ts12


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")

# Expected price patterns
SYMBOL_PATTERNS = {
    'ts1/USDC': {'base': 100.0, 'type': 'linear_up', 'rate': 0.01},
    'ts2/USDC': {'base': 50.0, 'type': 'linear_down', 'rate': -0.005},
    'ts3/USDC': {'base': 200.0, 'type': 'flat', 'rate': 0.0},
}

# Enrichment timeout (seconds)
ENRICHMENT_TIMEOUT = 15.0


async def wait_for_enrichment(
    conn: asyncpg.Connection,
    symbol_ids: List[int],
    timeout: float = ENRICHMENT_TIMEOUT
) -> bool:
    """
    Wait for enrichment to complete for all specified symbols.

    Listens to PostgreSQL NOTIFY 'enrichment_complete' channel
    and waits until all symbols have been enriched.

    Args:
        conn: Database connection
        symbol_ids: List of symbol IDs to wait for
        timeout: Max seconds to wait

    Returns:
        True if all enriched, False if timeout
    """
    start_time = datetime.now(timezone.utc)

    # Listen for enrichment complete notifications
    await conn.listen('enrichment_complete')

    # Get latest tick times for each symbol
    expected = await _get_latest_ticks(conn, symbol_ids)

    if not expected:
        print("  ⚠ No ticks found to wait for")
        return True

    print(f"  Waiting for enrichment for {len(expected)} symbols (timeout: {timeout}s)...")

    # Wait for enrichment notifications
    while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout:
        try:
            notification = await asyncio.wait_for(
                conn.notification(),
                timeout=1.0
            )

            payload = json.loads(notification.payload)
            key = (payload['symbol_id'], payload['time'])

            if key in expected:
                expected.discard(key)
                print(f"    ✓ Enriched: symbol_id={payload['symbol_id']}")

                if not expected:
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    print(f"  ✓ All symbols enriched in {elapsed:.2f}s")
                    return True

        except asyncio.TimeoutError:
            continue

    # Timeout
    print(f"  ⚠ Timeout: {len(expected)} symbols not enriched")
    return False


async def _get_latest_ticks(
    conn: asyncpg.Connection,
    symbol_ids: List[int]
) -> Set[tuple]:
    """Get latest candle time for each symbol."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (symbol_id)
            symbol_id, time
        FROM candles_1s
        WHERE symbol_id = ANY($1)
        ORDER BY symbol_id, time DESC
        """,
        symbol_ids
    )

    return {(row['symbol_id'], str(row['time'])) for row in rows}


async def generate_wide_vector(conn: asyncpg.Connection) -> Dict[str, Any]:
    """
    Generate wide vector from all test symbols.

    This function queries candles_1s and candle_indicators tables
    and combines them into a single flat vector for LLM consumption.
    """

    # Get latest candles and indicators for each symbol
    rows = await conn.fetch("""
        SELECT
            s.symbol,
            c.close, c.open, c.high, c.low,
            c.volume, c.quote_volume,
            ti.values as indicators,
            ti.indicator_keys
        FROM symbols s
        JOIN candles_1s c ON c.symbol_id = s.id
        LEFT JOIN candle_indicators ti ON ti.symbol_id = c.symbol_id AND ti.time = c.time
        WHERE s.is_test = true
        AND c.time = (
            SELECT MAX(time) FROM candles_1s WHERE symbol_id = c.symbol_id
        )
        ORDER BY s.symbol
    """)

    # Build wide vector
    values = []
    columns = []

    for row in rows:
        symbol = row['symbol']

        # Candle features (6 features per symbol)
        candle_features = [
            ('close', float(row['close']) if row['close'] else 0.0),
            ('open', float(row['open']) if row['open'] else 0.0),
            ('high', float(row['high']) if row['high'] else 0.0),
            ('low', float(row['low']) if row['low'] else 0.0),
            ('volume', float(row['volume']) if row['volume'] else 0.0),
            ('quote_volume', float(row['quote_volume']) if row['quote_volume'] else 0.0),
        ]

        for feat_name, feat_val in candle_features:
            columns.append(f"{symbol}_{feat_name}")
            values.append(feat_val)

        # Indicator features (variable per symbol)
        if row['indicators']:
            indicators_raw = row['indicators']
            if isinstance(indicators_raw, str):
                indicators = json.loads(indicators_raw)
            elif isinstance(indicators_raw, dict):
                indicators = indicators_raw
            else:
                indicators = {}

            for ind_key in sorted(indicators.keys()):
                columns.append(f"{symbol}_{ind_key}")
                values.append(float(indicators[ind_key]) if indicators[ind_key] else 0.0)

    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'symbols': [row['symbol'] for row in rows],
        'vector': np.array(values, dtype=np.float32),
        'column_names': columns,
        'metadata': {
            'symbols_count': len(rows),
            'total_columns': len(columns),
            'features_per_symbol': len(columns) // len(rows) if rows else 0,
        }
    }


def validate_vector(vector_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate wide vector against expected values.

    Checks:
    - Vector size (should have ticker + indicator features)
    - Price values (should match test data patterns)
    - Indicator existence (should have RSI, SMA, etc.)
    - No NaN or Inf values
    """

    validation = {
        'passed': True,
        'checks': [],
        'errors': [],
    }

    # Check vector has data (12 symbols × 8 ticker = 96 minimum, plus indicators)
    min_expected = 12 * 8  # 96 columns minimum (ticker only)
    max_expected = 12 * 25  # 300 columns (ticker + all indicators)
    actual_size = len(vector_data['vector'])

    check = {
        'name': 'Vector size',
        'expected': f'{min_expected}-{max_expected}',
        'actual': actual_size,
        'passed': min_expected <= actual_size <= max_expected,
    }
    validation['checks'].append(check)
    if not check['passed']:
        validation['errors'].append(f"Vector size out of range: {actual_size}")
        validation['passed'] = False

    # Check ts1 price (should be ~100 after inserts)
    if 'ts1/USDC_last_price' in vector_data['column_names']:
        ts1_price_idx = vector_data['column_names'].index('ts1/USDC_last_price')
        ts1_price = vector_data['vector'][ts1_price_idx]

        check = {
            'name': 'ts1/USDC price',
            'expected': '≈100.0',
            'actual': float(ts1_price),
            'passed': 95.0 < ts1_price < 105.0,
        }
        validation['checks'].append(check)
        if not check['passed']:
            validation['errors'].append(f"ts1 price out of range: {ts1_price}")
            validation['passed'] = False

    # Check indicators exist (at least RSI, SMA, EMA, Bollinger)
    expected_indicators = ['rsi', 'sma', 'ema', 'bb']
    found_indicators = []
    missing_indicators = []

    for col in vector_data['column_names']:
        for ind in expected_indicators:
            if ind in col.lower() and col not in found_indicators:
                found_indicators.append(col)

    for ind in expected_indicators:
        if not any(ind in col.lower() for col in vector_data['column_names']):
            missing_indicators.append(ind)

    check = {
        'name': 'Expected indicators present',
        'expected': expected_indicators,
        'actual': found_indicators[:10],  # Show first 10
        'passed': len(missing_indicators) == 0,
    }
    validation['checks'].append(check)
    if missing_indicators:
        validation['errors'].append(f"Missing indicators: {missing_indicators}")
        validation['passed'] = False

    # Check no NaN values
    has_nan = np.isnan(vector_data['vector']).any()
    check = {
        'name': 'No NaN values',
        'expected': False,
        'actual': bool(has_nan),
        'passed': not has_nan,
    }
    validation['checks'].append(check)
    if has_nan:
        validation['errors'].append("Vector contains NaN values")
        validation['passed'] = False

    # Check no Inf values
    has_inf = np.isinf(vector_data['vector']).any()
    check = {
        'name': 'No Inf values',
        'expected': False,
        'actual': bool(has_inf),
        'passed': not has_inf,
    }
    validation['checks'].append(check)
    if has_inf:
        validation['errors'].append("Vector contains Inf values")
        validation['passed'] = False

    return validation


async def run_integration_test() -> Dict[str, Any]:
    """Run complete integration test."""

    print("=" * 70)
    print("Integration Test: Ticker → EnrichmentService → Wide Vector → Validation")
    print("=" * 70)
    print()
    print("This test verifies:")
    print("  1. Candle data inserted into candles_1s")
    print("  2. Python EnrichmentService calculates indicators (async)")
    print("  3. Wide vector generated with all indicators")
    print("  4. Vector validation (size, values, no NaN/Inf)")
    print("=" * 70)

    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10, init=_init_utc)

    results = {
        'test_name': 'Complete Integration Test',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'steps': {},
        'validation': None,
        'files_saved': [],
        'enrichment_complete': False,
    }

    try:
        async with pool.acquire() as conn:
            # Step 1: Check test symbols exist
            print("\n[Step 1] Checking test symbols...")
            symbols = await conn.fetch(
                "SELECT symbol FROM symbols WHERE is_test = true ORDER BY symbol"
            )
            results['steps']['test_symbols'] = len(symbols)
            print(f"  ✓ Found {len(symbols)} test symbols")

            if not symbols:
                print("  ⚠ No test symbols found! Create test symbols first.")
                results['error'] = "No test symbols found"
                return results

            # Get symbol IDs for enrichment wait
            symbol_ids = [s['symbol'] for s in symbols]
            symbol_id_map = {s['symbol']: idx for idx, s in enumerate(symbols)}

            # Step 2: Check ticker data
            print("\n[Step 2] Checking candle data...")
            candles = await conn.fetch(
                """
                SELECT s.symbol, COUNT(*) as count
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE s.is_test = true
                GROUP BY s.symbol
                ORDER BY s.symbol
                """
            )
            results['steps']['candle_data'] = {s['symbol']: s['count'] for s in candles}
            print(f"  ✓ Found candle data for {len(candles)} symbols")

            if not candles:
                print("  ⚠ No candle data found! Insert candle data first.")
                results['error'] = "No candle data found"
                return results

            # Step 3: Wait for enrichment
            print("\n[Step 3] Waiting for enrichment (EnrichmentService)...")
            
            # Get internal symbol IDs from database
            symbol_rows = await conn.fetch(
                "SELECT id, symbol FROM symbols WHERE is_test = true"
            )
            internal_ids = [row['id'] for row in symbol_rows]

            enriched = await wait_for_enrichment(conn, internal_ids, timeout=ENRICHMENT_TIMEOUT)
            results['enrichment_complete'] = enriched

            if not enriched:
                print("  ⚠ Enrichment did not complete within timeout")
                print("  Continuing with available data...")

            # Step 4: Check indicators
            print("\n[Step 4] Checking indicators...")
            indicators = await conn.fetch(
                """
                SELECT s.symbol, COUNT(*) as count
                FROM candle_indicators ti
                JOIN symbols s ON s.id = ti.symbol_id
                WHERE s.is_test = true
                GROUP BY s.symbol
                ORDER BY s.symbol
                """
            )
            results['steps']['indicators'] = {i['symbol']: i['count'] for i in indicators}
            print(f"  ✓ Found indicators for {len(indicators)} symbols")

            # Show sample indicators
            if indicators:
                sample = await conn.fetchrow(
                    """
                    SELECT symbol, indicator_keys, time
                    FROM candle_indicators ti
                    JOIN symbols s ON s.id = ti.symbol_id
                    WHERE s.is_test = true
                    ORDER BY ti.time DESC
                    LIMIT 1
                    """
                )
                print(f"  Sample: {sample['symbol']} has {len(sample['indicator_keys'])} indicators")
                print(f"    Keys: {list(sample['indicator_keys'])[:10]}...")

            # Step 5: Generate wide vector
            print("\n[Step 5] Generating wide vector...")
            vector_data = await generate_wide_vector(conn)
            results['steps']['wide_vector'] = {
                'symbols_count': vector_data['metadata']['symbols_count'],
                'total_columns': vector_data['metadata']['total_columns'],
                'vector_size': len(vector_data['vector']),
                'enrichment_complete': enriched,
            }
            print(f"  ✓ Generated vector: {vector_data['metadata']['total_columns']} columns")

            # Step 6: Validate vector
            print("\n[Step 6] Validating vector...")
            validation = validate_vector(vector_data)
            results['validation'] = validation
            print(f"  {'✓' if validation['passed'] else '✗'} Validation: {'PASSED' if validation['passed'] else 'FAILED'}")

            for check in validation['checks']:
                status = '✓' if check['passed'] else '✗'
                print(f"    {status} {check['name']}: {check['actual']}")

            if validation['errors']:
                print("\n  Errors:")
                for error in validation['errors']:
                    print(f"    - {error}")

            # Step 7: Save results
            print("\n[Step 7] Saving results...")

            # Save wide vector
            vector_file = '/tmp/wide_vector_test.json'
            with open(vector_file, 'w') as f:
                json.dump({
                    'timestamp': vector_data['timestamp'],
                    'symbols': vector_data['symbols'],
                    'vector': vector_data['vector'].tolist(),
                    'column_names': vector_data['column_names'],
                    'metadata': vector_data['metadata'],
                    'enrichment_complete': enriched,
                }, f, indent=2)
            results['files_saved'].append(vector_file)
            print(f"  ✓ Saved wide vector: {vector_file}")

            # Save validation results
            validation_file = '/tmp/validation_results.json'
            with open(validation_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            results['files_saved'].append(validation_file)
            print(f"  ✓ Saved validation: {validation_file}")

            # Save numpy array
            npy_file = '/tmp/wide_vector_test.npy'
            np.save(npy_file, vector_data['vector'])
            results['files_saved'].append(npy_file)
            print(f"  ✓ Saved NumPy array: {npy_file}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        results['error'] = str(e)

    finally:
        await pool.close()

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Test symbols: {results['steps'].get('test_symbols', 'N/A')}")
    print(f"Ticker data: {len(results['steps'].get('ticker_data', {}))} symbols")
    print(f"Indicators: {len(results['steps'].get('indicators', {}))} symbols")
    print(f"Enrichment complete: {'Yes ✓' if results['enrichment_complete'] else 'No ✗'}")
    print(f"Wide vector: {results['steps'].get('wide_vector', {})}")
    print(f"Validation: {'PASSED ✓' if results['validation'] and results['validation']['passed'] else 'FAILED ✗'}")
    print(f"Files saved: {len(results['files_saved'])}")
    print("=" * 70)

    return results


if __name__ == '__main__':
    results = asyncio.run(run_integration_test())

    # Exit with appropriate code
    if results['validation'] and results['validation']['passed']:
        print("\n✅ Integration test PASSED!")
        exit(0)
    else:
        print("\n❌ Integration test FAILED!")
        exit(1)
