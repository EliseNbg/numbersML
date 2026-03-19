# Architecture Planning Guide - Phase 1: Data Gathering

## How to Use This Document

This is your **architecture workshop checklist**. Work through each section systematically before implementation.

**Estimated Time**: 2-4 days for thorough architecture review

---

## Part 1: Requirements Clarification

### 1.1 Data Requirements

```yaml
Questions to Answer:

Symbols:
  - How many symbols initially? (5, 10, 50?)
  - Which symbols? (BTC/USDT, ETH/USDT, ...?)
  - How to select which symbols to activate?

Data Types:
  - Ticks (trades): Yes/No?
  - Order book: Depth? (top 10, full book?)
  - Candles: Which timeframes? (1s, 1m, 5m, 1h?)
  - Which is primary vs. derived?

Historical Data:
  - How far back? (1 month, 6 months, all available?)
  - Tick data or candles? (storage difference is huge)
  - One-time backfill or ongoing?

Update Frequency:
  - Ticks per second per symbol? (10, 100, 1000?)
  - Order book updates per second?
  - Peak vs. average load?
```

### 1.2 Quality Requirements

```yaml
Questions to Answer:

Data Quality:
  - What validation rules make sense?
  - Price move threshold? (5%, 10%, 20%?)
  - Max acceptable gap? (5s, 30s, 1min?)
  - How to handle bad data? (reject, flag, store separately?)

Availability:
  - Target uptime? (99%, 99.9%, 99.99%?)
  - Acceptable data loss? (0%, <0.1%?)
  - Manual intervention OK? Or must be automatic?

Freshness:
  - Max latency from trade to database? (100ms, 1s, 10s?)
  - Real-time indicator calculation needed?
  - Or batch calculation OK?
```

### 1.3 Operational Requirements

```yaml
Questions to Answer:

Monitoring:
  - What must you monitor? (data flow, gaps, errors?)
  - Alert channels? (email, Slack, SMS?)
  - Who gets alerted? (you, team, on-call?)

Maintenance:
  - When to do maintenance? (weekends, nights?)
  - How long maintenance window? (1h, 4h, 24h?)
  - Zero-downtime updates needed?

Data Retention:
  - How long to keep tick data? (30 days, 1 year, forever?)
  - How long to keep indicators? (same as ticks?)
  - Archive strategy? (compress old data?)

Backup & Recovery:
  - Backup frequency? (hourly, daily, weekly?)
  - RPO (Recovery Point Objective)? (how much data can you lose?)
  - RTO (Recovery Time Objective)? (how fast must you recover?)
```

---

## Part 2: Architecture Decisions

### 2.1 Data Flow Architecture

**Decision Record Template**:

```markdown
## Decision: [Title]

### Context
What is the issue we're deciding?

### Options
Option A: ...
Option B: ...
Option C: ...

### Decision
We chose [Option] because...

### Consequences
- Positive: ...
- Negative: ...
- Risks: ...

### Status
[Proposed | Decided | Superseded]

### Date
[YYYY-MM-DD]
```

**Decisions to Make**:

1. **Data Flow Pattern**
   - Option A: Direct (WebSocket → DB → Enrichment)
   - Option B: Queue-based (WebSocket → Kafka → DB → Enrichment)
   - Option C: Hybrid (WebSocket → Memory → Batch DB → Enrichment)

2. **Indicator Storage**
   - Option A: JSONB in single table (flexible, slower queries)
   - Option B: Wide table with columns per indicator (fast, schema changes)
   - Option C: Time-series DB (InfluxDB, TimescaleDB hypertables)

3. **Enrichment Timing**
   - Option A: Real-time (every tick triggers calculation)
   - Option B: Micro-batch (every 100ms, batch of ticks)
   - Option C: Deferred (calculate on-demand for backtesting)

---

### 2.2 Technology Choices

**Database**:

```yaml
Decision: Primary Database

Options:
  PostgreSQL:
    pros:
      - Familiar, SQL support
      - JSONB for flexible indicators
      - Good for relational data
    cons:
      - Not optimized for time-series
      - Write throughput limits (~10k writes/sec)
      - Storage intensive for ticks
    
    Best for: < 1000 ticks/sec, complex queries

TimescaleDB (PostgreSQL extension):
    pros:
      - PostgreSQL compatible
      - Automatic partitioning (hypertables)
      - Time-series optimized
      - Compression for old data
    cons:
      - Additional complexity
      - Slightly different SQL
    
    Best for: > 1000 ticks/sec, time-series queries

InfluxDB:
    pros:
      - Purpose-built for time-series
      - High write throughput
      - Automatic retention policies
      - Built-in downsampling
    cons:
      - Different query language (Flux)
      - Less flexible for relational data
      - Another technology to learn
    
    Best for: Pure time-series, very high throughput

ClickHouse:
    pros:
      - Extremely fast analytical queries
      - Excellent compression
      - High write throughput
    cons:
      - Not for transactional workloads
      - Steeper learning curve
      - Overkill for Phase 1
    
    Best for: Analytics, very large datasets

Decision: [Your choice]
Rationale: [Why?]
```

**Message Queue** (if needed):

```yaml
Options:
  Redis Pub/Sub:
    - Simple, fast
    - No persistence
    - Good for: Real-time distribution to strategies
  
  RabbitMQ:
    - Persistent queues
    - Routing, exchanges
    - Good for: Reliable delivery, multiple consumers
  
  Apache Kafka:
    - High throughput
    - Persistent, replayable
    - Good for: Event sourcing, multiple services
    - Overkill for: Simple data collection

Decision: [Your choice]
Rationale: [Why?]
```

---

### 2.3 Deployment Architecture

**Single Server (Phase 1)**:

```
┌─────────────────────────────────────┐
│  Your Laptop / Single Server         │
│                                      │
│  ┌──────────────────────────────┐   │
│  │  Docker Compose               │   │
│  │  ┌────────┐  ┌────────┐      │   │
│  │  │  App   │  │  App   │      │   │
│  │  │ (Collector) │ (Enrichment)│   │
│  │  └────────┘  └────────┘      │   │
│  │  ┌────────┐  ┌────────┐      │   │
│  │  │ Postgres│ │ Redis  │      │   │
│  │  └────────┘  └────────┘      │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

**Multi-Server (Phase 2/3)**:

```
┌──────────────┐    ┌──────────────┐
│  Load        │    │  Monitoring  │
│  Balancer    │    │  (Grafana)   │
└──────┬───────┘    └──────────────┘
       │
┌──────┴──────────────────────────────┐
│  App Servers (Auto-scale)            │
│  ┌────┐ ┌────┐ ┌────┐               │
│  │App │ │App │ │App │               │
│  └────┘ └────┘ └────┘               │
└──────┬──────────────────────────────┘
       │
┌──────┴──────────────────────────────┐
│  Data Layer                          │
│  ┌──────────┐  ┌──────────┐         │
│  │ Postgres │  │  Redis   │         │
│  │ Cluster  │  │ Cluster  │         │
│  └──────────┘  └──────────┘         │
└─────────────────────────────────────┘
```

---

## Part 3: Risk Analysis

### 3.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Data loss | Medium | High | Gap detection + auto-backfill |
| Database corruption | Low | Critical | Daily backups, point-in-time recovery |
| WebSocket disconnects | High | Medium | Auto-reconnect, buffer during disconnect |
| Disk full | Medium | High | Retention policies, monitoring |
| Memory exhaustion | Medium | High | Batch processing, limits |
| Indicator calculation too slow | Medium | Medium | Optimize, cache, batch |

### 3.2 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| You get sick/vacation | High | Medium | Documentation, automation |
| Exchange API changes | Medium | High | Abstraction layer, monitoring |
| System crashes at 3 AM | Medium | High | Alerts, auto-restart |
| Data quality issues | High | Medium | Validation, alerts |

---

## Part 4: Capacity Planning

### 4.1 Storage Estimates

**Tick Data** (per symbol, per day):

```
Assumptions:
- 100 ticks/second (varies by symbol)
- 86,400 seconds/day
- ~200 bytes per tick (stored)

Calculation:
100 ticks/sec × 86,400 sec × 200 bytes = 1.7 GB/day/symbol

For 10 symbols:
1.7 GB × 10 = 17 GB/day

For 6 months (180 days):
17 GB × 180 = 3 TB

With compression (3x):
~1 TB for 6 months, 10 symbols
```

**Indicator Data** (per symbol, per day):

```
Assumptions:
- 50 indicators per tick
- 8 bytes per indicator (float64)
- Same tick rate

Calculation:
100 ticks/sec × 86,400 sec × 50 indicators × 8 bytes = 3.5 GB/day/symbol

For 10 symbols, 6 months:
~2 TB uncompressed, ~700 GB compressed
```

**Total Storage** (6 months, 10 symbols):

```
Tick data:      ~1 TB (compressed)
Indicator data: ~700 GB (compressed)
Indexes:        ~300 GB
Overhead:       ~200 GB
─────────────────────────────
Total:          ~2.2 TB
```

**Recommendation**: Start with 500 GB - 1 TB SSD, monitor growth

---

### 4.2 Compute Requirements

**Data Collection** (per symbol):

```
WebSocket handling:    ~10% CPU core
Validation:            ~5% CPU core
Database writes:       ~10% CPU core
─────────────────────────────
Total per symbol:      ~25% CPU core

For 10 symbols:        ~2.5 CPU cores
```

**Indicator Calculation** (per symbol):

```
50 indicators × 100 ticks/sec:
TA-Lib (C-based): ~20% CPU core
Python overhead:  ~10% CPU core
─────────────────────────────
Total per symbol:  ~30% CPU core

For 10 symbols:    ~3 CPU cores
```

**Total Compute** (10 symbols):

```
Data collection:  ~2.5 cores
Enrichment:       ~3 cores
Database:         ~2 cores
Overhead:         ~1 core
─────────────────────────────
Total:            ~8.5 CPU cores
```

**Recommendation**: 8-16 core CPU, 16-32 GB RAM

---

### 4.3 Network Requirements

```
Inbound (WebSocket):
100 ticks/sec × 200 bytes × 10 symbols = 200 KB/sec = ~1.6 Mbps

Outbound (Redis pub/sub, monitoring):
~500 KB/sec = ~4 Mbps

Total: ~6 Mbps continuous

Recommendation: 10+ Mbps connection (most broadband is fine)
```

---

## Part 5: Architecture Review Checklist

### Before Implementation

```yaml
Requirements:
  [ ] Data requirements documented
  [ ] Quality requirements defined
  [ ] Operational requirements clear
  [ ] Stakeholders aligned (if team)

Architecture:
  [ ] Data flow architecture decided
  [ ] Technology choices made
  [ ] Deployment architecture planned
  [ ] Integration points identified

Risks:
  [ ] Technical risks identified
  [ ] Operational risks identified
  [ ] Mitigation strategies defined
  [ ] Acceptable risk level agreed

Capacity:
  [ ] Storage estimates calculated
  [ ] Compute requirements estimated
  [ ] Network requirements checked
  [ ] Budget aligned with requirements

Documentation:
  [ ] Architecture decisions recorded (ADRs)
  [ ] Diagrams created
  [ ] Runbooks drafted
  [ ] Monitoring requirements defined
```

---

## Part 6: Decision Log Template

Create a file: `docs/architecture/decisions/001-<title>.md`

```markdown
# ADR 001: [Title]

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
What is the issue that we're trying to resolve?

## Decision
What is the change that we're proposing?

## Consequences

### Positive
- ...

### Negative
- ...

### Risks
- ...

## Compliance
How will we get compliance with this decision?

## Notes
[Any additional context]
```

---

## Part 7: Next Steps

### After Architecture Phase

1. **Create detailed implementation plan**
   - Break down into sprints
   - Estimate effort per task
   - Identify dependencies

2. **Set up development environment**
   - Docker Compose for local dev
   - CI/CD pipeline
   - Test databases

3. **Start Phase 1, Week 1**
   - Step 001: Project Setup
   - Step 002: Database Schema
   - Step 003: Domain Models

4. **Weekly architecture review**
   - What's working?
   - What needs adjustment?
   - Any new risks identified?

---

## Appendix A: Example Architectures

### Minimal (1-2 symbols, learning)

```yaml
Infrastructure:
  - Single server (your laptop)
  - Docker Compose
  - PostgreSQL only (no Redis initially)
  - File-based logging

Data:
  - 1-2 symbols (BTC/USDT, ETH/USDT)
  - 1-minute candles (not ticks)
  - 30 days historical

Monitoring:
  - Log files
  - Manual checks

Effort: ~2 weeks
```

### Production-Ready (10 symbols)

```yaml
Infrastructure:
  - Dedicated server or cloud VM
  - Docker Compose or Kubernetes
  - PostgreSQL + Redis
  - Centralized logging (ELK or similar)

Data:
  - 10 symbols
  - Ticks + 1-minute candles
  - 6 months historical

Monitoring:
  - Prometheus + Grafana
  - Slack alerts
  - Health check endpoint

Effort: ~8-10 weeks
```

### Enterprise (50+ symbols)

```yaml
Infrastructure:
  - Multi-server cluster
  - Kubernetes
  - PostgreSQL cluster (Patroni)
  - Redis cluster
  - Kafka for event streaming
  - Full observability stack

Data:
  - 50+ symbols
  - Ticks + order book + candles
  - All available historical

Monitoring:
  - Full SRE setup
  - On-call rotation
  - Automated remediation

Effort: ~6 months
```

---

## Appendix B: Questions to Ponder

1. **What happens when Binance goes down for 4 hours?**
   - Will you notice?
   - How will you recover missing data?
   - Will backfill work?

2. **What happens when your disk is 95% full?**
   - Will you get alerted?
   - What data will you delete?
   - How do you prevent recurrence?

3. **What happens when you introduce a bug that corrupts data?**
   - How will you detect it?
   - Can you recover?
   - How do you prevent it happening again?

4. **What happens when indicator calculation takes 10x longer than expected?**
   - Will the system slow down or fail gracefully?
   - Will you get alerted?
   - How do you fix it?

5. **What happens in 6 months when you need 10x more storage?**
   - Did you plan for growth?
   - What's the migration path?
   - What's the cost?

---

## Summary

**Take your time with architecture.** It's much cheaper to change documents than code.

**Recommended approach**:
1. Work through this guide (2-4 days)
2. Create architecture decision records
3. Review with peers (if available)
4. Start implementation with confidence
5. Revisit architecture monthly

**Remember**: Perfect is the enemy of good. Make the best decisions you can with current knowledge, but design for change.

Good luck! 🚀
