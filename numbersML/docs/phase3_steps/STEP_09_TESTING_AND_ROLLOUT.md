# Step 9: Testing Algorithm and Rollout Gates

## Objective

Finalize release readiness with complete validation and phased rollout controls.

## Scope

- Test pyramid completion:
  - unit
  - integration
  - e2e (create -> activate -> backtest -> deactivate)
- CI quality gates and no-regression checks
- Rollout phases:
  - paper only
  - limited live pilot (small allocation)
  - broader live enablement
- Rollback plan and operator runbook
- Success criteria and sign-off checklist

## Out of Scope

- New core features beyond stabilization

## Dependencies

- Steps 1-8 substantially complete

## Deliverables

- Test plan and implemented missing tests
- CI gating updates
- Rollout checklist and rollback procedure
- Operational readiness doc updates

## Acceptance Criteria

- Critical user journeys are fully tested.
- CI blocks merge on safety/contract regressions.
- Rollback procedure is tested and documented.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 9 only: testing completion and rollout readiness.

Tasks:
1) Identify test gaps across Steps 1-8 and implement missing tests.
2) Add e2e workflow test:
   create strategy -> validate -> activate (paper) -> run backtest -> deactivate.
3) Define CI gates for:
   - lint/type/test
   - API contract checks
   - critical safety tests
4) Write phased rollout checklist:
   - paper soak period
   - small-capital live pilot
   - expansion criteria
5) Write rollback and incident response runbook.

Constraints:
- Prioritize reproducibility and safety over breadth.
- Keep acceptance criteria measurable.

Output:
- Files changed
- Coverage and gap closure summary
- Rollout gate table with pass/fail criteria
```

## Testing Prompt (Best Prompt for LLM)

```text
Audit Step 9 readiness package as release reviewer.

Tasks:
1) Re-run full relevant test suite and summarize results.
2) Validate CI gates would catch known critical failures.
3) Dry-run rollback procedure in a controlled scenario.
4) Produce go/no-go recommendation with explicit conditions.

Deliver:
- Final readiness report
- Blockers (if any)
- Recommended next actions
```
