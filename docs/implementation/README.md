# Implementation Guide - Crypto Trading System

## Welcome!

This directory contains step-by-step implementation guides for building a robust crypto trading data system with dynamic indicators.

---

## Quick Start

```bash
# 1. Read the overview
cat docs/implementation/000-overview.md

# 2. Start with Step 001
cat docs/implementation/001-project-setup.md

# 3. Complete each step in order
# Each step has:
#   - Clear goals
#   - Specific tasks
#   - Test requirements
#   - Acceptance criteria
#   - Verification commands
```

---

## Implementation Roadmap

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Foundation (Week 1-2)                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                            │
│  │ Step 001│ │ Step 002│ │ Step 003│                            │
│  │ Setup   │ │  DB     │ │ Domain  │                            │
│  └─────────┘ └─────────┘ └─────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: Data Collection (Week 2-3)                             │
│  ┌─────────┐ ┌─────────┐                                        │
│  │ Step 004│ │ Step 005│                                        │
│  │ Collect │ │ Repo    │                                        │
│  └─────────┘ └─────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: Indicators (Week 3-4)                                  │
│  ┌─────────┐ ┌─────────┐                                        │
│  │ Step 006│ │ Step 007│                                        │
│  │ Framework│ │ Implement│                                       │
│  └─────────┘ └─────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4-7: Enrichment, Recalc, Strategies, Testing              │
│  Steps 008-015 (see summary document)                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Available Steps

### ✅ Completed

| Step | Document | Status |
|------|----------|--------|
| 001 | [Project Setup](001-project-setup.md) | Complete |
| 002 | [Database Schema](002-database-schema.md) | Complete |
| 003 | [Domain Models](003-domain-models.md) | Complete |

### 📋 Ready to Implement

| Step | Document | Phase | Effort |
|------|----------|-------|--------|
| 004 | Data Collection Service | Phase 2 | 8h |
| 005 | Repository Pattern | Phase 2 | 4h |
| 006 | Indicator Framework | Phase 3 | 6h |
| 007 | Indicator Implementations | Phase 3 | 8h |
| 008 | Enrichment Service | Phase 4 | 8h |
| 009 | Redis Pub/Sub | Phase 4 | 4h |
| 010 | Recalculation Service | Phase 5 | 8h |
| 011 | CLI Tools | Phase 5 | 4h |
| 012 | Strategy Interface | Phase 6 | 6h |
| 013 | Sample Strategies | Phase 6 | 8h |
| 014 | Integration Tests | Phase 7 | 8h |
| 015 | Monitoring & Logging | Phase 7 | 4h |

See [004-to-015-summary.md](004-to-015-summary.md) for details.

---

## Each Step Contains

```markdown
# Step NNN: Title

## Context
- Phase
- Dependencies
- Effort estimate

## Goal
Clear statement of what will be accomplished

## Domain Model
Entities, value objects, events (if applicable)

## Implementation Tasks
Specific coding tasks with code examples

## Test Requirements
- Coverage targets
- Test files to create
- Example tests

## Acceptance Criteria
Checklist for "done"

## Verification Commands
Commands to verify completion
```

---

## Development Workflow

### 1. Before Starting a Step

```bash
# Ensure previous step is complete
git status
git log --oneline -5

# Read the step document
cat docs/implementation/NNN-step-name.md

# Review design document
cat docs/data-flow-design.md
```

### 2. During Implementation

```bash
# Create feature branch
git checkout -b feature/step-NNN

# Implement code
# Write tests
# Run verification

# Commit frequently
git add .
git commit -m "feat: implement Step NNN - task 1"
```

### 3. After Completion

```bash
# Run all tests
pytest

# Check coverage
pytest --cov=src --cov-report=html

# Type checking
mypy src

# Linting
ruff check src

# Commit final changes
git commit -m "feat: complete Step NNN"

# Merge to main
git checkout main
git merge feature/step-NNN
```

---

## Test Coverage Requirements

### Overall Target: **75%+**

```bash
# Run tests with coverage
pytest --cov=src --cov-report=term-missing --cov-fail-under=75

# View HTML report
open htmlcov/index.html
```

### Coverage by Layer

| Layer | Target | Rationale |
|-------|--------|-----------|
| Domain | 90%+ | Pure business logic, no dependencies |
| Application | 80%+ | Use cases, handlers |
| Infrastructure | 70%+ | External dependencies make 100% hard |
| Integration | 80%+ | Real database, Redis |
| E2E | 50%+ | Full system flows |

---

## Quality Gates

### Before Committing

- [ ] All tests pass
- [ ] Coverage meets target
- [ ] Type checking passes (`mypy src`)
- [ ] Linting passes (`ruff check src`)
- [ ] Pre-commit hooks pass
- [ ] Documentation updated

### Commands

```bash
# Full quality check
pytest --cov=src --cov-fail-under=75 && \
mypy src && \
ruff check src && \
pre-commit run --all-files
```

---

## Troubleshooting

### Common Issues

**Issue**: Tests fail with "database not found"  
**Solution**: Run `docker-compose up -d postgres` or check DSN

**Issue**: TA-Lib installation fails  
**Solution**: Install system library first:
```bash
# Ubuntu
sudo apt-get install ta-lib

# macOS
brew install ta-lib
```

**Issue**: Type checking errors  
**Solution**: Check `mypy.ini` configuration, add type stubs

---

## Getting Help

### Resources

- **Design Document**: [docs/data-flow-design.md](../data-flow-design.md)
- **Overview**: [000-overview.md](000-overview.md)
- **Python Docs**: https://docs.python.org/3/
- **DDD Reference**: https://martinfowler.com/tags/domain_driven_design.html

### Questions?

Review the step document first - most answers are there. If still stuck:
1. Check the troubleshooting section
2. Review the design document
3. Ask for clarification

---

## Progress Tracking

Track your progress:

```bash
# View completed steps
ls -la docs/implementation/ | grep "^-" | wc -l

# View remaining steps
cat docs/implementation/004-to-015-summary.md
```

---

## Next Step

Start with **[001-project-setup.md](001-project-setup.md)** if you haven't already!

Already completed steps 001-003? Continue with **[004-data-collection-service.md](004-data-collection-service.md)** (summary available in [004-to-015-summary.md](004-to-015-summary.md)).
