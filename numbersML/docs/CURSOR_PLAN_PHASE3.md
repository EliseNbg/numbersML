# CURSOR Plan: Phase 3 (Algorithm Builder, Market Service, Activation, Backtesting)

## Goal

Build a production-safe algorithm lifecycle with:
1. Web GUI to create and modify trading algorithms.
2. Market Service for trade endpoints (paper/test and live/prod modes).
3. Activate/deactivate algorithms from the dashboard pipeline page.
4. Backtest algorithms over a time range with detailed statistics using the Market Service execution model.

This plan is split into implementation steps that a modern LLM model can execute one by one.

---

## Design Principles (Best Practices)

- **Canonical algorithm spec first**: represent algorithm logic and risk rules as versioned JSON config, not hard-coded Python classes only.
- **Separation of concerns**: signal generation, risk checks, and order execution are separate modules.
- **One execution contract**: paper and live trading share the same `MarketService` interface.
- **Safe rollout**: paper-first, small-size live pilot, kill switch, hard risk limits.
- **Reproducibility and auditability**: every algorithm change, activation, and backtest run is versioned and logged.
- **Realistic backtesting**: include fees, slippage, latency assumptions, and order-fill semantics aligned with Market Service.
- **LLM guardrails**: JSON schema validation, bounded parameter ranges, prompt-injection protection, and human approval for activation.

---

## Target Architecture (Phase 3)

1. `Algorithm Config Layer`  
   - Stores versioned algorithm definitions, parameters, risk limits, and mode.
2. `Algorithm Runtime Layer`  
   - Loads active algorithm versions, processes signals, calls Market Service.
3. `Market Service Layer`  
   - `PaperMarketService` and `LiveMarketService` implement one domain interface.
4. `Backtest Engine Layer`  
   - Replays historical data and executes orders through paper-mode semantics.
5. `API + Dashboard Layer`  
   - CRUD, activation controls, and backtest workflows from `dashboard/`.
6. `LLM Copilot Layer`  
   - Converts natural language to validated algorithm config suggestions.

---

## Canonical Algorithm Config (v1)

Use a single JSON schema (stored in code and DB) to avoid config drift.

Core sections:
- `meta`: `algorithm_id`, `name`, `version`, `created_by`, `schema_version`
- `universe`: symbols, timeframe, market filters
- `signal`: indicators, entry rules, exit rules
- `risk`: max position size, max exposure, stop loss, take profit, max daily loss
- `execution`: order types, slippage model, fee model, timeout, retry policy
- `mode`: `paper` or `live`
- `status`: draft, validated, active, paused, archived

All LLM-generated configs must be transformed into this schema and validated before persistence.

---

## Step-by-Step Plan (LLM-Executable)

## Step 1 - Domain and Schema Foundation

**Objective**
- Introduce algorithm/backtest domain models and database schema.

**Implementation Tasks**
- Add migrations for:
  - `algorithms`
  - `algorithm_versions`
  - `algorithm_runs` (live/paper executions)
  - `algorithm_backtests`
  - `algorithm_events` (activation/deactivation/audit trail)
- Add domain models and repository interfaces.
- Add JSON schema file for algorithm config v1.

**Deliverables**
- Migration SQL files.
- Domain entities/value objects.
- Repository interfaces and PostgreSQL implementations.

**Definition of Done**
- Migrations apply cleanly.
- Algorithm config validation works for valid/invalid payloads.
- Unit tests for repository CRUD + versioning behavior.

**Suggested LLM Prompt Packet**
- "Implement Step 1 only. Create migrations, domain models, and schema validator. Add unit tests. Do not implement API yet."

---

## Step 2 - Market Service (Paper + Live with Shared Contract)

**Objective**
- Build the execution abstraction used by runtime and backtesting.

**Implementation Tasks**
- Define `MarketService` interface:
  - `get_balance`, `get_positions`, `place_order`, `cancel_order`, `get_order_status`
- Implement `PaperMarketService`:
  - deterministic fills (configurable),
  - simulated slippage/fees,
  - persistent virtual account state.
- Implement `LiveMarketService` adapter (Binance):
  - order translation,
  - retry/backoff,
  - idempotency keys,
  - error mapping.
- Add service factory by mode (`paper`, `live`).

**Deliverables**
- Domain service interface and concrete infrastructure services.
- Integration tests for paper mode execution flow.

**Definition of Done**
- Same API contract works in both modes.
- Paper mode deterministic test scenarios pass.
- Live mode supports dry-run and does not execute orders when disabled.

**Suggested LLM Prompt Packet**
- "Implement MarketService contract + paper/live adapters with tests. Keep live adapter behind explicit enable flag."

---

## Step 3 - Algorithm Runtime and Lifecycle Service

**Objective**
- Execute active algorithms from pipeline and manage lifecycle transitions.

**Implementation Tasks**
- Build `AlgorithmLifecycleService`:
  - create draft, validate, publish new version, activate, deactivate, pause/resume.
- Build `AlgorithmRunner`:
  - loads active algorithms,
  - subscribes to market events,
  - evaluates signals,
  - enforces risk rules,
  - routes orders via `MarketService`.
- Ensure one active version per algorithm (or explicit multi-version policy).
- Write `algorithm_events` for all lifecycle changes.

**Deliverables**
- Application services for lifecycle and runtime.
- Pipeline integration point for activation/deactivation.

**Definition of Done**
- Algorithm can be toggled without restart.
- Deactivated algorithm stops creating new orders immediately.
- Runtime errors are isolated per algorithm (no global crash).

**Suggested LLM Prompt Packet**
- "Implement lifecycle + runtime orchestration with event logging and graceful algorithm-level error isolation."

---

## Step 4 - LLM Algorithm Copilot (Create + Modify)

**Objective**
- Enable natural language algorithm creation and modification with strong guardrails.

**Implementation Tasks**
- Add `LLMAlgorithmService` with two operations:
  - `generate_config(description, constraints)`
  - `modify_config(existing_config, change_request)`
- Build prompt templates that reference:
  - available indicators,
  - risk limits,
  - symbol/timeframe constraints,
  - previous phase LLM context (wide-vector feature set).
- Add structured output requirement (JSON schema).
- Add guardrails:
  - prompt injection filter,
  - response schema validation,
  - range checks,
  - forbidden field mutations (for safety-critical fields unless explicit approval).
- Persist proposal as draft version; require user approval before activation.

**Deliverables**
- LLM service, prompt templates, validation/guardrail pipeline.
- Unit tests with mocked LLM responses (valid, invalid, adversarial).

**Definition of Done**
- LLM output never bypasses schema/range validation.
- Invalid output returns actionable validation errors for UI.
- Copilot can modify an existing algorithm version safely.

**Suggested LLM Prompt Packet**
- "Implement LLM create/modify flow with strict JSON schema output and explicit validation pipeline before DB write."

---

## Step 5 - API Endpoints (Algorithms, Market, Backtesting)

**Objective**
- Expose all required capabilities through FastAPI routes.

**Implementation Tasks**
- Algorithm routes:
  - create/list/get/update/version-history
  - activate/deactivate/pause/resume
  - LLM generate/modify suggestion endpoints
- Market routes:
  - balance, positions, orders, mode visibility
- Backtest routes:
  - start backtest
  - poll status
  - fetch summary + detailed report
- Add auth/role checks for dangerous operations (activate live, change risk hard limits).

**Deliverables**
- Route modules + request/response schemas.
- API tests (happy path + failure path).

**Definition of Done**
- All routes documented and validated.
- Activation endpoints enforce permission and safety checks.
- Backtest endpoint supports async job execution.

**Suggested LLM Prompt Packet**
- "Implement API routes with pydantic models, validation, and tests. Include authorization hooks for live operations."

---

## Step 6 - Dashboard UI (Create/Modify + Activation Control)

**Objective**
- Add UX in `dashboard/` for algorithm management from web GUI.

**Implementation Tasks**
- Add algorithm page:
  - list table with status and mode badges,
  - create/edit form wizard (basic + advanced),
  - JSON preview and validation panel,
  - LLM assistant panel ("describe algorithm", "modify algorithm").
- Add activation controls on pipeline/dashboard page:
  - activate/deactivate toggle,
  - confirmation modal for live mode,
  - inline validation and error display.
- Add market panel:
  - paper/live account status, open positions, recent orders.

**Deliverables**
- New/updated HTML/JS in `dashboard/`.
- Integration with new API endpoints.

**Definition of Done**
- User can create algorithm, edit draft, publish, activate/deactivate from GUI.
- UI clearly separates paper and live modes.
- Failed validations show clear remediation hints.

**Suggested LLM Prompt Packet**
- "Implement dashboard algorithm management UI with API integration and robust form validation; include activation controls in pipeline page."

---

## Step 7 - Backtesting Engine with Detailed Statistics

**Objective**
- Build realistic, reproducible backtesting powered by market-service-like execution semantics.

**Implementation Tasks**
- Implement event-driven backtest loop:
  - historical candle/tick replay in chronological order,
  - signal generation -> risk checks -> simulated execution.
- Use paper execution semantics for consistency:
  - commissions, slippage model, order types, fill policy.
- Compute metrics:
  - total return, CAGR, max drawdown, Sharpe/Sortino, win rate,
  - expectancy, profit factor, avg hold time,
  - exposure, turnover, per-symbol contribution.
- Store trade blotter + equity curve + parameter snapshot.
- Add walk-forward option (train window / test window).

**Deliverables**
- Backtest service + persistence + statistics module.
- API contract for summary and detailed report.

**Definition of Done**
- Backtest is deterministic for fixed seed/config/data.
- Report includes both aggregate and trade-level details.
- Runtime algorithm and backtest algorithm share config/runtime logic where possible.

**Suggested LLM Prompt Packet**
- "Implement event-driven backtesting with realistic cost/fill models and rich metrics; persist full results for dashboard consumption."

---

## Step 8 - Observability, Safety, and Operational Controls

**Objective**
- Make the system safe to operate in production.

**Implementation Tasks**
- Add risk guardrails:
  - max daily loss kill switch,
  - max open positions,
  - symbol-level notional caps,
  - stale-data trade block.
- Add observability:
  - algorithm health metrics,
  - order error rates,
  - drift between backtest and paper/live performance.
- Add audit logging:
  - who changed config, who activated live mode, why.
- Add runbooks for incident response and rollback.

**Deliverables**
- Safety middleware/services.
- Operational dashboards/metrics and runbook docs.

**Definition of Done**
- Any guardrail breach blocks new orders and emits alert.
- Operators can disable all algorithms quickly from dashboard/API.
- Audit trail can reconstruct algorithm change history end-to-end.

**Suggested LLM Prompt Packet**
- "Implement operational safety controls, metrics, and audit logs; add tests for guardrail-triggered order blocking."

---

## Step 9 - Testing, Rollout, and Acceptance Gates

**Objective**
- Ensure reliable release from dev to production.

**Implementation Tasks**
- Test layers:
  - unit tests for domain services,
  - integration tests for API + DB + paper market,
  - e2e test for dashboard create->activate->backtest workflow.
- Add staged rollout:
  - phase A: paper only,
  - phase B: limited live with small size,
  - phase C: broader live activation.
- Define go-live gates:
  - passing tests,
  - no critical alerts for N days,
  - paper/live divergence below threshold.

**Deliverables**
- Test suite additions and rollout checklist.

**Definition of Done**
- CI validates core algorithm lifecycle flows.
- Rollback process documented and tested.
- Team sign-off criteria are explicit and measurable.

**Suggested LLM Prompt Packet**
- "Implement missing tests and rollout gates. Focus on reproducibility, safety, and no-regression coverage."

---

## Recommended Execution Order

1. Step 1 (domain/schema)
2. Step 2 (market service)
3. Step 3 (lifecycle/runtime)
4. Step 5 (API)
5. Step 6 (dashboard)
6. Step 7 (backtesting)
7. Step 4 (LLM copilot hardening and UX polish)
8. Step 8 (observability/safety)
9. Step 9 (rollout and acceptance)

Reason: this sequence provides a stable backend foundation first, then UI and advanced intelligence.

---

## Work Package Split for Modern LLM Models

Use one PR per step. Keep each step independently reviewable.

- **Package size target**: 5-12 files changed per PR where possible.
- **Prompt quality**: include clear scope, out-of-scope list, and acceptance tests.
- **Context files**: always pass AGENTS rules + relevant docs + touched files only.
- **Verification command set per PR**:
  - `ruff check src/ tests/`
  - `black src/ tests/`
  - `.venv/bin/python -m pytest tests/unit/ -v` (plus step-specific integration tests)

---

## Open Questions (Need Your Confirmation)

1. Which exact exchange scope for live mode in Phase 3: Binance only or pluggable broker interface from day one?
2. Should activation support multi-algorithm capital allocation rules (portfolio-level limits) now or in Phase 4?
3. For LLM provider: keep current provider from previous phase only, or add provider abstraction now?
4. Backtesting granularity: candle-based first (faster) or candle + optional tick simulation in this phase?
5. Do you want role-based access now (admin/operator/viewer) or simple authenticated mode first?

---

## Acceptance Criteria for Phase 3 Completion

- User can create and modify algorithm via web GUI and LLM assistant.
- User can activate/deactivate algorithm from dashboard without restarting pipeline.
- Market Service supports both paper and live modes with a shared contract.
- Backtest can run for arbitrary time range and returns detailed, persisted statistics.
- Safety controls prevent dangerous live execution and all critical actions are auditable.
