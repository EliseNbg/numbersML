# Step 001: Project Setup

## Context

**Phase**: 1 - Foundation  
**Effort**: 2 hours  
**Dependencies**: None (first step)

---

## Goal

Set up the project structure, dependencies, and development tooling for a Python-based crypto trading data system.

---

## Domain Overview

This is an **infrastructure setup** step - no domain logic yet.

```
crypto-trading-system/
├── src/
│   ├── __init__.py
│   ├── domain/              # Domain layer (DDD)
│   │   ├── __init__.py
│   │   ├── models/          # Entities, Value Objects
│   │   ├── events/          # Domain Events
│   │   └── services/        # Domain Services
│   │
│   ├── application/         # Application layer
│   │   ├── __init__.py
│   │   ├── commands/        # Command handlers
│   │   ├── queries/         # Query handlers
│   │   └── services/        # Application services
│   │
│   ├── infrastructure/      # Infrastructure layer
│   │   ├── __init__.py
│   │   ├── database/        # PostgreSQL connection
│   │   ├── redis/           # Redis connection
│   │   └── exchanges/       # Exchange clients
│   │
│   └── indicators/          # Indicator framework
│       ├── __init__.py
│       ├── base.py          # Base indicator class
│       └── registry.py      # Indicator registry
│
├── tests/
│   ├── __init__.py
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # End-to-end tests
│
├── scripts/                 # Utility scripts
├── docs/                    # Documentation
├── config/                  # Configuration files
│
├── pyproject.toml           # Project metadata, dependencies
├── requirements.txt         # Pin dependencies
├── requirements-dev.txt     # Development dependencies
├── pytest.ini               # Pytest configuration
├── mypy.ini                 # Type checking config
├── .pre-commit-config.yaml  # Git hooks
├── .gitignore
└── README.md
```

---

## Implementation Tasks

### Task 1.1: Create Directory Structure

```bash
# Create project structure
mkdir -p src/{domain/{models,events,services},application/{commands,queries,services},infrastructure/{database,redis,exchanges},indicators}
mkdir -p tests/{unit/{domain,application,indicators},integration,e2e}
mkdir -p scripts docs config
```

### Task 1.2: Create `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "crypto-trading-system"
version = "0.1.0"
description = "Crypto trading data system with dynamic indicators"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]

dependencies = [
    "asyncpg>=0.29.0",        # PostgreSQL async client
    "redis>=5.0.0",           # Redis client
    "websockets>=12.0",       # WebSocket client
    "numpy>=1.26.0",          # Numerical computing
    "pandas>=2.1.0",          # Data manipulation
    "TA-Lib>=0.4.28",         # Technical analysis library
    "pydantic>=2.5.0",        # Data validation
    "python-json-logger>=2.0.7",  # Structured logging
    "click>=8.1.7",           # CLI framework
    "pyyaml>=6.0.1",          # YAML config
    "jsonschema>=4.20.0",     # JSON schema validation
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.12.0",
    "mypy>=1.7.0",
    "ruff>=0.1.6",
    "black>=23.11.0",
    "pre-commit>=3.6.0",
    "testcontainers>=3.7.0",  # Docker containers for testing
]

[project.scripts]
crypto-collect = "src.infrastructure.exchanges.collector:main"
crypto-enrich = "src.application.services.enrichment:main"
crypto-recalc = "src.application.commands.recalculate:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*", "tests*"]

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "UP", "B", "C4"]
```

### Task 1.3: Create `requirements.txt`

```txt
# Runtime dependencies (pinned)
asyncpg==0.29.0
redis==5.0.1
websockets==12.0
numpy==1.26.2
pandas==2.1.4
TA-Lib==0.4.28
pydantic==2.5.2
python-json-logger==2.0.7
click==8.1.7
pyyaml==6.0.1
jsonschema==4.20.0
```

### Task 1.4: Create `requirements-dev.txt`

```txt
# Development dependencies (pinned)
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pytest-mock==3.12.0
mypy==1.7.1
ruff==0.1.8
black==23.12.0
pre-commit==3.6.0
testcontainers==3.7.1
```

### Task 1.5: Create `pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
addopts = 
    -v
    --strict-markers
    --tb=short
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=70
markers =
    unit: Unit tests
    integration: Integration tests (requires database)
    e2e: End-to-end tests
    slow: Slow running tests
```

### Task 1.6: Create `mypy.ini`

```ini
[mypy]
python_version = 3.11
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_configs = true

# Per-module overrides
[mypy-src.infrastructure.*]
disallow_untyped_defs = false

[mypy-tests.*]
disallow_untyped_defs = false
```

### Task 1.7: Create `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.8
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]

  - repo: https://github.com/psf/black
    rev: 23.12.0
    hooks:
      - id: black
```

### Task 1.8: Create `.gitignore`

```gitignore
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/

# Translations
*.mo
*.pot

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Project specific
data/
*.db
*.log
config/local.yaml
```

### Task 1.9: Create `README.md`

```markdown
# Crypto Trading System

Real-time crypto trading data system with dynamic indicators and event-driven architecture.

## Features

- Real-time tick data collection from Binance
- Dynamic indicator framework (add/change indicators without schema changes)
- Automatic indicator recalculation on changes
- Redis pub/sub for strategy integration
- PostgreSQL for persistent storage

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install TA-Lib (system dependency required)
# Ubuntu: sudo apt-get install ta-lib
# macOS: brew install ta-lib

# Run tests
pytest

# Type checking
mypy src

# Linting
ruff check src
```

## Architecture

See [docs/](docs/) for detailed architecture documentation.

## Development

```bash
# Install pre-commit hooks
pre-commit install

# Run tests with coverage
pytest --cov=src

# Type checking
mypy src
```
```

### Task 1.10: Create `src/__init__.py`

```python
"""Crypto Trading System - Real-time data collection and indicator framework."""

__version__ = "0.1.0"
```

### Task 1.11: Create Package Init Files

Create `__init__.py` in all subdirectories under `src/` and `tests/`.

### Task 1.12: Install Pre-commit Hooks

```bash
pre-commit install
```

---

## Test Requirements

### Test Coverage Target: **N/A** (infrastructure setup only)

### Tests to Create

**File**: `tests/unit/test_project_structure.py`

```python
"""Test that project structure is correct."""

def test_src_directory_exists():
    """Test that src directory exists."""
    import src
    assert src.__version__ == "0.1.0"

def test_domain_layer_exists():
    """Test domain layer structure."""
    from src.domain import models
    from src.domain import events
    from src.domain import services

def test_application_layer_exists():
    """Test application layer structure."""
    from src.application import commands
    from src.application import queries
    from src.application import services

def test_infrastructure_layer_exists():
    """Test infrastructure layer structure."""
    from src.infrastructure import database
    from src.infrastructure import redis
    from src.infrastructure import exchanges

def test_indicators_module_exists():
    """Test indicators module structure."""
    from src.indicators import base
    from src.indicators import registry
```

---

## Acceptance Criteria

- [ ] Directory structure created as specified
- [ ] `pyproject.toml` with all dependencies
- [ ] `requirements.txt` and `requirements-dev.txt` created
- [ ] `pytest.ini` configured
- [ ] `mypy.ini` configured for strict type checking
- [ ] `.pre-commit-config.yaml` with hooks
- [ ] `.gitignore` configured
- [ ] `README.md` with basic documentation
- [ ] All `__init__.py` files created
- [ ] `pip install -r requirements.txt` works
- [ ] `pytest` runs successfully (even with no tests)
- [ ] `mypy src` passes
- [ ] Pre-commit hooks installed and working

---

## Verification Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run structure tests
pytest tests/unit/test_project_structure.py -v

# Type checking
mypy src

# Linting
ruff check src

# Pre-commit
pre-commit run --all-files
```

---

## Next Step

After completing this step, proceed to **[002-database-schema.md](002-database-schema.md)**
