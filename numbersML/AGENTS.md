# AGENTS.md — numbersML Coding Agent Guide

## Project Overview

Python 3.11 real-time crypto trading pipeline with ML inference. Uses asyncpg (PostgreSQL),
FastAPI, PyTorch, and Binance WebSocket feeds. Follows Domain-Driven Design (DDD).

## Environment Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # Dev + test dependencies
pip install -e ".[dev]"                          # Editable install with dev extras
docker compose -f docker/docker-compose-infra.yml up -d  # Start Postgres + Redis
```

Python version is pinned to **3.11** (`.python-version`).

### Test Database Setup

For integration tests, the database needs to be populated with test data:

```bash
# Load test data into the database
export DB_HOST=localhost DB_PORT=5432 DB_NAME=crypto_trading DB_USER=crypto DB_PASS=crypto_secret
./scripts/load_test_data.sh

# Or manually with psql
psql -h localhost -p 5432 -U crypto -d crypto_trading -f migrations/test_data.sql
```

The test data SQL script (`migrations/test_data.sql`) creates:
- Test symbols (BTC/USDC, ETH/USDC, DOGE/USDC, ADA/USDC) marked with `is_test=true`
- Collection configuration for test symbols
- Common indicator definitions (RSI, SMA, EMA, MACD, Bollinger Bands)
- System configuration entries
- Sample candles and indicators for tests that need existing data

The pytest fixture in `tests/integration/conftest.py` automatically sets up test data when running integration tests.

---

## Build, Lint & Test Commands

### Linting and Formatting

```bash
ruff check src/ tests/                  # Lint (rules: E, W, F, I, N, UP, B, C4)
ruff check --fix src/ tests/            # Lint with auto-fix
black src/ tests/                       # Format (line-length=100, py311)
mypy src/                               # Type checking (strict mode)
pre-commit run --all-files              # Run all pre-commit hooks
```

### Running Tests

```bash
# All unit tests (~457 tests, ~40 seconds)
.venv/bin/python -m pytest tests/unit/ -v

# All tests
.venv/bin/python -m pytest tests/ -v

# Single test file
.venv/bin/python -m pytest tests/unit/indicators/test_indicator_framework.py -v

# Single test class
.venv/bin/python -m pytest tests/unit/pipeline/test_aggregator.py::TestCandleAggregator -v

# Single test function
.venv/bin/python -m pytest tests/unit/indicators/test_indicator_framework.py::TestRSIIndicator::test_rsi_calculation -v

# By marker
.venv/bin/python -m pytest -m unit -v
.venv/bin/python -m pytest -m "not integration" -v
```

Available markers: `unit`, `integration`, `e2e`, `slow`, `pipeline`, `indicators`

`asyncio_mode = auto` is set — all test functions may be `async def` without decorators.

> **Note**: Some integration tests in `tests/integration/` require a live database and
> are excluded by default. See `BROKEN_TESTS.md` for details.

---

## Project Structure

```
src/
├── main.py                  # Entry point (asyncio.run)
├── pipeline/                # Real-time trade pipeline (aggregation, indicators, DB write)
├── indicators/              # Technical indicator framework (base ABC + registry)
├── domain/                  # DDD: entities, value objects, domain events, repositories
├── application/             # Application services / use cases
├── infrastructure/          # asyncpg DB, FastAPI routes, Binance exchange adapter
├── cli/                     # Click-based CLI entry points
└── external/                # External service integrations
ml/                          # PyTorch models, training loop, dataset, inference
tests/
├── conftest.py
├── unit/                    # Mirror of src/ structure
├── integration/
└── e2e/
migrations/                  # SQL schema files (apply with psql)
docker/                      # docker-compose-infra.yml
```

---

## Code Style Guidelines

### Formatting

- **Line length**: 100 characters (`black` + `ruff` both configured to 100)
- **Formatter**: `black` (do not manually reformat; run `black src/ tests/`)
- **Linter**: `ruff` with rule sets E, W, F, I, N, UP, B, C4 (E501 ignored)
- **Target**: Python 3.11 syntax and stdlib

### Imports

- Order: standard library → third-party → local (enforced by `ruff I` / isort)
- Use **relative imports** within a package: `from .base import Indicator`
- Use **absolute imports** across packages: `from src.pipeline.ticket import PipelineTicket`
- No wildcard imports (`from module import *`)

### Naming Conventions

| Construct | Convention | Example |
|-----------|------------|---------|
| Classes | `PascalCase` | `TradePipeline`, `RSIIndicator` |
| Functions / methods | `snake_case` | `calculate`, `get_code_hash` |
| Private methods | `_snake_case` | `_calculate_rsi`, `_ticker_loop` |
| Constants | `UPPER_SNAKE_CASE` | `LIVE_STEPS`, `MAX_RETRIES` |
| Modules | `snake_case` | `indicator_calculator.py` |

### Type Annotations

- **All public functions and methods must have full type annotations** (`mypy strict=true`)
- Return type `-> None` is explicit, never omitted
- Use `Optional[X]` or `X | None` (both styles exist; prefer `X | None` for new code)
- Use `Dict`, `List`, `Tuple` from `typing` for complex generics; prefer built-in generics
  (`dict[str, Any]`, `list[str]`) for Python 3.11+ new code
- `numpy.ndarray` types should be explicitly typed
- `mypy` is relaxed for `src.infrastructure.*` and `tests.*` (typed defs not required there)

### Docstrings

- **Google-style** docstrings throughout
- Every module has a module-level docstring
- Classes and public methods document `Args:`, `Returns:`, `Raises:` sections
- Include `Example:` blocks with `>>>` notation where helpful

```python
def calculate(self, data: np.ndarray) -> IndicatorResult:
    """Calculate RSI from price data.

    Args:
        data: 1-D array of closing prices, at least `period + 1` elements.

    Returns:
        IndicatorResult with `value` (float) and `metadata` dict.

    Raises:
        ValueError: If data length is insufficient for the configured period.
    """
```

### Logging

- Every module defines: `logger = logging.getLogger(__name__)`
- Use f-strings in log messages: `logger.error(f"Connection failed: {e}")`
- Do **not** use `print()` in production code

### Error Handling

- Use `try/except Exception as e: logger.error(f"...")` in async loops
- Handle `asyncio.CancelledError` explicitly in every long-running async coroutine
- Raise `ValueError` with descriptive messages for validation failures
- Track error counts in stats dicts (`self._stats["database_errors"] += 1`)
- No broad `except:` — always catch a specific exception type or `Exception`

### Async Patterns

- All database access via `asyncpg` — use `async with pool.acquire() as conn:`
- Background tasks via `asyncio.create_task(self._loop())` with graceful cancellation
- Entry points use `asyncio.run(main())` in `if __name__ == "__main__":` blocks
- In tests, mark async tests `async def test_...` — `asyncio_mode = auto` handles the rest

### Data Classes

- Use `@dataclass` for value objects and results
- Use `@dataclass(frozen=True)` for immutable value objects / domain events
- Domain entities inherit from `Entity` base class in `src/domain/models/base.py`

### Classes and Architecture

- Follow the DDD layer boundaries: `domain` ← `application` ← `infrastructure`
- Dependency injection via constructor (no global singletons outside registries)
- `indicators/registry.py` uses auto-discovery; new indicators are registered automatically
- Use ABCs (`abc.ABC`, `@abstractmethod`) for framework extension points

### Tests

- Tests mirror `src/` structure under `tests/unit/`
- Group related tests in `class TestXxx:` — no module-level test functions
- Use `pytest.raises(SomeError)` context manager for exception assertions
- Use `numpy.testing.assert_array_almost_equal` for float array comparisons
- Mock external I/O (DB, WebSocket, HTTP) with `unittest.mock.AsyncMock` / `MagicMock`
- Fixtures go in `conftest.py` at the appropriate directory level
- Tests should not require network access or a running database unless marked `integration`

---

## ML Module Notes (`ml/`)

- Models defined in `ml/model.py`: `SimpleMLP`, CNN+Attention (`FullModel`), `TransformerModel`
- Dataset loading from PostgreSQL via `ml/dataset.py` (`WideVectorDataset`)
- Configuration via dataclasses in `ml/config.py`: `PipelineConfig`, `ModelConfig`, `TrainingConfig`
- Saved model artefacts go in `ml/models/<model_type>/`

```bash
.venv/bin/python -m ml.train --model simple --epochs 30 --symbol BTC/USDC
.venv/bin/python -m ml.compare --models ml/models/simple/best_model.pt
```
