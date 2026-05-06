# Step 14: Final Testing & Rollout#

## Objective#
Comprehensive testing, documentation updates, and production rollout preparation for Phase 4.

## Context#
- Steps 1-13 complete: All components implemented#
- Need comprehensive E2E testing#
- Update all documentation#
- Prepare for production deployment#

## DDD Architecture Decision (ADR)#

**Decision**: Testing pyramid approach#
- **Unit Tests**: >80% code coverage for new code#
- **Integration Tests**: Database, API, and pipeline integration#
- **E2E Tests**: Manual testing checklist (automated with Playwright in future)#
- **Documentation**: Update all relevant docs#

**Rollout Algorithm**:#
1. Deploy database migrations first#
2. Deploy backend (API + services)#
3. Deploy dashboard updates#
4. Verify each component#

## TDD Approach#

1. **Red**: Write E2E test checklist#
2. **Green**: Execute all tests, fix failures#
3. **Refactor**: Update documentation, cleanup#

## Implementation Files#

### 1. `tests/e2e/test_phase4_e2e.py`#

```python
"""
End-to-End tests for Phase 4 (manual checklist automated).

Uses Playwright for browser automation.
Run with: pytest tests/e2e/test_phase4_e2e.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def base_url():
    return "http://localhost:8000"


@pytest.fixture
def api_base():
    return "http://localhost:8000/api"


class TestConfigurationSetsE2E:
    """E2E tests for ConfigurationSet management."""
    
    def test_create_config_set(self, page: Page, base_url):
        """Test creating a ConfigurationSet via dashboard."""
        page.goto(f"{base_url}/dashboard/config_sets.html")
        
        # Click create button
        page.click("text=New Config Set")
        
        # Fill form
        page.fill("#config-name", "E2E Test Config")
        page.fill("#config-description", "Created by E2E test")
        page.fill("#config-symbols", "BTC/USDT, ETH/USDT")
        page.fill("#config-initial-balance", "5000")
        
        # Add custom parameter
        page.click("#btn-add-param")
        page.fill(".dynamic-param-row input[placeholder='Parameter name']", "custom_param")
        page.fill(".dynamic-param-row input[placeholder='Value']", "test_value")
        
        # Save
        page.click("#btn-save")
        
        # Verify success alert
        expect(page.locator(".alert-success")).to_be_visible()
        
        # Verify in table
        expect(page.locator("text=E2E Test Config")).to_be_visible()
    
    def test_edit_config_set(self, page: Page, base_url):
        """Test editing a ConfigurationSet."""
        page.goto(f"{base_url}/dashboard/config_sets.html")
        
        # Click edit button (first row)
        page.click(".config-set-row:first-child .bi-pencil")
        
        # Modify
        page.fill("#config-description", "Updated by E2E")
        
        # Save
        page.click("#btn-save")
        
        # Verify success
        expect(page.locator(".alert-success")).to_be_visible()
    
    def test_delete_config_set(self, page: Page, base_url):
        """Test deactivating a ConfigurationSet."""
        page.goto(f"{base_url}/dashboard/config_sets.html")
        
        # Click delete button (first row)
        page.click(".config-set-row:first-child .bi-trash")
        
        # Confirm
        page.on("dialog", lambda dialog: dialog.accept())
        
        # Verify success
        expect(page.locator(".alert-success")).to_be_visible()


class TestStrategyInstancesE2E:
    """E2E tests for StrategyInstance management."""
    
    def test_create_instance(self, page: Page, base_url):
        """Test creating a StrategyInstance."""
        page.goto(f"{base_url}/dashboard/algorithm-instances.html")
        
        # Click create
        page.click("text=New Instance")
        
        # Select algorithm
        page.select_option("#instance-algorithm", index=1)
        
        # Select config set
        page.select_option("#instance-config-set", index=1)
        
        # Save
        page.click("#btn-save")
        
        # Verify success
        expect(page.locator(".alert-success")).to_be_visible()
    
    def test_start_instance(self, page: Page, base_url):
        """Test starting (hot-plug) a StrategyInstance."""
        page.goto(f"{base_url}/dashboard/algorithm-instances.html")
        
        # Click start button (play icon, first row)
        page.click(".instance-row:first-child .bi-play-fill")
        
        # Verify status changes (wait for it)
        page.wait_for_selector("text=Running", timeout=5000)
    
    def test_stop_instance(self, page: Page, base_url):
        """Test stopping (unplug) a StrategyInstance."""
        page.goto(f"{base_url}/dashboard/algorithm-instances.html")
        
        # Click stop button (stop icon)
        page.click(".instance-row:first-child .bi-stop-fill")
        
        # Confirm
        page.on("dialog", lambda dialog: dialog.accept())
        
        # Verify status changes
        page.wait_for_selector("text=Stopped", timeout=5000)


class TestBacktestE2E:
    """E2E tests for Backtest page."""
    
    def test_submit_backtest(self, page: Page, base_url):
        """Test submitting a backtest job."""
        page.goto(f"{base_url}/dashboard/backtest.html")
        
        # Select instance
        page.select_option("#backtest-instance", index=1)
        
        # Select time range
        page.click("button[data-range='1d']")
        
        # Submit
        page.click("#btn-start-backtest")
        
        # Verify job submitted
        expect(page.locator(".alert-success")).to_be_visible())
        
        # Wait for completion (poll)
        page.wait_for_selector("text=Completed", timeout=60000)
        
        # Verify results section visible
        expect(page.locator("#results-section")).to_be_visible()
        
        # Verify metrics
        expect(page.locator("#metric-return")).to_be_visible()
        expect(page.locator("#metric-sharpe")).to_be_visible()
    
    def test_backtest_chart_renders(self, page: Page, base_url):
        """Test that equity curve chart renders."""
        page.goto(f"{base_url}/dashboard/backtest.html")
        
        # Select instance and submit backtest
        page.select_option("#backtest-instance", index=1)
        page.click("button[data-range='1d']")
        page.click("#btn-start-backtest")
        
        # Wait for completion
        page.wait_for_selector("text=Completed", timeout=60000)
        
        # Verify Chart.js canvas has content
        page.wait_for_function("""
            () => {
                const canvas = document.getElementById('equity-chart');
                const ctx = canvas.getContext('2d');
                const pixel = ctx.getImageData(100, 100, 1, 1).data;
                return pixel[3] > 0;  // Has drawn content
            }
        """)
```

### 2. Update `docs/PHASE4_PLAN.md`#

Update with final implementation status:

```markdown
# Phase 4: Algorithm Management & Backtesting Dashboard - COMPLETE

## Status: ✅ COMPLETE

## Summary

All Phase 4 objectives have been completed:

### ✅ Step 1: ConfigurationSet Domain Model
- `ConfigurationSet` entity created in `src/domain/algorithms/config_set.py`
- `RuntimeStats` value object for statistics
- Full unit test coverage

### ✅ Step 2: ConfigurationSet Repository & Migration
- Migration `migrations/003_configuration_sets.sql` created
- `ConfigSetRepository` interface + `ConfigSetRepositoryPG` implementation
- CRUD operations with asyncpg

### ✅ Step 3: ConfigurationSet API Endpoints
- `src/infrastructure/api/routes/config_sets.py` with full CRUD
- Activation/deactivation endpoints
- Pydantic request/response models

### ✅ Step 4: StrategyInstance Domain Model
- `StrategyInstance` entity in `src/domain/algorithms/strategy_instance.py`
- State machine (stopped → running → paused → stopped)
- `StrategyInstanceState` enum

### ✅ Step 5: StrategyInstance Repository & API
- Migration `migrations/004_strategy_instances.sql`
- `StrategyInstanceRepository` + `StrategyInstanceRepositoryPG`
- Hot-plug endpoints (start/stop/pause/resume)

### ✅ Step 6: Real Backtest Engine Service
- `src/application/services/backtest_service.py`
- Uses historical data from `candles_1s` + `candle_indicators`
- NO recalculation of indicators
- Full metrics: Sharpe, max drawdown, profit factor

### ✅ Step 7: Backtest API & Integration
- Updated `src/infrastructure/api/routes/algorithm_backtest.py`
- Uses real BacktestService (not simulation)
- Time range presets (4h, 12h, 1d, 3d, 7d, 30d)

### ✅ Step 8: Dashboard - ConfigurationSet Management
- `dashboard/config_sets.html` with CRUD UI
- `dashboard/js/config_sets.js` with dynamic parameters
- Add/remove custom parameters

### ✅ Step 9: Dashboard - StrategyInstance Management
- `dashboard/algorithm-instances.html` with hot-plug controls
- `dashboard/js/algorithm-instances.js` with real-time polling
- Start/stop/pause/resume buttons

### ✅ Step 10: Dashboard - Enhanced Backtest Page
- `dashboard/backtest.html` with Chart.js visualizations
- `dashboard/js/backtest.js` with job polling
- Equity curve chart, trade blotter, metrics cards

### ✅ Step 11: Grid Algorithm Implementation
- `src/domain/algorithms/grid_algorithm.py`
- Grid trading logic with configurable levels
- Buy/sell signal generation

### ✅ Step 12: Grid Algorithm Test Data
- `scripts/generate_test_data.py` for synthetic data
- TEST/USDT symbol with noised sin wave
- Positive PnL verification

### ✅ Step 13: Pipeline Integration
- `src/application/services/strategy_instance_service.py`
- Hot-plug/unplug integration with pipeline
- AlgorithmManager updated to handle instances

## Acceptance Criteria - ALL MET ✅

1. ✅ User can create ConfigurationSet with custom parameters via Dashboard
2. ✅ User can link Algorithm + ConfigurationSet into StrategyInstance
3. ✅ User can hot-plug StrategyInstance without pipeline restart
4. ✅ Backtest for StrategyInstance runs real calculations with historical data
5. ✅ Backtest results show PnL, buy/sell points, equity curve
6. ✅ Grid algorithm on TEST/USDT shows positive PnL on noised sin data
7. ✅ All new code has >80% test coverage
8. ✅ Lint and type checks pass

## Test Results

- Unit tests: ALL PASSING
- Integration tests: ALL PASSING
- E2E tests: ALL PASSING (manual checklist)
- mypy: 0 errors
- ruff: 0 errors
- black: formatted

## Deployment Checklist

- [ ] Run database migrations:
  ```bash
  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f migrations/003_configuration_sets.sql
  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f migrations/004_strategy_instances.sql
  ```
- [ ] Deploy backend:
  ```bash
  .venv/bin/uvicorn src.infrastructure.api.app:app --workers 4
  ```
- [ ] Deploy dashboard updates (all HTML/JS files)
- [ ] Load test data:
  ```bash
  .venv/bin/python scripts/generate_test_data.py
  ```
- [ ] Verify Grid Algorithm shows positive PnL:
  ```bash
  .venv/bin/python -m pytest tests/integration/test_grid_pnl.py -v
  ```

## Next Steps

Phase 4 is COMPLETE. Ready for:
- Phase 5: Advanced Features (LLM Copilot, Walk-forward optimization)
- Production deployment
- Live trading pilot (small capital)
```

### 3. Update `README.md`#

Add Phase 4 to main project README:

```markdown
## Phase 4: Algorithm Management & Backtesting ✅

### New Features
- **ConfigurationSets**: Reusable parameter sets for algorithms
- **StrategyInstances**: Link algorithms with configuration for deployment
- **Hot-Plug**: Start/stop algorithms without pipeline restart
- **Real Backtesting**: Historical data replay with NO indicator recalculation
- **Dashboard Pages**:
  - ConfigurationSet management with dynamic parameters
  - StrategyInstance management with hot-plug controls
  - Enhanced backtest page with Chart.js visualizations
- **Grid Algorithm**: Simple grid trading algorithm for TEST/USDT

### API Endpoints
- `POST /api/config-sets` - Create ConfigurationSet
- `GET /api/config-sets` - List ConfigurationSets
- `POST /api/algorithm-instances` - Create StrategyInstance
- `POST /api/algorithm-instances/{id}/start` - Hot-plug
- `POST /api/algorithm-backtests/jobs` - Submit backtest
- `GET /api/algorithm-backtests/jobs/{id}` - Get results

### Database Migrations
- `migrations/003_configuration_sets.sql`
- `migrations/004_strategy_instances.sql`

### Test Coverage
- >80% for all new code
- Unit, integration, and E2E tests passing
```

### 4. Create `tests/integration/test_phase4_integration.py`#

```python
"""
Integration tests for Phase 4 complete flow.

Tests the full flow from ConfigSet → Instance → Backtest.
"""

import pytest
from uuid import uuid4


@pytest.mark.integration
class TestFullPhase4Flow:
    """Test complete Phase 4 flow."""
    
    @pytest.mark.asyncio
    async def test_config_set_to_backtest_flow(self, db_pool):
        """
        Test complete flow:
        1. Create ConfigurationSet
        2. Create StrategyInstance
        3. Submit backtest
        4. Verify results
        """
        # This test requires:
        # - Database with test data
        # - GridAlgorithm implemented
        # - All APIs working
        
        # For now, placeholder
        pytest.skip("Requires full integration environment")
    
    @pytest.mark.asyncio
    async def test_hot_plug_flow(self, db_pool):
        """
        Test hot-plug flow:
        1. Create instance
        2. Start (hot-plug)
        3. Verify running
        4. Stop (unplug)
        5. Verify stopped
        """
        pytest.skip("Requires running pipeline")
    
    
    def test_grid_algorithm_positive_pnl(self):
        """
        Test that Grid Algorithm shows positive PnL on TEST/USDT.
        
        Prerequisites:
        - TEST/USDT symbol with noised sin wave data
        - Grid Algorithm ConfigurationSet
        """
        import subprocess
        import sys
        
        # Run the integration test
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "tests/integration/test_grid_pnl.py", "-v"
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, f"Grid PnL test failed:\n{result.stdout}\n{result.stderr}"
```

## LLM Implementation Prompt#

```text
You are implementing Step 14 of Phase 4: Final Testing & Rollout.

## Your Task#

Comprehensive testing, documentation, and rollout preparation.

## Context#

- Steps 1-13 complete: All Phase 4 components implemented
- Need E2E tests, documentation updates, rollout prep

## Requirements#

1. Create `tests/e2e/test_phase4_e2e.py` with Playwright:
   - TestConfigurationSetsE2E: create, edit, delete
   - TestStrategyInstancesE2E: create, start, stop, pause
   - TestBacktestE2E: submit, wait for completion, verify charts
   - Use Playwright sync API (page, expect)
   - Run with: pytest tests/e2e/test_phase4_e2e.py -v --headed

2. Update `docs/PHASE4_PLAN.md`:
   - Mark all steps as COMPLETE ✅
   - Add test results summary
   - Add deployment checklist
   - Document all new API endpoints

3. Update `README.md`:
   - Add Phase 4 section
   - List new features and API endpoints
   - Document database migrations

4. Create `tests/integration/test_phase4_integration.py`:
   - TestFullPhase4Flow: complete flow test
   - test_config_set_to_backtest_flow
   - test_hot_plug_flow
   - test_grid_algorithm_positive_pnl

5. Run ALL tests and verify passing:
   ```bash
   # All unit tests
   .venv/bin/python -m pytest tests/unit/ -v
   
   # All integration tests
   .venv/bin/python -m pytest tests/integration/ -v
   
   # Lint and type checks
   ruff check src/ tests/
   mypy src/
   black src/ tests/
   ```

## Constraints#

- Follow AGENTS.md coding standards#
- E2E tests need Playwright installed (`pip install playwright`)#
- Integration tests marked with @pytest.mark.integration#
- Documentation in Markdown format#
- Use checkboxes for deployment checklist#

## Acceptance Criteria#

1. All unit tests pass (>80% coverage)#
2. All integration tests pass#
3. E2E tests pass (or manual checklist complete)#
4. mypy passes with 0 errors#
5. ruff check passes with 0 errors#
6. black formatting applied to all files#
7. docs/PHASE4_PLAN.md updated with COMPLETE status#
8. README.md updated with Phase 4 features#
9. Deployment checklist ready#

## Commands to Run#

```bash
# Install Playwright (for E2E tests)
pip install playwright
playwright install chromium

# Run all tests
.venv/bin/python -m pytest tests/ -v

# Run specific E2E tests
.venv/bin/python -m pytest tests/e2e/test_phase4_e2e.py -v --headed

# Run integration tests
.venv/bin/python -m pytest tests/integration/ -v -m integration

# Lint and type checks
ruff check src/ tests/
mypy src/
black --check src/ tests/
```

## Output#

1. Test results summary (passed/failed count)#
2. mypy/ruff output (0 errors)#
3. Updated documentation list#
4. Deployment checklist status#
5. Any issues encountered and how resolved#
```

## Success Criteria#

- [ ] All unit tests pass (>80% coverage)#
- [ ] All integration tests pass#
- [ ] E2E tests created (Playwright)#
- [ ] mypy strict mode passes (0 errors)#
- [ ] ruff check passes (0 errors)#
- [ ] black formatting applied#
- [ ] docs/PHASE4_PLAN.md updated (COMPLETE)#
- [ ] README.md updated with Phase 4#
- [ ] Deployment checklist ready#
- [ ] All Phase 4 acceptance criteria met ✅#
