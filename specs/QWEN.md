# Trading Backend - Specifications Directory

**Project:** Multi-Strategy Cryptocurrency/Stock Trading Backend  
**Location:** `/home/andy/projects/numbers/specs`  
**Date:** 2026-03-15

---

## Directory Overview

This directory contains the complete specifications, architecture documentation, and implementation guides for building a **low-latency trading backend** supporting multiple parallel trading strategies for cryptocurrency (Binance) and stock (Yahoo Finance) markets.

**Key Requirements:**
- End-to-end latency: **<40ms**
- Candle intervals: **1-second** (scalping support)
- Architecture: **Modular Monolith with Hexagonal Architecture** (Ports & Adapters)
- Stack: **Python 3.11+**, **PostgreSQL 16**, **Redis 7**

---

## Key Files

| File | Purpose |
|------|---------|
| `project_overview_for_all_agents.md` | **Primary reference** - Complete project overview, architecture summary, implementation steps table, development workflow, and success criteria |
| `backend_propose.md` | Detailed architecture proposal with ADRs (Architecture Decision Records), Docker Compose setup, domain models, and port interfaces |
| `MVP_Steps.md` | High-level implementation roadmap with 6 ordered steps, effort estimates, and dependencies |
| `Step1.md` - `Step6.md` | Detailed specifications for each implementation step (deliverables, code examples, acceptance criteria, testing requirements) |
| `loki-config.yaml` | Loki logging configuration optimized for trading workloads (200MB/s ingestion, 30-day retention) |
| `promtail-config.yaml` | Promtail configuration for collecting structured JSON logs with trading-specific labels |
| `grafana-dashboard-trading.json` | Grafana dashboard for real-time trading monitoring |
| `deep-research-backend-report.md` | Research report comparing architecture styles (Monolith vs Microservices vs Event-Driven) |

---

## Architecture Summary

### Technology Stack
| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Python 3.11+ | All application code |
| Database | PostgreSQL 16 | Persistent storage (orders, trades, candles) |
| Cache | Redis 7 | Low-latency cache + pub/sub |
| Exchange | Binance (crypto), Yahoo Finance (stocks) | Market data + execution |
| Logging | Loki + Promtail + Grafana | Structured logging with correlation IDs |
| Deployment | Docker Compose | Final deployment |

### Hexagonal Architecture Layers
```
Domain Layer (pure Python)
    ↓
Ports Layer (interfaces)
    ↓
Adapters Layer (PostgreSQL, Redis, Binance implementations)
    ↓
Services Layer (coordination: data_ingest, strategy_runner, order_manager)
```

### Data Flow
```
Binance WebSocket → Data Ingest → Redis Cache → Strategy Engine → Signals
                                                              ↓
PostgreSQL ← Order Manager ← Risk Manager ← Signal Processor
```

---

## Implementation Steps

| Step | File | Title | Effort | Status |
|------|------|-------|--------|--------|
| 1 | `Step1.md` | Project Foundation & Infrastructure | 2-4h | ⏳ Pending |
| 2 | `Step2.md` | Database Layer - Schema & Repositories | 6-8h | ⏳ Pending |
| 3 | `Step3.md` | Binance Data Ingest - WebSocket & REST | 8-12h | ⏳ Pending |
| 4 | `Step4.md` | Redis Cache Layer & Pub/Sub | 4-6h | ⏳ Pending |
| 5 | `Step5.md` | Strategy Engine & Signal Generation | 8-12h | ⏳ Pending |
| 6 | `Step6.md` | Order Management & Execution | 12-16h | ⏳ Pending |

**Total Effort:** 40-58 hours

---

## Development Workflow

### Local Development (No Docker for iteration)
```bash
# 1. Install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 2. Install PostgreSQL and Redis locally
# Ubuntu: sudo apt install postgresql postgresql-contrib redis-server
# macOS: brew install postgresql redis

# 3. Run tests
pytest tests/ -v

# 4. Run application
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
```

---

## Logging System (Loki Stack)

### Structured Log Format
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

### Required Loki Labels
- `correlation_id` - Unique ID per operation for tracing
- `strategy_id` - Strategy identifier
- `symbol` - Trading pair
- `component` - System component
- `order_id`, `trade_id` - When applicable

---

## Key Design Decisions (ADRs)

| ADR | Decision | Rationale |
|-----|----------|-----------|
| ADR-001 | Modular Monolith | Lower complexity, faster development, can split to microservices later |
| ADR-002 | PostgreSQL (no TimescaleDB) | ACID-compliant, sufficient performance, simpler setup |
| ADR-003 | Redis Cache | Sub-millisecond latency, pub/sub for real-time distribution |
| ADR-004 | Python 3.11+ | Fast development, excellent async support, rich trading ecosystem |
| ADR-005 | Local Dev First | Develop natively (no Docker), Docker only for deployment |
| ADR-006 | Hexagonal Architecture | Domain logic isolated, easy to test, swap implementations |
| ADR-007 | Frontend/Backend Config Separation | Separate configs for UI vs backend concerns |
| ADR-008 | System-Wide Logging | Correlation IDs, structured JSON, Loki for aggregation |

---

## Database Schema Overview

### Core Tables
- `candles` - OHLCV market data (high write volume, partitioned)
- `orders` - Order lifecycle (PENDING → SUBMITTED → FILLED/CANCELLED)
- `trades` - Executed trades
- `positions` - Current holdings with PnL tracking
- `strategies` - Strategy metadata
- `strategy_performance` - Daily metrics
- `audit_log` - Audit trail

**Note:** Final schema updated after Step 3 (Binance data exploration).

---

## Testing Strategy

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

## Success Criteria

Project is complete when:
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

## Usage

**For implementing a step:**
1. Read `project_overview_for_all_agents.md` for context
2. Read the specific step file (`Step1.md` through `Step6.md`) for detailed specs
3. Reference `backend_propose.md` for architecture patterns and code examples
4. Follow the logging requirements (correlation IDs, structured JSON)
5. Run tests after implementation
6. Build Docker image for validation

**For understanding the architecture:**
1. Start with `project_overview_for_all_agents.md`
2. Read `backend_propose.md` for detailed ADRs and patterns

**For logging configuration:**
- `loki-config.yaml` - Loki server configuration
- `promtail-config.yaml` - Log collection configuration
- `grafana-dashboard-trading.json` - Dashboard import

---

## Reference

- **Start here:** `project_overview_for_all_agents.md`
- **Implementation guide:** `MVP_Steps.md` + individual `Step*.md` files
- **Architecture details:** `backend_propose.md`
