"""
DANGEROUS Integration Test - FOR MANUAL RUN ONLY!

This test will:
1. Stop the pipeline
2. Delete ALL ticks and candles from the database
3. Start the pipeline for 10 minutes
4. Verify that all data is written correctly:
   - candles_1s for each active symbol and each second
   - indicators for each active symbol and each second
   - wide_vectors for each second

WARNING: This test is DESTRUCTIVE and will delete all trading data!
Only run this test manually with explicit confirmation.
"""

import asyncio
import asyncpg
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Database configuration
DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

# Test duration in seconds
TEST_DURATION = 600  # 10 minutes

# Warmup period: wait for recovery + indicator warmup before verifying
# Recovery of ~400K trades takes ~2-3 min, indicators need 50 candles (~50s)
WARMUP_DURATION = 180  # 3 minutes warmup


class DangerousIntegrationTest:
    """Dangerous integration test for the trading pipeline."""

    def __init__(self):
        self.db_pool = None
        self.active_symbols = []
        self.pipeline_process = None

    async def setup(self):
        """Setup database connection."""
        async def _set_utc(conn):
            await conn.execute("SET timezone = 'UTC'")
        
        self.db_pool = await asyncpg.create_pool(DB_URL, min_size=5, max_size=20, init=_set_utc)
        logger.info("Database connection established")

    async def teardown(self):
        """Cleanup database connection."""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Database connection closed")

    async def get_active_symbols(self) -> List[Dict]:
        """Get all active symbols from the database."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, symbol, is_active
                FROM symbols
                WHERE is_active = true
                ORDER BY symbol
                """
            )
            return [dict(row) for row in rows]

    async def stop_pipeline(self):
        """Stop any running pipeline processes."""
        logger.info("Stopping pipeline processes...")
        
        # Kill any existing pipeline processes
        try:
            subprocess.run(
                ["pkill", "-f", "start_trade_pipeline"],
                capture_output=True,
                timeout=10
            )
            subprocess.run(
                ["pkill", "-f", "uvicorn"],
                capture_output=True,
                timeout=10
            )
            await asyncio.sleep(2)
            logger.info("Pipeline processes stopped")
        except Exception as e:
            logger.warning(f"Error stopping pipeline: {e}")

    async def delete_all_data(self):
        """Delete ALL ticks and candles from the database."""
        logger.warning("DELETING ALL TICKS AND CANDLES FROM DATABASE!")
        
        async with self.db_pool.acquire() as conn:
            # Delete in order to respect foreign keys
            tables_to_clear = [
                "wide_vectors",
                "candle_indicators",
                "candles_1s",
                "trades",
                "pipeline_state",  # Also clear pipeline state to reset recovery
            ]
            
            for table in tables_to_clear:
                try:
                    result = await conn.execute(f"DELETE FROM {table}")
                    count = int(result.split()[-1])
                    logger.info(f"Deleted {count} rows from {table}")
                except Exception as e:
                    logger.warning(f"Could not delete from {table}: {e}")
            
            # Reset processed flag on symbols (if exists)
            try:
                await conn.execute("UPDATE symbols SET is_active = true WHERE symbol IN ('BTC/USDC', 'ETH/USDC', 'ADA/USDC', 'DOGE/USDC')")
                logger.info("Reset symbol flags")
            except:
                pass
            
            logger.warning("All trading data deleted!")

    async def start_pipeline(self):
        """Start the pipeline process."""
        logger.info("Starting pipeline...")
        
        # Start pipeline in background and capture output
        import os
        log_file = open('/tmp/pipeline_test.log', 'w')
        self.pipeline_process = subprocess.Popen(
            [".venv/bin/python", "-m", "src.cli.start_trade_pipeline"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd="/home/andy/projects/numbers/numbersML"
        )
        self._log_file = log_file
        
        # Wait for pipeline to initialize
        await asyncio.sleep(10)
        
        # Check if process is still running
        if self.pipeline_process.poll() is not None:
            logger.error("Pipeline failed to start")
            raise RuntimeError("Pipeline failed to start")
        
        logger.info("Pipeline started successfully")

    async def stop_pipeline_process(self):
        """Stop the pipeline process."""
        if self.pipeline_process:
            logger.info("Stopping pipeline process...")
            self.pipeline_process.terminate()
            try:
                self.pipeline_process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.pipeline_process.kill()
            
            # Close log file
            if hasattr(self, '_log_file') and self._log_file:
                self._log_file.close()
            
            logger.info("Pipeline process stopped")

    async def wait_for_data_collection(self, duration: int):
        """Wait for data collection to complete."""
        logger.info(f"Waiting {duration} seconds for data collection...")
        
        start_time = time.time()
        while time.time() - start_time < duration:
            elapsed = int(time.time() - start_time)
            remaining = duration - elapsed
            
            # Print progress every 30 seconds
            if elapsed % 30 == 0:
                logger.info(f"Progress: {elapsed}/{duration} seconds ({remaining} remaining)")
            
            await asyncio.sleep(1)
        
        logger.info("Data collection complete")

    async def verify_candles(self, symbol_ids: List[int], start_time: datetime, end_time: datetime) -> Dict:
        """Verify that candles_1s are written for each symbol and each second."""
        logger.info("Verifying candles_1s...")
        
        results = {}
        expected_seconds = int((end_time - start_time).total_seconds())
        
        async with self.db_pool.acquire() as conn:
            for symbol_id in symbol_ids:
                # Get candle count for this symbol
                row = await conn.fetchrow(
                    """
                    SELECT 
                        COUNT(*) as total,
                        COUNT(DISTINCT EXTRACT(EPOCH FROM time)::integer) as distinct_seconds,
                        MIN(time) as earliest,
                        MAX(time) as latest
                    FROM candles_1s
                    WHERE symbol_id = $1 AND time >= $2 AND time < $3
                    """,
                    symbol_id, start_time, end_time
                )
                
                total = row['total']
                distinct_seconds = row['distinct_seconds']
                earliest = row['earliest']
                latest = row['latest']
                
                # Calculate expected range
                if earliest and latest:
                    actual_seconds = int((latest - earliest).total_seconds()) + 1
                else:
                    actual_seconds = 0
                
                # Check for gaps
                gap_count = 0
                if distinct_seconds > 0:
                    gap_row = await conn.fetchrow(
                        """
                        WITH time_diffs AS (
                            SELECT 
                                time,
                                EXTRACT(EPOCH FROM time - LAG(time) OVER (ORDER BY time)) as gap
                            FROM candles_1s
                            WHERE symbol_id = $1 AND time >= $2 AND time < $3
                        )
                        SELECT COUNT(*) as gap_count
                        FROM time_diffs
                        WHERE gap > 1.5
                        """,
                        symbol_id, start_time, end_time
                    )
                    gap_count = gap_row['gap_count']
                
                results[symbol_id] = {
                    'total': total,
                    'distinct_seconds': distinct_seconds,
                    'expected_seconds': expected_seconds,
                    'actual_seconds': actual_seconds,
                    'gap_count': gap_count,
                    'earliest': earliest,
                    'latest': latest,
                    'passed': distinct_seconds >= expected_seconds * 0.95
                }
        
        return results

    async def verify_indicators(self, symbol_ids: List[int], start_time: datetime, end_time: datetime) -> Dict:
        """Verify that indicators are written for each symbol and each second."""
        logger.info("Verifying candle_indicators...")
        
        results = {}
        expected_seconds = int((end_time - start_time).total_seconds())
        
        async with self.db_pool.acquire() as conn:
            for symbol_id in symbol_ids:
                # Get indicator count for this symbol
                row = await conn.fetchrow(
                    """
                    SELECT 
                        COUNT(*) as total,
                        COUNT(DISTINCT EXTRACT(EPOCH FROM time)::integer) as distinct_seconds,
                        MIN(time) as earliest,
                        MAX(time) as latest
                    FROM candle_indicators
                    WHERE symbol_id = $1 AND time >= $2 AND time < $3
                    """,
                    symbol_id, start_time, end_time
                )
                
                total = row['total']
                distinct_seconds = row['distinct_seconds']
                earliest = row['earliest']
                latest = row['latest']
                
                # Check for gaps
                gap_count = 0
                if distinct_seconds > 0:
                    gap_row = await conn.fetchrow(
                        """
                        WITH time_diffs AS (
                            SELECT 
                                time,
                                EXTRACT(EPOCH FROM time - LAG(time) OVER (ORDER BY time)) as gap
                            FROM candle_indicators
                            WHERE symbol_id = $1 AND time >= $2 AND time < $3
                        )
                        SELECT COUNT(*) as gap_count
                        FROM time_diffs
                        WHERE gap > 1.5
                        """,
                        symbol_id, start_time, end_time
                    )
                    gap_count = gap_row['gap_count']
                
                results[symbol_id] = {
                    'total': total,
                    'distinct_seconds': distinct_seconds,
                    'expected_seconds': expected_seconds,
                    'gap_count': gap_count,
                    'earliest': earliest,
                    'latest': latest,
                    'passed': distinct_seconds >= expected_seconds * 0.95 and gap_count == 0
                }
        
        return results

    async def verify_wide_vectors(self, start_time: datetime, end_time: datetime) -> Dict:
        """Verify that wide_vectors are written for each second."""
        logger.info("Verifying wide_vectors...")
        
        expected_seconds = int((end_time - start_time).total_seconds())
        
        async with self.db_pool.acquire() as conn:
            # Get vector count
            row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT EXTRACT(EPOCH FROM time)::integer) as distinct_seconds,
                    MIN(time) as earliest,
                    MAX(time) as latest
                FROM wide_vectors
                WHERE time >= $1 AND time < $2
                """,
                start_time, end_time
            )
            
            total = row['total']
            distinct_seconds = row['distinct_seconds']
            earliest = row['earliest']
            latest = row['latest']
            
            # Check for gaps
            gap_count = 0
            if distinct_seconds > 0:
                gap_row = await conn.fetchrow(
                    """
                    WITH time_diffs AS (
                        SELECT 
                            time,
                            EXTRACT(EPOCH FROM time - LAG(time) OVER (ORDER BY time)) as gap
                        FROM wide_vectors
                        WHERE time >= $1 AND time < $2
                    )
                    SELECT COUNT(*) as gap_count
                    FROM time_diffs
                    WHERE gap > 1.5
                    """,
                    start_time, end_time
                )
                gap_count = gap_row['gap_count']
            
            return {
                'total': total,
                'distinct_seconds': distinct_seconds,
                'expected_seconds': expected_seconds,
                'gap_count': gap_count,
                'earliest': earliest,
                'latest': latest,
                'passed': distinct_seconds >= expected_seconds * 0.95
            }

    def print_results(self, candle_results: Dict, indicator_results: Dict, vector_results: Dict):
        """Print test results."""
        print("\n" + "=" * 80)
        print("DANGEROUS INTEGRATION TEST RESULTS")
        print("=" * 80)
        
        # Candles
        print("\n--- CANDLES_1S ---")
        all_passed = True
        for symbol_id, result in candle_results.items():
            status = "✓ PASS" if result['passed'] else "✗ FAIL"
            print(f"Symbol ID {symbol_id}: {status}")
            print(f"  Total: {result['total']}, Distinct seconds: {result['distinct_seconds']}/{result['expected_seconds']}")
            print(f"  Gaps: {result['gap_count']}")
            if result['earliest']:
                print(f"  Range: {result['earliest']} to {result['latest']}")
            if not result['passed']:
                all_passed = False
        
        # Indicators
        print("\n--- CANDLE_INDICATORS ---")
        for symbol_id, result in indicator_results.items():
            status = "✓ PASS" if result['passed'] else "✗ FAIL"
            print(f"Symbol ID {symbol_id}: {status}")
            print(f"  Total: {result['total']}, Distinct seconds: {result['distinct_seconds']}/{result['expected_seconds']}")
            print(f"  Gaps: {result['gap_count']}")
            if result['earliest']:
                print(f"  Range: {result['earliest']} to {result['latest']}")
            if not result['passed']:
                all_passed = False
        
        # Wide vectors
        print("\n--- WIDE_VECTORS ---")
        status = "✓ PASS" if vector_results['passed'] else "✗ FAIL"
        print(f"Status: {status}")
        print(f"Total: {vector_results['total']}, Distinct seconds: {vector_results['distinct_seconds']}/{vector_results['expected_seconds']}")
        print(f"Gaps: {vector_results['gap_count']}")
        if vector_results['earliest']:
            print(f"Range: {vector_results['earliest']} to {vector_results['latest']}")
        if not vector_results['passed']:
            all_passed = False
        
        print("\n" + "=" * 80)
        if all_passed:
            print("OVERALL: ✓ ALL TESTS PASSED")
        else:
            print("OVERALL: ✗ SOME TESTS FAILED")
        print("=" * 80 + "\n")
        
        return all_passed

    async def run_test(self):
        """Run the dangerous integration test."""
        logger.warning("=" * 80)
        logger.warning("DANGEROUS INTEGRATION TEST - THIS WILL DELETE ALL TRADING DATA!")
        logger.warning("=" * 80)
        
        # Confirmation prompt
        print("\nWARNING: This test will DELETE ALL ticks and candles from the database!")
        print("This action is IRREVERSIBLE!")
        print("\nType 'DELETE ALL DATA' to confirm:")
        
        confirmation = input("> ")
        if confirmation != "DELETE ALL DATA":
            logger.info("Test cancelled by user")
            return False
        
        try:
            # Setup
            await self.setup()
            
            # Get active symbols
            self.active_symbols = await self.get_active_symbols()
            symbol_ids = [s['id'] for s in self.active_symbols]
            logger.info(f"Active symbols: {[s['symbol'] for s in self.active_symbols]}")
            
            # Stop pipeline
            await self.stop_pipeline()
            
            # Delete all data
            await self.delete_all_data()
            
            # Start pipeline
            await self.start_pipeline()
            
            # Warmup period: wait for recovery + indicator warmup
            logger.info(f"Warming up for {WARMUP_DURATION}s (recovery + indicator warmup)...")
            await self.wait_for_data_collection(WARMUP_DURATION)
            
            # Record verification start time (after warmup)
            start_time = datetime.now(timezone.utc)
            logger.info(f"Verification start time: {start_time}")
            
            # Wait for data collection (post-warmup)
            remaining = TEST_DURATION - WARMUP_DURATION
            logger.info(f"Collecting data for {remaining}s...")
            await self.wait_for_data_collection(remaining)
            
            # Record end time
            end_time = datetime.now(timezone.utc)
            logger.info(f"Verification end time: {end_time}")
            
            # Stop pipeline
            await self.stop_pipeline_process()
            
            # Wait a moment for any pending writes
            await asyncio.sleep(5)
            
            # Verify data
            candle_results = await self.verify_candles(symbol_ids, start_time, end_time)
            indicator_results = await self.verify_indicators(symbol_ids, start_time, end_time)
            vector_results = await self.verify_wide_vectors(start_time, end_time)
            
            # Print results
            all_passed = self.print_results(candle_results, indicator_results, vector_results)
            
            return all_passed
            
        except Exception as e:
            logger.error(f"Test failed with error: {e}")
            raise
        finally:
            # Cleanup
            await self.stop_pipeline_process()
            await self.teardown()


async def main():
    """Main entry point."""
    test = DangerousIntegrationTest()
    result = await test.run_test()
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    asyncio.run(main())
