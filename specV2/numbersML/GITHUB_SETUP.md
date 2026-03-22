# GitHub Setup Guide

**Purpose**: Configure GitHub repository with CI/CD enforcement for test suite

---

## Quick Start

```bash
# 1. Initialize git repository (if not already done)
cd /home/andy/projects/numbers/specV2/numbersML
git init

# 2. Add all files
git add .

# 3. Initial commit
git commit -m "Initial commit: Crypto Trading System with test enforcement"

# 4. Create GitHub repository (via web or CLI)
# Go to: https://github.com/new
# Repository name: numbersML
# Visibility: Private (recommended) or Public

# 5. Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/numbersML.git
git branch -M main
git push -u origin main
```

---

## GitHub Actions Setup

### What's Configured

**File**: `.github/workflows/ci.yml`

**Jobs**:
1. ✅ **Quick Check** - Syntax and imports (fast feedback)
2. ✅ **Unit Tests** - All unit tests
3. ✅ **Integration Tests** - Requires PostgreSQL
4. ✅ **Pipeline Test** ⭐ - Critical path (6/6 tests must pass)
5. ✅ **Code Quality** - Linting and type checking (optional)
6. ✅ **Deploy** - Only on main branch after all tests pass

### Workflow Execution

```
Push/PR → Quick Check → Unit Tests → Integration Tests → Pipeline Test → Deploy
          (5s)          (30s)        (2min)              (5s)           (optional)
```

**Total time**: ~3-4 minutes for full pipeline

---

## Branch Protection Rules

**CRITICAL**: Configure branch protection to enforce tests!

### Steps

1. Go to: `https://github.com/YOUR_USERNAME/numbersML/settings/branches`

2. Click "Add branch protection rule"

3. Configure:

```
Branch name pattern: main

✅ Require a pull request before merging
   ✅ Require approvals (1)

✅ Require status checks to pass before merging
   ✅ Search for status checks:
      ✅ Quick Check
      ✅ Unit Tests
      ✅ Integration Tests
      ✅ Pipeline Test ⭐

✅ Require branches to be up to date before merging

✅ Include administrators (optional but recommended)
```

4. Click "Create"

---

## Repository Settings

### 1. Enable Merge Commit Squash

```
Settings → General → Pull Requests

✅ Allow squash merging
✅ Allow rebase merging
❌ Disable merge commits (keeps history clean)
```

### 2. Configure Default Branch

```
Settings → Branches

Default branch: main
```

### 3. Add Topics (Optional)

```
Repository home page → Topics

Add: crypto-trading, python, postgresql, indicators, technical-analysis
```

---

## Environment Variables

### For GitHub Actions

**File**: `.github/workflows/ci.yml` (already configured)

```yaml
DATABASE_URL: postgresql://crypto:crypto_secret_change_me@localhost:5432/crypto_trading
```

### For Local Development

**File**: `.env` (add to `.gitignore`!)

```bash
# Database
DATABASE_URL=postgresql://crypto:crypto_secret_change_me@localhost:5432/crypto_trading

# Logging
LOG_LEVEL=INFO

# Test configuration
TEST_TIMEOUT=300
```

---

## Required Files

### `.gitignore` (Create if missing)

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
ENV/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Test artifacts
.pytest_cache/
.coverage
htmlcov/
.tox/

# Local configuration
.env
.env.local
*.local

# Logs
*.log
logs/

# Temporary files
/tmp/
*.tmp

# OS
.DS_Store
Thumbs.db
```

### `requirements.txt` (Ensure it exists)

```txt
# Core dependencies
asyncpg>=0.29.0
numpy>=1.24.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-timeout>=2.2.0

# Optional: Code quality
flake8>=6.1.0
mypy>=1.5.0
black>=23.9.0
```

---

## First Push Checklist

Before pushing to GitHub:

- [ ] All tests pass locally
  ```bash
  ./scripts/test.sh
  ```

- [ ] `.gitignore` is configured

- [ ] `.github/workflows/ci.yml` exists

- [ ] `requirements.txt` is complete

- [ ] No sensitive data in code (passwords, API keys)

- [ ] README.md exists

---

## After First Push

### 1. Verify GitHub Actions Running

Go to: `https://github.com/YOUR_USERNAME/numbersML/actions`

You should see:
- ✅ Quick Check
- ✅ Unit Tests
- ✅ Integration Tests
- ✅ Pipeline Test

### 2. Check Test Results

Click on the workflow run → Click on job → View logs

Expected output:
```
✅ ALL TESTS PASSED
Pipeline is ready for deployment.
```

### 3. Configure Branch Protection

Follow the steps in "Branch Protection Rules" section above.

---

## Pull Request Workflow

### Developer Workflow

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes
# ... edit files ...

# 3. Run tests locally
./scripts/test.sh check
./scripts/test.sh unit

# 4. Commit
git add .
git commit -m "Add my feature"

# 5. Push
git push origin feature/my-feature

# 6. Create PR on GitHub
# Go to: https://github.com/YOUR_USERNAME/numbersML/pulls
# Click "New pull request"
```

### PR Requirements

Before merging, GitHub will check:
- ✅ Quick Check passed
- ✅ Unit Tests passed
- ✅ Integration Tests passed
- ✅ Pipeline Test passed
- ✅ At least 1 approval (if configured)

---

## Troubleshooting

### GitHub Actions Fails: "PostgreSQL not ready"

**Solution**: Increase health check retries in `ci.yml`:

```yaml
services:
  postgres:
    options: >-
      --health-cmd pg_isready
      --health-interval 5s
      --health-timeout 5s
      --health-retries 10  # Increase from 5
```

---

### GitHub Actions Fails: "Database not found"

**Solution**: Ensure migrations run successfully:

```yaml
- name: Initialize database
  run: |
    psql -h localhost -U crypto -d crypto_trading -f migrations/001_initial_schema.sql
    # Add more migrations as needed
```

---

### GitHub Actions Fails: "Module not found"

**Solution**: Ensure `requirements.txt` has all dependencies:

```bash
# Check what's imported
grep -r "^import\|^from" src/ | cut -d' ' -f2 | cut -d'.' -f1 | sort -u

# Add missing to requirements.txt
pip install missing_package
pip freeze >> requirements.txt
```

---

## Badge Integration

Add test status badge to README.md:

```markdown
# Crypto Trading System

[![Tests](https://github.com/YOUR_USERNAME/numbersML/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/numbersML/actions/workflows/ci.yml)
[![Branch Protection](https://img.shields.io/badge/branch%20protection-enabled-green)]()

**Status**: ✅ Production Ready

## Test Suite

- ✅ 6/6 pipeline tests passing
- ✅ 15 indicators configured
- ✅ Enforced in CI/CD
```

---

## Security Best Practices

### 1. Use GitHub Secrets for Sensitive Data

```
Settings → Secrets and variables → Actions

Add repository secrets:
- DATABASE_PASSWORD
- DEPLOY_TOKEN
- API_KEYS
```

Update workflow:
```yaml
env:
  DATABASE_PASSWORD: ${{ secrets.DATABASE_PASSWORD }}
```

### 2. Never Commit `.env`

```bash
# Add to .gitignore
.env
.env.*
!.env.example
```

### 3. Enable Dependabot

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

---

## Monitoring

### GitHub Insights

- **Actions**: `https://github.com/YOUR_USERNAME/numbersML/actions`
- **Issues**: `https://github.com/YOUR_USERNAME/numbersML/issues`
- **Pull Requests**: `https://github.com/YOUR_USERNAME/numbersML/pulls`

### Test Trends

GitHub Actions shows:
- Test pass/fail trends
- Average execution time
- Flaky tests detection

---

## Next Steps After GitHub Setup

1. ✅ Push code to GitHub
2. ✅ Verify Actions running
3. ✅ Configure branch protection
4. ✅ Add test status badge to README
5. ✅ Enable Dependabot
6. ✅ Configure deployment (optional)
7. ✅ Add team members (if applicable)

---

## Questions?

**GitHub Actions**: See `.github/workflows/ci.yml`

**Test Suite**: See `TEST_ENFORCEMENT.md` and `TEST_SUITE_COMPLETE.md`

**GitHub Support**: https://docs.github.com/en/actions

---

**Last Updated**: March 22, 2026
**Status**: ✅ READY FOR GITHUB
