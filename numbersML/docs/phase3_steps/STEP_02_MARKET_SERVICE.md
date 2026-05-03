# Step 2: Market Service (Paper + Live via Shared Contract)

## Objective

Implement a single market execution abstraction with two modes: paper/test and live/prod.

## Scope

- Define domain `MarketService` contract:
  - `get_balance`
  - `get_positions`
  - `place_order`
  - `cancel_order`
  - `get_order_status`
- Implement `PaperMarketService`:
  - deterministic fills
  - configurable slippage and fees
  - persistent virtual account state
- Implement `LiveMarketService` adapter:
  - exchange request translation
  - retries/backoff
  - idempotency key strategy
  - robust error mapping
- Implement mode-based factory
- Integration tests for paper flow

## Out of Scope

- Algorithm runner orchestration
- Dashboard UI

## Dependencies

- Step 1 repositories and domain objects available.

## Deliverables

- Domain interfaces + models (orders, fills, positions)
- Infrastructure adapters (paper/live)
- Factory wiring
- Tests for deterministic paper execution and failure handling

## Acceptance Criteria

- Same service contract in both modes.
- Paper mode produces repeatable results for fixed seed/config.
- Live mode is guarded by explicit enable flag.
- Order retries are idempotent.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 2 only: Market Service abstraction with paper and live adapters.

Project constraints:
- Python 3.11, asyncpg, DDD layering.
- Preserve clear boundary: strategy signal logic must not know exchange specifics.

Tasks:
1) Define MarketService interface and domain order/fill/position models.
2) Build PaperMarketService:
   - deterministic fills
   - configurable fee/slippage model
   - persisted account balances and positions
3) Build LiveMarketService adapter:
   - request translation to exchange client
   - retries with exponential backoff
   - idempotent submission protection
   - normalize errors into domain exceptions
4) Build market service factory by mode.
5) Write tests:
   - happy-path order lifecycle
   - partial/failed fill handling assumptions
   - retry/idempotency behavior
   - mode switch safety

Out of scope: API routes, dashboard, strategy runner.

Output:
- Files changed
- Interface contract summary
- Commands/tests run with concise results
```

## Testing Prompt (Best Prompt for LLM)

```text
Test and harden Step 2 market services.

Validation tasks:
1) Run unit + integration tests for paper/live adapters.
2) Add stress-style tests for:
   - rapid order bursts
   - cancel/replace race conditions
   - duplicate client order IDs
3) Verify risk/safety checks:
   - no live calls when mode != live
   - insufficient balance/position rejection behavior
4) Produce a gap report comparing paper assumptions vs live realities.

Deliver:
- Test report table with pass/fail
- Known limitations
- Follow-up hardening backlog items
```
