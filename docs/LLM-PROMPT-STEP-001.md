# LLM Agent Prompt - Step 001: Project Setup

**Copy and paste this entire prompt to your LLM agent to start implementation.**

---

## PROMPT START

```
You are a Senior Python Developer implementing a crypto trading data system.

ROLE:
  Senior Python Developer with expertise in:
  - Domain-Driven Design (DDD)
  - Hexagonal Architecture (Ports & Adapters)
  - Async Python (asyncio, asyncpg)
  - PostgreSQL database design
  - Docker containerization
  - Test-driven development

PROJECT CONTEXT:
  We are building a real-time crypto trading data system for Phase 1 (Data Gathering).
  
  System Purpose:
    - Collect market data from Binance WebSocket
    - Validate data quality (7 validation rules)
    - Store in PostgreSQL with dynamic indicators
    - Calculate 50+ technical indicators in real-time
    - Support backtesting with 6 months of historical data
  
  Architecture Principles:
    - DDD with strict layer separation (Domain → Application → Infrastructure)
    - Hexagonal architecture (ports in domain, adapters in infrastructure)
    - Modular Docker services (independent, deployable separately)
    - All configuration in database (only DATABASE_URL in .env)
    - EU compliance (regional filtering for allowed symbols)
  
  Technology Stack:
    - Python 3.11+
    - PostgreSQL 15+ (with asyncpg)
    - Redis 7+ (for pub/sub)
    - Docker & Docker Compose
    - pytest (testing), mypy (type checking), ruff (linting)
    - TA-Lib (technical analysis library)

CURRENT TASK:
  Step 001: Project Setup
  
  Goal: Create complete project structure with all configuration files,
        development tooling, and initial package structure.
  
  Estimated Time: 2 hours
  
  Deliverables:
    1. Complete directory structure
    2. pyproject.toml with all dependencies
    3. requirements.txt and requirements-dev.txt
    4. pytest.ini configuration
    5. mypy.ini configuration
    6. .pre-commit-config.yaml
    7. .gitignore
    8. README.md with setup instructions
    9. All __init__.py files for package structure
    10. Initial test structure

CODING STANDARDS (MANDATORY):
  
  1. KISS Principle:
     - Simple is better than complex
     - Functions < 50 lines, single responsibility
     - Readable over clever
  
  2. Type Hints (MANDATORY):
     - ALL parameters must have type hints
     - ALL return values must have type hints
     - Use Optional[T], List[T], Dict[K, V], etc.
     - Avoid 'Any' type
  
  3. Documentation (COMPREHENSIVE):
     - All public classes: docstring with purpose, example, attributes
     - All public methods: docstring with Args, Returns, Raises
     - All modules: module docstring
     - Inline comments for complex logic
  
  4. Error Handling (EXPLICIT):
     - No bare 'except:' clauses
     - Catch specific exceptions
     - Add context to error messages
     - Use exception chaining (from e)
     - Log errors with appropriate level
  
  5. Layer Separation (STRICT):
     - Domain Layer: Pure Python, NO external dependencies
     - Application Layer: Use cases, depends on Domain only
     - Infrastructure Layer: Implements Domain interfaces
  
  6. Testing (ARRANGE-ACT-ASSERT):
     - Domain layer: 90%+ coverage
     - Application layer: 80%+ coverage
     - Clear test names (test_method_with_condition)
     - Isolated tests

DIRECTORY STRUCTURE TO CREATE:

crypto-trading-system/
├── src/
│   ├── __init__.py                    # Version: "0.1.0"
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Entity, ValueObject, DomainEvent
│   │   │   └── README.md              # Layer documentation
│   │   ├── events/
│   │   │   ├── __init__.py
│   │   │   └── README.md
│   │   └── services/
│   │       ├── __init__.py
│   │       └── README.md
│   │
│   ├── application/
│   │   ├── __init__.py
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   └── README.md
│   │   ├── queries/
│   │   │   ├── __init__.py
│   │   │   └── README.md
│   │   └── services/
│   │       ├── __init__.py
│   │       └── README.md
│   │
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   └── README.md
│   │   ├── redis/
│   │   │   ├── __init__.py
│   │   │   └── README.md
│   │   └── exchanges/
│   │       ├── __init__.py
│   │       └── README.md
│   │
│   └── indicators/
│       ├── __init__.py
│       ├── base.py                    # Indicator ABC
│       └── registry.py                # Indicator registry
│
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── test_base.py
│   │   │   └── README.md
│   │   ├── application/
│   │   │   ├── __init__.py
│   │   │   └── README.md
│   │   └── infrastructure/
│   │       ├── __init__.py
│   │       └── README.md
│   ├── integration/
│   │   ├── __init__.py
│   │   └── README.md
│   └── e2e/
│       ├── __init__.py
│       └── README.md
│
├── docker/
│   ├── Dockerfile                     # Base image for all services
│   ├── docker-compose-infra.yml       # PostgreSQL + Redis
│   └── README.md
│
├── migrations/
│   ├── 001_initial_schema.sql         # Complete database schema
│   └── README.md
│
├── config/
│   ├── database.yaml                  # Database configuration
│   └── README.md
│
├── scripts/
│   ├── manage.sh                      # Service management
│   └── README.md
│
├── docs/                              # Reference to existing docs
│   └── README.md                      # Link to parent docs/
│
├── pyproject.toml                     # ⭐ CRITICAL - Complete configuration
├── requirements.txt                   # Runtime dependencies
├── requirements-dev.txt               # Development dependencies
├── pytest.ini                         # ⭐ CRITICAL - Test configuration
├── mypy.ini                           # ⭐ CRITICAL - Type checking
├── .pre-commit-config.yaml            # ⭐ CRITICAL - Git hooks
├── .gitignore                         # ⭐ CRITICAL - Git ignore rules
├── .python-version                    # Python version (3.11)
└── README.md                          # ⭐ CRITICAL - Setup instructions

IMPLEMENTATION TASKS:

Task 1: Create Directory Structure
  - Create all directories listed above
  - Create __init__.py in all Python packages
  - Add README.md to each layer explaining purpose

Task 2: Create pyproject.toml
  Requirements:
    - Build system: setuptools
    - Project name: crypto-trading-system
    - Python version: >=3.11
    - All runtime dependencies (see below)
    - All dev dependencies (see below)
    - Console scripts entry points
    - Black, ruff configuration
  
  Runtime Dependencies:
    - asyncpg>=0.29.0
    - redis>=5.0.0
    - websockets>=12.0
    - numpy>=1.26.0
    - pandas>=2.1.0
    - TA-Lib>=0.4.28
    - pydantic>=2.5.0
    - python-json-logger>=2.0.7
    - click>=8.1.7
    - pyyaml>=6.0.1
    - jsonschema>=4.20.0
    - aiohttp>=3.9.0
  
  Dev Dependencies:
    - pytest>=7.4.0
    - pytest-asyncio>=0.21.0
    - pytest-cov>=4.1.0
    - pytest-mock>=3.12.0
    - mypy>=1.7.0
    - ruff>=0.1.6
    - black>=23.11.0
    - pre-commit>=3.6.0
    - testcontainers>=3.7.0

Task 3: Create requirements.txt
  - Pin all runtime dependencies
  - Format: package==version

Task 4: Create requirements-dev.txt
  - Include -r requirements.txt
  - Pin all dev dependencies

Task 5: Create pytest.ini
  Requirements:
    - testpaths = tests
    - asyncio_mode = auto
    - Coverage settings (--cov=src, --cov-fail-under=70)
    - Markers for unit, integration, e2e
    - Verbose output

Task 6: Create mypy.ini
  Requirements:
    - Python version 3.11
    - Strict mode
    - warn_return_any = true
    - warn_unused_ignores = true
    - disallow_untyped_defs = true
    - Per-module overrides for infrastructure and tests

Task 7: Create .pre-commit-config.yaml
  Requirements:
    - pre-commit-hooks (trailing whitespace, end of file, check yaml)
    - ruff (with --fix)
    - black (formatting)
    - mypy (type checking)

Task 8: Create .gitignore
  Must include:
    - Python artifacts (__pycache__, *.pyc, *.pyo)
    - Virtual environments (venv/, .venv/)
    - IDE (.idea/, .vscode/)
    - Test coverage (htmlcov/, .coverage)
    - Environment files (.env)
    - Data files (data/, *.db)
    - Logs (*.log)

Task 9: Create .python-version
  - Content: 3.11

Task 10: Create README.md
  Sections:
    - Project title and description
    - Features (bullet points)
    - Tech stack
    - Quick start (installation, setup)
    - Development (running tests, linting)
    - Documentation (link to docs/)
    - License

Task 11: Create src/__init__.py
  - Define __version__ = "0.1.0"
  - Add module docstring

Task 12: Create Layer README Files
  Each layer (domain, application, infrastructure) needs README.md:
    - Purpose of layer
    - What belongs here
    - What NOT to include
    - Dependencies allowed

Task 13: Create Initial Test File
  File: tests/unit/domain/test_base.py
  Content:
    - Test Entity base class
    - Test ValueObject base class
    - Follow Arrange-Act-Assert pattern
    - Include docstrings

Task 14: Create Dockerfile
  Requirements:
    - Base: python:3.11-slim
    - Install system dependencies (build-essential, libta-lib-dev)
    - Copy and install requirements
    - Set working directory
    - Health check
    - Default command

Task 15: Create docker-compose-infra.yml
  Services:
    - postgres (PostgreSQL 15-alpine)
      - Environment variables
      - Volumes
      - Health check
      - Command with performance tuning
    - redis (Redis 7-alpine)
      - Environment variables
      - Volumes
      - Health check
      - Command with persistence
  Networks:
    - crypto_network (bridge)

Task 16: Create Initial Migration
  File: migrations/001_initial_schema.sql
  Content:
    - Enable extensions (uuid-ossp)
    - Create symbols table
    - Create trades table
    - Create indexes
    - Create helper functions (get_or_create_symbol)
    - Create triggers (updated_at)

ACCEPTANCE CRITERIA:

All files created:
  [ ] Directory structure complete
  [ ] All __init__.py files present
  [ ] All README.md files present
  [ ] pyproject.toml complete and valid
  [ ] requirements.txt complete
  [ ] requirements-dev.txt complete
  [ ] pytest.ini configured
  [ ] mypy.ini configured
  [ ] .pre-commit-config.yaml configured
  [ ] .gitignore comprehensive
  [ ] .python-version set to 3.11
  [ ] README.md with setup instructions
  [ ] Dockerfile working
  [ ] docker-compose-infra.yml working
  [ ] Initial migration valid

Code quality:
  [ ] All type hints present
  [ ] All docstrings present
  [ ] No bare except clauses
  [ ] Functions < 50 lines
  [ ] Layer separation clear

Tests:
  [ ] Initial test file created
  [ ] Test follows Arrange-Act-Assert
  [ ] Test has docstrings
  [ ] Test coverage > 90% for domain layer

Verification commands work:
  [ ] pip install -r requirements.txt
  [ ] pip install -r requirements-dev.txt
  [ ] pytest --version
  [ ] mypy --version
  [ ] pre-commit --version
  [ ] docker-compose -f docker-compose-infra.yml config

OUTPUT FORMAT:

For each file, provide:
  1. File path (relative to project root)
  2. Complete file content
  3. Brief explanation of key decisions

Example:
```
File: pyproject.toml
[Explanation: Complete project configuration with all dependencies...]

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "crypto-trading-system"
version = "0.1.0"
...
```

DOCUMENTATION REFERENCES:

For architecture context, refer to:
  - docs/00-START-HERE.md (quick start)
  - docs/ARCHITECTURE-SUMMARY.md (architecture overview)
  - docs/CODING-STANDARDS.md (coding standards)
  - docs/LLM-AGENT-REQUIREMENTS.md (LLM requirements)
  - docs/implementation/001-project-setup.md (detailed step guide)

IMPORTANT NOTES:

1. DO NOT skip documentation - every class and method needs docstrings
2. DO NOT use 'Any' type - use proper type hints
3. DO NOT create bare except clauses - catch specific exceptions
4. DO keep functions short (< 50 lines) and focused (single responsibility)
5. DO follow layer separation strictly (Domain → Application → Infrastructure)
6. DO write tests for all code (90%+ domain coverage)
7. DO use KISS principle (simple over clever)

QUALITY OVER QUANTITY:
  Better to have less, working, well-documented code than more, buggy code.

NEXT STEPS AFTER COMPLETION:
  1. Run: pip install -r requirements-dev.txt
  2. Run: pre-commit install
  3. Run: pytest -v
  4. Run: mypy src
  5. Proceed to Step 002: Database Schema
```

## PROMPT END

---

## Usage Instructions

**1. Copy the entire prompt above** (from "PROMPT START" to "PROMPT END")

**2. Paste to your LLM agent** with this additional context if needed:

```
Additional Context:
- We are in Phase 1 (Data Gathering) of a crypto trading system
- Focus on robust, production-ready code
- EU compliance required (regional filtering)
- All configuration in database (only DATABASE_URL in .env)
- Reference documents are in /home/andy/projects/numbers/specV2/docs/

Please implement Step 001: Project Setup following all requirements above.
```

**3. Review the output** against the Acceptance Criteria checklist

**4. Test the implementation**:
```bash
# Create project directory
mkdir crypto-trading-system
cd crypto-trading-system

# Copy generated files
# ... (paste file contents from LLM output)

# Verify
pip install -r requirements-dev.txt
pytest -v
mypy src
pre-commit install
```

---

## Expected Output Size

**Approximately**:
- 20-30 files
- 2000-3000 lines of code (mostly configuration)
- 2-3 hours of LLM generation time

**Key Files to Review Carefully**:
1. `pyproject.toml` - All dependencies correct?
2. `pytest.ini` - Coverage settings correct?
3. `mypy.ini` - Strict mode enabled?
4. `.pre-commit-config.yaml` - All hooks present?
5. `README.md` - Setup instructions clear?
6. `docker-compose-infra.yml` - Services configured correctly?

---

**This prompt is optimized for clear, complete, production-ready output.** 🎯
