# Step 020: Historical Data Backfill

**Status**: Ready for Implementation  
**Priority**: High (Phase 1 completion)  
**Effort**: 4-6 hours  

---

## 🎯 Objective

Implement a historical data backfill system that:
1. Collects active symbols from Binance (1-min sampling)
2. Fetches 1-second klines via REST API
3. Inserts data into database
4. Calculates indicators **inline** (matches real-time behavior)
5. Stores checkpoint in `system_config` table

---

## 📋 Requirements

### Functional Requirements

| # | Requirement | Details |
|---|-------------|---------|
| 1 | Collect active symbols | Sample 24hr ticker for 1 minute |
| 2 | Filter EU-compliant symbols | Exclude leveraged tokens, low volume |
| 3 | Fetch historical data | 1-second klines from Binance REST API |
| 4 | Configurable days | Default: 3 days, parameter: `--days N` |
| 5 | Inline enrichment | Calculate indicators during backfill |
| 6 | Checkpoint storage | Use `system_config` table |
| 7 | Resume capability | Skip already backfilled symbols |
| 8 | Dry-run mode | Test without inserting data |

### Non-Functional Requirements

| # | Requirement | Details |
|---|-------------|---------|
| 1 | Sequential fetching | KISS, avoid CPU overload |
| 2 | Rate limiting | 100ms delay between API calls |
| 3 | Progress logging | Every 1000 records |
| 4 | Error handling | Retry with backoff, skip failures |
| 5 | Idempotent | ON CONFLICT DO NOTHING/UPDATE |

---

## 🏗️ Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│              HISTORICAL BACKFILL PIPELINE                        │
│                                                                  │
│  1. Collect Active Symbols (60 sec)                             │
│     └─→ Sample 24hr ticker every 1 second                       │
│     └─→ Filter EU compliant (no UP/DOWN tokens, >1M volume)     │
│                                                                  │
│  2. For Each Symbol (sequential):                               │
│     ├─→ Check checkpoint (system_config)                        │
│     ├─→ Fetch 1-sec klines (Binance REST API)                   │
│     ├─→ Insert to ticker_24hr_stats                             │
│     ├─→ Calculate indicators INLINE (TickWindow + indicators)   │
│     ├─→ Insert to tick_indicators                               │
│     └─→ Update checkpoint (system_config)                       │
│                                                                  │
│  3. Summary Report                                              │
│     └─→ Symbols processed, records inserted, errors             │
└─────────────────────────────────────────────────────────────────┘
```

### Database Schema Usage

**Existing tables** (no new tables needed):

| Table | Purpose |
|-------|---------|
| `symbols` | Symbol metadata |
| `ticker_24hr_stats` | 1-sec kline data |
| `tick_indicators` | Calculated indicators |
| `system_config` | **Checkpoint storage** |

**Checkpoint storage in `system_config`**:

```sql
-- Store checkpoint
INSERT INTO system_config (key, value, description)
VALUES (
    'backfill_checkpoint_BTCUSDT',
    '{"last_time": "2026-03-22T10:00:00Z", "days": 3, "records": 259200}',
    'Backfill checkpoint for BTCUSDT'
)
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW(),
    version = system_config.version + 1;
```

---

## 📐 Implementation Design

### File Structure

```
numbersML/
├── src/
│   └── cli/
│       └── backfill.py              # NEW: Main backfill script
├── tests/
│   └── integration/
│       └── test_backfill.py         # NEW: Integration tests
└── docs/
    └── implementation/
        └── 020-backfill.md          # This file
```

### CLI Interface

```bash
# Backfill last 3 days (default) for all active symbols
.venv/bin/python src/cli/backfill.py

# Backfill last 7 days
.venv/bin/python src/cli/backfill.py --days 7

# Backfill specific symbol
.venv/bin/python src/cli/backfill.py --days 3 --symbol BTC/USDT

# Dry run (no inserts)
.venv/bin/python src/cli/backfill.py --days 3 --dry-run

# Custom database URL
.venv/bin/python src/cli/backfill.py --days 3 --db-url postgresql://...
```

### Key Classes

```python
class HistoricalBackfill:
    """
    Backfill historical data from Binance.
    
    Attributes:
        db_url: Database connection string
        days: Days to backfill (default: 3)
        symbol_filter: Optional specific symbol
        dry_run: If True, don't insert data
    """
    
    async def run() -> Dict:
        """Run backfill process."""
    
    async def _collect_active_symbols(duration_sec: int = 60) -> List[str]:
        """Collect active symbols by sampling 24hr ticker."""
    
    async def _backfill_symbol(symbol: str) -> int:
        """Backfill single symbol."""
    
    async def _fetch_klines(start_time, end_time) -> List[Dict]:
        """Fetch 1-sec klines from Binance."""
    
    async def _insert_and_enrich(klines: List[Dict]) -> int:
        """Insert klines and calculate indicators inline."""
    
    async def _save_checkpoint(symbol: str, last_time: datetime, count: int):
        """Save checkpoint to system_config table."""
```

### Inline Enrichment Logic

```python
# After inserting batch of klines
tick_window = TickWindow(window_size=200)

for kline in klines:
    # Parse kline
    tick_data = {
        'time': datetime.fromtimestamp(kline[0] / 1000),
        'open': Decimal(kline[1]),
        'high': Decimal(kline[2]),
        'low': Decimal(kline[3]),
        'close': Decimal(kline[4]),
        'volume': Decimal(kline[5]),
    }
    
    # Update tick window
    tick_window.update(tick_data)
    
    # Calculate indicators (if enough data)
    if len(tick_window) >= 50:
        indicator_values = calculate_indicators(tick_window)
        await store_indicators(conn, symbol_id, tick_data['time'], indicator_values)
```

### Checkpoint Storage

```python
async def _save_checkpoint(
    self,
    conn: asyncpg.Connection,
    symbol: str,
    last_time: datetime,
    records_count: int
) -> None:
    """Save checkpoint to system_config table."""
    await conn.execute(
        """
        INSERT INTO system_config (key, value, description)
        VALUES (
            $1, $2, $3
        )
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = NOW(),
            version = system_config.version + 1
        """,
        f'backfill_checkpoint_{symbol}',
        json.dumps({
            'last_time': last_time.isoformat(),
            'days': self.days,
            'records': records_count,
        }),
        f'Backfill checkpoint for {symbol}',
    )
```

---

## 📊 Data Volume Estimates

### Storage Calculation

**Per symbol, per day**:
- 24 hours × 60 min × 60 sec = **86,400 klines**

**For 100 symbols, 3 days**:
- 100 × 3 × 86,400 = **25,920,000 records**
- ~200 bytes per record
- 25.9M × 200 bytes = **~5.2 GB**

### API Call Estimates

**Per request**: 1000 klines (max)

**For 1 symbol, 1 day**:
- 86,400 / 1000 = **87 requests**

**For 100 symbols, 3 days**:
- 100 × 3 × 87 = **26,100 requests**
- At 100ms delay: **~43 minutes**

---

## ⚠️ Edge Cases & Error Handling

| Case | Handling |
|------|----------|
| **API rate limit** | 100ms delay, retry with exponential backoff |
| **Symbol delisted** | Skip, log warning, continue |
| **Database connection lost** | Retry 3 times, then fail with error |
| **Partial backfill** | Checkpoint allows resume |
| **Duplicate data** | ON CONFLICT DO NOTHING |
| **Indicator calculation fails** | Log error, continue with next kline |
| **Disk space low** | Check before starting, warn if <10GB free |

---

## 🧪 Testing Strategy

### Unit Tests

```python
# tests/unit/cli/test_backfill.py

class TestHistoricalBackfill:
    def test_backfill_initialization(self):
        """Test backfill initializes correctly."""
    
    def test_is_eu_compliant(self):
        """Test EU compliance filtering."""
    
    def test_parse_kline(self):
        """Test kline parsing."""
```

### Integration Tests

```python
# tests/integration/test_backfill.py

class TestBackfillIntegration:
    @pytest.mark.asyncio
    async def test_backfill_single_symbol(self):
        """Test backfilling single symbol."""
    
    @pytest.mark.asyncio
    async def test_backfill_with_checkpoint(self):
        """Test resume from checkpoint."""
    
    @pytest.mark.asyncio
    async def test_backfill_dry_run(self):
        """Test dry-run mode."""
```

---

## ✅ Acceptance Criteria

- [ ] Collects active symbols (60-sec sampling)
- [ ] Filters EU-compliant symbols (no UP/DOWN, >1M volume)
- [ ] Fetches 1-sec klines via Binance REST API
- [ ] Inserts into `ticker_24hr_stats` (ON CONFLICT DO NOTHING)
- [ ] Calculates indicators **inline** (TickWindow + indicator classes)
- [ ] Inserts into `tick_indicators` (ON CONFLICT DO UPDATE)
- [ ] Checkpoint stored in `system_config` table
- [ ] Default: 3 days backfill
- [ ] CLI: `--days N`, `--symbol`, `--dry-run`, `--db-url`
- [ ] Sequential fetching (no parallel)
- [ ] Rate limiting: 100ms between API calls
- [ ] Progress logging: every 1000 records
- [ ] Resume capability (skip checkpointed symbols)
- [ ] Error handling: retry, skip, continue
- [ ] Unit tests (80%+ coverage)
- [ ] Integration tests (with real DB)
- [ ] Documentation complete

---

## 📝 Implementation Steps

### Step 1: Create Backfill Script (2 hours)

1. Create `src/cli/backfill.py`
2. Implement `HistoricalBackfill` class
3. Implement `_collect_active_symbols()`
4. Implement `_fetch_klines()` with rate limiting
5. Implement `_insert_and_enrich()` with inline indicators
6. Implement checkpoint storage in `system_config`
7. Add CLI argument parsing
8. Add progress logging

### Step 2: Add Tests (1-2 hours)

1. Create `tests/unit/cli/test_backfill.py`
2. Create `tests/integration/test_backfill.py`
3. Write unit tests for filtering, parsing
4. Write integration tests for full pipeline
5. Run tests, fix issues

### Step 3: Documentation (30 min)

1. Update `docs/implementation/020-backfill.md` (this file)
2. Add usage examples
3. Add troubleshooting section

### Step 4: Manual Testing (1 hour)

1. Run backfill for 1 symbol, 1 day
2. Verify data in database
3. Verify indicators calculated
4. Verify checkpoint saved
5. Test resume capability
6. Test dry-run mode

---

## 🚀 Usage Examples

### Basic Usage

```bash
cd numbersML

# Backfill last 3 days for all active symbols
.venv/bin/python src/cli/backfill.py

# Backfill last 7 days
.venv/bin/python src/cli/backfill.py --days 7
```

### Advanced Usage

```bash
# Backfill specific symbol
.venv/bin/python src/cli/backfill.py --days 7 --symbol BTC/USDT

# Dry run (test without inserting)
.venv/bin/python src/cli/backfill.py --days 3 --dry-run

# Resume interrupted backfill
.venv/bin/python src/cli/backfill.py --days 7
# (automatically resumes from checkpoint)

# Custom database
.venv/bin/python src/cli/backfill.py --days 3 \
  --db-url postgresql://user:pass@host:5432/db
```

---

## 📈 Monitoring

### Check Backfill Progress

```sql
-- Check checkpoints
SELECT 
    key,
    value->>'last_time' as last_time,
    value->>'days' as days,
    value->>'records' as records,
    updated_at
FROM system_config
WHERE key LIKE 'backfill_checkpoint_%'
ORDER BY updated_at DESC;

-- Check records inserted
SELECT 
    symbol,
    COUNT(*) as records,
    MIN(time) as earliest,
    MAX(time) as latest
FROM ticker_24hr_stats
GROUP BY symbol
ORDER BY records DESC;

-- Check indicators calculated
SELECT 
    s.symbol,
    COUNT(*) as indicators,
    COUNT(DISTINCT ti.indicator_keys) as indicator_types
FROM tick_indicators ti
JOIN symbols s ON s.id = ti.symbol_id
GROUP BY s.symbol
ORDER BY indicators DESC;
```

### View Logs

```bash
# Backfill logs
tail -f /tmp/backfill.log

# Or with journalctl (if running as service)
journalctl -u crypto-backfill -f
```

---

## 🔧 Troubleshooting

### Issue: "API rate limit exceeded"

**Solution**: Increase delay between requests:
```python
await asyncio.sleep(0.2)  # Increase from 0.1 to 0.2
```

### Issue: "Checkpoint not saving"

**Solution**: Check `system_config` table exists and is writable:
```sql
SELECT COUNT(*) FROM system_config;
```

### Issue: "Indicators not calculated"

**Solution**: Ensure minimum tick window size (50 ticks):
```python
if len(tick_window) >= 50:
    # Calculate indicators
```

### Issue: "Out of disk space"

**Solution**: Reduce days or symbols:
```bash
# Backfill only 1 day
.venv/bin/python src/cli/backfill.py --days 1

# Backfill only specific symbol
.venv/bin/python src/cli/backfill.py --days 3 --symbol BTC/USDT
```

---

## 📚 References

- [Binance API Documentation](https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/current/)
- [Step 004: Data Collection Service](004-data-collection.md)
- [Step 008: Enrichment Service](008-enrichment-service.md)

---

**Last Updated**: March 22, 2026  
**Status**: Ready for Implementation  
**Phase**: 1 (Data Gathering)
