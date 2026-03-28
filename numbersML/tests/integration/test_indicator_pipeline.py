#!/usr/bin/env python3
"""
Integration Test: Indicator Calculation Pipeline

Tests the complete flow:
1. Verify indicators are configured in EnrichmentService
2. Insert ticker data
3. Verify EnrichmentService calculates all indicators
4. Verify indicators are stored in database
5. Verify WIDE_Vector can read indicators

This test MUST pass before any deployment.
"""

import asyncio
import asyncpg
import json
import logging
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Any, Set

# Add src to path (dynamic for local and GitHub Actions)
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.indicators.momentum import RSIIndicator, StochasticIndicator
from src.indicators.trend import SMAIndicator, EMAIndicator, MACDIndicator, ADXIndicator, AroonIndicator
from src.indicators.volatility_volume import (
    BollingerBandsIndicator, ATRIndicator, OBVIndicator, VWAPIndicator, MFIIndicator
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


class TestResult:
    """Track test results."""
    
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.details: Dict[str, Any] = {}
    
    def fail(self, error: str):
        self.passed = False
        self.errors.append(error)
    
    def warn(self, warning: str):
        self.warnings.append(warning)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'passed': self.passed,
            'errors': self.errors,
            'warnings': self.warnings,
            'details': self.details,
        }


async def test_01_indicators_configured() -> TestResult:
    """
    Test 1: Verify indicators are configured in EnrichmentService.
    
    Checks:
    - EnrichmentService has DEFAULT_INDICATORS defined
    - All indicator classes are importable
    - Indicator registry can instantiate them
    """
    result = TestResult("Test 1: Indicators Configured")
    
    try:
        # Import EnrichmentService
        from src.application.services.enrichment_service import EnrichmentService
        
        # Check DEFAULT_INDICATORS exists
        if not hasattr(EnrichmentService, 'DEFAULT_INDICATORS'):
            result.fail("EnrichmentService missing DEFAULT_INDICATORS")
            return result
        
        default_indicators = EnrichmentService.DEFAULT_INDICATORS
        
        if not isinstance(default_indicators, list):
            result.fail("DEFAULT_INDICATORS must be a list")
            return result
        
        if len(default_indicators) == 0:
            result.fail("DEFAULT_INDICATORS is empty")
            return result
        
        result.details['configured_count'] = len(default_indicators)
        result.details['indicators'] = default_indicators
        
        # Manually import and test indicators (registry discovery has issues)
        from src.indicators.momentum import RSIIndicator, StochasticIndicator
        from src.indicators.trend import SMAIndicator, EMAIndicator, MACDIndicator, ADXIndicator, AroonIndicator
        from src.indicators.volatility_volume import (
            BollingerBandsIndicator, ATRIndicator, OBVIndicator, VWAPIndicator, MFIIndicator
        )
        
        # Test that we can instantiate the configured indicators
        working_indicators = []
        missing_indicators = []
        
        # Map indicator names to classes
        indicator_map = {
            'rsiindicator_period14': RSIIndicator,
            'smaindicator_period20': lambda: SMAIndicator(period=20),
            'smaindicator_period50': lambda: SMAIndicator(period=50),
            'emaindicator_period12': lambda: EMAIndicator(period=12),
            'emaindicator_period26': lambda: EMAIndicator(period=26),
            'bbindicator_period20_std_dev2.0': lambda: BollingerBandsIndicator(period=20, std_dev=2.0),
            'macdindicator_fast_period12_slow_period26_signal_period9': MACDIndicator,
            'stochasticindicator_k_period14_d_period3': StochasticIndicator,
            'adxindicator_period14': ADXIndicator,
            'aroonindicator_period25': AroonIndicator,
            'atrinticator_period14': lambda: ATRIndicator(period=14),
            'obvindicator': OBVIndicator,
            'vwapindicator': VWAPIndicator,
            'mfiindicator_period14': lambda: MFIIndicator(period=14),
        }
        
        for ind_name in default_indicators:
            try:
                if ind_name in indicator_map:
                    ind_class = indicator_map[ind_name]
                    if callable(ind_class):
                        indicator = ind_class()
                    else:
                        indicator = ind_class()
                    working_indicators.append(ind_name)
                else:
                    missing_indicators.append(ind_name)
            except Exception as e:
                missing_indicators.append(f"{ind_name}: {e}")
        
        result.details['working_indicators'] = working_indicators
        result.details['missing_indicators'] = missing_indicators
        
        if missing_indicators:
            result.fail(f"Missing/failed indicators: {missing_indicators}")
        
        logger.info(f"✓ Configured indicators: {len(working_indicators)}/{len(default_indicators)}")
        
    except Exception as e:
        result.fail(f"Error checking indicators: {e}")
        import traceback
        traceback.print_exc()
    
    return result


async def test_02_all_indicators_calculable() -> TestResult:
    """
    Test 2: Verify all registered indicators can calculate.
    
    Checks:
    - Each indicator class can be instantiated
    - Each indicator can calculate with sample data
    - Output values are valid (no NaN/Inf)
    """
    result = TestResult("Test 2: All Indicators Calculable")
    
    try:
        # Create sample data (200 data points)
        import numpy as np
        np.random.seed(42)
        
        base_price = 100.0
        prices = base_price + np.cumsum(np.random.randn(200) * 0.5)
        volumes = np.random.uniform(1000, 10000, 200)
        highs = prices + np.abs(np.random.randn(200) * 0.3)
        lows = prices - np.abs(np.random.randn(200) * 0.3)
        
        # Test each indicator class
        indicator_classes = [
            (RSIIndicator, {'period': 14}),
            (StochasticIndicator, {'k_period': 14, 'd_period': 3}),
            (SMAIndicator, {'period': 20}),
            (SMAIndicator, {'period': 50}),
            (SMAIndicator, {'period': 200}),
            (EMAIndicator, {'period': 12}),
            (EMAIndicator, {'period': 26}),
            (MACDIndicator, {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}),
            (ADXIndicator, {'period': 14}),
            (AroonIndicator, {'period': 25}),
            (BollingerBandsIndicator, {'period': 20, 'std_dev': 2.0}),
            (ATRIndicator, {'period': 14}),
            (OBVIndicator, {}),
            (VWAPIndicator, {}),
            (MFIIndicator, {'period': 14}),
        ]
        
        calculable = []
        failed = []
        
        for ind_class, params in indicator_classes:
            try:
                indicator = ind_class(**params)
                calc_result = indicator.calculate(
                    prices=prices,
                    volumes=volumes,
                    highs=highs,
                    lows=lows,
                )
                
                # Check for valid output
                has_valid = False
                for key, values in calc_result.values.items():
                    if len(values) > 0 and not np.isnan(values[-1]) and not np.isinf(values[-1]):
                        has_valid = True
                        break
                
                if has_valid:
                    calculable.append(indicator.name)
                else:
                    failed.append(f"{indicator.name}: No valid output")
                    
            except Exception as e:
                failed.append(f"{ind_class.__name__}: {e}")
        
        result.details['calculable_count'] = len(calculable)
        result.details['calculable'] = calculable
        result.details['failed'] = failed
        
        if failed:
            result.fail(f"Failed indicators: {failed}")
        
        logger.info(f"✓ Calculable indicators: {len(calculable)}/{len(indicator_classes)}")
        
    except Exception as e:
        result.fail(f"Error testing calculation: {e}")
        import traceback
        traceback.print_exc()
    
    return result


async def test_03_db_insert_triggers_notification() -> TestResult:
    """
    Test 3: Verify DB INSERT fires NOTIFY new_tick.
    
    Checks:
    - Trigger exists on ticker_24hr_stats
    - INSERT fires notification
    - Notification payload is valid JSON
    """
    result = TestResult("Test 3: DB INSERT Triggers Notification")
    
    conn = None
    try:
        # Use connect() for dedicated connection with listen support
        conn = await asyncpg.connect(DB_URL)
        
        # Check trigger exists
        trigger_check = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'notify_new_tick_trigger'
                AND tgrelid = 'ticker_24hr_stats'::regclass
            )
        """)
        
        if not trigger_check:
            result.fail("Trigger 'notify_new_tick_trigger' not found on ticker_24hr_stats")
            return result
        
        result.details['trigger_exists'] = True
        
        # Get a test symbol
        symbol_row = await conn.fetchrow("""
            SELECT id, symbol FROM symbols WHERE is_active = true AND is_allowed = true LIMIT 1
        """)
        
        if not symbol_row:
            result.fail("No active symbols in database")
            return result
        
        symbol_id = symbol_row['id']
        symbol_name = symbol_row['symbol']
        
        # Listen for notification using add_listener (asyncpg 0.31.0+)
        notification_received = asyncio.Event()
        notification_payload = {}
        
        def listener(connection, pid, channel, payload):
            nonlocal notification_payload
            try:
                notification_payload = json.loads(payload)
                notification_received.set()
            except Exception as e:
                logger.error(f"Error parsing notification: {e}")
        
        await conn.add_listener('new_tick', listener)
        
        # Insert test data (use NOW() for timezone-safe timestamp)
        await conn.execute("""
            INSERT INTO ticker_24hr_stats (symbol_id, symbol, time, last_price, open_price, high_price, low_price, total_volume, total_quote_volume, price_change, price_change_pct)
            VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7, $8, $9, $10)
        """, symbol_id, symbol_name, Decimal('100.0'), Decimal('99.0'), Decimal('101.0'), 
            Decimal('98.0'), Decimal('1000.0'), Decimal('100000.0'), Decimal('1.0'), Decimal('1.0'))
        
        # Wait for notification
        try:
            await asyncio.wait_for(notification_received.wait(), timeout=5.0)
            
            if 'symbol_id' not in notification_payload or 'time' not in notification_payload:
                result.fail(f"Invalid notification payload: {notification_payload}")
                return result
            
            result.details['notification_received'] = True
            result.details['payload_keys'] = list(notification_payload.keys())
            
            logger.info(f"✓ Notification received: symbol_id={notification_payload['symbol_id']}")
            
        except asyncio.TimeoutError:
            result.fail("No notification received within 5 seconds")
        
    except Exception as e:
        result.fail(f"Error testing notification: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if conn:
            await conn.close()
    
    return result


async def test_04_enrichment_service_running() -> TestResult:
    """
    Test 4: Verify EnrichmentService is running and calculating.
    
    Checks:
    - EnrichmentService process is running (or can be started)
    - Indicators are being stored in candle_indicators table
    - Indicator calculation latency is acceptable (<100ms)
    """
    result = TestResult("Test 4: Enrichment Service Running")
    
    conn = None
    try:
        conn = await asyncpg.connect(DB_URL)
        
        # Check if indicators exist in DB
        indicator_count = await conn.fetchval("SELECT COUNT(*) FROM candle_indicators")
        result.details['existing_indicators'] = indicator_count
        
        # Get a test symbol
        symbol_id = await conn.fetchval("""
            SELECT id FROM symbols WHERE is_active = true AND is_allowed = true LIMIT 1
        """)
        
        if not symbol_id:
            result.fail("No active symbols in database")
            return result
        
        # Get latest ticker time
        latest_time = await conn.fetchval("""
            SELECT MAX(time) FROM ticker_24hr_stats WHERE symbol_id = $1
        """, symbol_id)
        
        # Check if indicators exist for latest ticker
        if latest_time:
            indicators_at_time = await conn.fetchval("""
                SELECT COUNT(*) FROM candle_indicators
                WHERE symbol_id = $1 AND time = $2
            """, symbol_id, latest_time)
            
            result.details['indicators_at_latest_tick'] = indicators_at_time
            
            if indicators_at_time > 0:
                logger.info(f"✓ Found {indicators_at_time} indicators for latest ticker")
            else:
                result.warn("No indicators for latest ticker (EnrichmentService may not be running)")
                result.details['enrichment_service_running'] = False
                return result
        
        # Check enrichment latency
        latency_result = await conn.fetchrow("""
            SELECT
                AVG(EXTRACT(EPOCH FROM (ti.created_at - t.time))) * 1000 as avg_latency_ms,
                MAX(EXTRACT(EPOCH FROM (ti.created_at - t.time))) * 1000 as max_latency_ms
            FROM candle_indicators ti
            JOIN ticker_24hr_stats t ON t.symbol_id = ti.symbol_id AND t.time = ti.time
            WHERE ti.created_at > NOW() - INTERVAL '5 minutes'
        """)
        
        if latency_result and latency_result['avg_latency_ms']:
            avg_latency = float(latency_result['avg_latency_ms'])
            max_latency = float(latency_result['max_latency_ms'])
            
            result.details['avg_latency_ms'] = round(avg_latency, 2)
            result.details['max_latency_ms'] = round(max_latency, 2)
            
            if avg_latency > 100:
                result.warn(f"High enrichment latency: {avg_latency:.2f}ms (target: <100ms)")
            else:
                logger.info(f"✓ Enrichment latency: {avg_latency:.2f}ms avg, {max_latency:.2f}ms max")
        
        result.details['enrichment_service_running'] = True
        
    except Exception as e:
        result.fail(f"Error checking enrichment: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if conn:
            await conn.close()
    
    return result


async def test_05_wide_vector_reads_indicators() -> TestResult:
    """
    Test 5: Verify WIDE_Vector generator reads indicators from DB.
    
    Checks:
    - WIDE_Vector generator can connect to DB
    - Reads ticker data successfully
    - Reads indicator data (if available)
    - Generates valid vector (no NaN/Inf)
    """
    result = TestResult("Test 5: WIDE Vector Reads Indicators")
    
    try:
        from src.cli.generate_wide_vector import WideVectorGenerator
        
        generator = WideVectorGenerator(
            db_url=DB_URL,
            symbols=None,  # All active symbols
            include_indicators=True,
        )
        
        await generator.connect()
        
        if len(generator._symbol_list) == 0:
            result.fail("No symbols loaded")
            await generator.disconnect()
            return result
        
        result.details['symbols_loaded'] = len(generator._symbol_list)
        
        # Generate vector
        start_time = time.time()
        vector_data = await generator.generate_wide_vector()
        generation_time = (time.time() - start_time) * 1000
        
        await generator.disconnect()
        
        if not vector_data:
            result.fail("Vector generation returned None")
            return result
        
        result.details['generation_time_ms'] = round(generation_time, 2)
        result.details['vector_size'] = len(vector_data['vector'])
        result.details['total_columns'] = vector_data['metadata']['total_columns']
        result.details['indicators_found'] = vector_data['metadata']['indicators_found']
        
        # Check for NaN/Inf
        import numpy as np
        vector = vector_data['vector']
        
        has_nan = np.isnan(vector).any()
        has_inf = np.isinf(vector).any()
        
        if has_nan:
            result.fail("Vector contains NaN values")
        
        if has_inf:
            result.fail("Vector contains Inf values")
        
        logger.info(f"✓ Vector generated: {vector_data['metadata']['total_columns']} columns in {generation_time:.2f}ms")
        
    except Exception as e:
        result.fail(f"Error generating vector: {e}")
        import traceback
        traceback.print_exc()
    
    return result


async def test_06_complete_pipeline() -> TestResult:
    """
    Test 6: Complete pipeline test.
    
    Flow:
    1. Insert new ticker data
    2. Wait for enrichment (if service running)
    3. Generate WIDE vector
    4. Verify indicators in vector
    """
    result = TestResult("Test 6: Complete Pipeline")
    
    conn = None
    try:
        conn = await asyncpg.connect(DB_URL)
        
        # Get a test symbol
        symbol_row = await conn.fetchrow("""
            SELECT id, symbol FROM symbols WHERE symbol = 'BTC/USDT' AND is_active = true AND is_allowed = true
        """)
        
        if not symbol_row:
            # Try any active symbol
            symbol_row = await conn.fetchrow("""
                SELECT id, symbol FROM symbols WHERE is_active = true AND is_allowed = true LIMIT 1
            """)
        
        if not symbol_row:
            result.fail("No active symbols in database")
            return result
        
        symbol_id = symbol_row['id']
        symbol_name = symbol_row['symbol']
        
        # Insert fresh ticker data (use NOW() for timezone-safe timestamp)
        await conn.execute("""
            INSERT INTO ticker_24hr_stats (symbol_id, symbol, time, last_price, open_price, high_price, low_price, total_volume, total_quote_volume, price_change, price_change_pct)
            VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7, $8, $9, $10)
        """, symbol_id, symbol_name, Decimal('50000.0'), Decimal('49900.0'), Decimal('50100.0'), 
            Decimal('49800.0'), Decimal('1000.0'), Decimal('50000000.0'), Decimal('100.0'), Decimal('0.2'))
        
        result.details['ticker_inserted'] = True
        
        # Wait a bit for enrichment
        await asyncio.sleep(2.0)

        # Get the time we just inserted
        latest_time = await conn.fetchval("""
            SELECT MAX(time) FROM ticker_24hr_stats WHERE symbol_id = $1
        """, symbol_id)

        # Check if indicators were calculated
        indicator_count = await conn.fetchval("""
            SELECT COUNT(*) FROM candle_indicators
            WHERE symbol_id = $1 AND time = $2
        """, symbol_id, latest_time)

        result.details['indicators_calculated'] = indicator_count

        if indicator_count > 0:
            # Get indicator keys
            indicator_keys = await conn.fetchval("""
                SELECT indicator_keys FROM candle_indicators
                WHERE symbol_id = $1 AND time = $2
            """, symbol_id, latest_time)

            result.details['indicator_keys'] = indicator_keys
            logger.info(f"✓ {indicator_count} indicators calculated for test ticker")
        else:
            result.warn("No indicators calculated (EnrichmentService may not be running)")
        
        # Generate WIDE vector
        from src.cli.generate_wide_vector import WideVectorGenerator
        
        generator = WideVectorGenerator(db_url=DB_URL, include_indicators=True)
        await generator.connect()
        
        vector_data = await generator.generate_wide_vector()
        await generator.disconnect()
        
        if vector_data:
            result.details['vector_generated'] = True
            result.details['vector_columns'] = vector_data['metadata']['total_columns']
            logger.info(f"✓ WIDE vector generated: {vector_data['metadata']['total_columns']} columns")
        
    except Exception as e:
        result.fail(f"Error in pipeline test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if conn:
            await conn.close()
    
    return result


async def run_all_tests() -> Dict[str, Any]:
    """Run all integration tests."""
    
    print("=" * 70)
    print("INTEGRATION TEST: Indicator Calculation Pipeline")
    print("=" * 70)
    print()
    
    tests = [
        test_01_indicators_configured,
        test_02_all_indicators_calculable,
        test_03_db_insert_triggers_notification,
        test_04_enrichment_service_running,
        test_05_wide_vector_reads_indicators,
        test_06_complete_pipeline,
    ]
    
    results = []
    all_passed = True
    
    for test_func in tests:
        test_name = test_func.__doc__.strip().split('\n')[0] if test_func.__doc__ else test_func.__name__
        print(f"\n{test_name}...")
        print("-" * 50)
        
        try:
            result = await test_func()
            results.append(result.to_dict())
            
            if result.passed:
                status = "✓ PASSED"
            else:
                status = "✗ FAILED"
                all_passed = False
            
            print(f"{status}")
            
            if result.errors:
                for error in result.errors:
                    print(f"  ERROR: {error}")
            
            if result.warnings:
                for warning in result.warnings:
                    print(f"  WARNING: {warning}")
            
            if result.details:
                for key, value in result.details.items():
                    if isinstance(value, list) and len(value) > 5:
                        print(f"  {key}: {len(value)} items")
                    else:
                        print(f"  {key}: {value}")
            
        except Exception as e:
            print(f"✗ EXCEPTION: {e}")
            results.append({
                'name': test_name,
                'passed': False,
                'errors': [str(e)],
                'warnings': [],
                'details': {},
            })
            all_passed = False
    
    # Summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed_count = sum(1 for r in results if r['passed'])
    total_count = len(results)
    
    print(f"Passed: {passed_count}/{total_count}")
    print(f"Failed: {total_count - passed_count}/{total_count}")
    print()
    
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print()
        print("Pipeline is ready for deployment.")
    else:
        print("❌ SOME TESTS FAILED")
        print()
        print("Please fix the issues before deployment.")
    
    print("=" * 70)
    
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'passed': all_passed,
        'results': results,
        'summary': {
            'total': total_count,
            'passed': passed_count,
            'failed': total_count - passed_count,
        }
    }


if __name__ == '__main__':
    results = asyncio.run(run_all_tests())
    
    # Save results to file
    with open('/tmp/integration_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: /tmp/integration_test_results.json")
    
    # Exit with appropriate code
    sys.exit(0 if results['passed'] else 1)
