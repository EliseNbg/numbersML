# Phase 3 Session Kickoff Template (LLM)

Use this template at the start of each independent implementation session.

```text
You are implementing exactly one Phase 3 packet in this session.

Step file:
<PASTE_STEP_FILE_PATH>

Mandatory context:
- Read and follow `AGENTS.md`
- Read and follow `AGENT.md`
- Read the selected step packet completely
- Read only the minimum code files needed for this step

Execution rules:
1) Respect DDD boundaries (domain <- application <- infrastructure).
2) Do not introduce cross-layer leakage.
3) Keep changes scoped to this step only.
4) If a design decision is non-trivial, create/update an ADR before coding.
5) Prefer small, testable functions and explicit type hints.
6) Add/extend tests together with implementation.
7) Run lint/format/tests before finishing.

Required output format:
1) Scope confirmation (in/out of scope)
2) Implementation plan (short)
3) File changes
4) Test commands run + results
5) ADRs created/updated
6) Risks and follow-up tasks

Quality gates (must pass):
- `ruff check src/ tests/`
- `black src/ tests/`
- Step-specific tests from the packet
- No unresolved TODOs without issue reference

Stop conditions:
- If blocked by missing context or conflicting requirements, stop and ask targeted questions.
```

## Optional Strict Add-on

```text
Additional strict mode:
- Reject any change that bypasses domain invariants in infrastructure.
- Reject any API route containing core business logic.
- Reject any LLM-generated config that fails schema + business validation.
```
