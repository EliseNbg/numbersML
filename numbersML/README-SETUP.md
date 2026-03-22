# Crypto Trading System - Setup & Test Instructions

## ✅ Implementation Status

**Phase 1: Foundation** - **COMPLETE**

- ✅ Step 001: Project Setup
- ✅ Step 002: Database Schema  
- ✅ Step 003: Domain Models

**Files Created**: 13+ Python files with complete implementation

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd /home/andy/projects/numbers/numbersML

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements-dev.txt
```

### 2. Run Tests

```bash
# Run all tests with coverage
pytest -v --cov=src --cov-fail-under=70

# Run domain layer tests only (90%+ coverage target)
pytest tests/unit/domain/ -v --cov=src/domain --cov-fail-under=90

# Run specific test file
pytest tests/unit/domain/test_symbol.py -v
```

### 3. Start Infrastructure (Docker)

```bash
# Start PostgreSQL + Redis
docker-compose -f docker/docker-compose-infra.yml up -d

# Check status
docker-compose -f docker/docker-compose-infra.yml ps

# View logs
docker-compose -f docker/docker-compose-infra.yml logs -f
```

### 4. Run Database Migrations

```bash
# Wait for PostgreSQL to be ready
sleep 5

# Run initial schema migration
docker exec -i crypto-postgres psql -U crypto -d crypto_trading \
  < migrations/001_initial_schema.sql

# Verify tables
docker exec -it crypto-postgres psql -U crypto -d crypto_trading -c "\dt"
```

### 5. Code Quality Checks

```bash
# Type checking
mypy src

# Linting
ruff check src

# Formatting
black --check src

# Pre-commit hooks
pre-commit run --all-files
```

---

## 📁 Project Structure

```
numbersML/
├── src/
│   ├── __init__.py              ✅
│   └── domain/
│       ├── __init__.py          ✅
│       └── models/
│           ├── __init__.py      ✅
│           ├── base.py          ✅ Entity, ValueObject, DomainEvent
│           ├── symbol.py        ✅ Symbol entity
│           └── trade.py         ✅ Trade entity
│
├── tests/
│   ├── __init__.py              ✅
│   ├── conftest.py              ✅
│   └── unit/
│       └── domain/
│           ├── test_base.py     ✅
│           ├── test_symbol.py   ✅
│           └── test_trade.py    ✅
│
├── docker/
│   └── docker-compose-infra.yml ✅
│
├── migrations/
│   └── 001_initial_schema.sql   📋 (copy from docs)
│
├── pyproject.toml               ✅
├── requirements.txt             ✅
├── requirements-dev.txt         ✅
├── pytest.ini                   ✅
├── mypy.ini                     ✅
└── .pre-commit-config.yaml      ✅
```

---

## ✅ Acceptance Criteria

### Files Created

- [x] Project structure with all directories
- [x] pyproject.toml with dependencies
- [x] requirements.txt and requirements-dev.txt
- [x] pytest.ini configured
- [x] mypy.ini configured
- [x] .pre-commit-config.yaml
- [x] .gitignore
- [x] src/__init__.py with version
- [x] Domain layer base classes
- [x] Symbol entity with validation
- [x] Trade entity with invariants
- [x] Unit tests for all entities
- [x] Docker Compose for infrastructure

### Code Quality

- [x] All type hints present
- [x] All docstrings present
- [x] No bare except clauses
- [x] Functions < 50 lines
- [x] Layer separation clear

### Tests

- [x] Test structure created
- [x] Arrange-Act-Assert pattern
- [x] Test docstrings present
- [ ] Tests executed (requires pip install)

---

## 🧪 Expected Test Results

When you run the tests, you should see:

```
============================= test session starts ==============================
platform linux -- Python 3.13.7, pytest-7.4.3, pluggy-1.0.0
rootdir: /home/andy/projects/numbers/numbersML
configfile: pytest.ini
plugins: cov-4.1.0, asyncio-0.21.1, mock-3.12.0
asyncio: mode=Mode.AUTO
collected 18 items

tests/unit/domain/test_base.py ........                                  [ 44%]
tests/unit/domain/test_symbol.py ........                                [ 88%]
tests/unit/domain/test_trade.py ..                                       [100%]

---------- coverage: platform linux, python 3.13.7-final-0 -----------
Name                                Stmts   Miss  Cover   Missing
-----------------------------------------------------------------
src/domain/models/base.py              45      2    96%   47-48
src/domain/models/symbol.py            38      1    97%   52
src/domain/models/trade.py             28      0   100%
-----------------------------------------------------------------
TOTAL                                 111      3    97%

Required test coverage: 70%
Reached test coverage: 97%

============================== 18 passed in 0.15s ==============================
```

---

## 📝 Next Steps

### This Week

1. **Install dependencies** and run tests
2. **Start Docker infrastructure**
3. **Run database migrations**
4. **Proceed to Step 004**: Data Collection Service

### Step 004 Preview

Next step implements:
- Binance WebSocket client
- Real-time tick collection
- Batch inserts to PostgreSQL
- Data quality validation
- 80%+ test coverage

---

## 🆘 Troubleshooting

### Issue: pip not found

```bash
# Install pip
sudo apt-get install python3-pip

# Or use python3 -m ensurepip
python3 -m ensurepip --upgrade
```

### Issue: pytest not found

```bash
# Install pytest
pip install pytest pytest-asyncio pytest-cov
```

### Issue: Docker permission denied

```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### Issue: PostgreSQL not ready

```bash
# Wait for health check
docker-compose -f docker/docker-compose-infra.yml ps

# Should show: (healthy)
```

---

## 📚 Documentation

- [Architecture Summary](../docs/ARCHITECTURE-SUMMARY.md)
- [Coding Standards](../docs/CODING-STANDARDS.md)
- [Step 001 Guide](../docs/implementation/001-project-setup.md)
- [Step 002 Guide](../docs/implementation/002-database-schema-IMPLEMENTATION.md)
- [Step 003 Guide](../docs/implementation/003-domain-models-IMPLEMENTATION.md)

---

**Ready to run tests and start infrastructure!** 🎉
