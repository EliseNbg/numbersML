# 📊 numbersML

**Real-time crypto trading data infrastructure for ML/LLM models**

[![Tests](https://github.com/EliseNbg/numbersML/actions/workflows/ci.yml/badge.svg)](https://github.com/EliseNbg/numbersML/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🚀 Quick Start

```bash
# 1. Clone and enter project
git clone https://github.com/EliseNbg/numbersML.git
cd numbersML

# 2. Start infrastructure (PostgreSQL + Redis)
./scripts/test.sh start

# 3. Run the critical pipeline test
./scripts/test.sh pipeline

# 4. Backfill historical data (optional)
.venv/bin/python src/cli/backfill.py --days 7

# 5. Generate a wide vector for LLM input
.venv/bin/python src/cli/generate_wide_vector.py
```

**That's it!** You now have:
- ✅ Real-time market data collection
- ✅ 15+ technical indicators calculated
- ✅ Historical backfill capability
- ✅ Wide vector ready for ML/LLM models

---

## 📋 What is numbersML?

**numbersML** is a production-ready data infrastructure that:

1. **Collects** real-time crypto market data from Binance
2. **Validates** data quality with 7+ rules
3. **Calculates** 15+ technical indicators in real-time
4. **Generates** wide vectors for ML/LLM consumption

```
┌─────────────────────────────────────────────────────────────┐
│                    numbersML Pipeline                        │
│                                                              │
│  Binance WebSocket → Validate → Store → Enrich → ML Vector  │
│                                                              │
│  • 24hr ticker stats (all symbols)                          │
│  • Individual trades (volatile symbols)                     │
│  • 15+ indicators (RSI, MACD, SMA, EMA, BB, etc.)          │
│  • Wide vector output for LLM/ML models                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Features

| Feature | Description |
|---------|-------------|
| **Real-time Collection** | 24hr ticker stats + individual trades from Binance |
| **Data Quality** | 7 validation rules + 8 anomaly detectors |
| **Technical Indicators** | 15+ indicators (momentum, trend, volatility, volume) |
| **Wide Vector Output** | Single flat vector for all symbols → LLM ready |
| **Test Suite** | 244 passing tests, enforced in CI/CD |
| **GitHub Actions** | Auto-test on every push/PR |

---

## 📊 Indicators

### Momentum (2)
- RSI (14)
- Stochastic (14, 3)

### Trend (5)
- SMA (20, 50, 200)
- EMA (12, 26, 50)
- MACD (12, 26, 9)
- ADX (14)
- Aroon (25)

### Volatility (2)
- Bollinger Bands (20, 2σ)
- ATR (14)

### Volume (3)
- OBV
- VWAP
- MFI (14)

---

## 🗂️ Project Structure

```
numbersML/
├── src/
│   ├── application/         # Application services
│   │   └── services/        # Enrichment, Recalculation, Asset Sync
│   ├── cli/                 # CLI tools
│   │   ├── backfill.py              # Historical data backfill ⭐ NEW
│   │   ├── generate_wide_vector.py  # LLM vector generator
│   │   ├── sync_assets.py           # Asset metadata sync
│   │   └── health_check.py          # System health
│   ├── domain/              # Domain models (DDD)
│   ├── infrastructure/      # DB, Redis, Binance clients
│   └── indicators/          # 15+ technical indicators
│       ├── base.py          # Indicator ABC
│       ├── momentum.py      # RSI, Stochastic
│       ├── trend.py         # SMA, EMA, MACD, ADX, Aroon
│       └── volatility_volume.py  # BB, ATR, OBV, VWAP, MFI
│
├── tests/
│   ├── unit/                # Unit tests (244 passing)
│   └── integration/         # Integration tests (6/6 passing)
│
├── migrations/              # Database migrations
│   └── INIT_DATABASE.sql    # Complete schema (12 tables)
│
├── scripts/
│   └── test.sh              # Test runner
│
└── docker/
    └── docker-compose-infra.yml  # PostgreSQL + Redis
```

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.11+ |
| **Database** | PostgreSQL 15+ (time-series data) |
| **Cache** | Redis 7+ (pub/sub messaging) |
| **Data Processing** | NumPy, Pandas |
| **Testing** | pytest (244 tests) |
| **CI/CD** | GitHub Actions |
| **Deployment** | Docker |

---

## 📁 Documentation

| Document | Purpose |
|----------|---------|
| [QUICKSTART.md](QUICKSTART.md) | 1-minute setup guide |
| [GITHUB_SETUP.md](GITHUB_SETUP.md) | GitHub + CI/CD configuration |
| [TEST_ENFORCEMENT.md](TEST_ENFORCEMENT.md) | Test policy and enforcement |
| [docs/00-START-HERE.md](docs/00-START-HERE.md) | Complete architecture guide |
| [docs/data-flow-design.md](docs/data-flow-design.md) | Data pipeline design |
| [docs/modular-service-architecture.md](docs/modular-service-architecture.md) | Service architecture |

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

## 🔧 CLI Commands

### Data Generation
```bash
# Generate wide vector for LLM
.venv/bin/python src/cli/generate_wide_vector.py

# Output files:
# /tmp/wide_vector_llm.json  - JSON format
# /tmp/wide_vector_llm.npy   - NumPy array
# /tmp/wide_vector_columns.json - Column names
```

### Operations
```bash
# Sync asset metadata from Binance
.venv/bin/python src/cli/sync_assets.py

# Health check
.venv/bin/python src/cli/health_check

# Backfill historical data (NEW!)
.venv/bin/python src/cli/backfill.py --days 7
```

### Backfill Examples
```bash
# Backfill last 3 days (default) for all active symbols
python -m src.cli.backfill.py

# Backfill last 7 days
python -m src.cli.backfill.py --days 7

# Backfill specific symbol
python -m src.cli.backfill.py --days 3 --symbol BTC/USDT

# Dry run (test without inserting)
python -m src.cli.backfill.py --days 3 --dry-run
```

---

## 📈 Wide Vector Format

The wide vector generator produces a **single flat vector** with all symbols' data:

```python
# Load in Python
import numpy as np

vector = np.load('/tmp/wide_vector_llm.npy')
# Shape: (9198,) for 657 symbols × 14 features

# Reshape for transformer model
# (batch=1, symbols=657, features=14)
vector_reshaped = vector.reshape(1, 657, 14)

# Pass to LLM for buy/sell/hold decisions
```

### Features per Symbol (14)

| Feature | Description |
|---------|-------------|
| `last_price` | Current price |
| `open_price` | 24hr open |
| `high_price` | 24hr high |
| `low_price` | 24hr low |
| `volume` | 24hr volume |
| `quote_volume` | 24hr quote volume |
| `price_change` | Price change |
| `price_change_pct` | Price change % |
| `rsi_14_rsi` | RSI indicator |
| `sma_20_sma` | 20-period SMA |
| `sma_50_sma` | 50-period SMA |
| `macd_macd` | MACD value |
| `bb_upper_upper` | Bollinger upper band |
| `bb_lower_lower` | Bollinger lower band |

---

## 🚀 Deployment

### Local Development

```bash
# Start infrastructure
./scripts/test.sh start

# Run collectors (optional)
.venv/bin/python src/cli/collect_ticker_24hr.py
.venv/bin/python src/cli/collect_volatile.py

# Generate vectors
.venv/bin/python src/cli/generate_wide_vector.py
```

### Docker

```bash
# Start PostgreSQL + Redis
docker compose -f docker/docker-compose-infra.yml up -d

# Check status
docker compose -f docker/docker-compose-infra.yml ps
```

### GitHub Actions

Every push/PR triggers:
1. ✅ Quick Check (syntax/imports)
2. ✅ Unit Tests (244 tests)
3. ✅ Integration Tests (with PostgreSQL + Redis)
4. ✅ Pipeline Test (critical path)

---

## ✅ Validation Checklist

Before using in production:

- [ ] Infrastructure running (`./scripts/test.sh start`)
- [ ] Database initialized (`./scripts/test.sh pipeline`)
- [ ] All tests passing (`./scripts/test.sh`)
- [ ] Wide vector generates successfully
- [ ] Monitoring configured

---

## 📊 Current Status

| Component | Status | Tests |
|-----------|--------|-------|
| **Data Collection** | ✅ Complete | 10/10 |
| **Data Quality** | ✅ Complete | 50/50 |
| **Indicators** | ✅ 15 indicators | 29/29 |
| **Enrichment Service** | ✅ Complete | 8/8 |
| **Wide Vector** | ✅ Complete | 16/16 |
| **Historical Backfill** | ✅ Complete ⭐ NEW | 6/6 |
| **Test Suite** | ✅ 250 passing | 250/250 |
| **CI/CD** | ✅ GitHub Actions | ✅ |

**Overall**: ✅ **Phase 1 Complete - Production Ready**

### Phase 1 Progress

```
Phase 1: Data Gathering        [████████████] 100%
  ✅ Foundation (Steps 001-003)
  ✅ Data Collection (Steps 004-005)
  ✅ Data Quality (Steps 017-018)
  ✅ Enrichment (Steps 006-010)
  ✅ Operations (Steps 011, 015, 016)
  ✅ Historical Backfill (Step 020) ⭐ NEW
  ✅ Wide Vector (Step 014)
  ✅ Test Suite (6/6 passing)
  ✅ CI/CD Pipeline

Overall: ✅ PRODUCTION READY
```

---

## 🎯 What's Next (Phase 2)

Phase 1 is complete! Planned for Phase 2:

- [ ] Backtesting engine
- [ ] Strategy execution framework
- [ ] Risk management
- [ ] Live trading support

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/EliseNbg/numbersML/issues)
- **Discussions**: [GitHub Discussions](https://github.com/EliseNbg/numbersML/discussions)
- **Architecture**: See [docs/](docs/) folder

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

**Last Updated**: March 22, 2026  
**Version**: 4.0 - Phase 1 Complete  
**Status**: ✅ Production Ready  
**Tests**: ✅ 250 passing  
**Backfill**: ✅ Tested (87,000 records for BTC/USDT)
