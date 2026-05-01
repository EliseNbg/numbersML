# Performance Optimization Plan: `recalculate_indicators`

## Executive Summary

The `recalculate_indicators` function in `src/cli/recalculate.py` has several performance bottlenecks that limit throughput when processing large numbers of symbols and candles. This plan outlines specific optimizations to achieve **5-10x performance improvement**.

## Current Performance Characteristics

- **Concurrent symbol processing**: 8 symbols at a time (semaphore)
- **Batch inserts**: 5000 rows per batch
- **Pre-created indicators**: Indicator instances created once per run
- **Ring buffer**: Efficient numpy array storage via `IndicatorsBuffer`
- **Skip optimization**: Skips candles with existing indicators

### Measured Bottlenecks (from code analysis)

1. **~1000+ DB queries** for checking existing indicators (per chunk, per symbol)
2. **Per-symbol buffer initialization** queries (1 query per symbol)
3. **Per-candle indicator calculation** using full buffer (wasteful)
4. **Per-candle quality guard validation** (sync overhead)
5. **Multiple DB connection acquisitions** per symbol (~3-4 per chunk)

---

## Optimization Strategy

### Phase 1: Eliminate Redundant DB Queries (HIGH IMPACT - 3-5x improvement)

#### 1.1 Bulk Pre-fetch Existing Indicators

**Problem**: Lines 192-202 in `recalculate.py` query existing indicators per chunk:
```python
# CURRENT: Per chunk query (executed N times per symbol)
async with db_pool.acquire() as conn:
    existing_rows = await conn.fetch(
        "SELECT time FROM candle_indicators WHERE symbol_id = $1 AND time >= $2 AND time < $3",
        sid, chunk_start_time, chunk_end_time + timedelta(seconds=1)
    )
    existing_indicator_times = {row["time"] for row in existing_rows}
```

**Solution**: Pre-fetch ALL existing indicator times for all symbols in 1-2 queries:
```python
# OPTIMIZED: Bulk pre-fetch once at start
async def bulk_fetch_existing_indicators(db_pool, symbol_ids, from_time, to_time):
    """Fetch all existing indicator times in single query."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT symbol_id, time 
            FROM candle_indicators 
            WHERE symbol_id = ANY($1) 
              AND time >= $2 
              AND time < $3
            """,
            symbol_ids, from_time, to_time
        )
        # Structure: {symbol_id: {time1, time2, ...}}
        existing = {}
        for row in rows:
            sid = row["symbol_id"]
            if sid not in existing:
                existing[sid] = set()
            existing[sid].add(row["time"])
        return existing
```

**Impact**: 
- Eliminates O(symbols × chunks) queries
- Replaces with O(1) in-memory lookup
- **Expected improvement**: 10-50x fewer DB queries

---

#### 1.2 Bulk Pre-fetch Historical Candles

**Problem**: Each symbol's `IndicatorsBuffer.initialization()` performs separate DB query (line 161, 217)

**Solution**: Pre-fetch all candles needed for all symbols in one query:
```python
async def bulk_fetch_historical_candles(
    db_pool, symbol_ids, lookback_start, to_time
):
    """Fetch all candles for all symbols in single query."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT time, symbol_id, high, low, close, volume
            FROM candles_1s
            WHERE symbol_id = ANY($1)
              AND time >= $2 
              AND time < $3
            ORDER BY symbol_id, time ASC
            """,
            symbol_ids, lookback_start, to_time
        )
        # Structure: {symbol_id: [(time, high, low, close, volume), ...]}
        candles_by_symbol = {}
        for row in rows:
            sid = row["symbol_id"]
            if sid not in candles_by_symbol:
                candles_by_symbol[sid] = []
            candles_by_symbol[sid].append(row)
        return candles_by_symbol
```

**Impact**:
- Eliminates per-symbol initialization queries
- Enables memory-based buffer population
- **Expected improvement**: 2-5x fewer DB queries

---

### Phase 2: Vectorize Indicator Calculations (HIGH IMPACT - 2-5x improvement)

#### 2.1 Calculate Only Required Values

**Problem**: Lines 236-244 calculate indicators on entire buffer but only use `values[-1]`:
```python
# CURRENT: Calculates for entire buffer, uses only last value
closes_arr = np.asarray(buffer.closes_buff)  # Entire buffer
result = indicator.calculate(prices=closes_arr, ...)  # Calc all values
val = result.values[sub_key][-1]  # Use only LAST value
```

**Solution**: For recalculation, we only need the latest indicator value. Options:

**Option A**: Modify indicators to support `calculate_latest()` method:
```python
# In indicator base class
def calculate_latest(self, prices, volumes, highs, lows) -> float:
    """Calculate only the most recent indicator value."""
    full_result = self.calculate(prices, volumes, highs, lows)
    return {k: v[-1] for k, v in full_result.values.items()}
```

**Option B**: Use rolling window calculations more efficiently:
```python
# For indicators like SMA, EMA - calculate incrementally
# Instead of recalculating from scratch each time
```

**Impact**:
- Reduces computation by O(buffer_size) factor
- **Expected improvement**: 10-50x faster for long buffers

---

#### 2.2 Batch Indicator Calculation

**Problem**: Indicators calculated one-at-a-time per candle (inner loop lines 237-265)

**Solution**: For some indicators, calculate for multiple candles at once:
```python
# Pseudo-code for batch calculation
def calculate_indicators_batch(indicators, candles_by_symbol):
    """Calculate indicators for multiple candles at once."""
    results = {}
    for defn, indicator in indicators:
        # Get all candle data as 2D arrays
        all_closes = np.array([...])  # Shape: (n_candles, buffer_size)
        # Vectorized calculation where possible
        if hasattr(indicator, 'calculate_batch'):
            batch_results = indicator.calculate_batch(all_closes)
        else:
            # Fallback to loop
            for i in range(n_candles):
                result = indicator.calculate(all_closes[i])
                ...
    return results
```

**Impact**:
- Better CPU cache utilization
- Enables numpy vectorization
- **Expected improvement**: 2-10x for vectorizable indicators

---

### Phase 3: Optimize Data Structures (MEDIUM IMPACT - 1.5-3x improvement)

#### 3.1 Shared Indicator Instances Across Symbols

**Problem**: Indicator instances are created once (lines 114-119) but could be shared more efficiently.

**Current** (good):
```python
indicators = []
for defn in calc._definitions:
    cls = calc._get_indicator_class(defn["class_name"], defn["module_path"])
    if cls:
        indicator = cls(**defn["params"])
        indicators.append((defn, indicator))
```

**Optimization**: Cache at module level for true sharing:
```python
# In indicator_calculator.py or recalculate.py
_indicator_cache = {}

def get_cached_indicator(defn):
    """Get or create indicator with caching."""
    cache_key = f"{defn['module_path']}.{defn['class_name']}:{str(defn['params'])}"
    if cache_key not in _indicator_cache:
        cls = calc._get_indicator_class(defn["class_name"], defn["module_path"])
        _indicator_cache[cache_key] = cls(**defn["params"])
    return _indicator_cache[cache_key]
```

**Impact**:
- Reduces memory allocation
- Faster initialization
- **Expected improvement**: Minor (5-10%)

---

#### 3.2 Optimize Ring Buffer Usage

**Problem**: `np.asarray(buffer.closes_buff)` creates a view each time (line 230)

**Solution**: The `numpy_ringbuffer` RingBuffer should already return a numpy array. Verify and optimize:
```python
# Check if RingBuffer returns array directly
closes_arr = buffer.closes_buff  # May already be array-like
# If not, ensure it's a view, not a copy
```

**Impact**:
- Reduces memory allocation
- **Expected improvement**: Minor (5-15%)

---

### Phase 4: Batch Processing Optimization (MEDIUM IMPACT - 2-3x improvement)

#### 4.1 Batch Quality Guard Validation

**Problem**: Lines 269-284 validate quality per candle

**Solution**: Batch validate multiple candles:
```python
# Collect results and validate in batch
batch_for_validation = []
for row in rows:
    if results:
        batch_for_validation.append((t, results))

# After processing chunk, validate batch
if with_quality_guard and batch_for_validation:
    quality_issues = calc._quality_guard.validate_batch(batch_for_validation)
    # Filter out critical issues
```

**Impact**:
- Reduces per-candle overhead
- **Expected improvement**: 1.5-2x for quality guard

---

#### 4.2 Larger Batch Inserts with COPY

**Problem**: `store_indicator_results_batch` uses `executemany` (line 446 in indicator_repo.py)

**Solution**: Use PostgreSQL `COPY FROM` for maximum throughput:
```python
async def bulk_copy_indicators(conn, records):
    """Use COPY FROM for fast bulk insert."""
    import io
    output = io.StringIO()
    for time, symbol_id, price, volume, values in records:
        # Format for TSV
        output.write(f"{time}\t{symbol_id}\t{price}\t{volume}\t{json.dumps(values)}\n")
    output.seek(0)
    
    await conn.copy_from(
        output, 'candle_indicators',
        columns=('time', 'symbol_id', 'price', 'volume', 'values', 'indicator_version')
    )
```

**Impact**:
- 10-100x faster inserts
- **Expected improvement**: 2-5x for write-heavy workloads

---

### Phase 5: Connection Pool Optimization (LOW-MEDIUM IMPACT)

#### 5.1 Increase Pool Size

**Problem**: Default pool size may be too small for 8 concurrent symbols

**Solution**:
```python
# In main() or where pool is created
pool = await asyncpg.create_pool(
    DB_URL,
    min_size=10,  # Increased from 2
    max_size=20,  # Increased from 5
)
```

#### 5.2 Reduce Connection Acquisitions

**Problem**: Multiple `async with db_pool.acquire()` per symbol

**Solution**: Use single connection per symbol where possible:
```python
async def process_symbol(sid):
    # Acquire one connection for entire symbol processing
    async with db_pool.acquire() as conn:
        # Use `conn` for all queries in this symbol
        rows = await conn.fetch("SELECT ...")
        existing = await conn.fetch("SELECT ...")
        # ...
```

**Impact**:
- Reduces connection pool contention
- **Expected improvement**: 1.2-1.5x

---

## Implementation Roadmap

### Week 1: High-Impact Changes (Phase 1 + 2.1)
- [ ] Implement bulk pre-fetch for existing indicators
- [ ] Implement bulk pre-fetch for historical candles
- [ ] Modify indicator calculation to only compute latest value
- [ ] Add unit tests for new functions

### Week 2: Medium-Impact Changes (Phase 2.2 + 3 + 4)
- [ ] Implement batch indicator calculation where possible
- [ ] Add indicator instance caching
- [ ] Implement batch quality guard validation
- [ ] Optimize ring buffer usage

### Week 3: Fine-Tuning (Phase 4.2 + 5)
- [ ] Implement COPY FROM for bulk inserts
- [ ] Optimize connection pool usage
- [ ] Performance benchmarking and tuning

---

## Expected Performance Gains

| Optimization | Expected Improvement | Difficulty |
|--------------|---------------------|------------|
| Bulk pre-fetch existing indicators | 10-50x fewer queries | Medium |
| Bulk pre-fetch candles | 2-5x fewer queries | Medium |
| Calculate only latest indicator value | 10-50x faster calculation | High |
| Batch indicator calculation | 2-10x for some indicators | High |
| Batch quality validation | 1.5-2x | Low |
| COPY FROM for inserts | 10-100x faster inserts | Medium |
| Connection pool tuning | 1.2-1.5x | Low |

### Overall Expected Improvement: **5-20x faster** recalculation

---

## Testing Strategy

### Unit Tests
```python
# tests/unit/pipeline/test_recalculate_optimized.py

async def test_bulk_fetch_existing_indicators():
    """Test bulk pre-fetch returns correct structure."""
    
async def test_bulk_fetch_candles():
    """Test bulk candle fetch for multiple symbols."""
    
async def test_calculate_latest_only():
    """Test indicator calculates only latest value."""
```

### Integration Tests
```python
# tests/integration/test_recalculate_performance.py

@pytest.mark.integration
async def test_recalculate_performance_benchmark():
    """Benchmark optimized vs original implementation."""
    # Measure time for 100 symbols × 1000 candles
    # Compare before/after optimization
```

### Performance Benchmarking
```bash
# Before optimization
time python -m src.cli.recalculate --indicators --symbols "BTC/USDC" --from "..."

# After optimization  
time python -m src.cli.recalculate --indicators --symbols "BTC/USDC" --from "..."
```

---

## Risk Mitigation

1. **Backward Compatibility**: Maintain same function signature for `recalculate_indicators`
2. **Data Integrity**: Compare indicator values before/after optimization
3. **Gradual Rollout**: Use feature flags to enable optimizations incrementally
4. **Monitoring**: Add timing logs to measure each optimization's impact

---

## Code Changes Summary

### Files to Modify:
1. `src/cli/recalculate.py` - Main optimization implementation
2. `src/pipeline/indicator_calculator.py` - Add `calculate_latest()` method
3. `src/indicators/base.py` - Add batch calculation support
4. `src/infrastructure/repositories/indicator_repo.py` - Add COPY FROM support

### New Files:
1. `tests/unit/pipeline/test_recalculate_optimized.py` - Unit tests
2. `tests/integration/test_recalculate_performance.py` - Performance tests
3. `benchmarks/benchmark_recalculate.py` - Benchmarking script

---

## Success Metrics

- [ ] **Query count**: Reduce from ~1000 to ~10 per 100 symbols
- [ ] **Processing rate**: Increase from ~100 to ~1000+ candles/second
- [ ] **Memory usage**: Reduce per-symbol overhead by 50%+
- [ ] **Accuracy**: 100% match with original calculation results
- [ ] **Scalability**: Linear scaling up to 500+ symbols
