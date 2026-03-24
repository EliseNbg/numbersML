# Test Repair Plan

**Created**: March 24, 2026  
**Goal**: Fix all failing integration tests  
**Status**: 🔄 IN PROGRESS

---

## Current Status

```
Total: 68 tests
✅ PASSED: 51 (75%)
❌ FAILED: 11 (16%)
⏭️ SKIPPED: 3 (4%)
🔴 ERRORS: 2 (3%)
Duration: 5:43 (needs timeout increase)
```

---

## Failure Analysis

### Category 1: Outdated Test Assertions (4 failures)

| Test | Issue | Fix |
|------|-------|-----|
| `test_validation_pipeline` | Wrong error message format | Update assertion |
| `test_anomaly_detection_pipeline` | `should_flag` vs `is_anomaly` | Fix attribute |
| `test_enrichment_service_initialization` | `_indicator_names` → `indicator_names` | Fix attribute |
| `test_quality_metrics_dashboard` | Missing `anomaly_rate` | Fix attribute |

**Effort**: 1-2 hours  
**Priority**: HIGH

---

### Category 2: Indicator Registry Issues (2 failures)

| Test | Issue | Fix |
|------|-------|-----|
| `test_indicator_registry_discovery` | Returns 0 indicators | Fix path/imports |
| `test_indicator_factory_creation` | Returns None | Fix path/imports |

**Root Cause**: Tests use hardcoded paths that don't work  
**Effort**: 1-2 hours  
**Priority**: HIGH

---

### Category 3: Database/Connection Issues (2 errors)

| Test | Issue | Fix |
|------|-------|-----|
| `test_symbol_repository_operations` | Connection error | Fix fixture |
| `test_asset_sync_database_integration` | Connection error | Fix fixture |

**Root Cause**: Test fixtures not properly configured  
**Effort**: 2-3 hours  
**Priority**: MEDIUM

---

### Category 4: Mock/Integration Issues (3 failures)

| Test | Issue | Fix |
|------|-------|-----|
| `test_message_bus_publish` | Redis mock not called | Fix mock setup |
| `test_data_quality_degradation_scenario` | Quality score wrong | Fix assertion |
| `test_backfill_resume_from_checkpoint` | Timeout (300s) | Increase timeout |

**Effort**: 2-3 hours  
**Priority**: MEDIUM

---

## Action Plan

### Phase 1: Quick Wins (Category 1) - 2 hours

1. Fix attribute names (`_indicator_names` → `indicator_names`)
2. Fix error message assertions
3. Fix `should_flag` vs `is_anomaly`

### Phase 2: Indicator Tests (Category 2) - 2 hours

1. Fix import paths in test files
2. Ensure indicator registry works in test context
3. Verify indicator factory

### Phase 3: Database Fixtures (Category 3) - 3 hours

1. Review database fixture setup
2. Fix connection issues
3. Test fixtures independently

### Phase 4: Mock/Integration (Category 4) - 3 hours

1. Fix Redis mock setup
2. Fix quality metrics assertions
3. Increase timeout for backfill tests

### Phase 5: Verification - 1 hour

1. Run full test suite
2. Verify all tests pass
3. Remove from pytest.ini ignore list
4. Update BROKEN_TESTS.md

---

## Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1 | 2 hours | 2 hours |
| Phase 2 | 2 hours | 4 hours |
| Phase 3 | 3 hours | 7 hours |
| Phase 4 | 3 hours | 10 hours |
| Phase 5 | 1 hour | 11 hours |

**Total Estimated Time**: 10-11 hours

---

## Success Criteria

- [ ] All 68 tests run (no exclusions)
- [ ] 65+ tests pass (95%+)
- [ ] 0 errors
- [ ] Test duration < 10 minutes
- [ ] Removed from pytest.ini ignore list
- [ ] BROKEN_TESTS.md updated/closed

---

## Notes

- **Do NOT exclude tests** - Fix them properly
- **Update tests when code changes** - Tests must match current implementation
- **Remove obsolete tests** - If workflow changed, update or delete test
- **Increase timeouts** - Some tests need more time (backfill)

---

**Start Date**: March 24, 2026  
**Target Completion**: March 25, 2026  
**Owner**: Development Team
