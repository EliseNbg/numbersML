> **Note:** This document references the old architecture. See [CLI Reference](docs/CLI_REFERENCE.md) and [Wide Vector](docs/WIDE_VECTOR.md) for current docs.

# GitHub CI/CD Infrastructure Setup

**Answer**: ✅ **YES, GitHub Actions CAN start your infrastructure!**

---

## What GitHub Actions Does

GitHub Actions automatically starts **PostgreSQL + Redis** for every test run using **Docker containers**.

```yaml
# From .github/workflows/ci.yml
jobs:
  integration-tests:
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: crypto_trading
          POSTGRES_USER: crypto
          POSTGRES_PASSWORD: crypto_secret_change_me
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10
      
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10
```

---

## Infrastructure Flow

```
GitHub Push/PR
       ↓
GitHub Actions starts
       ↓
┌─────────────────────────────────────┐
│  Runner (Ubuntu 22.04)              │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │  PostgreSQL  │  │    Redis    │ │
│  │  :5432       │  │   :6379     │ │
│  │  (Docker)    │  │  (Docker)   │ │
│  └──────────────┘  └─────────────┘ │
│                                     │
│  ┌──────────────┐                   │
│  │   Python     │                   │
│  │   Tests      │                   │
│  └──────────────┘                   │
└─────────────────────────────────────┘
       ↓
Tests run with full infrastructure
       ↓
Results uploaded to GitHub
```

---

## What's Configured

### PostgreSQL

| Setting | Value |
|---------|-------|
| **Version** | 15-alpine |
| **Database** | crypto_trading |
| **User** | crypto |
| **Password** | crypto_secret_change_me |
| **Port** | 5432 (exposed to runner) |
| **Health Check** | `pg_isready` every 10s |
| **Migrations** | Auto-run on start |

### Redis

| Setting | Value |
|---------|-------|
| **Version** | 7-alpine |
| **Port** | 6379 (exposed to runner) |
| **Health Check** | `redis-cli ping` every 10s |
| **Usage** | Future (for EnrichmentService pub/sub) |

---

## Workflow Execution

### Full Pipeline (~4-5 minutes)

```
1. Quick Check (5s)
   ↓
2. Unit Tests (30s)
   ↓
3. Infrastructure Starts (30s)
   ├─ PostgreSQL container
   └─ Redis container
   ↓
4. Database Migrations (10s)
   ├─ 001_initial_schema.sql
   ├─ 002_ticker_24hr_stats.sql
   └─ 004_remove_plpgsql_indicators.sql
   ↓
5. Integration Tests (2min)
   ↓
6. Pipeline Test (5s)
   ↓
7. Deploy (if main branch)
```

---

## Test Output Example

```
Integration Tests (with Infrastructure)
✅ Quick Check
✅ Unit Tests
✅ Integration Tests (with Infrastructure)
   ├─ ✅ Wait for PostgreSQL
   ├─ ✅ Wait for Redis
   ├─ ✅ Initialize database schema
   ├─ ✅ Verify infrastructure
   └─ ✅ Run integration tests

Pipeline Test ⭐
✅ Pipeline Test ⭐
   ├─ ✅ Wait for PostgreSQL
   ├─ ✅ Wait for Redis
   ├─ ✅ Initialize database
   ├─ ✅ Start infrastructure simulation
   └─ ✅ Run pipeline test

All checks have passed — ready to merge!
```

---

## Comparison: Local vs GitHub

| Aspect | Local Development | GitHub Actions |
|--------|------------------|----------------|
| **Infrastructure** | `docker compose -f docker-compose-infra.yml up -d` | Auto-started by GitHub |
| **PostgreSQL** | localhost:5432 | localhost:5432 (in runner) |
| **Redis** | localhost:6379 | localhost:6379 (in runner) |
| **Database** | Persistent volume | Ephemeral (fresh each run) |
| **Migrations** | Manual run | Auto-run in workflow |
| **Test Command** | `./scripts/test.sh` | `./scripts/test.sh` (same!) |

---

## Key Benefits

### 1. **Consistent Environment**

Every test run gets:
- ✅ Fresh PostgreSQL instance
- ✅ Fresh Redis instance
- ✅ Clean database schema
- ✅ No leftover data

### 2. **No Manual Setup**

GitHub handles:
- ✅ Container orchestration
- ✅ Health checks
- ✅ Port mapping
- ✅ Network configuration

### 3. **Parallel Testing**

Multiple PRs can run simultaneously:
- ✅ Each gets its own runner
- ✅ Isolated infrastructure
- ✅ No conflicts

---

## Customization

### Change PostgreSQL Version

```yaml
services:
  postgres:
    image: postgres:15-alpine  # Change to 16-alpine if needed
```

### Add More Services

```yaml
services:
  postgres:
    # ...
  
  redis:
    # ...
  
  # Add more services as needed
  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - 5672:5672
```

### Custom Configuration

```yaml
services:
  postgres:
    image: postgres:15-alpine
    volumes:
      # Mount custom config
      - ./postgres.conf:/etc/postgresql/postgresql.conf
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

---

## Troubleshooting

### PostgreSQL Not Ready

**Error**: `could not connect to server: Connection refused`

**Solution**: Increase health check retries:

```yaml
postgres:
  options: >-
    --health-cmd pg_isready
    --health-interval 5s
    --health-timeout 5s
    --health-retries 15  # Increase from 10
```

---

### Redis Not Connecting

**Error**: `Could not connect to Redis at localhost:6379`

**Solution**: Check Redis health check:

```yaml
redis:
  options: >-
    --health-cmd "redis-cli ping"
    --health-interval 5s
    --health-timeout 5s
    --health-retries 15
```

---

### Database Migration Fails

**Error**: `relation "symbols" does not exist`

**Solution**: Ensure migrations run in correct order:

```yaml
- name: Initialize database schema
  run: |
    psql -h localhost -U crypto -d crypto_trading -f migrations/001_initial_schema.sql
    psql -h localhost -U crypto -d crypto_trading -f migrations/002_ticker_24hr_stats.sql
    psql -h localhost -U crypto -d crypto_trading -f migrations/004_remove_plpgsql_indicators.sql
```

---

## Cost

**GitHub Actions Pricing**:

| Plan | Free Minutes/Month | Included Storage |
|------|-------------------|------------------|
| **Free** | 2,000 minutes | 500 MB |
| **Pro** | 3,000 minutes | 6 GB |
| **Team** | 3,000 minutes | 6 GB |
| **Enterprise** | 50,000 minutes | 50 GB |

**Estimated Usage**:
- Each test run: ~5 minutes
- 10 PRs/day: ~50 minutes/day = ~1,500 minutes/month
- **Well within free tier!**

---

## Security

### Secrets Management

**Never hardcode passwords!** Use GitHub Secrets:

```yaml
# In workflow
env:
  POSTGRES_PASSWORD: ${{ secrets.DB_PASSWORD }}

# Configure in GitHub: Settings → Secrets → Actions
```

### Network Isolation

- ✅ Each workflow run is isolated
- ✅ Containers are ephemeral
- ✅ No persistent network access
- ✅ Runner is destroyed after job

---

## Monitoring

### View Infrastructure Status

GitHub Actions tab → Click workflow run → Click job:

```
📦 Running database migrations...
✅ Database schema initialized

🔍 Checking infrastructure...
PostgreSQL: localhost:5432 - accepting connections
Redis: PONG
✅ Infrastructure ready
```

### Test Summary

GitHub shows test results in PR:

```
## 🧪 Pipeline Test Results

✅ **PASSED**: 6/6 tests

### Test Details
✅ Test 1: Indicators Configured
✅ Test 2: All Indicators Calculable
✅ Test 3: DB INSERT Triggers Notification
✅ Test 4: EnrichmentService Running
✅ Test 5: WIDE_Vector Reads Indicators
✅ Test 6: Complete Pipeline
```

---

## Summary

### What GitHub Actions Provides

| Component | Provided By GitHub |
|-----------|-------------------|
| **Runner** | ✅ Ubuntu 22.04 VM |
| **PostgreSQL** | ✅ Docker container |
| **Redis** | ✅ Docker container |
| **Network** | ✅ Internal Docker network |
| **Health Checks** | ✅ Configured in workflow |
| **Python** | ✅ setup-python action |
| **Test Results** | ✅ Uploaded as artifacts |

### What You Provide

| Component | Your Responsibility |
|-----------|---------------------|
| **Test Scripts** | ✅ `scripts/test.sh` |
| **Migrations** | ✅ SQL files in `migrations/` |
| **Dependencies** | ✅ `requirements.txt` |
| **Test Code** | ✅ `tests/` directory |

---

**Answer**: ✅ **YES, GitHub Actions fully supports starting PostgreSQL + Redis for your tests!**

**No manual infrastructure setup needed** - GitHub handles everything automatically! 🎉

---

**Last Updated**: March 22, 2026
**Status**: ✅ CONFIGURED IN CI.YML
