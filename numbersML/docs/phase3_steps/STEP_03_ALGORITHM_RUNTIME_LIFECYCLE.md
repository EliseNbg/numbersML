# Step 3: Algorithm Runtime and Lifecycle

## Objective

Make algorithms executable and controllable at runtime (activate/deactivate/pause/resume) without service restart.

## Scope

- `AlgorithmLifecycleService`:
  - create draft
  - validate
  - publish version
  - activate/deactivate/pause/resume
- `AlgorithmRunner`:
  - load active algorithms
  - subscribe/process market events
  - evaluate signals
  - enforce risk rules
  - call `MarketService`
- Write algorithm lifecycle events to audit stream/table

## Out of Scope

- REST endpoints
- GUI

## Dependencies

- Step 1 schema/repositories
- Step 2 market services

## Deliverables

- Lifecycle service
- Runtime orchestration service
- Error isolation and graceful shutdown logic
- Tests for state transitions and execution behavior

## Acceptance Criteria

- Toggle algorithm state while system is running.
- Deactivated algorithm cannot emit new orders.
- Single algorithm failure does not crash global runner.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 3 only: Algorithm runtime and lifecycle management.

Tasks:
1) Create AlgorithmLifecycleService with strict state transition rules.
2) Create AlgorithmRunner that:
   - loads active algorithm versions
   - processes market updates
   - evaluates algorithm signal logic
   - runs risk checks before order placement
   - routes orders through MarketService
3) Persist algorithm lifecycle and runtime events.
4) Ensure algorithm-level failure isolation and robust cancellation handling.
5) Add tests for:
   - transition validity matrix
   - activate/deactivate behavior during active event stream
   - error isolation and recovery

Constraints:
- Keep orchestration in application layer.
- Keep market specifics hidden behind interface.
- No API/UI work in this step.

Output:
- Changed files
- State machine summary
- Test results summary
```

## Testing Prompt (Best Prompt for LLM)

```text
Validate Step 3 lifecycle/runtime implementation.

Tasks:
1) Execute lifecycle transition tests and runner tests.
2) Add race-condition tests:
   - activate + immediate deactivate
   - concurrent update + activate
3) Validate no-order guarantee after deactivation.
4) Validate graceful handling of malformed market events.

Deliver:
- Transition matrix with allowed/disallowed states
- Runtime reliability findings
- Residual risk list
```
