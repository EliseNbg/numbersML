# Step 7: Backtest Engine with Detailed Statistics

## Objective

Build a realistic, reproducible backtesting system for strategy versions over configurable time ranges.

## Scope

- Event-driven backtest loop:
  - replay historical data in chronological order
  - generate signals
  - apply risk checks
  - execute with paper-like fill semantics
- Cost and execution realism:
  - fees
  - slippage
  - fill policy/order type assumptions
- Detailed analytics:
  - return, CAGR, max drawdown, Sharpe/Sortino
  - win rate, expectancy, profit factor
  - exposure, turnover, holding time
  - trade blotter and equity curve
- Persistence for full run artifacts

## Out of Scope

- UI polishing
- Live execution path changes

## Dependencies

- Steps 1-3 core contracts
- Step 5 backtest API endpoint contracts

## Deliverables

- Backtest service and execution simulator integration
- Metrics/statistics module
- Persistence schema usage and report serializers
- Unit and integration tests

## Acceptance Criteria

- Deterministic outputs for fixed data/config/seed.
- Detailed report includes aggregate and trade-level stats.
- Behavior aligns with paper market execution assumptions.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 7 only: event-driven backtesting engine with detailed statistics.

Tasks:
1) Implement chronological event-driven backtest runner.
2) Reuse strategy config and risk logic from runtime path where possible.
3) Execute orders through consistent paper execution semantics (fees/slippage/fill rules).
4) Compute and persist:
   - summary metrics
   - trade blotter
   - equity curve
   - parameter snapshot
5) Add tests:
   - deterministic replay
   - metric correctness on controlled dataset
   - edge cases (no trades, all losses, flat market)

Constraints:
- Avoid lookahead bias.
- Keep simulation assumptions explicit and configurable.

Output:
- Changed files
- Simulation semantics summary
- Test results + metric validation notes
```

## Testing Prompt (Best Prompt for LLM)

```text
Deep-test Step 7 backtesting implementation.

Tasks:
1) Run deterministic regression tests with fixed fixtures.
2) Add validation tests for:
   - fee/slippage sensitivity
   - order type semantics
   - drawdown and Sharpe calculation correctness
3) Verify no lookahead data access path exists.
4) Produce a realism-gap report (backtest vs expected paper/live differences).

Deliver:
- Metrics validation table
- Determinism evidence
- Residual model-risk notes
```
