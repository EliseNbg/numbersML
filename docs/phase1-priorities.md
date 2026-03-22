# Phase 1 Priorities - Data Gathering Only

## Context

**Current Phase**: 1 - Data Infrastructure  
**Goal**: Build robust data collection and storage  
**NOT in scope**: Trading, risk management, order execution

---

## Revised Architecture Review (Phase 1 Focus)

### What's Actually Critical for Data Gathering

```
┌─────────────────────────────────────────────────────────────┐
│              PHASE 1: DATA GATHERING                         │
│                                                               │
│  Binance WebSocket → Collect → Validate → Store → Enrich    │
│                                                               │
│  Success Criteria:                                            │
│  ✅ Reliable data collection (no gaps)                        │
│  ✅ Data quality (no garbage)                                 │
│  ✅ Indicator calculation (accurate)                          │
│  ✅ Historical backfill (6 months)                            │
│  ✅ Active symbol management                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Critical vs. Can Wait

### ✅ CRITICAL for Phase 1 (Do Now)

| Step | Description | Why Critical |
|------|-------------|--------------|
| **017** | Data Quality | Prevent garbage data in database |
| **019** | Gap Detection | Detect missing data early |
| **022** | Health Monitoring | Know if system is working |

**Total**: 3 steps, ~18 hours

### ⏸️ CAN WAIT Until Phase 2/3

| Step | Description | Why Not Critical Yet |
|------|-------------|---------------------|
| 018 | Circuit Breaker | No trading = no runaway risk |
| 020 | Latency Monitoring | Sub-second not critical for data collection |
| 021 | Exchange Failover | Can restart manually for now |
| 023 | Backtesting Validation | Phase 2 (backtesting) concern |
| 024 | Risk Management | No orders = no risk |

---

## Revised Phase 1 Roadmap

### Week 1-2: Foundation ✅

```
✅ Step 001: Project Setup
✅ Step 002: Database Schema
✅ Step 003: Domain Models
```

**Status**: COMPLETE

---

### Week 3-4: Data Collection ⏳

```
⬜ Step 004: Data Collection Service (Binance WebSocket)
⬜ Step 005: Repository Pattern
⬜ Step 016: Asset Sync Service (daily metadata sync)
```

**Status**: Ready to implement

---

### Week 5: Data Quality & Reliability 🎯

```
⬜ Step 017: Data Quality Framework (NEW - CRITICAL)
⬜ Step 019: Gap Detection & Backfill (NEW - CRITICAL)
⬜ Step 022: Health Check API (NEW - CRITICAL)
```

**Status**: Design ready

---

### Week 6-8: Enrichment & Indicators ⏳

```
⬜ Step 006: Indicator Framework
⬜ Step 007: Indicator Implementations (10-15 indicators)
⬜ Step 008: Enrichment Service (real-time calculation)
⬜ Step 009: Redis Pub/Sub
⬜ Step 010: Recalculation Service
```

**Status**: Design ready

---

### Week 9: CLI & Operations ⏳

```
⬜ Step 011: CLI Tools
⬜ Step 015: Monitoring & Logging
```

**Status**: Design ready

---

## Phase 1 Deliverables

### End of Phase 1 Checklist

```yaml
Data Collection:
  ✓ Collects ticks from Binance WebSocket
  ✓ Validates data quality (no garbage)
  ✓ Detects gaps automatically
  ✓ Stores in PostgreSQL
  ✓ Syncs asset metadata daily

Data Enrichment:
  ✓ Calculates 10-15 indicators per tick
  ✓ Stores in PostgreSQL (JSONB)
  ✓ Auto-recalculates on indicator changes
  ✓ Publishes to Redis for subscribers

Operations:
  ✓ CLI for management (activate symbols, trigger recalc, etc.)
  ✓ Health monitoring (is system running?)
  ✓ Logging (what happened?)
  ✓ 6 months historical data backfilled

NOT in Phase 1:
  ✗ Trading strategies
  ✗ Risk management
  ✗ Order execution
  ✗ Backtesting engine
  ✗ Exchange failover
```

---

## Updated Critical Path (Phase 1 Only)

```
Week 1-2: Foundation          ✅ DONE (Steps 001-003)
              ↓
Week 3-4: Data Collection     ⏳ NEXT (Steps 004, 005, 016)
              ↓
Week 5: Data Quality          🎯 (Steps 017, 019, 022)
              ↓
Week 6-8: Enrichment          ⏳ (Steps 006-010)
              ↓
Week 9: Operations            ⏳ (Steps 011, 015)
              ↓
Phase 1 Complete! → Ready for Phase 2 (Backtesting)
```

---

## What Changed from Original Plan

### Added (Critical for Data Quality)

1. **Step 017**: Data Quality Framework
   - Validate ticks before storage
   - Reject bad data (price spikes, time travel, duplicates)
   - Track quality metrics

2. **Step 019**: Gap Detection
   - Detect missing data in real-time
   - Alert on gaps >5 seconds
   - Auto-backfill gaps

3. **Step 022**: Health Monitoring
   - `/health` endpoint
   - Check: DB, WebSocket, data freshness
   - Basic alerts

### Deferred to Phase 2/3

- Circuit breakers (no trading yet)
- Latency monitoring (not critical for data collection)
- Exchange failover (manual restart is fine for now)
- Risk management (no orders yet)
- Backtesting validation (Phase 2)

---

## Resource Requirements

### Phase 1 Only

| Resource | Estimate |
|----------|----------|
| **Time** | 9 weeks (vs. original 8) |
| **Steps** | 15 steps (001-011, 015-017, 019, 022) |
| **Effort** | ~80 hours total |

### Infrastructure

```yaml
Database:
  - PostgreSQL 15+
  - ~100GB storage (6 months, 10 symbols, tick data)
  - Daily backups

Redis:
  - Redis 7+
  - ~2GB RAM (pub/sub, latest ticks)

Application:
  - Python 3.11+
  - 2-4 GB RAM
  - 1-2 CPU cores

Monitoring:
  - Basic logging (file-based)
  - Health check endpoint
  - Optional: Prometheus + Grafana
```

---

## Success Metrics (Phase 1)

### Data Quality

```yaml
ticks_collected: >99% of actual ticks
data_quality_score: >95%
gap_detection_time: <10 seconds
indicator_accuracy: 100% (vs. TA-Lib reference)
```

### System Reliability

```yaml
uptime: >99% (excluding maintenance)
restart_time: <5 minutes
data_loss: 0 (with gap detection + backfill)
```

### Performance

```yaml
websocket_to_db_latency: <100ms (p99)
indicator_calculation: <50ms (p99)
redis_publish_latency: <10ms (p99)
```

---

## Next Actions (This Week)

### Immediate (Steps 004-005)

```bash
# 1. Implement data collection service
cat docs/implementation/004-data-collection-service.md

# 2. Implement repository pattern
cat docs/implementation/005-repository-pattern.md

# 3. Test with 1-2 symbols
python -m src.infrastructure.exchanges.collector --symbols BTC/USDT,ETH/USDT
```

### Next Week (Step 016)

```bash
# Asset sync service
python -m src.cli.sync-assets --dry-run
python -m src.cli.sync-assets  # Actual sync
```

### Week 5 (Steps 017, 019, 022)

```bash
# Data quality validation
# Gap detection
# Health monitoring
```

---

## Questions?

### For Data Gathering Phase

1. **How many symbols to collect?**
   - Recommended: Start with 5-10 major pairs
   - Activate more gradually

2. **How much historical data?**
   - 6 months of 1-minute candles
   - 7-30 days of tick data (storage intensive)

3. **When to run backfill?**
   - After Step 004 is working
   - Before Step 008 (enrichment)

4. **How to verify data quality?**
   - Step 017 (quality metrics)
   - Manual spot checks
   - Compare with exchange

---

## Summary

**Focus**: Phase 1 only (data gathering)  
**Added**: 3 critical data quality steps (017, 019, 022)  
**Deferred**: Trading concerns to Phase 2/3  
**Timeline**: 9 weeks total for Phase 1  
**Goal**: Robust, validated data pipeline

**Ready to proceed with Steps 004-005?**
