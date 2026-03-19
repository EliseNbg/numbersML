# Implementation Plan - Crypto Trading Data System

## Overview

This implementation plan splits the system into **incremental, testable steps** that can be executed by LLM code agents.

---

## Domain-Driven Design (DDD) Structure

### Bounded Contexts

```
┌────────────────────────────────────────────────────────────────┐
│                     CORE DOMAIN                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │  Data Collection │  │  Data Enrichment │  │  Strategies  │ │
│  │  Context         │  │  Context         │  │  Context     │ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────────────┘
                         │
┌────────────────────────────────────────────────────────────────┐
│                   SUPPORTING DOMAINS                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │  Infrastructure  │  │   Backfill       │  │ Recalculation│ │
│  │  (DB, Redis)     │  │   Context        │  │   Context    │ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

### Domain Layers (per Context)

```
┌─────────────────────────────────────────┐
│  Domain Layer                           │
│  - Entities (business objects)          │
│  - Value Objects (immutable)            │
│  - Domain Events                        │
│  - Domain Services (business logic)     │
└─────────────────────────────────────────┘
         │
┌─────────────────────────────────────────┐
│  Application Layer                      │
│  - Use Cases / Commands / Queries       │
│  - Application Services                 │
│  - DTOs                                 │
└─────────────────────────────────────────┘
         │
┌─────────────────────────────────────────┐
│  Infrastructure Layer                   │
│  - Repository implementations           │
│  - External service clients             │
│  - Database connections                 │
└─────────────────────────────────────────┘
```

---

## Implementation Steps

### Phase 1: Foundation (Week 1-2)

| Step | Document | Description | Effort |
|------|----------|-------------|--------|
| 001 | `001-project-setup.md` | Project structure, dependencies, tooling | 2h |
| 002 | `002-database-schema.md` | PostgreSQL schema, migrations | 4h |
| 003 | `003-domain-models.md` | Core entities, value objects | 4h |

### Phase 2: Data Collection (Week 2-3)

| Step | Document | Description | Effort |
|------|----------|-------------|--------|
| 004 | `004-data-collection-service.md` | Binance WebSocket collector | 8h |
| 005 | `005-repository-pattern.md` | Repository pattern for data access | 4h |
| 016 | `016-asset-sync-service.md` | **NEW**: Binance asset metadata sync (daily) | 6h |

### Phase 3: Indicator Framework (Week 3-4)

| Step | Document | Description | Effort |
|------|----------|-------------|--------|
| 006 | `006-indicator-framework.md` | Dynamic indicator base classes | 6h |
| 007 | `007-indicator-implementations.md` | Core indicators (RSI, MACD, SMA, etc.) | 8h |

### Phase 4: Data Enrichment (Week 4-5)

| Step | Document | Description | Effort |
|------|----------|-------------|--------|
| 008 | `008-enrichment-service.md` | Real-time indicator calculation | 8h |
| 009 | `009-redis-pubsub.md` | Message queue for strategies | 4h |

### Phase 5: Recalculation (Week 5-6)

| Step | Document | Description | Effort |
|------|----------|-------------|--------|
| 010 | `010-recalculation-service.md` | Auto-recalc on indicator change | 8h |
| 011 | `011-cli-tools.md` | CLI for management | 4h |

### Phase 6: Strategy Integration (Week 6-7)

| Step | Document | Description | Effort |
|------|----------|-------------|--------|
| 012 | `012-strategy-interface.md` | Strategy base class, registry | 6h |
| 013 | `013-sample-strategies.md` | Market maker, trend follower | 8h |

### Phase 7: Testing & Hardening (Week 7-8)

| Step | Document | Description | Effort |
|------|----------|-------------|--------|
| 014 | `014-integration-tests.md` | End-to-end tests | 8h |
| 015 | `015-monitoring-logging.md` | Observability | 4h |

---

## Test Coverage Requirements

### Overall Targets

| Component | Unit Tests | Integration Tests | E2E Tests |
|-----------|-----------|-------------------|-----------|
| Domain Layer | 90%+ | - | - |
| Application Layer | 80%+ | 70%+ | - |
| Infrastructure | 70%+ | 80%+ | - |
| Services | 60%+ | 80%+ | 50%+ |

### Test Categories

```python
# Unit Tests (fast, isolated)
tests/unit/
├── domain/
│   ├── test_entities.py
│   ├── test_value_objects.py
│   └── test_domain_events.py
├── application/
│   ├── test_commands.py
│   └── test_handlers.py
└── indicators/
    ├── test_base.py
    └── test_calculations.py

# Integration Tests (database, external services)
tests/integration/
├── test_data_collector.py
├── test_enrichment_service.py
├── test_recalculation_service.py
└── test_repositories.py

# End-to-End Tests (full system)
tests/e2e/
├── test_data_pipeline.py
├── test_indicator_recalc.py
└── test_strategy_execution.py
```

### Test Quality Rules

1. **Domain Layer**: Pure business logic, no external dependencies
2. **Application Layer**: Mock repositories, test use cases
3. **Infrastructure**: Testcontainers for real DB/Redis
4. **E2E**: Full pipeline with test data

---

## Agent Instructions

Each implementation step document contains:

1. **Context** - What has been done, what comes next
2. **Domain Model** - Entities, value objects, events
3. **Implementation Tasks** - Specific coding tasks
4. **Test Requirements** - What to test, coverage targets
5. **Acceptance Criteria** - Definition of done
6. **Dependencies** - What must be completed first

---

## Getting Started

```bash
# Clone repository
cd /home/andy/projects/numbers/specV2

# Start with Step 001
cat docs/implementation/001-project-setup.md

# After completing each step:
# 1. Run tests
# 2. Commit changes
# 3. Move to next step
```

---

## Next Step

Proceed to **[001-project-setup.md](001-project-setup.md)**
