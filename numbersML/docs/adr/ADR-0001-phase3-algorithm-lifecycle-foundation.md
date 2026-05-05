# ADR-0001: Phase 3 Algorithm Lifecycle Foundation

- Status: accepted
- Date: 2026-04-25
- Decision Makers: numbersML maintainers

## Context

Phase 3 introduces user-managed algorithm creation, modification, activation/deactivation, and
backtesting. Without a canonical model and versioned persistence, configuration drift and unsafe
runtime changes are likely. The system also needs reproducibility for backtests and auditable
change history for operational safety.

## Decision

Adopt a configuration-driven algorithm lifecycle with:

1. Versioned algorithm storage (`algorithms` + `algorithm_versions`) with explicit status/mode.
2. Canonical JSON schema (`algorithm_config_v1`) as the single contract for algorithm definitions.
3. Separate runtime/backtest records (`algorithm_runs`, `algorithm_backtests`) and audit events
   (`algorithm_events`).
4. Repository abstraction in domain and PostgreSQL adapter in infrastructure.
5. Validation at creation/update boundaries using JSON schema and business rule checks.

## Consequences

### Positive

- Clear and reproducible algorithm definitions across runtime and backtesting.
- Better auditability for algorithm changes and lifecycle operations.
- Reduced coupling between API/UI and execution internals.
- Safer future LLM integration with a strict schema contract.

### Negative

- Additional schema/repository complexity early in implementation.
- Migration and test maintenance overhead for new tables.

## Alternatives Considered

1. Store algorithm config directly in a single table without versioning.
   - Rejected: weak auditability and hard rollback.
2. Keep algorithm definitions code-only in Python classes.
   - Rejected: does not support GUI-driven algorithm creation/modification.
3. Delay schema and start with API/UI prototypes.
   - Rejected: risks rework and inconsistent contracts.

## Rollback Plan

If this design causes operational issues:

1. Disable new algorithm endpoints and lifecycle actions.
2. Keep existing algorithm execution path active.
3. Roll back migration `003_phase3_algorithm_foundation.sql`.
4. Archive invalid algorithm configs and re-enable only validated versions.

## Related

- `docs/CURSOR_PLAN_PHASE3.md`
- `docs/phase3_steps/STEP_01_DOMAIN_AND_SCHEMA.md`
- `AGENT.md`
