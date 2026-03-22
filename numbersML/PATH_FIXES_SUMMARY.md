# Path and Folder Name Fixes - Summary

**Date**: March 22, 2026
**Status**: ✅ COMPLETE

---

## Issues Fixed

### 1. Incorrect Repository Path (`specV2` → `numbers`)

**Problem**: Documentation referenced old `specV2` folder name instead of `numbers`.

**Files Fixed**:

| File | Old Path | New Path |
|------|----------|----------|
| `GITHUB_SETUP.md` | `/home/andy/projects/numbers/specV2/numbersML` | `/home/andy/projects/numbers/numbersML` |
| `PHASE1-COMPLETE.md` | `/home/andy/projects/numbers/specV2/numbersML` | `/home/andy/projects/numbers/numbersML` |
| `QUICKSTART.md` | `/home/andy/projects/numbers/specV2/numbersML` | `/home/andy/projects/numbers/numbersML` |
| `README-SETUP.md` | `/home/andy/projects/numbers/specV2/numbersML` | `/home/andy/projects/numbers/numbersML` |
| `README-SETUP.md` | `rootdir: /home/andy/projects/numbers/specV2/numbersML` | `rootdir: /home/andy/projects/numbers/numbersML` |
| `WIDE_VECTOR_LLM.md` | `/home/andy/projects/numbers/specV2/numbersML` | `/home/andy/projects/numbers/numbersML` |

---

## Repository Structure

**Correct structure**:
```
/home/andy/projects/numbers/           ← Repository root
├── .github/
│   └── workflows/
│       └── ci.yml
├── numbersML/                          ← Main project folder
│   ├── src/
│   ├── tests/
│   ├── migrations/
│   ├── scripts/
│   └── *.md (documentation)
├── docs/                               ← Architecture docs
└── specs/                              ← Original specifications
```

**Important**: The repository name is `numbersML` on GitHub, but the parent folder is `numbers`.

---

## CI/CD Path Fixes

### GitHub Actions Workflow (`.github/workflows/ci.yml`)

**Fixed paths**:
- `requirements.txt` → `numbersML/requirements.txt`
- Added `cd numbersML` before running commands

**Why**: The workflow runs from the repository root, not from inside `numbersML/`.

---

## Test Script Fix (`numbersML/scripts/test.sh`)

**Added CI detection**:
```bash
if [ -n "${GITHUB_ACTIONS:-}" ]; then
    PYTHON="python"
    PYTEST="pytest"
else
    PYTHON="${PROJECT_DIR}/.venv/bin/python"
    PYTEST="${PROJECT_DIR}/.venv/bin/pytest"
fi
```

**Why**: GitHub Actions doesn't have a virtual environment at `.venv/bin/python`.

---

## Verification

All path references have been verified:

```bash
# Check for old specV2 references (should return empty)
grep -r "specV2" numbersML/*.md

# Check for correct paths
grep -r "numbers/numbersML" numbersML/*.md
```

---

## Files Changed

| File | Changes |
|------|---------|
| `.github/workflows/ci.yml` | Fixed requirements path, added cd numbersML |
| `numbersML/scripts/test.sh` | Added CI detection for Python paths |
| `numbersML/GITHUB_SETUP.md` | Fixed repository path |
| `numbersML/PHASE1-COMPLETE.md` | Fixed repository path |
| `numbersML/QUICKSTART.md` | Fixed repository path |
| `numbersML/README-SETUP.md` | Fixed repository path (2 places) |
| `numbersML/WIDE_VECTOR_LLM.md` | Fixed repository path |
| `numbersML/GITHUB_ACTIONS_FIX.md` | New file - CI/CD documentation |

---

## Commit History

1. **0d7839e** - Fix GitHub Actions CI pipeline
   - Updated actions to Node.js 24 compatible versions
   - Fixed requirements.txt path
   - Fixed test.sh CI detection

2. **0c112bf** - Fix incorrect path references in documentation
   - Replaced all specV2 references with numbers
   - Fixed 6 documentation files

---

## Correct Usage Examples

### Local Development
```bash
cd /home/andy/projects/numbers/numbersML
./scripts/test.sh start
./scripts/test.sh pipeline
```

### GitHub Actions
```yaml
- name: Install dependencies
  run: |
    pip install -r numbersML/requirements.txt

- name: Run tests
  run: |
    cd numbersML
    ./scripts/test.sh pipeline
```

---

**Status**: ✅ All paths corrected and verified
**Next**: No further path fixes needed
