# START HERE - Crypto Trading System Architecture

**Welcome!** This is your entry point to the complete architecture documentation.

---

## Quick Overview

**What**: Real-time crypto trading data system with dynamic indicators  
**Phase**: 1 - Data Gathering (Backtesting Infrastructure)  
**Status**: ✅ Architecture Complete, Ready for Implementation  
**Timeline**: 9 weeks total (Weeks 1-2 ready to start)

---

## 🎯 What This System Does

```
┌─────────────────────────────────────────────────────────────┐
│              PHASE 1: DATA GATHERING                         │
│                                                             │
│  Binance WebSocket → Collect → Validate → Store → Enrich   │
│                                                             │
│  Output: High-quality, validated market data for backtesting│
└─────────────────────────────────────────────────────────────┘

NOT in Phase 1:
  ✗ Trading strategies
  ✗ Order execution
  ✗ Risk management
  ✗ Live trading
```

---

## 📁 Document Guide (Read in This Order)

### 1. First Time Setup (30 minutes)

```
✅ STEP 1: Read this document (you're here)
   Time: 10 minutes
   Goal: Understand what you're building

✅ STEP 2: Review Architecture Summary
   Document: ARCHITECTURE-SUMMARY.md
   Time: 15 minutes
   Goal: Understand system components

✅ STEP 3: Review Coding Standards
   Document: CODING-STANDARDS.md
   Time: 5 minutes
   Goal: Understand code quality requirements
```

### 2. Core Architecture (1 hour)

```
✅ Data Flow Design
   Document: data-flow-design.md
   Time: 20 minutes
   Goal: Understand how data moves through system

✅ Modular Services
   Document: modular-service-architecture.md
   Time: 20 minutes
   Goal: Understand Docker service architecture

✅ Database Configuration
   Document: database-configuration-schema.md
   Time: 20 minutes
   Goal: Understand configuration management
```

### 3. Implementation Steps (Start Coding!)

```
✅ Week 1-2: Foundation
   Step 001: implementation/001-project-setup.md
   Step 002: implementation/002-database-schema.md
   Step 003: implementation/003-domain-models.md
   
✅ Week 3-4: Data Collection
   Step 004: (Create this document first)
   Step 005: (Create this document first)
   Step 016: implementation/016-asset-sync-service.md
```

---

## 🚀 Quick Start Checklist

### Before You Start

- [ ] Read this document
- [ ] Review ARCHITECTURE-SUMMARY.md
- [ ] Review CODING-STANDARDS.md
- [ ] Set up development environment (Python 3.11+, PostgreSQL 15+, Docker)
- [ ] Clone repository

### Week 1 Tasks

- [ ] Step 001: Project Setup (2 hours)
  - Create directory structure
  - Create pyproject.toml
  - Set up pre-commit hooks
  - Verify with tests

- [ ] Step 002: Database Schema (4 hours)
  - Create migrations
  - Run initial migration
  - Verify tables created
  - Test helper functions

- [ ] Step 003: Domain Models (4 hours)
  - Implement entities (Symbol, Trade, etc.)
  - Implement value objects
  - Implement domain services
  - Write unit tests (90%+ coverage)

### Week 2 Tasks

- [ ] Create Step 004 document (2 hours)
  - Data Collection Service design
  - WebSocket client details
  - Test requirements

- [ ] Create Step 005 document (2 hours)
  - Repository pattern design
  - Interface definitions
  - Test requirements

- [ ] Continue implementation...

---

## 📊 System Architecture (Simplified)

```
┌────────────────────────────────────────────────────────────┐
│                    INDEPENDENT SERVICES                     │
│                                                            │
│  Core Services (Always Running):                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Collector   │  │   Enricher   │  │  Asset Sync  │    │
│  │  (Trades)    │  │ (Indicators) │  │  (Metadata)  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                            │
│  ┌──────────────┐                                          │
│  │   Ticker     │  ⭐ NEW - Low storage alternative        │
│  │  Collector   │     Collects 24hr stats for all symbols │
│  └──────────────┘                                          │
│                                                            │
│  Shared Infrastructure:                                    │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │  PostgreSQL  │  │    Redis     │                       │
│  │  (Database)  │  │  (Pub/Sub)   │                       │
│  └──────────────┘  └──────────────┘                       │
└────────────────────────────────────────────────────────────┘
```

---

## 🔧 Key Features

### 1. Hybrid Data Collection

```yaml
24hr Ticker Stats:
  - ALL symbols (low storage)
  - 1-second resolution
  - ~43 MB/day/symbol
  - ✅ Recommended for most strategies

Individual Trades:
  - KEY symbols only (BTC, ETH)
  - Every trade
  - ~1.7 GB/day/symbol
  - ✅ For detailed backtesting

Result: 53% storage savings!
```

### 2. Dynamic Configuration

```bash
# All configuration in database (not .env)
# Only DATABASE_URL in .env file

# Change settings without restart
crypto config set-symbol BTC/USDT tick_snapshot_interval_sec 5
crypto config set-symbol BTC/USDT collect_orderbook true

# Changes apply automatically via PostgreSQL NOTIFY
```

### 3. EU Compliance

```yaml
Allowed Quote Assets:
  - USDC ✅
  - BTC ✅
  - ETH ✅
  - USDT ❌ (Not allowed in EU)

Auto-filtering enabled by default
```

### 4. Quality Framework

```python
Validation Rules:
  - Price sanity (no >10% moves)
  - Time monotonicity (no time travel)
  - Precision (tick_size, step_size)
  - Duplicates detection
  - Stale data detection

Quality Metrics:
  - Tracked per hour
  - Quality score (0-100)
  - Alert on issues
```

---

## 💾 Storage Estimates (6 Months, 10 Symbols)

| Data Type | Storage | Notes |
|-----------|---------|-------|
| **24hr Ticker** | ~77 GB | ALL symbols, 1-sec updates |
| **Individual Trades** | ~100 GB | BTC+ETH only, 30 days |
| **Indicators** | ~700 GB | 50 indicators per tick |
| **Order Book** | ~500 GB | Future implementation |
| **TOTAL** | **~1.4 TB** | **53% savings vs. all trades** |

---

## 📝 Coding Standards (Mandatory)

### KISS Principle

```python
# ✅ Simple and clear
def calculate_sma(prices: Sequence[Decimal], period: int) -> Optional[Decimal]:
    """Calculate Simple Moving Average."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / Decimal(period)

# ❌ Over-engineered
def calculate_sma(*args, **kwargs):
    return reduce(lambda acc, x: ..., args)
```

### Type Hints (Mandatory)

```python
# ✅ All parameters and returns typed
def process_ticks(
    ticks: List[Tick],
    config: TickConfig
) -> ProcessTicksResult:
    pass
```

### Documentation (Comprehensive)

```python
class TickerCollector:
    """
    Collects 24hr ticker statistics from Binance.
    
    Purpose: ...
    Example: ...
    Attributes: ...
    """
```

**See CODING-STANDARDS.md for complete requirements.**

---

## 🧪 Testing Requirements

| Layer | Coverage Target |
|-------|-----------------|
| **Domain** | 90%+ |
| **Application** | 80%+ |
| **Infrastructure** | 70%+ |
| **Integration** | 80%+ |

**Test Structure**:
```
tests/
├── unit/
│   ├── domain/      (90%+ coverage)
│   ├── application/ (80%+ coverage)
│   └── infrastructure/
├── integration/
└── e2e/
```

---

## 🔗 Document Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                     START HERE (You!)                        │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Architecture  │   │  Standards    │   │   Implementation
│   Summary     │   │               │   │     Steps     │
└───────────────┘   └───────────────┘   └───────────────┘
        │                   │                   │
        │                   │                   ├─ 001-003 ✅
        ├─ data-flow        │                   ├─ 004-005 ⏳
        ├─ services         ├─ CODING-          ├─ 016-017 ✅
        ├─ configuration    │   STANDARDS       └─ 018-024 ⏳
        └─ regional         └─ LLM-AGENT-
                            REQUIREMENTS
```

---

## ⚠️ Common Pitfalls

### 1. Skipping Documentation

```
❌ BAD: Start coding immediately
✅ GOOD: Read architecture docs first (1-2 hours)
```

### 2. Ignoring Layer Separation

```
❌ BAD: Import database code in domain layer
✅ GOOD: Domain layer has NO external dependencies
```

### 3. Missing Type Hints

```
❌ BAD: def process(ticks, db):
✅ GOOD: def process(ticks: List[Tick], db: TickRepository) -> Result:
```

### 4. Inadequate Testing

```
❌ BAD: 50% test coverage
✅ GOOD: 90%+ domain, 80%+ application
```

---

## 🆘 Getting Help

### Architecture Questions

1. Check ARCHITECTURE-SUMMARY.md
2. Check data-flow-design.md
3. Check ARCHITECTURE-VALIDATION-REPORT.md

### Implementation Questions

1. Check specific step document (001, 002, etc.)
2. Check CODING-STANDARDS.md
3. Check existing tests for examples

### Configuration Questions

1. Check database-configuration-schema.md
2. Check regional-configuration-eu.md
3. Check CLI examples

---

## ✅ Validation Checklist

Before starting implementation, verify:

- [ ] Read this document
- [ ] Read ARCHITECTURE-SUMMARY.md
- [ ] Read CODING-STANDARDS.md
- [ ] Understand layer separation (Domain/Application/Infrastructure)
- [ ] Understand configuration management (database, not .env)
- [ ] Understand hybrid data collection (ticker + trades)
- [ ] Understand EU compliance (regional filtering)
- [ ] Development environment ready
- [ ] Repository cloned

---

## 📋 Implementation Checklist

### Week 1: Foundation

- [ ] Step 001: Project Setup
- [ ] Step 002: Database Schema
- [ ] Step 003: Domain Models

### Week 2: Create Missing Docs

- [ ] Create Step 004 document
- [ ] Create Step 005 document
- [ ] Create Step 018 document

### Week 3-4: Data Collection

- [ ] Step 004: Data Collection Service
- [ ] Step 005: Repository Pattern
- [ ] Step 016: Asset Sync Service

### Week 5: Data Quality

- [ ] Step 017: Data Quality Framework
- [ ] Step 018: Ticker Collector
- [ ] Step 019: Gap Detection

### Week 6-8: Enrichment

- [ ] Step 020: Indicator Framework
- [ ] Step 021: Enrichment Service
- [ ] Step 022: Recalculation Service

### Week 9: Operations

- [ ] Step 023: CLI Tools
- [ ] Step 024: Monitoring

---

## 🎯 Success Criteria

**Phase 1 Complete When**:

- ✅ Collects ticks from Binance (all active symbols)
- ✅ Collects 24hr ticker stats (all symbols)
- ✅ Validates data quality (7 rules)
- ✅ Calculates 10-15 indicators per tick
- ✅ Stores in PostgreSQL (6 months retention)
- ✅ Auto-recalculates on indicator changes
- ✅ CLI for management
- ✅ Health monitoring
- ✅ EU compliant (regional filtering)

---

## 🚀 Next Steps

**Right Now**:

1. ✅ You've read this document
2. → Read ARCHITECTURE-SUMMARY.md (15 min)
3. → Read CODING-STANDARDS.md (5 min)
4. → Start Step 001 (2 hours)

**This Week**:

- Complete Steps 001, 002, 003
- Set up development environment
- Run first tests

---

**Welcome to the project! Let's build something great.** 🎉

**Questions?** Check the document guide above or review ARCHITECTURE-VALIDATION-REPORT.md
