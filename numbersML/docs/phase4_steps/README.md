# Phase 4 Step Packets

This folder contains independent implementation packets for Phase 4: Algorithm Management & Backtesting Dashboard.

## Overview

Phase 4 focuses on creating a robust, decoupled management system for trading strategies. It introduces the concept of `ConfigurationSet` to separate algorithm logic from runtime parameters, and provides a rich dashboard for orchestration, monitoring, and backtesting.

## Progress

- ✅ **Step 1** (`STEP_01_CONFIGSET_DOMAIN.md`): Completed - ConfigurationSet domain model, entity implementation, TDD tests
- ✅ **Step 2** (`STEP_02_CONFIGSET_REPOSITORY.md`): Completed - ConfigurationSet repository, PostgreSQL implementation, migrations
- ✅ **Step 3** (`STEP_03_CONFIGSET_API.md`): Completed - FastAPI routes for config sets, request/response models
- ✅ **Step 4** (`STEP_04_STRATEGY_INSTANCE_DOMAIN.md`): Completed - StrategyInstance domain model, linking strategy to config
- ✅ **Step 5** (`STEP_05_STRATEGY_INSTANCE_REPO_API.md`): Completed - StrategyInstance repository and API, start/stop endpoints
- ✅ **Step 6** (`STEP_06_BACKTEST_SERVICE.md`): Completed - BacktestService implementation, candle loading, metrics calculation, unit tests
- ✅ **Step 7** (`STEP_07_BACKTEST_API.md`): Completed - Backtest API endpoints, job tracking, progress reporting, real BacktestService integration
- ✅ **Step 8** (`STEP_08_DASHBOARD_CONFIG_SETS.md`): Completed - Dashboard UI for config set CRUD, dynamic parameter editing
- ✅ **Step 9** (`STEP_09_DASHBOARD_INSTANCES.md`): Completed - Dashboard UI for strategy instances, hot-plug toggle, real-time stats
- ✅ **Step 10** (`STEP_10_DASHBOARD_BACKTEST.md`): Completed - Backtest result page, charts, metrics table, time range selector
- ✅ **Step 11** (`STEP_11_GRID_STRATEGY.md`): Completed - SimpleGridAlgorithm implementation, buy/sell grid logic, unit tests
- ✅ **Step 12** (`STEP_12_GRID_TEST_DATA.md`): Completed - Test data setup, TEST/USDT config, synthetic data for positive PnL
- ✅ **Step 13** (`STEP_13_PIPELINE_INTEGRATION.md`): Completed - Pipeline integration, strategy execution, signal generation
- ✅ **Step 14** (`STEP_14_TESTING_ROLLOUT.md`): Completed - Integration testing, automated tests, rollout checklist

## Definition of Done (DoD) for Each Step

Each step is considered complete when ALL of the following criteria are met:

### Code Quality Gates
- [ ] All new code follows AGENTS.md coding standards
- [ ] Google-style docstrings on all public methods/classes
- [ ] Full type annotations (mypy strict mode passes)
- [ ] Line length ≤ 100 characters (black formatted)
- [ ] ruff check passes (rules: E, W, F, I, N, UP, B, C4)
- [ ] black formatting applied

### Testing Requirements
- [ ] TDD approach followed (tests written before/during implementation)
- [ ] All new unit tests pass
- [ ] Test coverage for new code ≥ 80%
- [ ] Integration tests updated if needed
- [ ] No skipped or xfailed tests without justification

### Architecture & Design
- [ ] DDD boundaries respected (domain ← application ← infrastructure)
- [ ] No cross-layer leakage
- [ ] Dependency injection via constructor (no global singletons)
- [ ] ABCs used for framework extension points
- [ ] ADR created/updated for non-trivial design decisions

### Documentation
- [ ] Step file completed with implementation details
- [ ] API documentation updated (if new endpoints added)
- [ ] Migration scripts documented (if schema changes)
- [ ] LLM Implementation Prompt section completed

### Verification
- [ ] `ruff check src/ tests/` passes with no errors
- [ ] `black src/ tests/` applied
- [ ] `mypy src/` passes (strict mode for domain/application)
- [ ] Step-specific tests pass: `.venv/bin/python -m pytest tests/unit/[step_path] -v`
- [ ] No unresolved TODOs without issue reference

### Commit Requirements
- [ ] Changes committed with descriptive message
- [ ] Commit message follows project convention (see `git log`)
- [ ] No secrets or credentials in commit

## Suggested Execution Order

1. `STEP_01_CONFIGSET_DOMAIN.md` - Domain foundation
2. `STEP_02_CONFIGSET_REPOSITORY.md` - Data persistence
3. `STEP_03_CONFIGSET_API.md` - API layer
4. `STEP_04_STRATEGY_INSTANCE_DOMAIN.md` - Instance domain model
5. `STEP_05_STRATEGY_INSTANCE_REPO_API.md` - Instance persistence & API
6. `STEP_06_BACKTEST_SERVICE.md` - Backtest engine core
7. `STEP_07_BACKTEST_API.md` - Backtest API endpoints
8. `STEP_08_DASHBOARD_CONFIG_SETS.md` - Dashboard: config sets
9. `STEP_09_DASHBOARD_INSTANCES.md` - Dashboard: instances
10. `STEP_10_DASHBOARD_BACKTEST.md` - Dashboard: backtest visualization
11. `STEP_11_GRID_STRATEGY.md` - Grid strategy implementation
12. `STEP_12_GRID_TEST_DATA.md` - Test data & synthetic data
13. `STEP_13_PIPELINE_INTEGRATION.md` - Pipeline integration
14. `STEP_14_TESTING_ROLLOUT.md` - Final testing & rollout

**Dependency Chain:**
- Steps 1-3 must complete before 4-5
- Steps 4-5 must complete before 8-9
- Steps 6-7 can run in parallel after 1-3
- Steps 8-10 depend on their respective backend steps
- Steps 11-12 can run in parallel after 4-5
- Step 13 requires 11-12 complete
- Step 14 is final integration testing

## Session Kickoff Template

Use `SESSION_KICKOFF_TEMPLATE.md` at the start of each implementation session. It provides:
- Mandatory context requirements
- Execution rules
- Required output format
- Quality gates
- Stop conditions

## Phase 4 Acceptance Criteria

1. User can create a `ConfigurationSet` with custom parameters via Dashboard
2. User can link a `Algorithm` to a `ConfigurationSet` and start it without restarting the pipeline
3. Backtest for a Algorithm-Config pair can be executed and visualized on a chart
4. The system uses existing indicators from the DB during backtests (no recalculation)
5. `SimpleGridAlgorithm` is functional and included in the default test data
6. All dashboard features (config sets, instances, backtest) are fully functional
7. Integration tests verify end-to-end functionality with positive PnL on test data

## Notes for LLM Implementers

- Each step file is designed for a separate LLM session
- Read the step file completely before starting implementation
- Follow the "LLM Implementation Prompt" section in each step file
- Run quality gates before marking step complete
- Create ADRs for design decisions before implementing non-trivial features
- Keep changes scoped to the step - don't implement future steps prematurely
- If blocked by missing context, stop and ask targeted questions

## File Structure Per Step

Each step file should contain:
1. **Objective** - Clear goal statement
2. **Context** - What exists, what's needed
3. **DDD Architecture Decision** (if applicable) - ADR section
4. **TDD Approach** - Red-Green-Refactor notes
5. **Implementation Files** - Code examples and structure
6. **LLM Implementation Prompt** - Copy-paste prompt for implementation
7. **Success Criteria** - Checkbox list for verification
8. **Commands to Run** - Specific test/lint commands
9. **Output** - Expected deliverables format
