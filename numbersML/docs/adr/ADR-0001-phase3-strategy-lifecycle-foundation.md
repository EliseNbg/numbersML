# ADR-0001: Phase 3 Strategy Lifecycle Foundation

- Status: accepted
- Date: 2026-04-25
- Decision Makers: numbersML maintainers

## Context

Phase 3 introduces user-managed strategy creation, modification, activation/deactivation, and
backtesting. Without a canonical model and versioned persistence, configuration drift and unsafe
runtime changes are likely. The system also needs reproducibility for backtests and auditable
change history for operational safety.

## Decision

Adopt a configuration-driven strategy lifecycle with:

1. Versioned strategy storage (`strategies` + `strategy_versions`) with explicit status/mode.
2. Canonical JSON schema (`strategy_config_v1`) as the single contract for strategy definitions.
3. Separate runtime/backtest records (`strategy_runs`, `strategy_backtests`) and audit events
   (`strategy_events`).
4. Repository abstraction in domain and PostgreSQL adapter in infrastructure.
5. Validation at creation/update boundaries using JSON schema and business rule checks.

## Consequences

### Positive

- Clear and reproducible strategy definitions across runtime and backtesting.
- Better auditability for strategy changes and lifecycle operations.
- Reduced coupling between API/UI and execution internals.
- Safer future LLM integration with a strict schema contract.

### Negative

- Additional schema/repository complexity early in implementation.
- Migration and test maintenance overhead for new tables.

## Alternatives Considered

1. Store strategy config directly in a single table without versioning.
   - Rejected: weak auditability and hard rollback.
2. Keep strategy definitions code-only in Python classes.
   - Rejected: does not support GUI-driven strategy creation/modification.
3. Delay schema and start with API/UI prototypes.
   - Rejected: risks rework and inconsistent contracts.

## Rollback Plan

If this design causes operational issues:

1. Disable new strategy endpoints and lifecycle actions.
2. Keep existing strategy execution path active.
3. Roll back migration `003_phase3_strategy_foundation.sql`.
4. Archive invalid strategy configs and re-enable only validated versions.

## Related

- `docs/CURSOR_PLAN_PHASE3.md`
- `docs/phase3_steps/STEP_01_DOMAIN_AND_SCHEMA.md`
- `AGENT.md`
