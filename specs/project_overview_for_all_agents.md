# Trading Backend - Project Overview for All Agents

**Project:** Multi-Strategy Trading Backend  
**Version:** 1.0  
**Date:** 2026-03-15  
**Architect:** Claw (Senior Software Architect)

---

## 🎯 Project Goal

Build a scalable, low-latency trading backend for cryptocurrency and stock trading with:
- **<40ms latency** end-to-end
- **1-second candle intervals** (scalping support)
- **Parallel strategy execution** (training & testing)
- **Clean architecture** (hexagonal/ports & adapters)
- **Python 3.11+** stack

---

## 🏗️ Architecture Summary

### Technology Stack
| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Python 3.11+ | All application code |
| Database | PostgreSQL 16 | Persistent storage (orders, trades, candles) |
| Cache | Redis 7 | Low-latency cache + pub/sub |
| Exchange | Binance (crypto), Yahoo Finance (stocks) | Market data + execution |
| Deployment | Docker Compose | Final deployment (local dev is native Python) |

### Architecture Pattern
**Modular Monolith with Hexagonal Architecture**
- Domain layer: Business logic (pure Python, no external deps)
- Ports layer: Interfaces (repositories, exchanges, cache)
- Adapters layer: Implementations (PostgreSQL, Redis, Binance)
- Services layer: Application coordination

### Data Flow
```
Binance WebSocket → Data Ingest → Redis Cache → Strategy Engine → Signals
                                                              ↓
PostgreSQL ← Order Manager ← Risk Manager ← Signal Processor
```

---

## 📁 Project Structure

```
trading-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuration (pydantic-settings)
│   ├── logging_config.py       # Structured logging (structlog)
│   ├── domain/                 # Domain layer (business logic)
│   │   ├── __init__.py
│   │   ├── models.py           # Domain entities
│   │   ├── services.py         # Domain services
│   │   └── exceptions.py       # Domain exceptions
│   ├── ports/                  # Ports layer (interfaces)
│   │   ├── __init__.py
│   │   ├── repositories.py     # Repository interfaces
│   │   ├── exchanges.py        # Exchange interfaces
│   │   ├── cache.py            # Cache interfaces
│   │   └── strategies.py       # Strategy interfaces
│   └── adapters/               # Adapters layer (implementations)
│       ├── __init__.py
│       ├── repositories/       # PostgreSQL repositories
│       ├── exchanges/          # Binance, Yahoo adapters
│       └── cache/              # Redis cache
├── services/                   # Application services
│   ├── __init__.py
│   ├── data_ingest.py          # Market data ingestion
│   ├── strategy_runner.py      # Strategy execution
│   ├── order_manager.py        # Order lifecycle
│   ├── risk_manager.py         # Risk controls
│   └── position_tracker.py     # Position tracking
├── strategies/                 # User-defined strategies
│   ├── __init__.py
│   ├── base.py                 # Base strategy class
│   └── example_sma.py          # Example strategy
├── tests/                      # All tests
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── domain/
│   ├── adapters/
│   └── services/
├── scripts/                    # Utility scripts
│   ├── setup.sh                # Development setup
│   ├── init_db.sql             # Database initialization
│   └── explore_binance_data.py # Binance schema exploration
├── docker-compose.yml          # Docker deployment
├── Dockerfile                  # Application container
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Development dependencies
├── pyproject.toml              # Project metadata, tool config
├── .env.example                # Environment template
├── .gitignore
└── README.md                   # Project documentation
```

---

## 🚀 Implementation Steps

| Step | File | Title | Effort | Status |
|------|------|-------|--------|--------|
| 1 | Step1.md | Project Foundation & Infrastructure | 2-4h | ⏳ Pending |
| 2 | Step2.md | Database Layer - Schema & Repositories | 6-8h | ⏳ Pending |
| 3 | Step3.md | Binance Data Ingest - WebSocket & REST | 8-12h | ⏳ Pending |
| 4 | Step4.md | Redis Cache Layer & Pub/Sub | 4-6h | ⏳ Pending |
| 5 | Step5.md | Strategy Engine & Signal Generation | 8-12h | ⏳ Pending |
| 6 | Step6.md | Order Management & Execution | 12-16h | ⏳ Pending |

**Total Effort:** 40-58 hours

---

## 🛠️ Development Workflow

### Local Development (No Docker)
```bash
# 1. Install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 2. Install PostgreSQL locally
# Ubuntu: sudo apt install postgresql postgresql-contrib
# macOS: brew install postgresql

# 3. Install Redis locally
# Ubuntu: sudo apt install redis-server
# macOS: brew install redis

# 4. Run tests
pytest tests/ -v

# 5. Run application
python -m app.main
```

### After Each Step
```bash
# 1. Ensure all tests pass
pytest tests/ -v --cov=app

# 2. Build Docker image
docker-compose build

# 3. Test in Docker
docker-compose up -d
docker-compose logs -f

# 4. Commit
git add .
git commit -m "Step N: <description>"
git push
```

---

## 📋 Key Design Decisions (ADRs)

### ADR-001: Modular Monolith
- Start with modular monolith (not microservices)
- Can split to microservices later if needed
- Lower complexity, faster development

### ADR-002: PostgreSQL
- ACID-compliant for financial transactions
- No TimescaleDB needed (overkill for our scale)
- JSONB for flexible configs

### ADR-003: Redis Cache
- Sub-millisecond latency for hot data
- Pub/sub for real-time data distribution
- TTL for volatile data

### ADR-004: Python 3.11+
- Fast development velocity
- Excellent async support (asyncio)
- Rich trading ecosystem

### ADR-005: Local Dev First
- Develop natively (no Docker) for fast iteration
- Docker only for deployment/validation
- Seconds between edit and test

### ADR-006: Hexagonal Architecture
- Domain logic isolated from external concerns
- Easy to test (mock adapters)
- Swap implementations without changing core

---

## 🔑 Key Requirements

### Functional
- Real-time market data (Binance WebSocket)
- 1-second candle intervals (scalping)
- Multiple parallel strategies
- Order management with lifecycle tracking
- Risk controls (position limits, circuit breakers)
- Real-time PnL calculation

### Non-Functional
- **Latency:** <40ms end-to-end
- **Throughput:** Handle 10+ symbols × 1-second candles
- **Reliability:** Auto-reconnect on failures
- **Testability:** >80% code coverage
- **Maintainability:** Clean architecture, documented

---

## 📊 Database Schema Overview

### Core Tables
- `candles` - OHLCV market data (high write volume)
- `orders` - Order lifecycle
- `trades` - Executed trades
- `positions` - Current holdings
- `strategies` - Strategy metadata
- `strategy_performance` - Daily metrics
- `audit_log` - Audit trail

**Note:** Final schema will be updated after Step 3 (Binance data exploration).

---

## 🧪 Testing Strategy

### Unit Tests
- Test domain logic in isolation
- Mock external dependencies (DB, Redis, exchanges)
- Fast execution (<1 second per test)

### Integration Tests
- Test with real PostgreSQL
- Test with real Redis
- Test with Binance testnet (if available)

### Performance Tests
- Batch insert 1000 candles in <100ms
- Cache get/set <5ms
- Strategy execution <40ms

---

## 📝 Conventions

### Code Style
- Black for formatting
- MyPy for type checking
- Flake8 for linting
- Type hints required

### Logging
- Structured logging (structlog)
- Include context: strategy_id, symbol, etc.
- JSON format in production, console in development

### Error Handling
- Custom exceptions in `app/domain/exceptions.py`
- Log errors with full context
- Graceful degradation (no crashes)

### Async
- Use asyncio throughout
- No blocking I/O in hot path
- Proper timeout handling

---

## 🎯 Success Criteria

**Project is complete when:**
- [ ] All 6 steps implemented and tested
- [ ] Real-time 1-second candles from Binance
- [ ] At least one working strategy (example SMA)
- [ ] Orders executed on Binance (testnet or live)
- [ ] Risk controls working
- [ ] Real-time PnL tracking
- [ ] >80% test coverage
- [ ] Docker deployment working
- [ ] Documentation complete

---

## 📚 Reference Documents

- `backend_propose.md` - Full architecture proposal with ADRs
- `MVP_Steps.md` - High-level step overview
- `Step1.md` through `Step6.md` - Detailed step specifications

---

## 🆘 Getting Help

If you're implementing a step and encounter issues:
1. Check the step file for detailed specs
2. Review `backend_propose.md` for architecture context
3. Check existing code for patterns
4. Ask for clarification if specs are unclear

---

**Ready to implement? Start with Step1.md** 🐾
