# Production Hardening Steps (017-024)

## Overview

These steps address **critical weaknesses** identified in the architecture review. Do **NOT** skip these before live trading.

---

## Critical Priority (Do First)

### Step 017: Data Quality Framework ✅ COMPLETE

**File**: `017-data-quality.md`  
**Effort**: 8 hours  
**Why Critical**: Garbage in → Garbage out → Financial losses

**What It Does**:
- Validates every tick before storage
- Detects price spikes (>10% move)
- Prevents "time travel" ticks
- Checks precision (tick_size, step_size)
- Detects duplicates
- Tracks quality metrics

**Key Components**:
- `TickValidator` - Validation rules
- `QualityTracker` - Metrics and alerting
- `data_quality_issues` table - Issue tracking
- `data_quality_metrics` table - Hourly stats

---

### Step 018: Circuit Breaker Pattern

**File**: `018-circuit-breaker.md` (to be created)  
**Effort**: 4 hours  
**Why Critical**: Prevents runaway failures

**What It Does**:
- Stops calling failing services
- Prevents cascade failures
- Auto-recovery after timeout
- Alerts on repeated failures

**States**:
- **CLOSED**: Normal operation
- **OPEN**: Service failed, stop calling
- **HALF_OPEN**: Testing if service recovered

**Example**:
```python
circuit_breaker.call(lambda: calculate_indicators(tick))
# If fails 5 times → circuit opens → alerts sent → system protected
```

---

### Step 019: Gap Detection & Backfill

**File**: `019-gap-detection.md` (to be created)  
**Effort**: 6 hours  
**Why Critical**: Silent data loss

**What It Does**:
- Detects missing data in real-time
- Alerts on gaps >5 seconds
- Automatically triggers backfill
- Tracks gap statistics

**Example**:
```
3:00:00 PM - Tick received
3:00:01 PM - Tick received
3:00:02 PM - NO TICK (gap detected!)
3:00:03 PM - Tick received → ALERT: 2-second gap
              → Auto-backfill triggered
```

---

### Step 024: Risk Management

**File**: `024-risk-management.md` (to be created)  
**Effort**: 6 hours  
**Why Critical**: Prevents catastrophic losses

**What It Does**:
- Position limits per symbol
- Daily loss limits
- Order size limits
- Concentration limits
- Circuit breaker for trading

**Example**:
```python
risk_manager.check_order(order)
# Returns: APPROVED or REJECTED with reason

# Checks:
# - Would this exceed position limit?
# - Have we hit daily loss limit?
# - Is order size too large?
# - Too much concentration in one symbol?
```

---

## High Priority (Week 2)

### Step 020: Latency Monitoring

**File**: `020-latency-monitoring.md` (to be created)  
**Effort**: 4 hours  

**What It Does**:
- Tracks end-to-end latency
- WebSocket → DB → Indicators → Strategy
- Alerts on p99 latency > threshold
- Historical latency tracking

**Metrics**:
- `websocket_to_db_latency_ms`
- `indicator_calculation_latency_ms`
- `total_pipeline_latency_ms`

---

### Step 021: Exchange Failover

**File**: `021-exchange-failover.md` (to be created)  
**Effort**: 8 hours  

**What It Does**:
- Primary: Binance
- Fallback 1: Coinbase
- Fallback 2: Kraken
- Automatic failover on failure
- Health monitoring

**Architecture**:
```
Your System → Exchange Aggregator
                 ↓
        ┌────────┼────────┐
        ↓        ↓        ↓
    Binance  Coinbase  Kraken
   (Primary) (Fall 1) (Fall 2)
```

---

### Step 022: Health Check API

**File**: `022-health-check.md` (to be created)  
**Effort**: 4 hours  

**What It Does**:
- `/health` endpoint
- Checks: DB, Redis, WebSocket, Data Freshness
- Prometheus metrics
- Slack alerts on degradation

**Response**:
```json
{
  "status": "healthy",
  "checks": {
    "database": {"healthy": true, "latency_ms": 2},
    "redis": {"healthy": true, "latency_ms": 1},
    "binance_ws": {"healthy": true, "uptime": "99.9%"},
    "data_freshness": {"healthy": true, "last_tick": "0.5s ago"}
  }
}
```

---

### Step 023: Backtesting Validation

**File**: `023-backtesting-validation.md` (to be created)  
**Effort**: 8 hours  

**What It Does**:
- Tests for look-ahead bias
- Detects repainting indicators
- Validates on out-of-sample data
- Includes transaction costs

**Tests**:
```python
validator.test_no_lookahead_bias(indicator, data)
validator.test_repainting(indicator, data)
validator.test_with_fees(indicator, data, fee_rate=0.001)
```

---

## Implementation Order

```
Week 1 (CRITICAL):
┌─────────────────────────────────────┐
│ Step 017: Data Quality      ✅ DONE │
│ Step 018: Circuit Breaker          │
│ Step 019: Gap Detection            │
│ Step 024: Risk Management          │
└─────────────────────────────────────┘

Week 2 (HIGH):
┌─────────────────────────────────────┐
│ Step 020: Latency Monitoring       │
│ Step 021: Exchange Failover        │
│ Step 022: Health Check API         │
│ Step 023: Backtesting Validation   │
└─────────────────────────────────────┘
```

---

## Testing Requirements

### Before Live Trading

1. ✅ **Chaos Engineering Tests**
   - Kill WebSocket connection → verify failover
   - Simulate bad data → verify rejection
   - Overload system → verify circuit breaker

2. ✅ **Data Quality Tests**
   - Inject fat-finger trades → verify detection
   - Inject time-travel ticks → verify rejection
   - Create gaps → verify detection + backfill

3. ✅ **Risk Management Tests**
   - Try to exceed position limits → verify rejection
   - Hit daily loss limit → verify trading stops
   - Large orders → verify size limits

---

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Data Quality Score | >95% | TBD |
| System Uptime | >99.5% | TBD |
| Latency p99 | <100ms | TBD |
| Gap Detection Time | <5s | TBD |
| Circuit Breaker Trips | 0 (in normal ops) | TBD |

---

## Next Steps

1. **Review** architecture-review.md
2. **Prioritize** Steps 017-024
3. **Implement** in order (017 → 018 → 019 → 024)
4. **Test** with chaos engineering
5. **Deploy** to staging
6. **Verify** all success metrics
7. **Go Live** (with small capital first)

---

## Remember

> **"In trading, what you don't know CAN hurt you."**

- Data gaps → blind trading
- No validation → garbage signals
- No risk management → catastrophic losses
- No monitoring → unaware of failures

**Don't be the 95% that fail. Be the 5% that survive and thrive.**

---

## Questions?

See:
- [architecture-review.md](../architecture-review.md) - Full analysis
- [017-data-quality.md](017-data-quality.md) - First critical step
- [data-flow-design.md](../data-flow-design.md) - Original design
