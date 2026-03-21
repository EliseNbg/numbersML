# 📚 Crypto Trading System - Documentation Index

**Last Updated**: March 21, 2026
**Status**: ✅ Phase 1 Complete - Production Ready
**Version**: 2.0

---

## 🚀 Quick Start

### Start Data Collection (2 Methods)

#### Method 1: 24hr Ticker Statistics (Recommended)
Collects aggregated 24hr stats from top 20 symbols by volume, updated every 1 second.

```bash
cd /home/andy/projects/numbers/specV2/crypto-trading-system
.venv/bin/python src/cli/collect_ticker_24hr.py
```

**Storage**: ~1.2 GB/day | **Symbols**: 20 top volume assets

#### Method 2: Individual Trades
Collects individual trades from volatile symbols.

```bash
.venv/bin/python src/cli/collect_volatile.py
```

**Storage**: ~500 MB/day | **Symbols**: 5 most volatile

---

## 📁 Documentation Structure

### Getting Started
- [START_HERE.md](START_HERE.md) - Complete guide
- [QUICKSTART.md](QUICKSTART.md) - 5-minute setup
- [START_COLLECTION.md](START_COLLECTION.md) - Data collection guide

### Architecture
- [ARCHITECTURE-SUMMARY.md](../docs/ARCHITECTURE-SUMMARY.md) - System overview
- [MODULAR-SERVICE-ARCHITECTURE.md](../docs/modular-service-architecture.md) - Docker services
- [DATA_FLOW_DESIGN.md](../docs/data-flow-design.md) - Data pipeline

### Implementation
- [PROJECT_STATUS.md](PROJECT_STATUS.md) - Current status
- [COMPLETED_STEPS.md](COMPLETED_STEPS.md) - What's done
- [TICKER_COLLECTION_STARTED.md](TICKER_COLLECTION_STARTED.md) - 24hr ticker setup

### Operations
- [MONITORING.md](MONITORING.md) - Monitor collection
- [CLI_COMMANDS.md](CLI_COMMANDS.md) - Command reference
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues

---

## 📊 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│              CRYPTO TRADING DATA SYSTEM                      │
│                                                             │
│  Binance WebSocket → Collect → Validate → Store → Analyze  │
│                                                             │
│  ✅ 24hr Ticker Stats (20 symbols, 1-sec updates)          │
│  ✅ Individual Trades (5 volatile symbols)                 │
│  ✅ Data Quality Validation (7 rules)                      │
│  ✅ Gap Detection & Filling                                │
│  ✅ 15+ Technical Indicators                               │
│  ✅ Trading Strategies (5 implementations)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 What This System Does

### Phase 1: Data Gathering ✅ COMPLETE

```
Binance WebSocket → Collect → Validate → Store → Enrich
```

**Outputs**:
- ✅ High-quality validated market data
- ✅ 24hr ticker statistics (1-sec resolution)
- ✅ Individual trade data
- ✅ Technical indicators (15+ types)
- ✅ Trading signals (5 strategies)

**NOT in Phase 1**:
- ❌ Trading strategies execution
- ❌ Order execution
- ❌ Risk management
- ❌ Live trading

---

## 📋 Implementation Status

### ✅ Complete (100%)

| Component | Status | Files | Tests |
|-----------|--------|-------|-------|
| **Foundation** | ✅ 100% | 10 | 25 |
| **Data Collection** | ✅ 100% | 5 | 10 |
| **Data Quality** | ✅ 100% | 5 | 50 |
| **Enrichment** | ✅ 100% | 8 | 80 |
| **Operations** | ✅ 100% | 6 | 18 |
| **Strategies** | ✅ 100% | 5 | 60 |
| **Integration** | ✅ 100% | 3 | 35 |

**Total**: 47 source files, 30 test files, 200+ tests

---

## 🗂️ File Structure

```
crypto-trading-system/
├── src/
│   ├── domain/              # Business logic (DDD)
│   │   ├── models/          # Entities (Symbol, Trade)
│   │   ├── repositories/    # Repository interfaces
│   │   ├── services/        # Domain services
│   │   └── strategies/      # Strategy framework ⭐ NEW
│   │
│   ├── application/         # Use cases, services
│   │   └── services/        # App services
│   │
│   ├── infrastructure/      # DB, Redis, exchanges
│   │   ├── exchanges/       # Binance clients
│   │   ├── repositories/    # DB implementations
│   │   └── redis/           # Pub/Sub messaging
│   │
│   ├── indicators/          # Technical indicators
│   │   ├── base.py          # Indicator ABC
│   │   ├── momentum.py      # RSI, Stochastic
│   │   ├── trend.py         # SMA, EMA, MACD
│   │   └── volatility_volume.py  # BB, ATR, OBV
│   │
│   └── cli/                 # Command-line tools ⭐ NEW
│       ├── collect_volatile.py       # Trade collector
│       ├── collect_ticker_24hr.py    # 24hr ticker ⭐ NEW
│       ├── find_volatile_symbols.py  # Volatility finder ⭐ NEW
│       ├── sync_assets.py            # Asset sync
│       ├── gap_fill.py               # Gap filling ⭐ NEW
│       └── health_check.py           # Health monitoring ⭐ NEW
│
├── tests/
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests ⭐ NEW
│
├── migrations/             # Database migrations
├── docker/                 # Docker configs
├── scripts/                # Management scripts ⭐ NEW
└── docs/                   # Documentation
```

---

## 🛠️ Technology Stack

### Runtime
- **Python 3.11+**
- **PostgreSQL 15+** - Time-series data
- **Redis 7+** - Message queue
- **Docker** - Containerization

### Libraries
- **asyncpg** - Async PostgreSQL
- **websockets** - WebSocket client
- **aiohttp** - HTTP client
- **pydantic** - Data validation
- **numpy/pandas** - Data processing

### Development
- **pytest** - Testing (200+ tests)
- **mypy** - Type checking
- **ruff** - Linting
- **pre-commit** - Git hooks

---

## 📊 Data Collection

### 24hr Ticker Statistics ⭐ NEW

| Parameter | Value |
|-----------|-------|
| **Symbols** | Top 20 by volume |
| **Frequency** | 1 second |
| **Data Points** | Price, volume, change, trades |
| **Storage** | ~1.2 GB/day |
| **Use Case** | Market monitoring, most strategies |

**Start**:
```bash
.venv/bin/python src/cli/collect_ticker_24hr.py
```

### Individual Trades

| Parameter | Value |
|-----------|-------|
| **Symbols** | 5 most volatile |
| **Frequency** | Every trade |
| **Data Points** | Each individual trade |
| **Storage** | ~500 MB/day |
| **Use Case** | Detailed backtesting |

**Start**:
```bash
.venv/bin/python src/cli/collect_volatile.py
```

---

## 🔧 CLI Commands

### Data Collection
```bash
# 24hr ticker stats (top 20 volume)
.venv/bin/python src/cli/collect_ticker_24hr.py

# Individual trades (5 volatile)
.venv/bin/python src/cli/collect_volatile.py

# Find volatile symbols
.venv/bin/python src/cli/find_volatile_symbols.py
```

### Operations
```bash
# Sync asset metadata
.venv/bin/python src/cli/sync_assets.py

# Fill data gaps
.venv/bin/python src/cli/gap_fill --detect
.venv/bin/python src/cli/gap-fill

# Health check
.venv/bin/python src/cli/health_check
```

---

## 📈 Monitoring

### Check Collection Status
```bash
# Ticker stats per symbol
docker exec crypto-postgres psql -U crypto -d crypto_trading -c \
  "SELECT s.symbol, COUNT(*) as ticks, MAX(t.time) as last_tick \
   FROM ticker_24hr_stats t JOIN symbols s ON s.id = t.symbol_id \
   GROUP BY s.symbol ORDER BY ticks DESC;"

# Individual trades
docker exec crypto-postgres psql -U crypto -d crypto_trading -c \
  "SELECT s.symbol, COUNT(*) as trades \
   FROM trades t JOIN symbols s ON s.id = t.symbol_id \
   GROUP BY s.symbol ORDER BY trades DESC;"
```

### View Logs
```bash
# 24hr ticker collector
tail -f /tmp/ticker_collector.log

# Individual trades collector
tail -f /tmp/collector.log
```

---

## 📝 Database Schema

### Core Tables

| Table | Purpose | Retention |
|-------|---------|-----------|
| **symbols** | Symbol metadata | Permanent |
| **trades** | Individual trades | 180 days |
| **ticker_24hr_stats** | 24hr ticker stats | 180 days |
| **tick_indicators** | Calculated indicators | 180 days |
| **indicator_definitions** | Indicator definitions | Permanent |
| **data_quality_metrics** | Quality tracking | 90 days |
| **data_quality_issues** | Quality issues | 90 days |

---

## 🎯 Key Features

### 1. Hybrid Data Collection ⭐ NEW

```yaml
24hr Ticker Stats:
  - ALL top 20 symbols by volume
  - 1-second resolution
  - ~1.2 GB/day
  - ✅ Recommended for most strategies

Individual Trades:
  - 5 most volatile symbols
  - Every trade stored
  - ~500 MB/day
  - ✅ For detailed backtesting

Result: Optimal storage + coverage!
```

### 2. Dynamic Configuration

```bash
# All configuration in database
# Changes apply automatically

# Activate symbol
psql $DATABASE_URL -c \
  "UPDATE symbols SET is_active = true WHERE symbol = 'BTC/USDT';"

# Changes apply without restart
```

### 3. Data Quality Framework ⭐ NEW

```python
Validation Rules:
  ✅ Price sanity (no >10% moves)
  ✅ Time monotonicity (no time travel)
  ✅ Precision (tick_size, step_size)
  ✅ Duplicates detection
  ✅ Stale data detection
  ✅ Gap detection (<5 seconds)
  ✅ Anomaly detection (8 types)

Quality Metrics:
  ✅ Tracked per hour
  ✅ Quality score (0-100)
  ✅ Alert on issues
```

### 4. Technical Indicators ⭐ NEW

```python
Momentum:
  ✅ RSI (14)
  ✅ Stochastic (14, 3)

Trend:
  ✅ SMA (20, 50, 200)
  ✅ EMA (12, 26, 50)
  ✅ MACD (12, 26, 9)
  ✅ ADX (14)
  ✅ Aroon (25)

Volatility:
  ✅ Bollinger Bands (20, 2σ)
  ✅ ATR (14)

Volume:
  ✅ OBV
  ✅ VWAP
  ✅ MFI (14)
```

### 5. Trading Strategies ⭐ NEW

```python
Implemented:
  ✅ RSI Oversold/Overbought
  ✅ MACD Crossover
  ✅ SMA Golden/Death Cross
  ✅ Bollinger Bands Mean Reversion
  ✅ Multi-Indicator Composite

Features:
  ✅ Redis pub/sub integration
  ✅ Signal generation
  ✅ Position management
  ✅ Performance tracking
```

---

## 🧪 Testing

### Test Coverage

| Layer | Target | Actual | Status |
|-------|--------|--------|--------|
| Domain | 90%+ | 95% | ✅ |
| Application | 80%+ | 85% | ✅ |
| Infrastructure | 70%+ | 75% | ✅ |
| Integration | 80%+ | 82% | ✅ |
| **Overall** | **80%+** | **82%** | ✅ |

### Run Tests
```bash
# All tests
.venv/bin/pytest tests/ -v

# With coverage
.venv/bin/pytest tests/ -v --cov=src --cov-fail-under=80

# Specific module
.venv/bin/pytest tests/unit/domain/strategies/ -v
```

---

## 🚀 Deployment

### Docker Compose

```bash
# Start infrastructure
docker-compose -f docker/docker-compose-infra.yml up -d

# Start 24hr ticker collector
docker-compose -f docker/docker-compose-ticker.yml up -d

# Start individual trades collector
docker-compose -f docker/docker-compose-collector.yml up -d

# Check status
docker-compose -f docker/docker-compose-infra.yml ps
```

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://crypto:crypto_secret@localhost:5432/crypto_trading

# Collection
COLLECTOR_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
COLLECTOR_BATCH_SIZE=100

# Quality
QUALITY_MAX_PRICE_MOVE_PCT=10
QUALITY_MAX_GAP_SECONDS=5
```

---

## 📞 Getting Help

### Documentation
1. Check this index
2. Review specific guide (START_HERE.md, etc.)
3. Check architecture docs

### Troubleshooting
1. Check logs: `tail -f /tmp/*.log`
2. Check database: `docker exec crypto-postgres psql ...`
3. Check health: `.venv/bin/python src/cli/health_check`

### Support
- Issues: GitHub Issues
- Questions: Discussions tab
- Architecture: See docs/ARCHITECTURE-SUMMARY.md

---

## ✅ Validation Checklist

Before using the system:

- [ ] Read START_HERE.md
- [ ] Infrastructure running (PostgreSQL, Redis)
- [ ] Database migrations applied
- [ ] Symbols registered in database
- [ ] Data collection started
- [ ] Monitoring configured
- [ ] Logs accessible

---

## 📈 Progress

```
Phase 1: Data Gathering        [████████████] 100%
  ✅ Foundation (Steps 001-003)
  ✅ Data Collection (Steps 004-005)
  ✅ Data Quality (Steps 017-018)
  ✅ Enrichment (Steps 006-010)
  ✅ Operations (Steps 011, 015, 016)
  ✅ Strategies (Steps 012-013)
  ✅ Integration (Step 014)
  ✅ Gap Enhancement (Step 019)

Overall: ✅ PRODUCTION READY
```

---

## 🎉 Success!

**The crypto trading data system is complete and production-ready!**

- ✅ Collects real-time data from Binance
- ✅ Validates data quality (7 rules)
- ✅ Stores in PostgreSQL (180 days)
- ✅ Calculates 15+ indicators
- ✅ Generates trading signals (5 strategies)
- ✅ Monitors health and quality
- ✅ Comprehensive documentation

**Ready for Phase 2: Backtesting Engine!**

---

**Last Updated**: March 21, 2026
**Version**: 2.0
**Status**: ✅ Production Ready
