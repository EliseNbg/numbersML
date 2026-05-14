# Step 8: Observability and Safety Controls

## Objective

Add operational controls and telemetry required for safe paper/live strategy operation.

## Scope

- Hard risk controls:
  - max daily loss kill switch
  - max open positions
  - notional caps per symbol
  - stale data block
- Observability:
  - strategy health metrics
  - order success/failure ratios
  - latency/error counters
  - backtest vs paper/live drift indicators
- Audit trail:
  - config changes
  - activations/deactivations
  - risk guardrail trigger events
- Operator controls:
  - emergency global strategy stop

## Out of Scope

- New strategy logic
- Frontend redesign

## Dependencies

- Steps 2-3 runtime and market services
- Step 5 API hooks

## Deliverables

- Guardrail enforcement middleware/services
- Metrics and structured logging additions
- Audit event persistence updates
- Tests for safety-trigger behavior

## Acceptance Criteria

- Guardrail breach blocks new orders.
- Critical events are logged and queryable.
- Emergency stop works quickly and predictably.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 8 only: observability and safety controls for strategy execution.

Tasks:
1) Add runtime guardrails:
   - daily loss kill switch
   - max exposure/position limits
   - stale feed block
2) Add telemetry/metrics:
   - per-strategy health
   - order errors and latency
   - guardrail trigger counters
3) Add audit logging for all critical actions/events.
4) Implement emergency global stop path.
5) Add tests:
   - guardrail breach blocks order placement
   - emergency stop halts new orders
   - audit event persistence correctness

Constraints:
- Keep rules configurable and explicit.
- No silent failure of guardrails.

Output:
- Changed files
- Guardrail configuration summary
- Test and risk findings summary
```

## Testing Prompt (Best Prompt for LLM)

```text
Test Step 8 safety and observability behavior.

Tasks:
1) Run safety-path tests for each guardrail trigger.
2) Validate metrics emission for normal and failure flows.
3) Validate audit completeness for config/lifecycle/risk events.
4) Simulate incident scenario and verify operator stop + recovery behavior.

Deliver:
- Safety scenario matrix
- Metrics/audit validation report
- Remaining operational risks
```
