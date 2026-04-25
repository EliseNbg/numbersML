# Step 5: API Layer (Strategies, Market, Backtesting)

## Objective

Expose strategy lifecycle, market operations, and backtesting through consistent FastAPI routes.

## Scope

- Strategy endpoints:
  - create/list/get/update
  - version history
  - activate/deactivate/pause/resume
  - LLM generate/modify
- Market endpoints:
  - balances, positions, order create/cancel/status
- Backtest endpoints:
  - start job
  - status
  - summary + detailed report
- Request/response models and validation
- Authorization hooks for sensitive operations

## Out of Scope

- Dashboard UI
- Deep strategy runtime refactors

## Dependencies

- Steps 1-3 core services
- Step 4 if including LLM endpoints now

## Deliverables

- Route modules and schema models
- Router registration
- API tests for happy/failure paths

## Acceptance Criteria

- Endpoint validation and error responses are consistent.
- Sensitive actions enforce auth/policy checks.
- Backtest endpoint supports async job handling.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 5 only: FastAPI routes for strategies, market, and backtesting.

Tasks:
1) Create/extend route modules for strategy, market, backtest domains.
2) Add request/response pydantic models with strong validation.
3) Wire routes into API app and ensure dependency injection for services.
4) Add authorization checks for:
   - live mode operations
   - activation/deactivation
   - risk-limit changes
5) Add tests for:
   - successful flows
   - invalid payloads
   - unauthorized operations
   - service failure propagation and error mapping

Constraints:
- Keep route handlers thin; business logic stays in services.
- Preserve existing API style conventions.

Output:
- Changed files
- Endpoint catalog
- Test command/results summary
```

## Testing Prompt (Best Prompt for LLM)

```text
Test Step 5 API layer end-to-end at handler/service boundary.

Tasks:
1) Run API-focused tests with mocked dependencies where needed.
2) Add contract tests for response shapes and error payload format.
3) Validate authorization path for dangerous endpoints.
4) Validate idempotency expectations for activation/order endpoints.

Deliver:
- API contract test report
- Security/authorization findings
- Backward compatibility notes
```
