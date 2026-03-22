# Quick Start Guide

**TL;DR**: Get started in 3 commands!

---

## Local Development

### 1. Start Infrastructure

```bash
cd /home/andy/projects/numbers/numbersML

# Start PostgreSQL + Redis
./scripts/test.sh start
```

**Output**:
```
✅ PostgreSQL is ready
✅ Redis is ready
✅ Infrastructure started successfully
```

---

### 2. Run Tests

```bash
# Run pipeline test (critical)
./scripts/test.sh pipeline
```

**Expected Output**:
```
✅ ALL TESTS PASSED
Pipeline is ready for deployment.
```

---

### 3. Push to GitHub

```bash
# Add all files
git add .

# Commit
git commit -m "Initial commit with test enforcement"

# Push (GitHub Actions will run tests automatically)
git push origin main
```

---

## Command Reference

| Command | Purpose | Time |
|---------|---------|------|
| `./scripts/test.sh start` | Start PostgreSQL + Redis | ~10s |
| `./scripts/test.sh status` | Check infrastructure status | ~2s |
| `./scripts/test.sh check` | Quick syntax check | ~5s |
| `./scripts/test.sh pipeline` | Run critical pipeline test | ~5s |
| `./scripts/test.sh unit` | Run unit tests | ~30s |
| `./scripts/test.sh integration` | Run integration tests | ~2min |
| `./scripts/test.sh` | Run all tests | ~3min |
| `./scripts/test.sh stop` | Stop infrastructure | ~2s |

---

## GitHub Actions

Once pushed, GitHub will automatically:

1. ✅ Start PostgreSQL + Redis
2. ✅ Run migrations
3. ✅ Run all tests
4. ✅ Show results on PR

**No manual setup needed on GitHub!**

---

## Daily Workflow

```bash
# Morning: Start infrastructure
./scripts/test.sh start

# Before commit: Quick check
./scripts/test.sh check

# Before push: Run tests
./scripts/test.sh pipeline

# Evening: Stop infrastructure (optional)
./scripts/test.sh stop
```

---

## Troubleshooting

### "Infrastructure not running"

```bash
# Start it
./scripts/test.sh start

# Or check what's wrong
./scripts/test.sh status
```

### "Tests failed"

```bash
# Run specific test
./scripts/test.sh pipeline -v

# Check results
cat /tmp/integration_test_results.json | jq
```

### "Database connection error"

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Restart if needed
./scripts/test.sh restart
```

---

## Next Steps

1. ✅ Start infrastructure: `./scripts/test.sh start`
2. ✅ Run tests: `./scripts/test.sh pipeline`
3. ✅ Push to GitHub
4. ✅ Configure branch protection (see `GITHUB_SETUP.md`)

---

**That's it! You're ready to go!** 🚀
