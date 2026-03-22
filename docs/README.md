# Crypto Trading System - Documentation Index

## Welcome!

This is the complete documentation for the crypto trading data system with dynamic indicators.

---

## 📚 Documentation Structure

```
docs/
├── README.md                          # This file - start here!
├── data-flow-design.md                # Complete system design
└── implementation/
    ├── README.md                      # Implementation guide
    ├── 000-overview.md                # Implementation overview
    ├── 001-project-setup.md           ✓ Complete
    ├── 002-database-schema.md         ✓ Complete
    ├── 003-domain-models.md           ✓ Complete
    ├── 004-to-015-summary.md          📋 Summaries for remaining steps
    └── [004-015 individual step docs] (to be created)
```

---

## 🚀 Getting Started

### New to the Project?

1. **Read this index** (you're here!) ✓
2. **Review the design** → [data-flow-design.md](data-flow-design.md)
3. **Start implementation** → [implementation/README.md](implementation/README.md)

### Already Started?

- **Completed steps 001-003?** → Continue with step 004 (see [implementation/004-to-015-summary.md](implementation/004-to-015-summary.md))
- **Need design reference?** → [data-flow-design.md](data-flow-design.md)

---

## 📖 Key Documents

### Design Documentation

| Document | Description | Status |
|----------|-------------|--------|
| [data-flow-design.md](data-flow-design.md) | Complete system architecture, database schema, services | ✅ Complete |

**What's in the design doc:**
- 4-stage data pipeline architecture
- PostgreSQL schema with dynamic indicators
- Service implementations (DataCollector, Enrichment, Recalculation)
- Indicator framework (Python-based, dynamic)
- Redis pub/sub for strategy integration
- Active symbol filtering

### Implementation Documentation

| Document | Description | Status |
|----------|-------------|--------|
| [implementation/README.md](implementation/README.md) | Guide for implementing the system | ✅ Complete |
| [implementation/000-overview.md](implementation/000-overview.md) | Implementation roadmap | ✅ Complete |
| [implementation/001-project-setup.md](implementation/001-project-setup.md) | Project structure, dependencies | ✅ Complete |
| [implementation/002-database-schema.md](implementation/002-database-schema.md) | Database setup, migrations | ✅ Complete |
| [implementation/003-domain-models.md](implementation/003-domain-models.md) | DDD domain layer | ✅ Complete |
| [implementation/004-to-015-summary.md](implementation/004-to-015-summary.md) | Steps 004-015 summaries | ✅ Complete |

---

## 🎯 System Overview

### What This System Does

```
┌─────────────────────────────────────────────────────────────────┐
│                    CRYPTO TRADING DATA SYSTEM                    │
└─────────────────────────────────────────────────────────────────┘

  Binance WebSocket → [Collect] → PostgreSQL → [Enrich] → Redis
       │                                              │
       │                                              ▼
       │                                    Strategies (plugins)
       │
       └── 6 months historical ← [Backfill]
```

### Key Features

✅ **Real-time data collection** - Binance WebSocket, tick-level precision  
✅ **Dynamic indicators** - Add/change indicators without schema changes  
✅ **Automatic recalculation** - Indicators recalculate when definitions change  
✅ **Flexible storage** - PostgreSQL with JSONB for indicator values  
✅ **Strategy integration** - Redis pub/sub for real-time signals  
✅ **Active symbol filtering** - Only process symbols you care about  

### What This System is NOT

❌ Not a trading bot (no order execution yet)  
❌ Not a backtesting engine (phase 2)  
❌ Not a live trading system (phase 3)  

---

## 📋 Implementation Steps

### Phase 1: Foundation ✅

- [x] **Step 001**: Project setup
- [x] **Step 002**: Database schema
- [x] **Step 003**: Domain models

### Phase 2: Data Collection 📋

- [ ] **Step 004**: Data collection service (Binance WebSocket)
- [ ] **Step 005**: Repository pattern
- [ ] **Step 016**: Binance asset metadata sync (daily) ✨ NEW

### Phase 3: Indicator Framework 📋

- [ ] **Step 006**: Indicator framework (base classes, registry)
- [ ] **Step 007**: Indicator implementations (RSI, MACD, SMA, etc.)

### Phase 4: Data Enrichment 📋

- [ ] **Step 008**: Enrichment service (real-time calculation)
- [ ] **Step 009**: Redis pub/sub

### Phase 5: Recalculation 📋

- [ ] **Step 010**: Recalculation service (auto on change)
- [ ] **Step 011**: CLI tools

### Phase 6: Strategy Integration 📋

- [ ] **Step 012**: Strategy interface
- [ ] **Step 013**: Sample strategies

### Phase 7: Testing & Hardening 📋

- [ ] **Step 014**: Integration tests
- [ ] **Step 015**: Monitoring & logging

---

## 🧪 Test Coverage

**Target**: 75%+ overall

| Component | Target | Status |
|-----------|--------|--------|
| Domain Layer | 90%+ | ✅ Specified |
| Database | 80%+ | ✅ Specified |
| Services | 70%+ | 📋 Planned |
| Integration | 80%+ | 📋 Planned |
| E2E | 50%+ | 📋 Planned |

---

## 🛠️ Technology Stack

### Runtime

- **Python 3.11+**
- **PostgreSQL 15+** - Time-series data
- **Redis 7+** - Message queue
- **TA-Lib** - Technical analysis

### Development

- **pytest** - Testing
- **mypy** - Type checking
- **ruff** - Linting
- **black** - Formatting
- **pre-commit** - Git hooks

### Infrastructure

- **asyncpg** - Async PostgreSQL
- **redis-py** - Redis client
- **websockets** - WebSocket client
- **pydantic** - Data validation

---

## 📁 Project Structure

```
crypto-trading-system/
├── src/
│   ├── domain/              # Business logic (DDD)
│   ├── application/         # Use cases, services
│   ├── infrastructure/      # DB, Redis, exchanges
│   ├── indicators/          # Indicator framework
│   └── strategies/          # Trading strategies
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   ├── data-flow-design.md
│   └── implementation/
│
├── scripts/
├── config/
└── migrations/
```

---

## 🎓 Learning Resources

### Domain-Driven Design

- [Martin Fowler - DDD](https://martinfowler.com/tags/domain_driven_design.html)
- [DDD Quick Reference](https://www.infoq.com/minibooks/domain-driven-design-quickly)

### Technical Analysis

- [TA-Lib Documentation](https://ta-lib.github.io/ta-lib-python/)
- [Technical Indicators Explained](https://www.investopedia.com/technical-analysis-4689657)

### Python Async

- [asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
- [Effective Python Async](https://effectivepython.com/)

---

## 🔧 Quick Commands

```bash
# Setup
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run migrations
python scripts/migrate.py

# Run tests
pytest

# Check code quality
mypy src
ruff check src
pre-commit run --all-files

# Start services (after implementation)
crypto-collect
crypto-enrich
crypto-recalc
```

---

## 📞 Getting Help

1. **Check documentation** - It's comprehensive!
2. **Review step documents** - Each step has troubleshooting
3. **Check tests** - They show usage examples
4. **Design document** - Full architecture reference

---

## 🎯 Next Steps

### If You're New

1. ✅ You've read this index
2. → Read [data-flow-design.md](data-flow-design.md)
3. → Start with [implementation/001-project-setup.md](implementation/001-project-setup.md)

### If You've Completed Steps 001-003

1. → Continue with step 004 (see [implementation/004-to-015-summary.md](implementation/004-to-015-summary.md))

---

## 📊 Progress

```
Phase 1: Foundation          [████████████] 100% (3/3)
Phase 2: Data Collection     [█           ]  33% (1/3)
Phase 3: Indicator Framework [            ]   0% (0/2)
Phase 4: Data Enrichment     [            ]   0% (0/2)
Phase 5: Recalculation       [            ]   0% (0/2)
Phase 6: Strategies          [            ]   0% (0/2)
Phase 7: Testing             [            ]   0% (0/2)

Overall Progress: 19% (3/16 steps)
```

---

## 📝 License

MIT License - see LICENSE file

---

## 🙏 Contributing

1. Fork the repository
2. Create a feature branch
3. Follow the implementation steps
4. Write tests
5. Submit a pull request

See [implementation/README.md](implementation/README.md) for contribution guidelines.

---

**Happy Coding! 🚀**
