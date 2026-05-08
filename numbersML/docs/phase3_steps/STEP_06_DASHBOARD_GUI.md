# Step 6: Dashboard GUI (Create/Modify/Activate Strategies)

## Objective

Deliver web GUI workflows to manage class-based and config-based strategy lifecycles from the pipeline dashboard.

## Scope

- Strategy management UI:
  - List, detail, create, edit, version history
  - Support for class-based (user-written) and config-based strategies
  - Class selection dropdown for class-based strategies
  - Validation feedback
- Activation controls in dashboard:
  - Activate/deactivate toggle
  - Mode-specific confirmation (paper vs live)
- User strategy class discovery:
  - List available user-written strategy classes from `src/strategies/user/`
  - Display class metadata (docstring, available indicators)
- Backtest initiation UI and result display hooks
- Market status widgets (balance, positions, orders)

## Out of Scope

- LLM-assisted strategy generation/modification
- Core backtesting math implementation
- Market service internals

## Dependencies

- Step 5 API endpoints ready (including `/api/strategies/user-classes`)
- Existing `dashboard/` pages and JS modules
- Updated `StrategyLifecycleService` with class-based loading support

## Deliverables

- New/updated `dashboard/*.html` and `dashboard/js/*.js`
- API integration with error handling and retries
- UI tests/manual verification checklist

## Acceptance Criteria

- User can create strategy from user-written Python class
- User can select strategy class from dropdown populated via API
- User can activate/deactivate strategy from dashboard page
- Validation and API errors are shown clearly
- Live mode actions require explicit confirmation
- Class-based strategies load correctly with config mapped to instance

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 6 only: dashboard UI for strategy lifecycle and activation controls.

Tasks:
1) Add/extend dashboard pages and JS modules to support:
   - Strategy list/detail/create/edit/version history
   - Class-based strategy creation with class selection dropdown
   - Fetch available classes from GET /api/strategies/user-classes
   - Activation/deactivation controls
2) Integrate with API endpoints from Step 5.
3) Add robust client-side validation mirroring server constraints where possible.
4) Add clear state handling:
   - Loading
   - Success
   - Empty
   - Error
5) Add confirmation UX for live-mode-sensitive actions.
6) Remove LLM-related UI elements (copilot panel, suggestion workflow).

Constraints:
- Reuse existing dashboard styles and patterns.
- Keep logic modular and testable.
- Support both class-based and config-based strategies.

Output:
- Changed UI files
- Workflow map (user action -> API call -> UI state)
- Verification checklist and results
```

## Testing Prompt (Best Prompt for LLM)

```text
Validate Step 6 dashboard workflows.

Tasks:
1) Perform UI integration checks for:
   - Create/edit strategy (both class-based and config-based)
   - Activate/deactivate
   - Error display for invalid configs
   - Class selection dropdown population
2) Verify live-mode confirmation cannot be bypassed by normal UI flow.
3) Test resilience for API timeouts/retries.
4) Test class-based strategy creation flow:
   - Select class from dropdown
   - Configure parameters
   - Activate and verify signal generation
5) Document cross-browser/basic responsiveness risks.

Deliver:
- UI test checklist with pass/fail
- UX edge-case findings
- Follow-up fixes backlog
```

## GUI Workflow for Class-Based Strategies

### Create Strategy Flow
1. User navigates to Strategies page
2. Clicks "Create Strategy"
3. Selects strategy type: "Class-based" or "Config-based"
4. If "Class-based":
   - Dropdown populated from `GET /api/strategies/user-classes`
   - User selects class (e.g., `src.strategies.user.example_rsi_strategy.ExampleRSIStrategy`)
   - Config form shows class docstring and default config fields
5. If "Config-based":
   - Legacy config JSON editor (existing behavior)
6. User fills in name, description, mode (paper/live)
7. Clicks "Create"
8. Strategy created via `POST /api/strategies/` with `strategy_type: "class"` and `class_path`

### Activate Strategy Flow
1. User clicks "Activate" on strategy card/row
2. If mode is "live", show confirmation dialog
3. Call `POST /api/strategies/{id}/activate`
4. Strategy loads user-written class and starts processing ticks
5. Runtime state changes to RUNNING
