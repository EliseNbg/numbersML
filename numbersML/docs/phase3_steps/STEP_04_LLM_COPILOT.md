# Step 4: LLM Copilot (Create and Modify Algorithm Config)

## Objective

Allow users to generate and modify algorithm configs with natural language, safely.

## Scope

- `LLMAlgorithmService` operations:
  - generate config from description
  - modify existing config from change request
- Prompt templates with domain context:
  - supported indicators
  - risk constraints
  - symbol/timeframe constraints
  - prior LLM feature context (wide vector)
- Structured output (JSON schema) enforcement
- Guardrails:
  - prompt injection checks
  - schema validation
  - numeric range checks
  - restricted field updates unless explicit approval
- Store output as draft version only

## Out of Scope

- Auto-activation of LLM outputs
- Live order placement changes

## Dependencies

- Step 1 schema and versioning
- Step 5 API (if endpoint integration included later)

## Deliverables

- LLM service + prompt templates
- Validation and guardrail pipeline
- Tests with mocked valid/invalid/adversarial outputs

## Acceptance Criteria

- LLM response cannot bypass validation.
- Invalid suggestions return actionable errors.
- Config modifications preserve immutable/safety-critical fields unless approved.

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 4 only: LLM copilot for algorithm config generation and modification.

Tasks:
1) Build LLMAlgorithmService with two methods:
   - generate_config(description, constraints)
   - modify_config(existing_config, change_request)
2) Implement robust prompts with explicit JSON-only output instructions.
3) Enforce JSON schema validation + range/business rules post-processing.
4) Add prompt-injection and unsafe-content checks for user input.
5) Save accepted output as draft algorithm version (never auto-activate).
6) Add tests:
   - valid generation
   - malformed JSON
   - schema mismatch
   - adversarial prompt attempts
   - forbidden field mutation

Constraints:
- Keep provider access abstracted for future model changes.
- Keep secrets/config out of logs.

Output:
- Files changed
- Guardrail chain summary
- Test results and known limitations
```

## Testing Prompt (Best Prompt for LLM)

```text
Security and reliability test for Step 4 LLM copilot.

Tasks:
1) Run all unit tests for LLM generation/modification pipeline.
2) Add red-team style test cases:
   - "ignore previous instructions"
   - schema-smuggling attempts
   - oversize payloads
3) Verify stable error contract returned to UI.
4) Confirm no auto-activation path exists.

Deliver:
- Attack case matrix and outcomes
- Validation failure taxonomy
- Recommended guardrail improvements
```
