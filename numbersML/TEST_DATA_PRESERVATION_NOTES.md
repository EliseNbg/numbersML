# Test Data Preservation Notes

## Summary
On 2026-05-11, DELETE statements in integration test files were commented out to preserve TEST/USDT test data in the database for backtesting purposes.

## Changes Made

### 1. tests/integration/repositories/test_repositories.py
- Changed test symbol from "TEST/USDC" to "TEST/USDT" for consistency
- Commented out DELETE statement that removes TEST/USDT symbol after tests:
  ```python
  # Cleanup - COMMENTED OUT TO PRESERVE TEST/USDT DATA FOR BACKTESTING
  # async with db_pool.acquire() as conn:
  #     await conn.execute("DELETE FROM symbols WHERE symbol = 'TEST/USDT'")
  ```

### 2. tests/integration/test_recalculation_simple.py
- Commented out cleanup_existing_data function DELETE statements:
  ```python
  async def cleanup_existing_data(conn: asyncpg.Connection):
      """Clean up any existing test data."""
      symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

      if symbol_id:
          # COMMENTED OUT TO PRESERVE TEST/USDT DATA FOR BACKTESTING
          # await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
          # await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
  ```

### 3. tests/integration/test_recalculation_full.py
- Commented out cleanup_existing_data function DELETE statements:
  ```python
  async def cleanup_existing_data(conn: asyncpg.Connection):
      """Remove old TEST/USDT artifacts from previous runs."""
      symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

      if symbol_id:
          # Remove from candle_indicators first (foreign key dependency)
          # await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
          # # Remove from candles_1s
          # await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
  ```

### 4. tests/integration/test_recalculation_service.py
- Commented out DELETE statements in fixture setup/teardown:
  ```python
  async with db_pool.acquire() as conn:
      # Get symbol ID if it exists
      symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

      if symbol_id:
          # Clean up existing data - COMMENTED OUT TO PRESERVE TEST/USDT DATA FOR BACKTESTING
          # await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
          # await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)

  yield

  # Cleanup after test (data cleanup only, symbol disallowing handled by conftest)
  async with db_pool.acquire() as conn:
      symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

      if symbol_id:
          # COMMENTED OUT TO PRESERVE TEST/USDT DATA FOR BACKTESTING
          # await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
          # await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
  ```
- Commented out DELETE statements in test_deterministic_results:
  ```python
  # Clear and run again
  # await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
  ```
- Commented out DELETE statements in test_cleanup_procedures:
  ```python
  # Perform cleanup (simulating test cleanup)
  # await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
  # await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
  # await conn.execute(
  #     "UPDATE symbols SET is_active = false, is_allowed = false WHERE symbol = $1",
  #     TEST_SYMBOL,
  # )
  ```

### 5. tests/integration/test_recalculation_direct.py
- Commented out cleanup_existing_data function DELETE statements:
  ```python
  async def cleanup_existing_data(conn: asyncpg.Connection):
      """Clean up any existing test data."""
      symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", TEST_SYMBOL)

      if symbol_id:
          # COMMENTED OUT TO PRESERVE TEST/USDT DATA FOR BACKTESTING
          # await conn.execute("DELETE FROM candle_indicators WHERE symbol_id = $1", symbol_id)
          # await conn.execute("DELETE FROM candles_1s WHERE symbol_id = $1", symbol_id)
  ```

## How to Restore Original Behavior
To restore the original behavior (where test data is deleted after tests):

1. Uncomment the DELETE statements in the files listed above
2. Change any "TEST/USDT" references back to "TEST/USDC" if needed (in test_repositories.py)
3. Run the tests again - they will clean up test data after execution

## Data Availability
The following test data is now preserved in the database:
- Symbol: TEST/USDT (with base_asset=TEST, quote_asset=USDT)
- Synthetic candle data (5000 rows in candles_1s table)
- Calculated indicator data (in candle_indicators table)

This data can be used for backtesting strategies and validating trading algorithms.

## Environment
- Date: 2026-05-11
- Working Directory: /home/andy/projects/numbers/numbersML
- Git Repository: numbersML