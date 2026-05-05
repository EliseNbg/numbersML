# Algorithm System - Operator Runbook

## Emergency Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| On-Call Engineer | [TBD] | +1 [TBD] |
| Risk Manager | [TBD] | +1 [TBD] |
| System Owner | [TBD] | +1 [TBD] |

---

## Quick Reference: Emergency Procedures

### 🔴 Global Emergency Stop (Kill Everything)
```bash
# Via API
curl -X POST http://api-host/api/v1/system/emergency-stop \
  -H "Content-Type: application/json" \
  -d '{
    "level": "full",
    "reason": "Critical incident - manual stop",
    "triggered_by": "operator-name"
  }'
```

**When to use:**
- Market crash detected
- System showing anomalous behavior
- Suspected security breach
- Massive unexpected P&L loss
- On-call engineer judgment

**After trigger:**
1. All algorithms stop immediately
2. All new orders blocked
3. Open positions remain (may need manual close)
4. Audit log records the stop

---

### 🟡 Single Algorithm Stop
```bash
# Via API
curl -X POST http://api-host/api/v1/system/emergency-stop \
  -H "Content-Type: application/json" \
  -d '{
    "level": "algorithm",
    "algorithm_id": "<uuid>",
    "reason": "Algorithm malfunction",
    "triggered_by": "operator-name"
  }'
```

**When to use:**
- Single algorithm generating bad signals
- Algorithm exceeding its risk limits
- Suspected bug in one algorithm

---

### 🟢 Release Emergency Stop
```bash
# Via API
curl -X POST http://api-host/api/v1/system/emergency-stop/release \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Issue resolved",
    "released_by": "operator-name"
  }'
```

**Requirements before release:**
- [ ] Root cause identified
- [ ] Fix implemented or false alarm confirmed
- [ ] Risk manager approval
- [ ] Test in paper mode first (recommended)

---

## Incident Response Playbooks

### Type 1: Daily Loss Limit Breached

**Detection:**
- Alert: `GUARDRAIL_BREACH: daily_loss_limit`
- Dashboard shows red status
- Kill switch auto-triggered

**Immediate Actions:**
1. Verify the loss is real (check exchange P&L)
2. Confirm kill switch is active
3. Check for any stuck orders

**Investigation:**
```bash
# Check audit logs
curl http://api-host/api/v1/audit?event_type=GUARDRAIL_BREACH&since=<timestamp>

# Check algorithm status
curl http://api-host/api/v1/algorithms/<id>/status
```

**Resolution:**
- If legitimate market move: Document, wait for next day (reset)
- If algorithm bug: Fix before reactivating
- If data issue: Recalculate indicators

---

### Type 2: Stale Data Detected

**Detection:**
- Alert: `STALE_DATA: Data feed delayed > 60s`
- Algorithms auto-paused

**Immediate Actions:**
1. Check data pipeline health
2. Verify Redis pub/sub connectivity
3. Check upstream data source

**Investigation:**
```bash
# Check data freshness
curl http://api-host/api/v1/market/health

# Check last candle timestamp
curl http://api-host/api/v1/candles/latest?symbol=BTC/USDC
```

**Resolution:**
- If upstream issue: Wait for recovery, data will backfill
- If pipeline issue: Restart pipeline service
- If Redis issue: Restart Redis connection

**Recovery:**
- Data will auto-resume when fresh
- Algorithms auto-resume (or manual resume if needed)

---

### Type 3: Algorithm Generating Bad Signals

**Detection:**
- Alert: `Signal quality degraded`
- Backtest vs live drift > 20%
- Unusual trade patterns

**Immediate Actions:**
1. Pause the algorithm (don't kill - preserve state)
2. Check recent signal history
3. Compare to backtest expectations

**Investigation:**
```bash
# Get algorithm telemetry
curl http://api-host/api/v1/algorithms/<id>/telemetry

# Check recent signals
curl http://api-host/api/v1/algorithms/<id>/signals?limit=100

# Run fresh backtest
curl -X POST http://api-host/api/v1/algorithms/<id>/backtest \
  -d '{"start_time": "...", "end_time": "..."}'
```

**Common Causes:**
- Market regime change (solution: retune or pause)
- Indicator calculation bug (solution: fix and redeploy)
- Config drift (solution: verify config matches backtest)

**Resolution:**
- If market regime: Pause until conditions normalize
- If bug: Fix, validate in paper, redeploy
- If config drift: Restore correct config

---

### Type 4: Order Execution Issues

**Detection:**
- Alert: `ORDER_REJECTED` or `ORDER_ERROR`
- Low fill rates
- High slippage

**Immediate Actions:**
1. Check exchange connectivity
2. Verify API keys valid
3. Check account balance/positions

**Investigation:**
```bash
# Check order history
curl http://api-host/api/v1/algorithms/<id>/orders?status=error

# Check exchange balance
curl http://api-host/api/v1/market/balance
```

**Common Causes:**
- API key expired (solution: refresh keys)
- Insufficient balance (solution: adjust position sizes)
- Exchange maintenance (solution: wait)
- Rate limiting (solution: backoff)

---

### Type 5: System Performance Degradation

**Detection:**
- High latency alerts
- Tick processing delays
- Memory/CPU warnings

**Investigation:**
```bash
# Check system metrics
curl http://api-host/api/v1/system/metrics

# Check algorithm health
curl http://api-host/api/v1/algorithms/health
```

**Resolution:**
- Scale horizontally (add instances)
- Restart affected services
- Reduce active algorithm count temporarily

---

## Rollback Procedures

### Rollback Type A: Code Rollback

**When:** New deployment causing issues

**Procedure:**
```bash
# 1. Emergency stop all algorithms
curl -X POST /api/v1/system/emergency-stop \
  -d '{"level": "full", "reason": "Code rollback"}'

# 2. Rollback deployment
kubectl rollout undo deployment/algorithm-api
# OR
docker-compose down && docker-compose up -d --build

# 3. Verify health
curl http://api-host/api/v1/health

# 4. Resume in paper mode first
curl -X POST /api/v1/system/emergency-stop/release
# Activate algorithms in paper mode

# 5. Verify stable, then enable live
```

### Rollback Type B: Database Rollback

**When:** Bad migration or data corruption

**Procedure:**
```bash
# 1. Emergency stop
curl -X POST /api/v1/system/emergency-stop

# 2. Restore from backup (requires DBA)
pg_restore --clean --if-exists backup.dump

# 3. Verify data integrity
# Run validation scripts

# 4. Gradual restart
```

### Rollback Type C: Configuration Rollback

**When:** Bad config change

**Procedure:**
```bash
# 1. Identify bad config version
curl http://api-host/api/v1/algorithms/<id>/config/history

# 2. Revert to previous version
curl -X POST /api/v1/algorithms/<id>/config/revert \
  -d '{"to_version": <previous_version>}'

# 3. If algorithm stuck, kill and reactivate
curl -X POST /api/v1/system/emergency-stop
# Wait 5 seconds
curl -X POST /api/v1/system/emergency-stop/release
curl -X POST /api/v1/algorithms/<id>/activate
```

---

## Monitoring Commands

### Health Checks
```bash
# System health
curl http://api-host/api/v1/health

# Algorithm health
curl http://api-host/api/v1/algorithms/health

# Risk status
curl http://api-host/api/v1/risk/status

# Emergency stop status
curl http://api-host/api/v1/system/emergency-stop/status
```

### Audit Queries
```bash
# Recent events
curl "http://api-host/api/v1/audit?limit=100"

# Critical events only
curl "http://api-host/api/v1/audit?min_severity=critical&since=2024-01-01"

# Specific algorithm
curl "http://api-host/api/v1/audit?target_type=algorithm&target_id=<uuid>"

# Kill switch events
curl "http://api-host/api/v1/audit?event_type=KILL_SWITCH_TRIGGERED"
```

### Algorithm Operations
```bash
# List all algorithms
curl http://api-host/api/v1/algorithms

# Get algorithm status
curl http://api-host/api/v1/algorithms/<id>/status

# Get P&L
curl http://api-host/api/v1/algorithms/<id>/pnl

# Get telemetry
curl http://api-host/api/v1/algorithms/<id>/telemetry
```

---

## Escalation Matrix

| Issue Type | First Response | Escalate If | Escalation Path |
|------------|----------------|-------------|-----------------|
| Data feed | On-call (15 min) | Not resolved | → Data Eng → CTO |
| Order errors | On-call (15 min) | > 5% error rate | → Risk → CTO |
| P&L anomaly | Risk Mgr (5 min) | > $X loss | → CFO → CEO |
| Security | Security (immediate) | Any breach | → CISO → CEO |
| System down | On-call (5 min) | > 15 min | → CTO → CEO |

---

## Post-Incident Review Template

**Incident ID:** [Auto-generated]
**Date/Time:** 
**Duration:** 
**Severity:** [Critical/High/Medium/Low]

### Summary
[One paragraph description]

### Timeline
| Time | Event |
|------|-------|
| HH:MM | Detection |
| HH:MM | Response start |
| HH:MM | Mitigation |
| HH:MM | Resolution |

### Impact
- Algorithms affected: 
- P&L impact: 
- Data gaps: 

### Root Cause
[Detailed technical explanation]

### Resolution
[What fixed it]

### Lessons Learned
- [ ] Detection could be improved
- [ ] Response procedure needs update
- [ ] Monitoring gap identified
- [ ] Documentation needs update

### Action Items
| Action | Owner | Due Date |
|--------|-------|----------|
| | | |

---

## Change Management

### Before Any Change
- [ ] Test in staging/paper environment
- [ ] Have rollback plan ready
- [ ] Notify on-call team
- [ ] Schedule during low-activity period

### Change Approval Levels
| Change Type | Approver | Testing Required |
|-------------|----------|------------------|
| Config change (minor) | Risk Manager | Paper mode |
| New algorithm | Risk Committee | 7-day paper |
| Code deployment | Tech Lead | Full suite |
| Risk limit change | CFO | N/A |
| Emergency patch | On-call | Minimal |

---

## Runbook Maintenance

**Last Updated:** [Date]
**Next Review:** [Date + 3 months]
**Owner:** [Name]

**Revision History:**
| Date | Version | Changes | Author |
|------|---------|---------|--------|
| | 1.0 | Initial release | |
