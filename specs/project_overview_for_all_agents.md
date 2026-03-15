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

## 🔧 Configuration & Logging System

### Configuration Management

**Frontend vs Backend Separation:**
- **Backend Configuration**: Database connections, Redis, exchange APIs, risk limits, performance tuning
- **Frontend Configuration**: UI preferences, display settings, notifications, chart configurations

**Configuration Layers:**
1. **Default values** (code-level defaults)
2. **Environment variables** (runtime configuration)
3. **Configuration files** (`.env`, `config.yaml`)
4. **Runtime API** (dynamic updates via admin endpoints)

**Security Considerations:**
- Sensitive data (API keys, passwords) stored in environment variables or secure vault
- Configuration validation before loading
- Runtime configuration reload without restart
- Audit trail for configuration changes

### System-Wide Logging

**Recommended Stack: Loki + Promtail + Grafana**

#### Why Loki for Trading Systems:
- **Lightweight & Low Overhead**: Minimal resource usage, perfect for high-throughput trading
- **Label-Based Querying**: Correlation IDs as labels for cross-component tracing
- **Integrated with Prometheus/Grafana**: Real-time dashboards and alerting
- **Cost Effective**: Much cheaper than ELK stack

#### Architecture:
```
Trading Backend (Python)
     ↓
Promtail (sidecar or separate process)
     ↓
Loki (log storage)
     ↓
Grafana (visualization & alerting)
```

#### Key Configuration Files:

**1. Loki Configuration (`loki-config.yaml`)**:
- Optimized for trading workloads (high ingestion rate: 200MB/s)
- Trading-specific labels: `correlation_id`, `strategy_id`, `symbol`, `component`
- 30-day retention for audit purposes
- High chunk sizes for efficient storage

**2. Promtail Configuration (`promtail-config.yaml`)**:
- Extracts structured fields from JSON logs
- Labels for correlation tracking: `correlation_id`, `strategy_id`, `symbol`, `order_id`
- Pipeline stages for JSON parsing and label extraction
- Optimized for high-volume trading logs

**3. Grafana Dashboard (`grafana-dashboard-trading.json`)**:
- Real-time monitoring of trading operations
- Log volume by component and level
- Order and signal tracking
- Latency metrics (<40ms target visibility)
- Error correlation with correlation IDs

#### Structured Logging Format (Python):
```json
{
  "timestamp": "2026-03-15T12:00:00Z",
  "level": "INFO",
  "logger": "strategy.sma_1",
  "message": "Signal generated",
  "correlation_id": "corr-12345",
  "strategy_id": "sma_1",
  "symbol": "BTCUSDT",
  "action": "BUY",
  "quantity": "0.01",
  "confidence": 0.85,
  "latency_ms": 23.5,
  "component": "strategy_runner"
}
```

#### Deployment Options:
- **Local Development**: Docker Compose on your notebook
- **Production**: Kubernetes with persistent volumes
- **Cloud**: AWS EKS/GKE with managed Loki

**Implementation Steps:**
1. Add Loki/Promtail to docker-compose.yml
2. Configure Python app to output structured JSON logs
3. Set up Grafana dashboard
4. Test correlation ID tracing across components

---

## 📁 Project Structure

```
trading-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuration (pydantic-settings)
│   ├── config_backend.py       # Backend-specific configuration
│   ├── config_frontend.py      # Frontend-specific configuration
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
├── api/                        # API layer
│   ├── __init__.py
│   ├── routes.py               # REST API endpoints
│   └── schemas.py              # API request/response schemas
├── web/                        # Frontend (if implemented later)
│   ├── __init__.py
│   ├── config.py               # Frontend configuration
│   └── static/                 # Static assets
├── logs/                       # Log files (gitignored)
│   ├── system.log              # System-wide logs
│   ├── backend.log             # Backend component logs
│   └── frontend.log            # Frontend component logs
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
├── .env.backend.example        # Backend environment template
├── .env.frontend.example       # Frontend environment template
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

### ADR-007: Frontend/Backend Configuration Separation
- Separate configuration for frontend and backend components
- Backend: database, Redis, exchange keys, risk limits
- Frontend: UI settings, display preferences, theme, notifications
- Runtime configuration updates via API (admin endpoints)
- Secure handling of sensitive credentials (environment variables, vault integration)

### ADR-008: System-Wide Logging
- Centralized structured logging across all components
- Correlation IDs for tracing requests across services
- Log aggregation and analysis capabilities
- Different log levels per component (debug, info, warning, error)
- Audit trail for all critical operations
- Log rotation and retention policies

---

## 🔑 Key Requirements

### Functional
- Real-time market data (Binance WebSocket)
- 1-second candle intervals (scalping)
- Multiple parallel strategies
- Order management with lifecycle tracking
- Risk controls (position limits, circuit breakers)
- Real-time PnL calculation
- **Configuration management** (frontend/backend separation)
- **System-wide logging** with correlation IDs

### Non-Functional
- **Latency:** <40ms end-to-end
- **Throughput:** Handle 10+ symbols × 1-second candles
- **Reliability:** Auto-reconnect on failures
- **Testability:** >80% code coverage
- **Maintainability:** Clean architecture, documented
- **Configurability:** Dynamic configuration updates
- **Observability:** Comprehensive system-wide logging and monitoring

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

### Configuration Management
- **Backend configuration** (`app/config_backend.py`):
  - Database connections
  - Redis connections  
  - Exchange API keys (Binance, etc.)
  - Risk limits and trading parameters
  - Performance tuning (batch sizes, timeouts)
  - Environment-specific settings (dev/staging/prod)

- **Frontend configuration** (`app/config_frontend.py`):
  - UI display preferences
  - Theme and styling options
  - Notification settings
  - Chart configurations
  - User preferences
  - API endpoint URLs

- **Runtime configuration**:
  - Admin API endpoints for dynamic updates
  - Configuration validation and reloading
  - Secure credential management (environment variables, secrets manager integration)
  - Configuration versioning and rollback

### Logging
- **System-wide structured logging** with correlation IDs
- **Correlation IDs**: Unique ID per request/operation for tracing across components
- **Log levels**: Per-component log level control (debug, info, warning, error, critical)
- **Log aggregation**: Support for centralized logging (ELK, Loki, or local file-based)
- **Audit trail**: All critical operations logged with user/context information
- **Log rotation**: Automatic rotation and retention policies
- **Context enrichment**: Strategy ID, symbol, order ID, request ID in all logs

### Error Handling
- Custom exceptions in `app/domain/exceptions.py`
- Log errors with full context (correlation ID, component, operation)
- Graceful degradation (no crashes, circuit breakers)
- Retry mechanisms for transient failures

### Async
- Use asyncio throughout
- No blocking I/O in hot path
- Proper timeout handling
- Backpressure management for high-throughput scenarios

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
