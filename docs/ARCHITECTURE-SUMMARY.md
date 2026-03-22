# Architecture Summary - Phase 1: Data Gathering

## Complete Architecture Documentation

This document summarizes all architecture decisions for Phase 1 (Data Gathering).

---

## 📁 Document Index

| Document | Purpose | Status |
|----------|---------|--------|
| [data-flow-design.md](data-flow-design.md) | Complete system design | ✅ Complete |
| [modular-service-architecture.md](modular-service-architecture.md) | Docker services | ✅ Complete |
| [dynamic-configuration-design.md](dynamic-configuration-design.md) | Runtime configuration | ✅ Complete |
| [orderbook-collection-design.md](orderbook-collection-design.md) | Order book design | ✅ Complete |
| [phase1-priorities.md](phase1-priorities.md) | Phase 1 roadmap | ✅ Complete |
| [architecture-planning-guide.md](architecture-planning-guide.md) | Architecture workshop | ✅ Complete |
| [architecture-review.md](architecture-review.md) | Critical analysis | ✅ Complete |

---

## 🎯 Key Design Decisions

### 1. Modular Service Architecture

**Decision**: Each service is independent, deployable via separate docker-compose file

**Rationale**:
- Independent scaling
- Independent deployment
- Fault isolation
- Easy maintenance

**Services**:
```yaml
Core (Always Running):
  - infrastructure (PostgreSQL + Redis)
  - data-collector (ticks)
  - data-enricher (indicators)
  - orderbook-collector (future)

On-Demand:
  - asset-sync (metadata)
  - data-pruner (cleanup)
  - backfill (historical)
  - gap-filler (repairs)
```

---

### 2. Dynamic Configuration

**Decision**: All collection parameters configurable at runtime

**Implementation**:
- Database tables: `collection_config`, `system_config`
- PostgreSQL NOTIFY/LISTEN for instant reload
- CLI commands for management
- Audit trail of all changes

**Configurable Without Restart**:
- ✅ Active symbols
- ✅ Data types per symbol (ticks, order book, candles)
- ✅ Collection frequency (1s, 5s, 1m)
- ✅ Retention policies
- ✅ Quality thresholds
- ✅ Order book settings (for future)

**Example**:
```bash
# Enable order book for BTC/USDT (when implemented)
crypto config set-symbol BTC/USDT collect_orderbook true
crypto config set-symbol BTC/USDT orderbook_levels 20

# Change tick frequency to 5 seconds
crypto config set-symbol BTC/USDT tick_snapshot_interval_sec 5

# Changes apply automatically, no restart needed
```

---

### 3. Data Storage Strategy

**Ticks (Trades)**:
```yaml
frequency: 1 second (every tick stored)
retention: 180 days (configurable per symbol)
storage: ~1 TB for 6 months, 10 symbols
format: Individual rows in trades table
```

**Order Book** (Future):
```yaml
frequency: 1 second (not 100ms - too much data)
levels: 10 bid + 10 ask
retention: 30 days (configurable)
storage: ~500 GB for 6 months, 10 symbols
format: PostgreSQL arrays (compact)
ready: Configuration fields ready, just enable when needed
```

**Indicators**:
```yaml
frequency: Real-time (calculated on every tick)
storage: JSONB (flexible, dynamic indicators)
retention: Same as ticks
auto-recalc: When indicator definitions change
```

---

### 4. Database Schema

**Core Tables**:
```sql
symbols                    -- Symbol metadata (from Binance)
trades                     -- Tick data (individual trades)
tick_indicators            -- Calculated indicators (JSONB)
indicator_definitions      -- Dynamic indicator definitions
collection_config          -- Per-symbol collection config ⭐ NEW
system_config              -- Global system config ⭐ NEW
config_change_log          -- Audit trail ⭐ NEW
orderbook_snapshots        -- Order book data (future)
recalculation_jobs         -- Indicator recalc tracking
data_quality_issues        -- Quality tracking ⭐ NEW
data_quality_metrics       -- Quality metrics ⭐ NEW
```

**Key Features**:
- ✅ Dynamic indicator support (add/change without schema changes)
- ✅ Per-symbol configuration
- ✅ Quality tracking
- ✅ Audit trail
- ✅ Partitioning ready (time-based)
- ✅ Compression ready (for old data)

---

### 5. Data Quality Framework

**Validation Rules**:
```python
Price sanity:      No >10% move in 1 second (configurable)
Time monotonicity: No "time travel" ticks
Precision:         Price aligns with tick_size
Quantity:          Quantity aligns with step_size
Duplicates:        No duplicate trade_id
Stale data:        Alert if data >60 seconds old
```

**Actions on Invalid Data**:
```python
WARNING:  Log, store with flag, continue
ERROR:    Reject, log, alert, skip tick
CRITICAL: Reject, alert, pause collection, notify operator
```

**Tracking**:
```sql
-- Every validation failure logged
data_quality_issues:
  - symbol_id
  - issue_type (price_spike, time_travel, duplicate, etc.)
  - severity (warning, error, critical)
  - raw_data (JSONB)
  - detected_at

-- Hourly metrics
data_quality_metrics:
  - ticks_received
  - ticks_validated
  - ticks_rejected
  - quality_score (0-100)
  - latency_percentiles
```

---

### 6. Indicator Framework

**Dynamic Indicators**:
```python
# Add new indicators without schema changes
class RSIIndicator(Indicator):
    category = 'momentum'
    params_schema = {'period': {'type': 'int', 'default': 14}}
    
    def calculate(self, prices, volumes) -> IndicatorResult:
        # Calculate using TA-Lib
        return IndicatorResult(name='rsi_14', values={'rsi': [...]})
```

**Auto-Recalculation**:
```
1. Change indicator params (e.g., RSI period 14 → 21)
   ↓
2. Database trigger fires NOTIFY 'indicator_changed'
   ↓
3. RecalculationService detects change
   ↓
4. Creates recalculation job
   ↓
5. Processes historical data in batches
   ↓
6. Updates all tick_indicators records
   ↓
7. Strategies automatically use new values
```

**Storage**:
```sql
tick_indicators:
  time TIMESTAMP
  symbol_id INTEGER
  price NUMERIC
  volume NUMERIC
  values JSONB  -- All indicators stored here
  indicator_keys TEXT[]  -- For fast lookup
  
-- Example values:
{
  "rsi_14": 55.5,
  "macd": 123.45,
  "sma_20": 50123.45,
  "bollinger_upper": 50500.00,
  "bollinger_lower": 49500.00
}
```

---

## 🚀 Implementation Roadmap

### Week 1-2: Foundation ✅

```
✅ Step 001: Project Setup
✅ Step 002: Database Schema
✅ Step 003: Domain Models
```

**Status**: Documentation complete, ready for implementation

---

### Week 3-4: Data Collection ⏳

```
⬜ Step 004: Data Collection Service (ticks)
⬜ Step 005: Repository Pattern
⬜ Step 016: Asset Sync Service (daily metadata)
```

**Key Features**:
- Binance WebSocket connection
- Tick validation (data quality)
- Batch storage
- Active symbol filtering
- Dynamic configuration support

---

### Week 5: Data Quality & Reliability 🎯

```
⬜ Step 017: Data Quality Framework
⬜ Step 019: Gap Detection & Backfill
⬜ Step 022: Health Monitoring
```

**Key Features**:
- Tick validation (7 rules)
- Quality metrics tracking
- Gap detection (<5 seconds)
- Auto-backfill
- Health check endpoints

---

### Week 6-8: Enrichment & Indicators ⏳

```
⬜ Step 006: Indicator Framework
⬜ Step 007: Indicator Implementations
⬜ Step 008: Enrichment Service
⬜ Step 009: Redis Pub/Sub
⬜ Step 010: Recalculation Service
```

**Key Features**:
- Dynamic indicator definitions
- 10-15 core indicators (RSI, MACD, SMA, etc.)
- Real-time calculation
- Auto-recalculation on changes
- Redis pub/sub for strategies

---

### Week 9: Operations ⏳

```
⬜ Step 011: CLI Tools
⬜ Step 015: Monitoring & Logging
```

**Key Features**:
- Configuration management CLI
- Service management scripts
- Health monitoring
- Logging infrastructure

---

## 📊 System Capacity

### Storage (6 Months, 10 Symbols)

| Data Type | Storage | Notes |
|-----------|---------|-------|
| Ticks | ~1 TB | 100 ticks/sec, compressed |
| Indicators | ~700 GB | 50 indicators per tick, compressed |
| Order Book | ~500 GB | 1 sec snapshots (future) |
| **Total** | **~2.2 TB** | With compression |

### Compute (10 Symbols)

| Component | CPU | Memory |
|-----------|-----|--------|
| Data Collection | 2.5 cores | 2 GB |
| Enrichment | 3 cores | 4 GB |
| Database | 2 cores | 2 GB |
| **Total** | **~8.5 cores** | **~10 GB** |

### Network

```
Inbound (WebSocket):  ~2 Mbps
Outbound (Redis):     ~4 Mbps
Total:                ~6 Mbps continuous
```

---

## 🔧 Configuration Examples

### Enable Order Book for Specific Symbols

```bash
# When order book collector is implemented
crypto config set-symbol BTC/USDT collect_orderbook true
crypto config set-symbol BTC/USDT orderbook_levels 20
crypto config set-symbol BTC/USDT orderbook_snapshot_interval_sec 1

# Service will automatically start collecting (no restart)
```

### Change Collection Frequency

```bash
# Reduce to 5-second snapshots (save storage)
crypto config set-symbol BTC/USDT tick_snapshot_interval_sec 5

# Apply to all symbols
psql $DATABASE_URL -c "
UPDATE collection_config 
SET tick_snapshot_interval_sec = 5 
WHERE symbol_id IN (SELECT id FROM symbols WHERE is_active = true);
SELECT pg_notify('config_changed', '{\"type\":\"bulk_update\"}');
"
```

### Adjust Retention

```bash
# Reduce tick retention to 90 days
crypto config set-symbol BTC/USDT tick_retention_days 90

# Run pruner
crypto run-pruner --days 90
```

### Configure Quality Thresholds

```bash
# Increase max price move for volatile symbols
crypto config set-symbol DOGE/USDT max_price_move_pct 20.0

# Reduce max gap for critical symbols
crypto config set-symbol BTC/USDT max_gap_seconds 3
```

---

## 📈 Monitoring & Operations

### Health Checks

```bash
# Check service status
./scripts/manage.sh status

# Check infrastructure health
./scripts/manage.sh health

# View logs
./scripts/manage.sh logs collector
./scripts/manage.sh logs enricher
```

### Quality Metrics

```sql
-- Check data quality score
SELECT 
    s.symbol,
    dm.quality_score,
    dm.ticks_received,
    dm.ticks_rejected,
    dm.latency_p99_ms
FROM data_quality_metrics dm
JOIN symbols s ON s.id = dm.symbol_id
WHERE dm.date = CURRENT_DATE
ORDER BY dm.quality_score DESC;

-- Check for issues
SELECT 
    symbol,
    issue_type,
    severity,
    COUNT(*) as issue_count
FROM data_quality_issues
WHERE resolved = false
GROUP BY symbol, issue_type, severity
ORDER BY issue_count DESC;
```

### Configuration Audit

```sql
-- View recent config changes
SELECT 
    config_type,
    config_key,
    new_value,
    changed_by,
    changed_at
FROM config_change_log
ORDER BY changed_at DESC
LIMIT 20;
```

---

## ✅ Phase 1 Deliverables Checklist

```yaml
Data Collection:
  ✓ Collects ticks from Binance WebSocket
  ✓ Validates data quality (7 validation rules)
  ✓ Detects gaps automatically
  ✓ Stores in PostgreSQL
  ✓ Syncs asset metadata daily
  ✓ Dynamic configuration (no restart needed)

Data Enrichment:
  ✓ Calculates 10-15 indicators per tick
  ✓ Stores in PostgreSQL (JSONB, flexible)
  ✓ Auto-recalculates on indicator changes
  ✓ Publishes to Redis for subscribers
  ✓ Dynamic indicator definitions

Operations:
  ✓ CLI for management (config, sync, backfill, etc.)
  ✓ Health monitoring
  ✓ Logging infrastructure
  ✓ Service management scripts
  ✓ Docker Compose deployment

Data Quality:
  ✓ Validation framework
  ✓ Quality metrics tracking
  ✓ Issue detection and alerting
  ✓ Audit trail

Configuration:
  ✓ Dynamic per-symbol configuration
  ✓ System-wide settings
  ✓ Runtime changes (no restart)
  ✓ Change audit log
```

---

## 🎯 What's NOT in Phase 1

```yaml
Deferred to Phase 2/3:
  - Trading strategies
  - Risk management
  - Order execution
  - Backtesting engine
  - Exchange failover (manual restart OK for now)
  - Circuit breakers (no trading yet)
  - Advanced latency monitoring
  - Order book collection (design ready, implement later)
```

---

## 🚀 Getting Started

### 1. Review Architecture

```bash
# Read the key documents
cat docs/data-flow-design.md
cat docs/modular-service-architecture.md
cat docs/dynamic-configuration-design.md
cat docs/phase1-priorities.md
```

### 2. Start Implementation

```bash
# Week 3: Data Collection
cat docs/implementation/004-data-collection-service.md
cat docs/implementation/005-repository-pattern.md

# Create Docker files
mkdir docker
# Create docker-compose-infra.yml, etc.
```

### 3. Test & Deploy

```bash
# Start infrastructure
./scripts/manage.sh start-infra

# Run migrations
docker-compose -f docker-compose-infra.yml exec postgres \
  psql -U crypto -d crypto_trading -f /docker-entrypoint-initdb.d/001_initial_schema.sql

# Start collector
./scripts/manage.sh start-collector

# Monitor
./scripts/manage.sh status
./scripts/manage.sh health
```

---

## 📞 Questions?

### Architecture Questions
→ See [architecture-planning-guide.md](architecture-planning-guide.md)

### Implementation Questions
→ See implementation steps (001-024)

### Configuration Questions
→ See [dynamic-configuration-design.md](dynamic-configuration-design.md)

### Order Book Questions
→ See [orderbook-collection-design.md](orderbook-collection-design.md)

---

## Summary

**Phase 1 Goal**: Build robust, validated data pipeline for backtesting

**Key Features**:
- ✅ Modular, independent services
- ✅ Dynamic configuration (no restart needed)
- ✅ Data quality validation
- ✅ Order book ready (design complete, implement later)
- ✅ Comprehensive monitoring
- ✅ Easy operations (CLI, Docker)

**Timeline**: 9 weeks

**Storage**: ~2.2 TB for 6 months, 10 symbols

**Ready to implement!** 🚀
