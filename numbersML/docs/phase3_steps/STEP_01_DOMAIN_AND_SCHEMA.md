# Step 1: Domain and Schema Foundation

## Objective

Create the canonical algorithm/backtest data model and persistence layer so every later step builds on stable contracts.

## Why This Step First

- Enables versioned algorithm configs.
- Provides audit and reproducibility baseline.
- Decouples runtime/UI work from database uncertainty.

## Scope

- DB migrations for:
  - `algorithms`
  - `algorithm_versions`
  - `algorithm_runs`
  - `algorithm_backtests`
  - `algorithm_events`
- Canonical algorithm JSON schema (`schema_version: 1`)
- Domain models and repository interfaces
- PostgreSQL repository implementation
- Unit tests for CRUD, versioning, and validation

## Out of Scope

- API routes
- Dashboard changes
- Live exchange calls

## Inputs / Context Needed

- Existing DDD structure in `src/domain`, `src/application`, `src/infrastructure`
- Existing migration pattern in `migrations/`
- Existing tests style in `tests/unit/`

## Deliverables

- Migration SQL files
- Schema file for algorithm config
- Domain entities/value objects
- Repository interface + PG implementation
- Unit tests and fixtures

## Acceptance Criteria

- Migrations apply and rollback cleanly.
- Valid config passes schema validation.
- Invalid config fails with clear error list.
- Algorithm version increments correctly.
- Repository tests pass.

## Implementation Prompt (Best Prompt for LLM)

```text
You are implementing Step 1 only: Domain and Schema Foundation for a Python 3.11 FastAPI/asyncpg project using DDD.

Requirements:
1) Add SQL migrations for:
   - algorithms
   - algorithm_versions
   - algorithm_runs
   - algorithm_backtests
   - algorithm_events
2) Create a canonical algorithm JSON schema v1 with sections:
   meta, universe, signal, risk, execution, mode, status.
3) Implement domain models/value objects and repository interfaces.
4) Implement PostgreSQL repository adapter with asyncpg.
5) Add unit tests for:
   - create/read/update algorithm
   - publish new version and version increment rules
   - config schema validation (valid + invalid payloads)

Constraints:
- Follow project AGENTS.md coding standards.
- Keep strict typing on public methods.
- Use explicit docstrings and descriptive errors.
- Do not implement API or UI here.

Output:
- Provide changed file list.
- Provide migration notes.
- Provide exact test commands run and results summary.
```

## Testing Prompt (Best Prompt for LLM)

```text
Validate Step 1 implementation comprehensively.

Tasks:
1) Run lint/format/type checks relevant to changed files.
2) Run all step-specific unit tests.
3) Add/adjust tests for uncovered edge cases:
   - duplicate algorithm names policy
   - invalid schema_version
   - invalid risk bounds (negative limits, impossible ranges)
   - version race-safety assumptions
4) Confirm migration idempotence assumptions and rollback behavior.

Deliver:
- Test matrix (test name -> purpose -> pass/fail)
- Coverage gaps and residual risks
- Minimal patch for any failing tests
```
