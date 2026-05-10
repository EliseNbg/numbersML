# Step 8: Dashboard GUI for Strategy Backtesting

## Objective

Deliver a serious backtesting workflow in the dashboard so an operator can launch a backtest, watch
it run, inspect the execution trace, and review price-action evidence for every buy/sell decision.

## Scope

- Backtest control UI:
  - select strategy and version
  - choose symbol, time range, and initial balance
  - submit backtest job
  - poll job status and progress
- Backtest result UI:
  - summary metrics
  - trade blotter
  - equity curve
  - close-price chart with buy/sell markers
  - debug/event log panel from strategy run
- Saved backtest history:
  - recent runs list
  - load previous result
  - filter by strategy
- Error and empty states
- Basic responsive behavior for desktop-first operator workflow

## Out of Scope

- Core backtesting math or execution semantics
- New live trading controls
- LLM copilot workflows
- Advanced BI/report export

## Dependencies

- Step 7 backtest engine and persistence complete
- Strategy backtest API endpoints available:
  - `POST /api/strategy-backtests/jobs`
  - `GET /api/strategy-backtests/jobs/{job_id}`
  - `GET /api/strategy-backtests/jobs`
  - `GET /api/strategy-backtests/results`
- Existing dashboard shell and strategy pages from Step 6

## Deliverables

- New or updated dashboard pages under `dashboard/`
- JS modules for:
  - backtest job submission
  - result polling
  - chart rendering
  - debug-log rendering
- Manual verification checklist

## Acceptance Criteria

- User can launch a backtest from the dashboard without using the API manually.
- UI shows live job progress until completion or failure.
- Completed result view displays:
  - headline metrics
  - trade list
  - close-price chart with buy and sell points
  - debug messages from the strategy run
- User can load saved backtests from history.
- API failures and empty-result states are shown clearly.

## Required Data Contract

The GUI should assume the completed job payload includes:

- `metrics`
- `trades`
- `equity_curve`
- `price_series`
- `debug_messages`
- `config_snapshot`
- `parameters`

### Debug Messages

Render debug messages as a time-ordered log table or console-like pane with:
- timestamp
- level
- message

The UI must support at least:
- auto-scroll to newest while job is running
- pause/freeze scrolling for investigation
- filtering by level if easy to add

### Chart Requirements

Render a primary chart with:
- close-price line from `price_series`
- buy markers derived from trade entry points
- sell markers derived from trade exit points

Minimum interaction:
- tooltip with timestamp and price
- visible distinction between buy and sell markers
- pan/zoom only if the existing charting library makes it cheap

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 8 only: dashboard GUI for strategy backtesting and run inspection.

Tasks:
1) Add a backtesting page or panel in the existing dashboard.
2) Support job submission to POST /api/strategy-backtests/jobs with:
   - strategy
   - version
   - symbol
   - time range
   - initial balance
3) Poll GET /api/strategy-backtests/jobs/{job_id} until completion/failure.
4) Render completed results with:
   - summary metric cards
   - trade blotter
   - equity curve
   - close-price chart with buy/sell markers
   - debug messages panel from strategy run
5) Add a saved-results view using GET /api/strategy-backtests/results.
6) Handle loading, empty, running, success, and error states clearly.

Constraints:
- Reuse existing dashboard styles and JS patterns.
- Keep the page operator-focused, dense, and practical.
- Do not add marketing or tutorial UI.
- Prefer a proven chart library already used in the repo; otherwise use a lightweight one.

Output:
- Changed UI files
- Workflow map (user action -> API call -> UI update)
- Verification checklist and results
```

## Testing Prompt (Best Prompt for LLM)

```text
Validate Step 8 backtesting dashboard workflows.

Tasks:
1) Test backtest submission with valid and invalid inputs.
2) Verify running job state updates until completion.
3) Verify completed result rendering includes:
   - debug messages
   - close-price chart
   - buy/sell markers
   - trade blotter
4) Verify saved-results history loads prior runs correctly.
5) Test resilience for:
   - API timeout
   - failed job
   - empty history
   - missing debug messages
   - missing price series

Deliver:
- UI verification checklist with pass/fail
- Data-contract gaps found
- Follow-up backlog for UX and operability
```

## Workflow Notes

### Operator Flow

1. Open strategy details or backtest page.
2. Select strategy version and backtest inputs.
3. Submit job.
4. Observe progress and intermediate state.
5. Review completed output:
   - metrics first
   - chart second
   - trade blotter and debug log for diagnosis
6. Compare with previous saved runs.

### Visual Priority

1. Result status and progress
2. Return, drawdown, Sharpe, win rate
3. Price chart with executions
4. Trade blotter
5. Debug log
