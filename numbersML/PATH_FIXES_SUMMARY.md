# Path Fixes Summary - Relative Paths

**Date**: March 22, 2026
**Status**: ✅ COMPLETE - Using Relative Paths

---

## Key Decision: Relative Paths Only

All documentation now uses **relative paths** instead of absolute paths.

**Why**:
- ✅ Works on any machine (not just `/home/andy/...`)
- ✅ Works in CI/CD (GitHub Actions)
- ✅ Easier to copy/paste
- ✅ No hardcoded usernames

---

## Repository Structure

```
numbers/                    ← Parent folder (repository root)
├── .github/
│   └── workflows/
│       └── ci.yml
├── numbersML/              ← Main project folder
│   ├── src/
│   ├── tests/
│   ├── migrations/
│   ├── scripts/
│   ├── docker/
│   └── *.md (documentation)
├── docs/                   ← Architecture docs
└── specs/                  ← Original specifications
```

---

## Correct Path Usage

### From Repository Root (`numbers/`)

```bash
# Navigate to project
cd numbersML

# Run tests
./scripts/test.sh check
./scripts/test.sh pipeline

# Start infrastructure
./scripts/test.sh start
```

### From Project Folder (`numbersML/`)

```bash
# All commands work from here
./scripts/test.sh check
./scripts/test.sh pipeline
python src/cli/generate_wide_vector.py
```

---

## Files Updated (All Using Relative Paths)

| File | Old (Absolute) | New (Relative) |
|------|----------------|----------------|
| `GITHUB_SETUP.md` | `cd /home/andy/projects/numbers/numbersML` | `cd numbersML` |
| `PHASE1-COMPLETE.md` | `cd /home/andy/projects/numbers/numbersML` | `cd numbersML` |
| `QUICKSTART.md` | `cd /home/andy/projects/numbers/numbersML` | `cd numbersML` |
| `README-SETUP.md` | `cd /home/andy/projects/numbers/numbersML` | `cd numbersML` |
| `README-SETUP.md` | `rootdir: /home/andy/projects/numbers/numbersML` | `rootdir: numbersML` |
| `WIDE_VECTOR_LLM.md` | `cd /home/andy/projects/numbers/numbersML` | `cd numbersML` |

---

## GitHub Actions Paths

The CI/CD workflow (`.github/workflows/ci.yml`) uses relative paths:

```yaml
- name: Install dependencies
  run: |
    pip install -r numbersML/requirements.txt

- name: Run quick check
  run: |
    cd numbersML
    ./scripts/test.sh check
```

---

## Test Script CI Detection

The `scripts/test.sh` automatically detects the environment:

```bash
if [ -n "${GITHUB_ACTIONS:-}" ]; then
    # GitHub Actions - use system Python
    PYTHON="python"
    PYTEST="pytest"
else
    # Local development - use virtual environment
    PYTHON="${PROJECT_DIR}/.venv/bin/python"
    PYTEST="${PROJECT_DIR}/.venv/bin/pytest"
fi
```

---

## Quick Reference

### Local Development (from any location)

```bash
# Clone repository
git clone https://github.com/EliseNbg/numbersML.git
cd numbersML

# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
./scripts/test.sh check
```

### GitHub Actions (automatic)

```yaml
# Workflow runs from repository root
steps:
  - uses: actions/checkout@v5
  
  - name: Run tests
    run: |
      cd numbersML
      ./scripts/test.sh pipeline
```

---

## Verification

All absolute paths have been removed:

```bash
# Check for absolute paths (should return empty)
grep -r "/home/andy" numbersML/*.md | grep -v PATH_FIXES

# Check for relative paths (should show correct usage)
grep -r "cd numbersML" numbersML/*.md
```

---

**Status**: ✅ All paths are now relative
**Works on**: Any machine, any username, any OS
