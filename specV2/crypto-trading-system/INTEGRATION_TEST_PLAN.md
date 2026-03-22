# ✅ Integration Test Plan - Implementation Status

## Overview

Integration test for complete data flow:
**Ticker Insert → DB Trigger → Indicators → Wide Vector → LLM**

---

## ✅ Step 1-2: Database Setup (COMPLETE)

### Migration Created
- **File**: `migrations/004_add_is_test_field.sql`
- **Status**: ✅ Executed successfully

### Changes
1. Added `is_test` BOOLEAN field to `symbols` table
2. Created index `idx_symbols_is_test`
3. Inserted 12 test symbols (ts1/USDC through ts12/USDC)

### Verification
```sql
SELECT symbol, is_test, is_active FROM symbols WHERE is_test = true;

 symbol   | is_test | is_active 
----------+---------+-----------
 ts1/USDC  | true    | true
 ts2/USDC  | true    | true
 ...
 ts12/USDC | true    | true
(12 rows)
```

---

## ✅ Step 3: Test Data Insertion Script (COMPLETE)

### Script Created
- **File**: `tests/integration/test_insert_ticker_data.py`
- **Status**: ✅ Created and tested

### Features
- Inserts ticker data for all 12 test symbols
- Configurable ticks per symbol (default: 3 for quick test, can be 20)
- 1-second pause between inserts (emulates !miniTicker@arr)
- Predictable price patterns per symbol:
  - `ts1`: Linear up (+1% per tick)
  - `ts2`: Linear down (-0.5% per tick)
  - `ts3`: Sine wave oscillation
  - `ts4`: Random walk
  - `ts5`: Flat (constant)
  - etc.

### Usage
```bash
# Quick test (3 ticks per symbol, ~36 seconds)
python tests/integration/test_insert_ticker_data.py

# Full test (edit NUM_TICKS = 20, ~4 minutes)
```

---

## ⚠️ Step 4: Indicator Verification (PARTIAL)

### DB Trigger Status
- **Trigger**: `calculate_indicators_trigger` ✅ Created
- **Function**: `calculate_indicators_on_insert()` ✅ Created

### Issue
The trigger function references columns that don't exist in the actual schema. Needs to be updated to match `ticker_24hr_stats` table structure.

### Fix Required
Update `migrations/003_indicator_calculation_trigger.sql` to use correct column names:
- `ts.last_price` instead of `ts.time` in subquery
- Match actual table columns

---

## ⏳ Step 5-6: Wide Vector Generation & Validation (PENDING)

### Script to Create
- **File**: `tests/integration/test_wide_vector_integration.py`
- **Purpose**: Generate wide vector from test data and validate

### Expected Output
```json
{
  "timestamp": "2026-03-21T20:00:00Z",
  "symbols_count": 12,
  "vector_size": 168,  // 12 symbols × 14 features
  "vector": [ts1_price, ts1_open, ..., ts12_indicators],
  "validation": {
    "ts1_price_expected": 103.0,  // After 3 ticks of +1%
    "ts1_price_actual": 103.0,
    "match": true
  }
}
```

---

## 📋 Remaining Tasks

### High Priority

1. **Fix DB Trigger** (30 min)
   - Update column names in `calculate_indicators_on_insert()`
   - Test trigger fires correctly
   - Verify indicators are stored

2. **Create Wide Vector Script** (1 hour)
   - Generate vector from test symbols
   - Validate against expected values
   - Save to file with metadata

3. **Run Full Integration Test** (1 hour)
   - Insert 20 ticks per symbol
   - Verify all indicators calculated
   - Generate and validate wide vector

### Medium Priority

4. **Automated Test Suite** (2 hours)
   - pytest integration tests
   - CI/CD pipeline integration
   - Performance benchmarks

---

## 🎯 Test Data Patterns

### Expected Prices After 20 Ticks

| Symbol | Base | Pattern | Tick 0 | Tick 20 | Change |
|--------|------|---------|--------|---------|--------|
| ts1 | 100 | linear_up | 100.0 | 120.0 | +20% |
| ts2 | 50 | linear_down | 50.0 | 45.0 | -10% |
| ts3 | 200 | sine_wave | 200.0 | ~200.0 | ~0% |
| ts4 | 75 | random_walk | 75.0 | ~75.0 | ±2% |
| ts5 | 150 | flat | 150.0 | 150.0 | 0% |

### Expected Indicators

For ts1 (linear up trend):
- **RSI**: Should be > 70 (overbought)
- **SMA_20**: Should be below current price (uptrend)
- **MACD**: Should be positive (bullish)

---

## 📁 Files Created

| File | Purpose | Status |
|------|---------|--------|
| `migrations/004_add_is_test_field.sql` | Add test symbols | ✅ Complete |
| `tests/integration/test_insert_ticker_data.py` | Insert test data | ✅ Complete |
| `tests/integration/test_wide_vector_integration.py` | Generate & validate | ⏳ TODO |

---

## 🚀 Next Steps

1. **Fix trigger function** to match actual schema
2. **Test trigger** fires on insert
3. **Create wide vector generator** for test data
4. **Validate** generated vector against expected values
5. **Document** results

---

**Last Updated**: March 21, 2026
**Status**: 50% Complete (Steps 1-3 done, 4-7 in progress)
