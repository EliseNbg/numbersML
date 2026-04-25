# Step 6: Dashboard GUI (Create/Modify/Activate Strategies)

## Objective

Deliver web GUI workflows to manage strategy lifecycle and control activation from pipeline dashboard.

## Scope

- Strategy management UI:
  - list, detail, create, edit, version history
  - validation feedback
  - LLM-assisted create/modify panel
- Activation controls in dashboard:
  - activate/deactivate toggle
  - mode-specific confirmation (paper vs live)
- Backtest initiation UI and result display hooks
- Market status widgets (balance, positions, orders)

## Out of Scope

- Core backtesting math implementation
- Market service internals

## Dependencies

- Step 5 API endpoints ready
- Existing `dashboard/` pages and JS modules

## Deliverables

- New/updated `dashboard/*.html` and `dashboard/js/*.js`
- API integration with error handling and retries
- UI tests/manual verification checklist

## Acceptance Criteria

- User can create and modify strategy from GUI.
- User can activate/deactivate strategy from dashboard page.
- Validation and API errors are shown clearly.
- Live mode actions require explicit confirmation.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 6 only: dashboard UI for strategy lifecycle and activation controls.

Tasks:
1) Add/extend dashboard pages and JS modules to support:
   - strategy list/detail/create/edit/version history
   - activation/deactivation controls
   - LLM suggestion workflow for create/modify
2) Integrate with API endpoints from Step 5.
3) Add robust client-side validation mirroring server constraints where possible.
4) Add clear state handling:
   - loading
   - success
   - empty
   - error
5) Add confirmation UX for live-mode-sensitive actions.

Constraints:
- Reuse existing dashboard styles and patterns.
- Keep logic modular and testable.

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
   - create/edit strategy
   - activate/deactivate
   - error display for invalid configs
2) Verify live-mode confirmation cannot be bypassed by normal UI flow.
3) Test resilience for API timeouts/retries.
4) Document cross-browser/basic responsiveness risks.

Deliver:
- UI test checklist with pass/fail
- UX edge-case findings
- Follow-up fixes backlog
```
