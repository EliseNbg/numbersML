# Step 1: Project Foundation & Infrastructure

**Status:** ⏳ Pending  
**Effort:** 2-4 hours  
**Dependencies:** None (foundational step)

---

## 🎯 Objective

Create the project foundation with configuration management, logging, and development infrastructure. This step establishes the base that all other steps build upon.

**Key Outcomes:**
- Working project structure
- Type-safe configuration (pydantic-settings)
- Structured logging (structlog)
- Test infrastructure (pytest)
- Development setup scripts

---

## 📁 Deliverables

Create the following file structure:

```
trading-backend/
├── app/
│   ├── __init__.py
│   ├── config.py                 # Configuration management
│   └── logging_config.py         # Structured logging setup
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   └── test_config.py            # Configuration tests
├── scripts/
│   └── setup.sh                  # Development setup script
├── requirements.txt              # Production dependencies
├── requirements-dev.txt          # Development dependencies
├── pyproject.toml                # Project metadata, tool config
├── .env.example                  # Environment template
├── .gitignore
└── README.md                     # Project documentation
```

---

## 📝 Specifications

### 1.1 Configuration Management (`app/config.py`)

**Requirements:**
- Use `pydantic-settings` for type-safe configuration
- Support environment variables and `.env` file
- Provide default values for development
- Validate required fields

**Implementation:**

```python
# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """
    Application configuration.
    Loads from environment variables and .env file.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # === Database ===
    database_url: str = Field(
        default="postgresql://trading:trading_secret@localhost:5432/trading",
        description="PostgreSQL connection URL"
    )
    database_pool_size: int = Field(
        default=10,
        ge=5,
        le=50,
        description="Maximum database connections"
    )
    database_pool_min_size: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Minimum database connections"
    )
    
    # === Redis ===
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    
    # === Application ===
    environment: str = Field(
        default="development",
        pattern="^(development|staging|production)$",
        description="Deployment environment"
    )
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level"
    )
    app_name: str = "Trading Backend"
    
    # === Binance ===
    binance_api_key: Optional[str] = Field(
        default=None,
        description="Binance API key (optional for data-only mode)"
    )
    binance_secret_key: Optional[str] = Field(
        default=None,
        description="Binance secret key (optional for data-only mode)"
    )
    
    # === Trading ===
    max_strategies: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum concurrent strategies"
    )
    default_timeframe: str = Field(
        default="1s",
        description="Default candle timeframe for scalping"
    )
    
    # === Performance ===
    candle_batch_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Candles per batch insert"
    )
    
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == "development"
    
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == "production"


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance (for dependency injection)"""
    return settings
```

---

### 1.2 Logging Setup (`app/logging_config.py`)

**Requirements:**
- Use `structlog` for structured JSON logging
- Different formats for development (console) vs. production (JSON)
- Include context: timestamp, level, logger, event
- Support adding context (strategy_id, symbol, etc.)

**Implementation:**

```python
# app/logging_config.py
import logging
import sys
from typing import Any, Dict

import structlog
from structlog.types import Processor


def setup_logging(environment: str = "development", log_level: str = "INFO") -> None:
    """
    Configure structured logging.
    
    Args:
        environment: "development" or "production"
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    
    # Shared processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    
    if environment == "development":
        # Development: Console output with colors
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Production: JSON output
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Structured logger with context support
    """
    return structlog.get_logger(name)
```

**Usage Example:**

```python
from app.logging_config import get_logger

logger = get_logger(__name__)

# Basic logging
logger.info("Application started")

# Logging with context
logger.info(
    "Candle received",
    symbol="BTCUSDT",
    timeframe="1s",
    price=50000.00
)

# Logging with error
try:
    # ... code ...
except Exception as e:
    logger.error(
        "Failed to process candle",
        symbol="BTCUSDT",
        error=str(e),
        exc_info=True
    )
```

---

### 1.3 Dependencies

**requirements.txt** (Production):

```txt
# === Core ===
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0

# === Async ===
asyncio==3.4.3

# === Database ===
asyncpg==0.29.0

# === Redis ===
redis==5.0.1
aioredis==2.0.1

# === Logging ===
structlog==23.2.0

# === Utilities ===
typing-extensions==4.9.0
```

**requirements-dev.txt** (Development):

```txt
# Include production requirements
-r requirements.txt

# === Testing ===
pytest==7.4.3
pytest-asyncio==0.23.2
pytest-cov==4.1.0
pytest-mock==3.12.0

# === Code Quality ===
black==23.12.1
mypy==1.8.0
flake8==7.0.0
isort==5.13.2

# === Development ===
ipython==8.20.0
```

---

### 1.4 Project Configuration (`pyproject.toml`)

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "trading-backend"
version = "0.1.0"
description = "Multi-strategy trading backend with low latency"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "Andreas", email = "andreas@example.com"}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "black>=23.12.0",
    "mypy>=1.8.0",
    "flake8>=7.0.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*", "services*", "strategies*"]

[tool.black]
line-length = 100
target-version = ['py311']
include = '\.pyi?$'

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.isort]
profile = "black"
line_length = 100
```

---

### 1.5 Environment Template (`.env.example`)

```bash
# === Database ===
DATABASE_URL=postgresql://trading:trading_secret@localhost:5432/trading
DATABASE_POOL_SIZE=10
DATABASE_POOL_MIN_SIZE=5

# === Redis ===
REDIS_URL=redis://localhost:6379/0

# === Application ===
ENVIRONMENT=development
LOG_LEVEL=INFO

# === Binance (optional - for data-only mode, leave empty) ===
BINANCE_API_KEY=
BINANCE_SECRET_KEY=

# === Trading ===
MAX_STRATEGIES=10
DEFAULT_TIMEFRAME=1s

# === Performance ===
CANDLE_BATCH_SIZE=100
```

---

### 1.6 Git Ignore (`.gitignore`)

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
.env.local
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
logs/
*.log
data/
!data/.gitkeep
```

---

### 1.7 Setup Script (`scripts/setup.sh`)

```bash
#!/bin/bash

# Trading Backend - Development Setup Script
# Usage: ./scripts/setup.sh

set -e

echo "🚀 Setting up Trading Backend development environment..."

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.11"

echo "📌 Checking Python version..."
if [[ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]]; then
    echo "❌ Python 3.11 or higher required (found: $PYTHON_VERSION)"
    exit 1
fi
echo "✅ Python version: $PYTHON_VERSION"

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📈 Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Installing production dependencies..."
pip install -r requirements.txt

echo "📥 Installing development dependencies..."
pip install -r requirements-dev.txt

# Install pre-commit hooks (optional)
if command -v pre-commit &> /dev/null; then
    echo "🔗 Installing pre-commit hooks..."
    pre-commit install
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs
mkdir -p data
touch logs/.gitkeep
touch data/.gitkeep

# Copy environment file
if [ ! -f ".env" ]; then
    echo "📋 Copying .env.example to .env..."
    cp .env.example .env
    echo "⚠️  Please update .env with your configuration"
fi

# Check PostgreSQL
echo "🗄️  Checking PostgreSQL..."
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL client found"
else
    echo "⚠️  PostgreSQL not found. Install with:"
    echo "   Ubuntu: sudo apt install postgresql postgresql-contrib"
    echo "   macOS:  brew install postgresql"
fi

# Check Redis
echo "🔴 Checking Redis..."
if command -v redis-cli &> /dev/null; then
    echo "✅ Redis client found"
else
    echo "⚠️  Redis not found. Install with:"
    echo "   Ubuntu: sudo apt install redis-server"
    echo "   macOS:  brew install redis"
fi

# Run tests
echo "🧪 Running tests..."
pytest tests/ -v

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env with your configuration"
echo "2. Start PostgreSQL: sudo systemctl start postgresql"
echo "3. Start Redis: sudo systemctl start redis"
echo "4. Create database: psql -c \"CREATE DATABASE trading;\""
echo "5. Run tests: pytest tests/ -v"
echo "6. Start development: python -m app.main"
echo ""
```

Make executable: `chmod +x scripts/setup.sh`

---

### 1.8 Pytest Fixtures (`tests/conftest.py`)

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Generator


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock settings for testing"""
    settings = MagicMock()
    settings.database_url = "postgresql://test:test@localhost:5432/test_db"
    settings.database_pool_size = 5
    settings.database_pool_min_size = 2
    settings.redis_url = "redis://localhost:6379/0"
    settings.environment = "testing"
    settings.log_level = "DEBUG"
    settings.binance_api_key = None
    settings.binance_secret_key = None
    settings.max_strategies = 5
    settings.default_timeframe = "1s"
    settings.candle_batch_size = 50
    return settings


@pytest.fixture
def mock_asyncpg_pool() -> AsyncMock:
    """Mock asyncpg connection pool"""
    pool = AsyncMock()
    
    # Mock acquire context manager
    connection = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = connection
    pool.acquire.return_value.__aexit__.return_value = None
    
    return pool


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client"""
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = True
    redis.publish.return_value = True
    return redis


@pytest.fixture
def sample_candle_data() -> dict:
    """Sample candle data for testing"""
    return {
        "symbol": "BTCUSDT",
        "timeframe": "1s",
        "timestamp": "2026-03-15T12:00:00Z",
        "open": 50000.00,
        "high": 50100.00,
        "low": 49900.00,
        "close": 50050.00,
        "volume": 100.5,
        "source": "binance"
    }
```

---

### 1.9 Configuration Tests (`tests/test_config.py`)

```python
# tests/test_config.py
import os
import pytest
from unittest.mock import patch
from app.config import Settings, get_settings


def test_settings_default_values():
    """Test that settings have correct default values"""
    settings = Settings()
    
    assert settings.database_pool_size == 10
    assert settings.database_pool_min_size == 5
    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.max_strategies == 10
    assert settings.default_timeframe == "1s"
    assert settings.candle_batch_size == 100


def test_settings_from_env_vars():
    """Test that settings load from environment variables"""
    with patch.dict(os.environ, {
        "DATABASE_URL": "postgresql://user:pass@host:5432/db",
        "ENVIRONMENT": "production",
        "LOG_LEVEL": "WARNING",
        "MAX_STRATEGIES": "20"
    }, clear=False):
        settings = Settings()
        
        assert settings.database_url == "postgresql://user:pass@host:5432/db"
        assert settings.environment == "production"
        assert settings.log_level == "WARNING"
        assert settings.max_strategies == 20


def test_settings_environment_validation():
    """Test that environment field validates correctly"""
    # Valid environments
    for env in ["development", "staging", "production"]:
        with patch.dict(os.environ, {"ENVIRONMENT": env}, clear=False):
            settings = Settings()
            assert settings.environment == env
    
    # Invalid environment
    with patch.dict(os.environ, {"ENVIRONMENT": "invalid"}, clear=False):
        with pytest.raises(Exception):  # pydantic validation error
            Settings()


def test_settings_pool_size_validation():
    """Test that pool size validates correctly"""
    # Valid pool size
    with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "20"}, clear=False):
        settings = Settings()
        assert settings.database_pool_size == 20
    
    # Too small
    with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "1"}, clear=False):
        with pytest.raises(Exception):
            Settings()
    
    # Too large
    with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "100"}, clear=False):
        with pytest.raises(Exception):
            Settings()


def test_get_settings():
    """Test get_settings function"""
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_is_development():
    """Test environment check methods"""
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
        settings = Settings()
        assert settings.is_development() is True
        assert settings.is_production() is False
    
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        settings = Settings()
        assert settings.is_development() is False
        assert settings.is_production() is True
```

---

### 1.10 README.md

```markdown
# Trading Backend

Multi-strategy trading backend with low-latency execution for cryptocurrency and stock trading.

## Features

- ⚡ Low latency (<40ms target)
- 🕐 1-second candle intervals (scalping support)
- 🔀 Parallel strategy execution
- 🏗️ Clean architecture (hexagonal/ports & adapters)
- 🐍 Python 3.11+

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis 7+

### Setup

```bash
# Clone repository
git clone <repository-url>
cd trading-backend

# Run setup script
./scripts/setup.sh

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start PostgreSQL and Redis
# Ubuntu:
sudo systemctl start postgresql
sudo systemctl start redis

# macOS:
brew services start postgresql
brew services start redis

# Create database
psql -c "CREATE DATABASE trading;"

# Run tests
pytest tests/ -v

# Start application
python -m app.main
```

## Development

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=app

# Specific test file
pytest tests/test_config.py -v
```

### Code Quality

```bash
# Format code
black app/ tests/

# Type checking
mypy app/

# Linting
flake8 app/ tests/

# Sort imports
isort app/ tests/
```

## Architecture

See `project_overview_for_all_agents.md` and `backend_propose.md` for detailed architecture documentation.

## Implementation Steps

| Step | Status | Description |
|------|--------|-------------|
| 1 | ✅ Complete | Project Foundation |
| 2 | ⏳ Pending | Database Layer |
| 3 | ⏳ Pending | Binance Data Ingest |
| 4 | ⏳ Pending | Redis Cache Layer |
| 5 | ⏳ Pending | Strategy Engine |
| 6 | ⏳ Pending | Order Management |

## Configuration

See `.env.example` for all configuration options.

## License

MIT
```

---

### 1.11 App Package Init (`app/__init__.py`)

```python
# app/__init__.py
"""Trading Backend Application"""

__version__ = "0.1.0"
```

---

### 1.12 Tests Package Init (`tests/__init__.py`)

```python
# tests/__init__.py
"""Test suite for Trading Backend"""
```

---

## ✅ Acceptance Criteria

Complete this step when all criteria are met:

- [ ] **Project structure created** - All directories and files exist
- [ ] **Configuration works** - Can import `app.config` and get settings
- [ ] **Environment variables load** - Settings load from `.env` file
- [ ] **Environment variables override** - Env vars override `.env` values
- [ ] **Validation works** - Invalid values raise errors
- [ ] **Logging configured** - `structlog` outputs structured logs
- [ ] **Development format** - Console output with colors in dev mode
- [ ] **Tests pass** - All configuration tests pass: `pytest tests/test_config.py -v`
- [ ] **Setup script works** - `./scripts/setup.sh` completes successfully
- [ ] **No Docker required** - Everything runs natively
- [ ] **Code quality** - Black, mypy, flake8 pass without errors

---

## 🧪 Testing Requirements

### Run All Tests

```bash
pytest tests/ -v
```

### Expected Output

```
tests/test_config.py::test_settings_default_values PASSED
tests/test_config.py::test_settings_from_env_vars PASSED
tests/test_config.py::test_settings_environment_validation PASSED
tests/test_config.py::test_settings_pool_size_validation PASSED
tests/test_config.py::test_get_settings PASSED
tests/test_config.py::test_is_development PASSED

============================== 6 passed in 0.05s ===============================
```

### Code Quality Checks

```bash
# Format check
black --check app/ tests/

# Type check
mypy app/

# Lint
flake8 app/ tests/
```

All should pass without errors.

---

## 🔧 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'app'"

**Solution:** Ensure you're running from the project root and virtual environment is activated:

```bash
cd trading-backend
source venv/bin/activate
python -m app.main
```

### Issue: "pydantic-settings not found"

**Solution:** Install dependencies:

```bash
pip install -r requirements.txt
```

### Issue: Tests fail with import errors

**Solution:** Install dev dependencies:

```bash
pip install -r requirements-dev.txt
```

### Issue: PostgreSQL connection refused

**Solution:** Start PostgreSQL service:

```bash
# Ubuntu
sudo systemctl start postgresql

# macOS
brew services start postgresql
```

### Issue: Redis connection refused

**Solution:** Start Redis service:

```bash
# Ubuntu
sudo systemctl start redis

# macOS
brew services start redis
```

---

## 📚 References

- `project_overview_for_all_agents.md` - Project overview
- `backend_propose.md` - Architecture proposal
- Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- Structlog: https://www.structlog.org/en/stable/
- Pytest: https://docs.pytest.org/

---

## 🎯 Next Step

After completing Step 1, proceed to **Step 2: Database Layer - Schema & Repositories** (`Step2.md`).

---

**Ready to implement? Start coding!** 🐾
