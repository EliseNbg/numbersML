# AGENT.md - Architecture and Code Quality Guardrails (ADR + DDD)

This file defines strict implementation rules for AI agents and contributors.
It complements `AGENTS.md` and is optimized for multi-session LLM execution.

---

## 1) Non-Negotiable Principles

- **DDD first**: business rules live in domain/application, not in transport/UI/infrastructure layers.
- **ADR required for non-trivial decisions**: architecture changes must be documented before or alongside implementation.
- **Safety over speed**: trading, risk, and execution changes must prioritize correctness and auditability.
- **Determinism and reproducibility**: backtesting and strategy configuration flows must be reproducible.
- **No silent failure**: all critical errors must be explicit, logged, and test-covered.

---

## 2) DDD Boundary Rules (Strict)

Layer dependency direction:
- `domain` <- `application` <- `infrastructure`
- `dashboard` and API are outer layers and must not contain domain rules.

Rules:
- Domain layer:
  - Pure business concepts, entities, value objects, domain services.
  - No FastAPI/asyncpg/exchange client imports.
- Application layer:
  - Orchestration, use cases, transaction boundaries, policy coordination.
  - Calls domain interfaces and infrastructure adapters through abstractions.
- Infrastructure layer:
  - DB, API adapters, external exchange integration, serialization.
  - Must not encode business invariants that belong to domain/application.

Reject any PR/session that:
- Adds business logic into route handlers or UI scripts.
- Imports infrastructure details into domain models.
- Breaks dependency direction.

---

## 3) ADR (Architecture Decision Record) Rules

When ADR is mandatory:
- New service boundaries or major refactor.
- New execution semantics (fills/slippage/risk behavior).
- Data model/schema strategy changes.
- Security/LLM guardrail approach changes.
- Any decision with trade-offs affecting future steps.

Minimum ADR template:
1. Title
2. Status (`proposed`, `accepted`, `superseded`)
3. Context
4. Decision
5. Consequences (pros/cons)
6. Alternatives considered
7. Rollback plan

Storage convention:
- `docs/adr/ADR-XXXX-<short-title>.md`

Session rule:
- If you made a non-trivial design decision and no ADR exists, create one before finalizing.

---

## 4) Code Quality Rules

- Python 3.11 syntax and typing discipline for all new public functions.
- Keep functions cohesive; avoid monolithic handlers.
- Prefer explicit interfaces over implicit behavior.
- Validate all external input at boundaries (API, LLM output, external adapters).
- Use descriptive domain exceptions; avoid broad silent catches.
- Add concise docstrings for public interfaces and complex logic.
- Keep logging structured and meaningful for operations.

Hard bans:
- Hidden global state for trading decisions.
- Copy-paste logic across services when shared policy belongs in one module.
- "Magic" constants without named config.

---

## 5) Testing Rules (Required)

For each change, include tests at appropriate level:
- Domain logic -> unit tests
- Service orchestration -> unit + integration tests
- API contract behavior -> API tests
- Safety/risk controls -> explicit failure-path tests

Minimum expectation per session:
- New behavior has at least one positive and one negative test.
- Edge cases relevant to money/risk have dedicated tests.

Backtest/runtime rules:
- Avoid lookahead bias.
- Keep deterministic behavior for fixed seed/config/data.
- Test fee/slippage/risk model assumptions explicitly.

---

## 6) Strategy and Market Safety Rules

- Separate **signal generation**, **risk checks**, and **order execution**.
- Never allow live execution without explicit mode guard.
- Activation/deactivation must be auditable and reversible.
- Guardrail breaches must block new orders and emit telemetry.
- Keep paper/live interface identical where practical.

---

## 7) LLM Integration Rules

- LLM output is untrusted input until validated.
- Enforce JSON schema + business rule validation.
- Prompt-injection resistance checks are mandatory for user-provided text.
- Never auto-activate strategy directly from raw LLM output.
- Persist provenance for LLM-generated strategy suggestions.

---

## 8) Session Workflow for Agents

For each task:
1. Confirm in-scope vs out-of-scope.
2. Check whether ADR is needed.
3. Implement smallest complete vertical slice.
4. Add/adjust tests.
5. Run quality gates.
6. Report files changed, tests run, risks, and ADR links.

Required quality gates:
- `ruff check src/ tests/`
- `black src/ tests/`
- Step-specific `pytest` selection

---

## 9) Definition of Done (DoD)

A task is done only if:
- Architecture boundaries remain intact.
- Required ADRs are present for non-trivial decisions.
- Tests pass for changed behavior.
- No critical safety regressions are introduced.
- Documentation is updated when behavior/contracts change.

---

## 10) Review Checklist (Quick)

- [ ] DDD boundaries respected
- [ ] ADR added/updated when needed
- [ ] Domain invariants enforced in correct layer
- [ ] API/UI kept thin
- [ ] Validation and error handling complete
- [ ] Tests include failure paths
- [ ] Lint/format/tests passed
