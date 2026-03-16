# Step 0.2: Operational Runbooks

**Status:** ⚠️ REQUIRED BEFORE LIVE TRADING
**Effort:** 4-6 hours
**Dependencies:** Step 0 (Critical Safety Infrastructure)

---

## 🎯 Objective

Create comprehensive operational runbooks that enable safe trading system operation, incident response, and recovery procedures.

**Key Principle:** If it's not documented, it's not operational. During an incident, you don't have time to figure things out.

---

## 📁 Runbook Structure

```
runbooks/
├── daily/
│   ├── RUNBOOK-001-daily-startup.md       # Morning startup procedure
│   ├── RUNBOOK-002-daily-monitoring.md    # Continuous monitoring
│   ├── RUNBOOK-003-daily-shutdown.md      # Evening shutdown
│   └── RUNBOOK-004-daily-reconciliation.md # Daily reconciliation
├── weekly/
│   ├── RUNBOOK-010-weekly-backup-test.md  # Test backup restoration
│   ├── RUNBOOK-011-weekly-performance.md  # Performance review
│   └── RUNBOOK-012-weekly-security.md     # Security audit
├── incident/
│   ├── RUNBOOK-100-emergency-stop.md      # Emergency shutdown
│   ├── RUNBOOK-101-exchange-outage.md     # Exchange goes down
│   ├── RUNBOOK-102-data-corruption.md     # Bad data detected
│   ├── RUNBOOK-103-network-failure.md     # Network connectivity loss
│   ├── RUNBOOK-104-system-crash.md        # Application crash
│   ├── RUNBOOK-105-database-corruption.md # Database failure
│   └── RUNBOOK-106-security-breach.md     # Security incident
├── maintenance/
│   ├── RUNBOOK-200-deploy-update.md       # Deploy new version
│   ├── RUNBOOK-201-add-strategy.md        # Add new strategy
│   ├── RUNBOOK-202-rotate-keys.md         # Rotate API keys
│   └── RUNBOOK-203-database-migration.md  # Schema migration
└── recovery/
    ├── RUNBOOK-300-recover-from-backup.md # Restore from backup
    ├── RUNBOOK-301-recover-positions.md   # Position recovery
    └── RUNBOOK-302-recover-from-loss.md   # Loss recovery
```

---

## 📝 Runbook Templates

### RUNBOOK-001: Daily Startup Procedure

**Purpose:** Safe system startup each trading day

**Frequency:** Daily, before market open

**Duration:** 15 minutes

**Prerequisites:**
- [ ] System hardware operational
- [ ] Network connectivity verified
- [ ] Database backup from previous night exists

**Procedure:**

```bash
# Step 1: Verify system time synchronization
echo "Checking time sync..."
timedatectl status
# EXPECTED: "System clock synchronized: yes"
# IF NOT: sudo timedatectl set-ntp true

# Step 2: Check PostgreSQL health
echo "Checking database..."
psql -U trading -d trading -c "SELECT 1"
# EXPECTED: Returns "1"
# IF FAIL: See RUNBOOK-105 (Database corruption)

# Step 3: Check Redis health
echo "Checking Redis..."
redis-cli ping
# EXPECTED: "PONG"
# IF FAIL: sudo systemctl start redis

# Step 4: Verify exchange connectivity
echo "Testing Binance connection..."
python scripts/test_exchange_connection.py
# EXPECTED: "Binance connected, latency: <100ms"
# IF FAIL: Check network, see RUNBOOK-101

# Step 5: Verify no kill switches active
echo "Checking kill switches..."
python scripts/check_kill_switches.py
# EXPECTED: "All kill switches inactive"
# IF FAIL: Investigate reason, do NOT deactivate without understanding

# Step 6: Verify capital availability
echo "Checking capital..."
python scripts/check_capital.py
# EXPECTED: Capital >= minimum required
# IF FAIL: Do not start trading

# Step 7: Start application
echo "Starting trading system..."
cd /path/to/trading-backend
source venv/bin/activate
python -m app.main
# EXPECTED: "System started successfully"
# IF FAIL: Check logs, see RUNBOOK-104

# Step 8: Verify all components running
echo "Verifying components..."
python scripts/health_check.py
# EXPECTED: All components "healthy"
# IF FAIL: Investigate specific component

# Step 9: Enable trading mode
echo "Enabling trading..."
python scripts/enable_trading.py
# EXPECTED: "Trading enabled"

# Step 10: Log startup
echo "Logging startup..."
python scripts/log_startup.py
# Include: Time, capital available, kill switch status, operator name
```

**Post-Startup Verification:**
- [ ] All strategies loaded
- [ ] Market data flowing (check logs)
- [ ] No errors in first 5 minutes
- [ ] Capital matches expected amount

**Rollback Procedure:**
If startup fails:
1. Do NOT force start
2. Check logs: `tail -f logs/trading.log`
3. Identify failing component
4. Fix root cause
5. Restart from Step 1

**Escalation:**
If unable to start after 2 attempts:
- Contact: [Senior Developer Name/Phone]
- Do not trade until system verified

---

### RUNBOOK-002: Continuous Monitoring

**Purpose:** Real-time system health monitoring

**Frequency:** Continuous (automated) + hourly (manual check)

**Duration:** Ongoing

**Automated Monitoring:**

```yaml
# Monitoring Dashboard (Grafana)
Metrics to monitor:
  - System latency (p50, p95, p99)
    - Alert if p99 > 40ms
  - Message throughput
    - Alert if drops > 50%
  - Error rate
    - Alert if > 1%
  - Queue depths
    - Alert if > 1000 messages
  - Memory usage
    - Alert if > 80%
  - CPU usage
    - Alert if > 70%
  - Active positions
    - Alert if > max allowed
  - Daily PnL
    - Alert if approaching daily loss limit
  - Kill switch status
    - Alert if activated
  - Exchange connectivity
    - Alert if disconnected > 10 seconds
```

**Hourly Manual Check:**

```bash
# Every hour, operator must check:

# 1. Check dashboard
open http://localhost:3000/d/trading

# 2. Verify no alerts
# Look for red indicators

# 3. Check PnL
python scripts/check_pnl.py
# Verify within expected range

# 4. Check positions
python scripts/check_positions.py
# Verify positions match expectations

# 5. Check logs for anomalies
tail -100 logs/trading.log | grep -i "error\|warning"
# Investigate any errors

# 6. Log hourly check
python scripts/log_hourly_check.py
# Include: Time, PnL, positions, any issues, operator name
```

**Alert Response Times:**
| Alert Type | Response Time | Action |
|------------|--------------|--------|
| Critical (kill switch, emergency stop) | Immediate | Stop trading, investigate |
| High (latency > 100ms, error rate > 5%) | < 5 minutes | Investigate, consider pause |
| Medium (latency > 40ms, queue depth) | < 15 minutes | Monitor, plan intervention |
| Low (informational) | < 1 hour | Review, document |

---

### RUNBOOK-100: Emergency Stop Procedure

**Purpose:** Immediately halt all trading activity

**Trigger Conditions:**
- Unexpected loss > $500 in 1 minute
- System behaving erratically
- Exchange reports issues
- Security breach suspected
- Any "something feels wrong" moment

**CRITICAL:** When in doubt, STOP FIRST, investigate later.

**Procedure:**

```bash
# METHOD 1: API Endpoint (Fastest)
curl -X POST http://localhost:8000/api/emergency-stop
# EXPECTED: "Emergency stop activated"

# METHOD 2: Kill Switch Script
python scripts/kill_switch.py --activate --reason "Emergency stop by [operator name]"
# EXPECTED: "Kill switch activated"

# METHOD 3: Database Flag (If API unavailable)
psql -U trading -d trading -c "UPDATE system_config SET emergency_stop = true"
# EXPECTED: "UPDATE 1"

# METHOD 4: Process Kill (Last resort)
pkill -f "python -m app.main"
# EXPECTED: Process terminated

# Step 5: Verify all activity stopped
python scripts/verify_stop.py
# EXPECTED: "All trading activity stopped"

# Step 6: Document emergency stop
python scripts/log_emergency_stop.py
# Include: Time, reason, operator name, system state

# Step 7: Notify team
# Send Slack/Email/SMS to trading team
```

**Post-Emergency Stop:**
1. DO NOT restart until root cause identified
2. Document everything
3. Review logs
4. Verify capital
5. Reconcile positions with exchange
6. Only restart after senior approval

**Common Mistakes to Avoid:**
- ❌ Restarting immediately without investigation
- ❌ Blaming without evidence
- ❌ Skipping position reconciliation
- ❌ Not documenting the incident

---

### RUNBOOK-101: Exchange Outage

**Purpose:** Handle exchange connectivity loss

**Detection:**
- WebSocket disconnects
- API requests timeout
- Exchange status page reports issues

**Procedure:**

```bash
# Step 1: Confirm outage
python scripts/check_exchange_status.py binance
# EXPECTED: "Connected" or "Disconnected"

# Step 2: Check exchange status page
# https://www.binance.com/en/support/announcement

# Step 3: If confirmed outage, activate exchange kill switch
python scripts/kill_switch.py --exchange binance --reason "Exchange outage"

# Step 4: Verify no pending orders
python scripts/check_pending_orders.py
# If orders pending, attempt cancellation

# Step 5: Document outage start
python scripts/log_outage.py --exchange binance --start

# Step 6: Monitor for restoration
# Check every 5 minutes

# Step 7: When restored, verify connectivity
python scripts/check_exchange_status.py binance

# Step 8: Reconcile positions
python scripts/reconcile_positions.py --exchange binance

# Step 9: Document outage end
python scripts/log_outage.py --exchange binance --end

# Step 10: Resume trading (if safe)
python scripts/resume_trading.py --exchange binance
```

**Decision Tree:**
```
Exchange disconnected
    ↓
Check status page
    ↓
┌─────────────────┬─────────────────┐
│ Planned         │ Unplanned       │
│ Maintenance     │ Outage          │
└────────┬────────┴────────┬────────┘
         │                 │
    Wait for          Activate
    completion        kill switch
         │                 │
         └────────┬────────┘
                  ↓
         Reconcile positions
                  ↓
         Resume trading
```

---

### RUNBOOK-102: Data Corruption Detected

**Purpose:** Handle bad market data

**Detection:**
- Market data validator rejects candles
- Price anomalies detected (>5% move in 1 second)
- Volume anomalies (zero or extreme volume)

**Procedure:**

```bash
# Step 1: Identify corrupted data
python scripts/investigate_data.py --symbol BTCUSDT --time "2024-03-16 12:00:00"

# Step 2: Check if isolated or widespread
python scripts/check_data_quality.py --timeframe 5m
# EXPECTED: "< 1% rejected"

# Step 3: If widespread, pause affected strategies
python scripts/pause_strategies.py --symbol BTCUSDT

# Step 4: Check data source
# - Is it just Binance or all exchanges?
# - Check alternative data source (Coinbase, Kraken)

# Step 5: If single exchange, switch to backup
python scripts/switch_data_source.py --symbol BTCUSDT --source coinbase

# Step 6: Document incident
python scripts/log_data_incident.py
# Include: Symbol, time, nature of corruption, affected strategies

# Step 7: Investigate root cause
# - Exchange issue?
# - Network issue?
# - Parser bug?

# Step 8: Fix and verify
# - If exchange issue: wait for resolution
# - If bug: deploy fix

# Step 9: Resume strategies
python scripts/resume_strategies.py --symbol BTCUSDT
```

**Data Quality Thresholds:**
| Metric | Warning | Critical |
|--------|---------|----------|
| Rejected candles | > 1% | > 5% |
| Price deviation | > 2% | > 5% |
| Volume anomaly | > 10x avg | > 100x avg |
| Timestamp drift | > 1 second | > 10 seconds |

---

### RUNBOOK-200: Deploy New Version

**Purpose:** Safely deploy system updates

**Prerequisites:**
- [ ] All tests passing
- [ ] Backtested on historical data
- [ ] Paper traded for 2+ weeks (if strategy change)
- [ ] Backup created
- [ ] Rollback plan documented

**Procedure:**

```bash
# Step 1: Create backup
python scripts/backup_system.py
# EXPECTED: "Backup created: backup-2024-03-16.tar.gz"

# Step 2: Stop trading
python scripts/disable_trading.py
# EXPECTED: "Trading disabled"

# Step 3: Wait for open orders to complete
python scripts/wait_for_orders.py
# EXPECTED: "No pending orders"

# Step 4: Stop application
pkill -f "python -m app.main"

# Step 5: Deploy new version
git pull origin main
pip install -r requirements.txt

# Step 6: Run database migrations (if any)
alembic upgrade head

# Step 7: Verify configuration
python scripts/verify_config.py

# Step 8: Start application
python -m app.main &

# Step 9: Verify health
python scripts/health_check.py

# Step 10: Enable trading
python scripts/enable_trading.py

# Step 11: Monitor for 30 minutes
# Watch for errors, anomalies

# Step 12: Document deployment
python scripts/log_deployment.py
# Include: Version, changes, operator, any issues
```

**Rollback Procedure:**
If issues detected after deployment:
```bash
# Step 1: Disable trading immediately
python scripts/disable_trading.py

# Step 2: Stop application
pkill -f "python -m app.main"

# Step 3: Restore previous version
git checkout <previous-commit>
pip install -r requirements.txt

# Step 4: Restore database (if schema changed)
python scripts/restore_database.py --backup backup-2024-03-16.tar.gz

# Step 5: Restart
python -m app.main &

# Step 6: Verify
python scripts/health_check.py

# Step 7: Document rollback
python scripts/log_rollback.py
```

---

### RUNBOOK-300: Recover from Backup

**Purpose:** Restore system from backup after catastrophic failure

**Trigger:**
- Database corruption
- Server failure
- Data loss

**Procedure:**

```bash
# Step 1: Stop all trading activity
python scripts/emergency_stop.py

# Step 2: Identify latest good backup
ls -la backups/
# Find most recent backup before incident

# Step 3: Verify backup integrity
python scripts/verify_backup.py --backup backup-2024-03-16.tar.gz
# EXPECTED: "Backup verified"

# Step 4: Stop application
pkill -f "python -m app.main"

# Step 5: Restore database
python scripts/restore_database.py --backup backup-2024-03-16.tar.gz

# Step 6: Restore configuration
python scripts/restore_config.py --backup backup-2024-03-16.tar.gz

# Step 7: Verify restoration
python scripts/verify_restoration.py
# Check:
# - Database connectivity
# - Configuration loaded
# - Capital matches expected

# Step 8: Reconcile with exchange
python scripts/reconcile_all.py
# CRITICAL: Backup may be stale vs. exchange

# Step 9: Start application
python -m app.main &

# Step 10: Verify health
python scripts/health_check.py

# Step 11: Document recovery
python scripts/log_recovery.py
# Include: Backup used, time recovered, discrepancies found, operator
```

**Reconciliation is CRITICAL:**
Backups are point-in-time. Exchange positions may have changed. Always:
1. Compare backup positions vs. exchange
2. Document discrepancies
3. Adjust internal state to match exchange
4. Investigate cause of discrepancy

---

## 🎯 Runbook Testing Schedule

Runbooks must be tested, not just documented.

| Runbook | Test Frequency | Last Tested | Next Test |
|---------|---------------|-------------|-----------|
| RUNBOOK-001 (Startup) | Monthly | | |
| RUNBOOK-100 (Emergency Stop) | Weekly | | |
| RUNBOOK-101 (Exchange Outage) | Monthly | | |
| RUNBOOK-200 (Deploy) | Every deployment | | |
| RUNBOOK-300 (Recovery) | Quarterly | | |

**Test Procedure:**
1. Schedule test window (off-hours)
2. Execute runbook step-by-step
3. Document any issues or ambiguities
4. Update runbook based on learnings
5. Sign off: "Tested by [name] on [date]"

---

## 📋 Runbook Checklist Template

Every runbook must include:

- [ ] **Purpose**: What this runbook does
- [ ] **Trigger**: When to use it
- [ ] **Prerequisites**: What must be true before starting
- [ ] **Step-by-step procedure**: Exact commands to run
- [ ] **Expected outputs**: What success looks like
- [ ] **Failure handling**: What to do if steps fail
- [ ] **Rollback**: How to undo if needed
- [ ] **Escalation**: Who to call if stuck
- [ ] **Documentation**: What to log after completion

---

## 🎯 Next Step

After completing Step 0.2, proceed to **Step 0.3: Performance & Stress Testing** (`Step0.3.md`).

---

**Remember:** During an incident, you operate at the level of your training, not the level of your documentation. Test these runbooks regularly.
