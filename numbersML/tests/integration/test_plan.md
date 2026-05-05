# Lifecycle Integration Test Plan for Phase 4 Dashboard Endpoints

## Overview
This document outlines the integration test algorithm for all new API endpoints implemented in Phase 4 (Dashboard features).

## Prerequisites

### Bugs Identified and Fixed
1. **`market.py:450`** - Parameter `status` shadows FastAPI `status` module
   - Fixed: Renamed parameter to `order_status`
   
2. **`PaperMarketService`** - Missing `get_orders()` and `get_trades()` methods
   - Fixed: Added methods to `PaperMarketService` and `MarketService` base class

3. **`market_service.py`** - Missing `Protocol` import
   - Fixed: Added `Protocol` to typing imports

## Test Structure

```
tests/
├── integration/
│   ├── api/
│   │   ├── test_config_set_api.py (EXISTS - ConfigSet lifecycle)
│   │   ├── test_algorithm_instances_lifecycle.py (CREATED - needs fixes)
│   │   ├── test_algorithm_backtest_lifecycle.py (CREATED - needs fixes)
│   │   └── test_dashboard_api.py (TO CREATE)
```

## Test Implementation Approach

### Option 1: Mock-Based Tests (Current Approach)
- Use `unittest.mock.patch` to mock repositories
- Use `TestClient` from FastAPI
- **Issue**: FastAPI dependency injection requires proper override mechanism

### Option 2: Database-Based Tests (Recommended)
- Use test database with `testcontainers` or existing test DB
- Load test data using `scripts/load_test_data.sh`
- Test against real database state

### Option 3: Dependency Override Approach
- Override FastAPI dependencies using `app.dependency_overrides`
- Mock the repository at the dependency level

## Test Cases by Endpoint

### 1. ConfigurationSet Endpoints (`/api/config-sets`)
**Test File**: `test_config_set_api.py` (already exists)

| Test Case | Method | Endpoint | Expected |
|-----------|--------|----------|----------|
| Create ConfigSet | POST | `/api/config-sets` | 201 |
| Get ConfigSet by ID | GET | `/api/config-sets/{id}` | 200 |
| List ConfigSets | GET | `/api/config-sets` | 200 |
| Update ConfigSet | PUT | `/api/config-sets/{id}` | 200 |
| Update Config Only | PATCH | `/api/config-sets/{id}/config` | 200 |
| Activate | POST | `/api/config-sets/{id}/activate` | 200 |
| Deactivate | POST | `/api/config-sets/{id}/deactivate` | 200 |
| Delete (soft) | DELETE | `/api/config-sets/{id}` | 204 |
| Auth: Create requires trader/admin | POST | `/api/config-sets` | 401/403 |
| Auth: Read with read key | GET | `/api/config-sets` | 200 |
| Error: Duplicate name | POST | `/api/config-sets` | 400 |
| Error: Non-existent ID | GET | `/api/config-sets/{fake_id}` | 404 |

### 2. AlgorithmInstance Endpoints (`/api/algorithm-instances`)
**Test File**: `test_algorithm_instances_lifecycle.py`

| Test Case | Method | Endpoint | Expected |
|-----------|--------|----------|----------|
| Create Instance | POST | `/api/algorithm-instances` | 201 |
| List Instances | GET | `/api/algorithm-instances` | 200 |
| List with status filter | GET | `/api/algorithm-instances?status=running` | 200 |
| Get Instance by ID | GET | `/api/algorithm-instances/{id}` | 200 |
| Start Instance | POST | `/api/algorithm-instances/{id}/start` | 200 |
| Stop Instance | POST | `/api/algorithm-instances/{id}/stop` | 200 |
| Pause Instance | POST | `/api/algorithm-instances/{id}/pause` | 200 |
| Resume Instance | POST | `/api/algorithm-instances/{id}/resume` | 200 |
| Delete Instance | DELETE | `/api/algorithm-instances/{id}` | 204 |
| Auth: Start requires trader | POST | `/api/algorithm-instances/{id}/start` | 403 (read key) |
| Error: Invalid UUID | POST | `/api/algorithm-instances` | 422 |
| Error: Non-existent instance | POST | `/api/algorithm-instances/{id}/start` | 404 |
| Error: Start stopped instance | POST | `/api/algorithm-instances/{id}/start` | 400 |
| Lifecycle: Create → Start → Stop → Delete | Multiple | Multiple | Various |

### 3. Backtest Endpoints (`/api/algorithm-backtests`)
**Test File**: `test_algorithm_backtest_lifecycle.py`

| Test Case | Method | Endpoint | Expected |
|-----------|--------|----------|----------|
| Submit job (1d preset) | POST | `/api/algorithm-backtests/jobs` | 202 |
| Submit job (custom range) | POST | `/api/algorithm-backtests/jobs` | 202 |
| Submit with all presets | POST | `/api/algorithm-backtests/jobs` | 202 |
| Check job status (pending) | GET | `/api/algorithm-backtests/jobs/{id}` | 200 |
| Check job status (completed) | GET | `/api/algorithm-backtests/jobs/{id}` | 200 |
| List all jobs | GET | `/api/algorithm-backtests/jobs` | 200 |
| Auth: Submit requires trader | POST | `/api/algorithm-backtests/jobs` | 403 (read key) |
| Error: Invalid time range | POST | `/api/algorithm-backtests/jobs` | 422 |
| Error: Custom range without dates | POST | `/api/algorithm-backtests/jobs` | 400 |
| Error: Non-existent instance | POST | `/api/algorithm-backtests/jobs` | 404 |
| Error: Non-existent job | GET | `/api/algorithm-backtests/jobs/{fake_id}` | 404 |

### 4. Dashboard Endpoints (`/api/dashboard`)
**Test File**: `test_dashboard_api.py` (to create)

| Test Case | Method | Endpoint | Expected |
|-----------|--------|----------|----------|
| Get collector status | GET | `/api/dashboard/status` | 200 |
| Start collector | POST | `/api/dashboard/collector/start` | 200 |
| Stop collector | POST | `/api/dashboard/collector/stop` | 200 |
| Get SLA metrics | GET | `/api/dashboard/metrics?seconds=60` | 200 |
| Get SLA metrics (invalid) | GET | `/api/dashboard/metrics?seconds=999` | 400 |
| Get dashboard stats | GET | `/api/dashboard/stats` | 200 |

## Recommended Implementation Steps

### Step 1: Fix Mock Approach
The current mock-based approach in `test_algorithm_instances_lifecycle.py` doesn't work because:
- FastAPI's dependency injection creates fresh repository instances
- Patching the class doesn't affect the dependency

**Solution**: Use `app.dependency_overrides` to mock at the dependency level.

```python
from fastapi.testclient import TestClient
from src.infrastructure.api.app import app

# Override dependency
async def mock_get_repo():
    mock_repo = MagicMock()
    yield mock_repo

app.dependency_overrides[get_instance_repository] = mock_get_repo

client = TestClient(app)
```

### Step 2: Use Existing Test Patterns
Follow the pattern in `test_config_set_api.py`:
- Set environment variables before imports
- Use module-scoped fixtures
- Mock at the right level

### Step 3: Create Test Data Fixtures
For database-based tests:
```python
@pytest.fixture
async def test_algorithm_instance(db_pool):
    """Create a test AlgorithmInstance in the database."""
    # Insert into database
    # Yield instance data
    # Cleanup after test
```

### Step 4: Run and Validate
```bash
# Run specific test file
.venv/bin/python -m pytest tests/integration/api/test_algorithm_instances_lifecycle.py -v

# Run all integration tests
.venv/bin/python -m pytest tests/integration/ -v

# Run with coverage
.venv/bin/python -m pytest tests/integration/ --cov=src --cov-report=html
```

## Current Status

### Fixed Files
- [x] `src/infrastructure/api/routes/market.py` - Fixed parameter shadowing
- [x] `src/domain/services/market_service.py` - Added `get_orders()`, `get_trades()`, `Protocol` import
- [x] `src/infrastructure/market/paper_market_service.py` - Added `get_orders()`, `get_trades()` implementation

### Created Test Files (Need Fixes)
- [x] `tests/integration/api/test_algorithm_instances_lifecycle.py` - Created (mock approach broken)
- [x] `tests/integration/api/test_algorithm_backtest_lifecycle.py` - Created (mock approach broken)

### TODO
- [ ] Fix dependency mocking in `test_algorithm_instances_lifecycle.py`
- [ ] Fix dependency mocking in `test_algorithm_backtest_lifecycle.py`
- [ ] Create `test_dashboard_api.py`
- [ ] Run all tests and verify they pass
- [ ] Add to CI/CD pipeline

## Running Tests

```bash
# Run all integration tests
.venv/bin/python -m pytest tests/integration/api/ -v --tb=short

# Run specific test class
.venv/bin/python -m pytest tests/integration/api/test_algorithm_instances_lifecycle.py::TestAlgorithmInstanceLifecycle -v

# Run single test
.venv/bin/python -m pytest tests/integration/api/test_algorithm_instances_lifecycle.py::TestAlgorithmInstanceLifecycle::test_create_and_list_instances -v
```

## Notes

1. The existing `test_config_set_api.py` uses a simple approach that works for basic CRUD
2. For AlgorithmInstance tests with state transitions (start/stop/pause/resume), proper mocking is crucial
3. Backtest tests may require actual BacktestService implementation or more complex mocking
4. Consider using `pytest-httpx` or `pytest-fastapi` for better async test support
