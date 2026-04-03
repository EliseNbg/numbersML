# Plan: Pipeline Integration Test for Candle → Indicators → Wide_Vectors

## Context
Create a deterministic integration test that generates synthetic data through the full pipeline, tests indicators, and verifies wide_vector alignment.

## Test Structure
File: `tests/integration/test_pipeline_synthetic_data.py`

### Test Flow
1.  **Setup test symbols**: Insert `T01/USDC` and `T02/USDC` into symbols table
2.  **Generate synthetic candles**: 2 hours of 1-second candles with noised sine wave (period 15 minutes)
3.  **Insert into pipeline**: Run generated candles through `PipelineTick` processing
4.  **Wait for processing**: Allow pipeline to compute indicators and wide vectors
5.  **Verification checks**:
    4.1 Indicator values exist for all timestamps
    4.2 Wide vectors are created
    4.3 Perfect time alignment between candles, indicators, wide_vectors (exact time match)

### Key Requirements
- Tests use actual database (not mocks)
- All pipeline components run real code
- Timestamps are exact integers, all tables join with `=` operator on `time` column

### Test Dependencies
- Uses existing pipeline fixtures from `conftest.py`
- Reuses candle generation pattern from existing tests
- Follows async test conventions with pytest.mark.asyncio

## Files to create/modify
1.  New test file: `tests/integration/test_pipeline_synthetic_data.py`

## Implementation Steps
1.  Create test with setup fixtures
2.  Implement sine wave candle generator
3.  Implement pipeline tick injection
4.  Implement verification queries for time alignment
5.  Add assertions for required invariants

## Verification Criteria
✅ T01/USDC and T02/USDC created
✅ 7200 candles inserted (2 hours × 2 symbols)
✅ All 7 indicators calculated for every timestamp
✅ Wide vector present for every timestamp
✅ All timestamps match exactly across tables
✅ No NULL values in generated data
