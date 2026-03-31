# Dangerous Integration Test

## ⚠️ WARNING: DESTRUCTIVE TEST

This test will **DELETE ALL TRADING DATA** from the database. Only run this test manually when you want to verify the complete pipeline from scratch.

## What It Does

1. **Stops** any running pipeline processes
2. **Deletes** ALL data from:
   - `wide_vectors`
   - `candle_indicators`
   - `candles_1s`
   - `trades`
3. **Starts** the pipeline for 10 minutes
4. **Verifies** that data is written correctly:
   - Candles for each active symbol and each second
   - Indicators for each active symbol and each second
   - Wide vectors for each second

## How to Run

```bash
# Navigate to project directory
cd /home/andy/projects/numbers/numbersML

# Run the test (will ask for confirmation)
python tests/integration/test_dangerous_pipeline.py
```

## Confirmation Required

The test will prompt you to type `DELETE ALL DATA` to confirm. This is intentional to prevent accidental data loss.

## Expected Output

```
========================================================================
DANGEROUS INTEGRATION TEST RESULTS
========================================================================

--- CANDLES_1S ---
Symbol ID 58: ✓ PASS
  Total: 3600, Distinct seconds: 3600/3600
  Gaps: 0
  Range: 2026-03-31 07:37:46 to 2026-03-31 07:47:45
...

--- CANDLE_INDICATORS ---
Symbol ID 58: ✓ PASS
  Total: 3600, Distinct seconds: 3600/3600
  Gaps: 0
...

--- WIDE_VECTORS ---
Status: ✓ PASS
Total: 3600, Distinct seconds: 3600/3600
Gaps: 0
...

========================================================================
OVERALL: ✓ ALL TESTS PASSED
========================================================================
```

## Troubleshooting

### Test Fails with "Pipeline failed to start"
- Check that PostgreSQL is running
- Check that Binance API is accessible
- Check pipeline logs in `/tmp/pipeline.log`

### Test Shows Gaps in Data
- Network issues during data collection
- Binance API rate limiting
- Pipeline process crashed during test

### Test Shows Missing Seconds
- WebSocket disconnections
- Recovery mechanism not working properly
- Database write failures
