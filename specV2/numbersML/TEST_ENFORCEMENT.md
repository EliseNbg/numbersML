# Test Enforcement Policy

**Effective Date**: March 22, 2026
**Status**: ✅ **ENFORCED**

---

## Policy

**All code changes MUST pass the test suite before merging.**

This is a **mandatory requirement**, not a suggestion.

---

## Test Suite Structure

```
tests/
├── unit/                    # Unit tests (fast, isolated)
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── cli/
│
├── integration/             # Integration tests (requires DB)
│   ├── test_indicator_pipeline.py  ← CRITICAL
│   └── test_complete_integration.py
│
└── e2e/                     # End-to-end tests (future)
```

---

## Test Execution Order

**MANDATORY SEQUENCE**:

```
1. Quick Check (syntax/imports)
   ↓
2. Unit Tests (must pass first)
   ↓
3. Integration Tests (only if unit tests pass)
   ↓
4. Deploy
```

**Rationale**: Unit tests are fast and catch basic issues. Integration tests verify the complete pipeline.

---

## Running Tests

### Quick Check (Pre-commit)

```bash
# Fast syntax and import check (<5 seconds)
./scripts/test.sh check
```

**When**: Before every commit

**What it checks**:
- Python syntax
- Import statements
- Basic module loading

---

### Unit Tests (Pre-push)

```bash
# Run all unit tests (~30 seconds)
./scripts/test.sh unit
```

**When**: Before every push to remote

**What it checks**:
- Domain logic
- Application services
- Infrastructure components (isolated)
- CLI commands

**Coverage target**: 80%+

---

### Integration Tests (Pre-merge)

```bash
# Run all integration tests (~2 minutes)
./scripts/test.sh integration

# OR run specific pipeline test
./scripts/test.sh pipeline
```

**When**: Before every merge to main branch

**What it checks**:
- Database triggers
- EnrichmentService integration
- WIDE_Vector generation
- Complete data flow

**Pass criteria**: 100% (all tests must pass)

---

### Full Test Suite (CI/CD)

```bash
# Run everything
./scripts/test.sh
```

**When**: Automated in CI/CD pipeline

**Stages**:
1. Quick check
2. Unit tests
3. Integration tests
4. Deploy (only if all pass)

---

## Test Files

### Critical Test: `test_indicator_pipeline.py`

**Purpose**: Verify the complete indicator calculation pipeline

**Tests**:
1. ✅ Indicators configured in EnrichmentService
2. ✅ All indicators can calculate (valid output)
3. ✅ DB INSERT fires NOTIFY trigger
4. ✅ EnrichmentService is running
5. ✅ WIDE_Vector reads indicators from DB
6. ✅ Complete pipeline flow

**Pass criteria**: 6/6 tests must pass

**Run command**:
```bash
./scripts/test.sh pipeline
```

---

## Enforcement Rules

### Rule 1: No Commit Without Quick Check

```bash
# ❌ BAD: Committing without check
git commit -m "Added feature"

# ✅ GOOD: Run check first
./scripts/test.sh check
git commit -m "Added feature"
```

---

### Rule 2: No Push Without Unit Tests

```bash
# ❌ BAD: Pushing without unit tests
git push origin feature-branch

# ✅ GOOD: Run unit tests first
./scripts/test.sh unit
git push origin feature-branch
```

---

### Rule 3: No Merge Without Integration Tests

```bash
# ❌ BAD: Merging without integration tests
git merge main

# ✅ GOOD: Run integration tests first
./scripts/test.sh integration
git merge main
```

---

### Rule 4: CI/CD Must Pass

```yaml
# .github/workflows/ci.yml (example)
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run tests
        run: ./scripts/test.sh
      
      - name: Deploy (only if tests pass)
        if: success()
        run: ./scripts/deploy.sh
```

---

## Test Results

### Location

Test results are saved to:
```
/tmp/integration_test_results.json
```

### Format

```json
{
  "timestamp": "2026-03-22T09:29:26.033Z",
  "passed": true,
  "results": [
    {
      "name": "Test 1: Indicators Configured",
      "passed": true,
      "details": {
        "configured_count": 14,
        "working_indicators": [...]
      }
    },
    ...
  ],
  "summary": {
    "total": 6,
    "passed": 6,
    "failed": 0
  }
}
```

---

## Troubleshooting

### Test Fails: "Infrastructure not ready"

```bash
# Start infrastructure
docker compose -f docker/docker-compose-infra.yml up -d

# Wait for PostgreSQL
sleep 5

# Verify
docker exec crypto-postgres pg_isready -U crypto -d crypto_trading

# Run tests again
./scripts/test.sh
```

---

### Test Fails: "No indicators calculated"

**Cause**: EnrichmentService is not running

**Solution**:
```bash
# Start EnrichmentService
python -m src.application.services.enrichment_service

# Or check if it's running
ps aux | grep enrichment

# Run pipeline test
./scripts/test.sh pipeline
```

---

### Test Fails: "Database connection error"

**Cause**: Database URL incorrect or database not accessible

**Solution**:
```bash
# Check DATABASE_URL
echo $DATABASE_URL

# Should be:
# postgresql://crypto:crypto_secret@localhost:5432/crypto_trading

# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Run tests again
./scripts/test.sh
```

---

## Coverage Requirements

| Test Type | Minimum Coverage |
|-----------|-----------------|
| Unit      | 80%+            |
| Integration | 100% (all tests pass) |
| Pipeline  | 100% (6/6 tests pass) |

---

## Exceptions

**Temporary test skip** (only with approval):

```bash
# Skip specific test (temporary!)
./scripts/test.sh unit -k "not test_specific_feature"

# MUST have follow-up ticket to fix
# Ticket: #1234 - Fix test_specific_feature
```

**Approval required from**:
- Tech lead
- Project manager

---

## Audit Trail

All test runs are logged:

```bash
# View recent test runs
ls -la /tmp/*test_results*.json

# View latest results
cat /tmp/integration_test_results.json | jq '.summary'
```

---

## Compliance Checklist

Before merging to main:

- [ ] Quick check passed (`./scripts/test.sh check`)
- [ ] Unit tests passed (`./scripts/test.sh unit`)
- [ ] Integration tests passed (`./scripts/test.sh integration`)
- [ ] Pipeline test passed (`./scripts/test.sh pipeline`)
- [ ] Test results saved (`/tmp/integration_test_results.json`)
- [ ] No test skips without approval

---

## Questions?

**Test failures**: Check `/tmp/integration_test_results.json`

**Infrastructure issues**: See `docker/docker-compose-infra.yml`

**Test writing**: See `tests/README.md` (create if missing)

---

**Last Updated**: March 22, 2026
**Policy Owner**: Development Team
**Status**: ✅ ENFORCED
