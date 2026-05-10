# ADR-0002: Phase 3 Backtest Runtime Reuse

- Status: accepted
- Date: 2026-05-10
- Decision Makers: numbersML maintainers

## Context

Phase 3 Step 7 requires a deterministic backtesting engine that is credible enough to guide capital
allocation decisions and scientific enough to support repeatable analysis. The codebase already has
strategy lifecycle loading, versioned strategy configs, and a placeholder backtest API, but the
existing backtest route was still returning simulated data and the engine was not reusing the same
strategy loading path as runtime activation.

Without runtime/backtest reuse, the system would drift in exactly the place where teams usually fool
themselves: a strategy that appears strong in research but behaves differently in production.

## Decision

Adopt a backtest architecture with these rules:

1. Backtests load the exact versioned strategy config used by lifecycle/runtime services.
2. Strategy instantiation is shared through a common loader for class-based and config-based
   strategies.
3. The FastAPI backtest route remains thin and delegates execution to an application service.
4. The async job API stores real engine results, not synthetic placeholders.
5. Backtest results must expose artifacts needed by later GUI work:
   - aggregate metrics
   - trade blotter
   - equity curve
   - close-price series
   - debug/event messages

## Consequences

### Positive

- Runtime and research paths now share strategy-loading semantics.
- Backtest jobs can support credible operator workflows and later dashboard visualization.
- The API layer becomes materially easier to test because orchestration is isolated in an
  application service.
- Config-driven strategies have a functional execution path instead of a placeholder no-op.

### Negative

- More coordination is required across application and infrastructure layers.
- Persisted schema still stores a reduced subset of run artifacts, so some rich artifacts are kept
  in the async job result rather than the database record.

## Alternatives Considered

1. Keep the placeholder backtest job simulation and postpone real execution.
   - Rejected: fails Step 7 and produces misleading operational signals.
2. Implement backtest-only strategy loading separate from runtime lifecycle loading.
   - Rejected: creates avoidable drift and raises model-risk.
3. Push orchestration into the API route.
   - Rejected: violates layer boundaries and makes testing brittle.

## Rollback Plan

If the shared loader or service orchestration causes regressions:

1. Disable async backtest job submission from the API.
2. Revert the backtest route to read-only saved-results behavior.
3. Restore the previous lifecycle loader path while keeping persisted strategy versions intact.
4. Re-run lifecycle and backtest regression suites before re-enabling submission.

## Related

- `docs/phase3_steps/STEP_07_BACKTEST_ENGINE.md`
- `docs/phase3_steps/STEP_05_API_LAYER.md`
- `docs/phase3_steps/STEP_03_STRATEGY_RUNTIME_LIFECYCLE.md`
- `docs/adr/ADR-0001-phase3-strategy-lifecycle-foundation.md`
