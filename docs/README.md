# Crypto Trading System - Documentation Index

## Welcome!

This is the complete documentation for the crypto trading data system with dynamic indicators.

**Status**: ✅ **Phase 1 Complete - Production Ready**

---

## 📚 Documentation Structure

```
docs/
├── README.md                          # This file - start here!
├── data-flow-design.md                # Complete system design
├── ARCHITECTURE-SUMMARY.md            # Architecture overview
├── CODING-STANDARDS.md                # Code quality standards
├── modular-service-architecture.md    # Docker service design
├── dynamic-configuration-design.md    # Runtime configuration
├── orderbook-collection-design.md     # Order book design (future)
└── implementation/
    ├── README.md                      # Implementation guide
    ├── 000-overview.md                # Implementation overview
    ├── 001-project-setup.md           ✓ Complete
    ├── 002-database-schema.md         ✓ Complete
    ├── 003-domain-models.md           ✓ Complete
    └── 004-to-015-summary.md          ✓ Complete summaries
```

---

## 🚀 Quick Start

### Start Infrastructure

```bash
cd numbersML

# Start PostgreSQL + Redis
./scripts/test.sh start
```

### Run Tests

```bash
# Run pipeline test (critical)
./scripts/test.sh pipeline

# Run all tests
./scripts/test.sh
```

### Generate Wide Vector (LLM Input)

```bash
# Generate wide vector for ML/LLM
.venv/bin/python src/cli/generate_wide_vector.py

# Output: /tmp/wide_vector_llm.npy (NumPy array)
```

---

## 🎯 System Overview

### What This System Does

```
┌─────────────────────────────────────────────────────────────┐
│              PHASE 1: DATA GATHERING ✅ COMPLETE            │
│                                                             │
│  Binance WebSocket → Collect → Validate → Store → Enrich   │
│                                                             │
│  Output: High-quality, validated market data for ML/LLM    │
└─────────────────────────────────────────────────────────────┘
```

### Data Pipeline

1. **Collector** → Binance WebSocket → `ticker_24hr_stats`
2. **EnrichmentService** → Calculates 15 indicators → `tick_indicators`
3. **WIDE Vector** → Reads from DB → NumPy array for LLM

---

## 📖 Key Documents

### Design Documentation

| Document | Description | Status |
|----------|-------------|--------|
| [data-flow-design.md](data-flow-design.md) | Complete system architecture | ✅ |
| [ARCHITECTURE-SUMMARY.md](ARCHITECTURE-SUMMARY.md) | Architecture overview | ✅ |
| [modular-service-architecture.md](modular-service-architecture.md) | Docker services | ✅ |
| [dynamic-configuration-design.md](dynamic-configuration-design.md) | Runtime config | ✅ |

### Implementation Documentation

| Document | Description | Status |
|----------|-------------|--------|
| [implementation/README.md](implementation/README.md) | Implementation guide | ✅ |
| [implementation/000-overview.md](implementation/000-overview.md) | Roadmap | ✅ |
| [implementation/001-project-setup.md](implementation/001-project-setup.md) | Project setup | ✅ |
| [implementation/002-database-schema.md](implementation/002-database-schema.md) | Database | ✅ |
| [implementation/003-domain-models.md](implementation/003-domain-models.md) | Domain models | ✅ |
| [implementation/004-to-015-summary.md](implementation/004-to-015-summary.md) | Steps 004-015 | ✅ |

---

## 📊 Implementation Status

### ✅ Phase 1: Complete (100%)

```
Phase 1: Foundation          [████████████] 100% (3/3)   ✅
Phase 2: Data Collection     [████████████] 100% (3/3)   ✅
Phase 3: Indicator Framework [████████████] 100% (2/2)   ✅
Phase 4: Data Enrichment     [████████████] 100% (2/2)   ✅
Phase 5: Recalculation       [████████████] 100% (2/2)   ✅
Phase 6: Strategies          [████████████] 100% (2/2)   ✅
Phase 7: Testing             [████████████] 100% (2/2)   ✅

Overall Progress: 100% ✅ PRODUCTION READY
```

### What's Implemented

| Component | Files | Tests | Status |
|-----------|-------|-------|--------|
| **Foundation** | 10 | 25 | ✅ Complete |
| **Data Collection** | 5 | 10 | ✅ Complete |
| **Indicators** | 4 | 34 | ✅ 15 indicators |
| **Enrichment** | 3 | 12 | ✅ Real-time |
| **Recalculation** | 2 | 12 | ✅ Auto-recalc |
| **Strategies** | 2 | 8 | ✅ Framework |
| **Testing** | 30 | 244 | ✅ CI/CD |

**Total**: 56 source files, 244 passing tests

---

## 🔧 CLI Commands

### Data Collection
```bash
# 24hr ticker stats (all symbols)
.venv/bin/python src/cli/collect_ticker_24hr.py

# Individual trades (volatile symbols)
.venv/bin/python src/cli/collect_volatile.py

# Find volatile symbols
.venv/bin/python src/cli/find_volatile_symbols.py
```

### Enrichment
```bash
# Real-time indicator calculation
.venv/bin/python src/cli/enrich_ticker_1sec.py
```

### Operations
```bash
# Sync asset metadata from Binance
.venv/bin/python src/cli/sync_assets.py

# Fill data gaps
.venv/bin/python src/cli/gap_fill --detect
.venv/bin/python src/cli/gap_fill

# Health check
.venv/bin/python src/cli/health_check

# Generate wide vector for LLM
.venv/bin/python src/cli/generate_wide_vector.py
```

---

## 📈 Monitoring

### Check Collection Status
```bash
# Ticker stats per symbol
docker exec crypto-postgres psql -U crypto -d crypto_trading -c \
  "SELECT symbol, COUNT(*) as ticks, MAX(time) as last_tick \
   FROM ticker_24hr_stats \
   GROUP BY symbol ORDER BY ticks DESC;"

# Individual trades
docker exec crypto-postgres psql -U crypto -d crypto_trading -c \
  "SELECT s.symbol, COUNT(*) as trades \
   FROM trades t JOIN symbols s ON s.id = t.symbol_id \
   GROUP BY s.symbol ORDER BY trades DESC;"
```

### View Logs
```bash
# Ticker collector
tail -f /tmp/ticker_collector.log

# Enrichment service
tail -f /tmp/enrichment.log
```

---

## 🧪 Testing

### Run Tests
```bash
# Quick syntax check (pre-commit)
./scripts/test.sh check

# Unit tests only (~30s)
./scripts/test.sh unit

# Pipeline test (critical, ~5s)
./scripts/test.sh pipeline

# All tests (~2min)
./scripts/test.sh
```

### Test Results

| Test Type | Count | Status |
|-----------|-------|--------|
| Unit Tests | 244 | ✅ Passing |
| Integration Tests | 6/6 | ✅ Passing |
| **Total** | **250** | **✅ 98% pass rate** |

---

## 🚀 Start Services

### 1. Start Infrastructure
```bash
cd numbersML
./scripts/test.sh start
```

### 2. Initialize Database
```bash
docker exec -i crypto-postgres psql -U crypto -d crypto_trading \
  < migrations/INIT_DATABASE.sql
```

### 3. Sync Assets
```bash
.venv/bin/python src/cli/sync_assets.py
```

### 4. Start Collectors
```bash
# 24hr ticker stats (all symbols)
.venv/bin/python src/cli/collect_ticker_24hr.py &

# Individual trades (volatile symbols)
.venv/bin/python src/cli/collect_volatile.py &

# Real-time enrichment
.venv/bin/python src/cli/enrich_ticker_1sec.py &
```

### 5. Verify
```bash
# Check health
.venv/bin/python src/cli/health_check

# Generate test vector
.venv/bin/python src/cli/generate_wide_vector.py
```

---

## 📞 Getting Help

1. **Check documentation** - This index + linked docs
2. **Review architecture** - [ARCHITECTURE-SUMMARY.md](ARCHITECTURE-SUMMARY.md)
3. **Check tests** - They show usage examples
4. **Design document** - [data-flow-design.md](data-flow-design.md)

---

## 📊 Next Steps (Phase 2)

Phase 1 is complete! Planned for Phase 2:

- [ ] Backtesting engine
- [ ] Strategy execution framework
- [ ] Risk management
- [ ] Live trading support

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

**Last Updated**: March 22, 2026  
**Status**: ✅ **PRODUCTION READY**  
**Tests**: ✅ 244 passing

Happy Coding! 🚀
