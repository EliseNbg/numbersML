# LLM Agent Prompts - Complete Collection

**Ready-to-use prompts for implementing each step with LLM agents.**

---

## How to Use These Prompts

1. **Copy** the entire prompt for your current step
2. **Paste** to your LLM agent (Claude, GPT-4, etc.)
3. **Review** output against acceptance criteria
4. **Test** the implementation
5. **Proceed** to next step

---

## Available Prompts

### Step 001: Project Setup ✅

**File**: [LLM-PROMPT-STEP-001.md](LLM-PROMPT-STEP-001.md)

**Purpose**: Create complete project structure with all configuration files

**Deliverables**:
- Directory structure (src/, tests/, docker/, etc.)
- pyproject.toml with all dependencies
- requirements.txt, requirements-dev.txt
- pytest.ini, mypy.ini
- .pre-commit-config.yaml, .gitignore
- README.md with setup instructions
- Dockerfile, docker-compose-infra.yml
- Initial database migration
- Test structure

**Estimated Time**: 2-3 hours

**Prompt Length**: ~2000 words

**Usage**:
```bash
# 1. Copy prompt from LLM-PROMPT-STEP-001.md
# 2. Paste to LLM agent
# 3. Generate all files
# 4. Test:
cd crypto-trading-system
pip install -r requirements-dev.txt
pytest -v
mypy src
pre-commit install
```

---

## Prompt Template for Future Steps

Use this template to create prompts for remaining steps:

```markdown
# LLM Agent Prompt - Step [NNN]: [Title]

**Copy and paste this entire prompt to your LLM agent.**

---

## PROMPT START

```
You are a Senior Python Developer implementing [COMPONENT].

ROLE:
  Senior Python Developer with expertise in:
  - Domain-Driven Design (DDD)
  - Hexagonal Architecture (Ports & Adapters)
  - [Specific expertise for this step]

PROJECT CONTEXT:
  [Brief context about system and phase]
  
  Architecture Principles:
    - DDD with strict layer separation
    - Hexagonal architecture
    - [Other relevant principles]
  
  Technology Stack:
    - Python 3.11+
    - [Relevant technologies for this step]

CURRENT TASK:
  Step [NNN]: [Title]
  
  Goal: [Clear goal statement]
  
  Estimated Time: [X hours]
  
  Deliverables:
    1. [Deliverable 1]
    2. [Deliverable 2]
    ...

CODING STANDARDS (MANDATORY):
  
  1. KISS Principle:
     [Requirements]
  
  2. Type Hints (MANDATORY):
     [Requirements]
  
  3. Documentation (COMPREHENSIVE):
     [Requirements]
  
  4. Error Handling (EXPLICIT):
     [Requirements]
  
  5. Layer Separation (STRICT):
     [Requirements]
  
  6. Testing (ARRANGE-ACT-ASSERT):
     [Requirements]

IMPLEMENTATION TASKS:

Task 1: [Task Name]
  Requirements:
    - [Requirement 1]
    - [Requirement 2]
    ...

Task 2: [Task Name]
  ...

[Add all tasks...]

ACCEPTANCE CRITERIA:

All files created:
  [ ] [Criterion 1]
  [ ] [Criterion 2]
  ...

Code quality:
  [ ] [Criterion 3]
  [ ] [Criterion 4]
  ...

Tests:
  [ ] [Criterion 5]
  [ ] [Criterion 6]
  ...

OUTPUT FORMAT:

For each file, provide:
  1. File path (relative to project root)
  2. Complete file content
  3. Brief explanation of key decisions

DOCUMENTATION REFERENCES:

For architecture context, refer to:
  - docs/00-START-HERE.md
  - docs/ARCHITECTURE-SUMMARY.md
  - docs/CODING-STANDARDS.md
  - docs/implementation/[step]-[name].md

IMPORTANT NOTES:

1. [Important note 1]
2. [Important note 2]
...

QUALITY OVER QUANTITY:
  Better to have less, working, well-documented code than more, buggy code.
```

## PROMPT END
```

---

## Prompts to Create (Priority Order)

### High Priority (Week 2)

| Step | Document to Create | Prompt Status |
|------|-------------------|---------------|
| 004 | Data Collection Service | ⏳ NEEDS CREATION |
| 005 | Repository Pattern | ⏳ NEEDS CREATION |
| 018 | Ticker Collector | ⏳ NEEDS CREATION |

### Medium Priority (Week 3-5)

| Step | Document to Create | Prompt Status |
|------|-------------------|---------------|
| 016 | Asset Sync Service | ✅ Already detailed |
| 017 | Data Quality Framework | ✅ Already detailed |
| 019 | Gap Detection | ⏳ NEEDS CREATION |

### Low Priority (Week 6-9)

| Step | Document to Create | Prompt Status |
|------|-------------------|---------------|
| 020-024 | Enrichment & Operations | ⏳ NEEDS CREATION |

---

## Using Step 001 Prompt

### Before Running

**Prerequisites**:
- Python 3.11+ installed
- Docker installed
- Git installed
- LLM agent access (Claude, GPT-4, etc.)

**Setup**:
```bash
# Create project directory
mkdir crypto-trading-system
cd crypto-trading-system

# Initialize git
git init
```

### Running the Prompt

**1. Copy the prompt**:
```bash
# Copy from file
cat docs/LLM-PROMPT-STEP-001.md | xclip -selection clipboard
# Or manually copy in your editor
```

**2. Paste to LLM agent**:
```
[Paste entire prompt from LLM-PROMPT-STEP-001.md]

Additional Context:
- Project directory: /home/andy/projects/numbers/specV2
- Reference docs: /home/andy/projects/numbers/specV2/docs/
- Please implement Step 001: Project Setup
```

**3. Wait for output** (may take several minutes)

**4. Save output files**:
```bash
# LLM will output file paths and contents
# Create each file as specified
mkdir -p src/domain/models
mkdir -p tests/unit/domain
# ... etc.

# Copy file contents from LLM output
# Example:
cat > pyproject.toml << 'EOF'
[LLM output here]
EOF
```

### After Running

**Verify implementation**:
```bash
# 1. Install dependencies
pip install -r requirements-dev.txt

# 2. Install pre-commit hooks
pre-commit install

# 3. Run tests
pytest -v

# 4. Run type checking
mypy src

# 5. Verify Docker
docker-compose -f docker-compose-infra.yml config
```

**Expected Results**:
- ✅ All dependencies installed
- ✅ Pre-commit hooks installed
- ✅ Tests pass (initial test file)
- ✅ Type checking passes
- ✅ Docker Compose config valid

**If Issues**:
- Review error messages
- Ask LLM to fix specific issues
- Re-test after fixes

---

## Tips for Best Results

### 1. Provide Complete Context

```
✅ GOOD: "We are building Phase 1 of a crypto trading system. 
         Architecture is DDD with strict layer separation.
         Reference docs are in docs/ directory."

❌ BAD: "Build a trading system."
```

### 2. Be Specific About Standards

```
✅ GOOD: "All functions must have type hints. 
         All public methods must have docstrings.
         Test coverage must be 90%+ for domain layer."

❌ BAD: "Write good code."
```

### 3. Specify Output Format

```
✅ GOOD: "For each file, provide:
         1. File path
         2. Complete content
         3. Brief explanation"

❌ BAD: "Show me the code."
```

### 4. Review Against Criteria

```
✅ GOOD: Check each acceptance criterion:
         [ ] All files created?
         [ ] Type hints present?
         [ ] Docstrings present?
         [ ] Tests pass?

❌ BAD: Accept first output without review
```

### 5. Iterate if Needed

```
✅ GOOD: "The pyproject.toml is missing black configuration.
         Please add it with line-length=100."

❌ BAD: Accept incomplete output
```

---

## Common Issues & Solutions

### Issue: LLM Skips Documentation

**Solution**: Add explicit requirement:
```
IMPORTANT: Every class and method MUST have comprehensive docstrings.
Include Args, Returns, Raises sections for all methods.
```

### Issue: Type Hints Missing

**Solution**: Add explicit requirement:
```
MANDATORY: All function parameters must have type hints.
All return values must have type hints.
Use Optional[T], List[T], Dict[K, V] appropriately.
```

### Issue: Functions Too Long

**Solution**: Add explicit requirement:
```
Functions must be < 50 lines.
Each function must do ONE thing only.
Split long functions into smaller helper functions.
```

### Issue: Layer Separation Violated

**Solution**: Add explicit requirement:
```
STRICT LAYER SEPARATION:
- Domain layer: NO imports from application or infrastructure
- Application layer: Only imports from domain
- Infrastructure layer: Implements domain interfaces
```

### Issue: Tests Missing

**Solution**: Add explicit requirement:
```
TESTING REQUIRED:
- Create test file for each module
- Follow Arrange-Act-Assert pattern
- Coverage: 90%+ domain, 80%+ application
- Clear, descriptive test names
```

---

## Next Prompts to Create

### Priority: HIGH (Create This Week)

**Step 004 Prompt**:
```
Topic: Data Collection Service (Binance WebSocket)
Key Files:
  - src/infrastructure/exchanges/data_collector.py
  - src/infrastructure/exchanges/binance_client.py
  - tests/unit/infrastructure/exchanges/test_data_collector.py
  - tests/integration/exchanges/test_data_collector.py
Focus:
  - WebSocket connection management
  - Trade message parsing
  - Batch inserts to PostgreSQL
  - Error handling and reconnection
```

**Step 005 Prompt**:
```
Topic: Repository Pattern
Key Files:
  - src/domain/repositories/base.py
  - src/domain/repositories/symbol_repository.py
  - src/domain/repositories/trade_repository.py
  - src/infrastructure/repositories/postgresql/*.py
Focus:
  - Repository interfaces (ports)
  - PostgreSQL implementations (adapters)
  - Dependency injection
  - Test mocks/stubs
```

**Step 018 Prompt**:
```
Topic: Ticker Collector Service
Key Files:
  - src/infrastructure/exchanges/ticker_collector.py
  - src/infrastructure/exchanges/ticker_client.py
  - tests/unit/infrastructure/exchanges/test_ticker_collector.py
Focus:
  - 24hr ticker WebSocket stream
  - Low-storage data collection
  - Regional filtering (EU compliance)
  - Integration with data collector
```

---

## Summary

**Available Now**:
- ✅ Step 001 Prompt (Project Setup) - [LLM-PROMPT-STEP-001.md](LLM-PROMPT-STEP-001.md)

**To Create This Week**:
- ⏳ Step 004 Prompt (Data Collection)
- ⏳ Step 005 Prompt (Repository Pattern)
- ⏳ Step 018 Prompt (Ticker Collector)

**Usage**:
1. Copy prompt from file
2. Paste to LLM agent
3. Generate implementation
4. Test against acceptance criteria
5. Proceed to next step

---

**Start with Step 001 prompt today!** 🚀
