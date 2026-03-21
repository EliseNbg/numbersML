# Trading System - Quick Reference Card
# The system goal is to designed the trading systems that survive and thrive, not like the others 95% that fail.

**Version:** 1.0
**Date:** 2026-03-16
**Purpose:** Quick access to critical limits and procedures

---

## 🚨 Emergency Procedures

### Emergency Stop (IMMEDIATE)
```bash
# Method 1: API (Fastest)
curl -X POST http://localhost:8000/api/emergency-stop

# Method 2: Script
python scripts/kill_switch.py --activate --reason "Emergency"

# Method 3: Database
psql -U trading -d trading -c "UPDATE system_config SET emergency_stop = true"
```

**When to use:**
- Unexpected loss > $500 in 1 minute
- System behaving erratically
- Exchange reports issues
- **Any "something feels wrong" moment**

**STOP FIRST, investigate later.**

---

## 📊 Critical Limits (Hard Stops)

### Order Limits
| Limit | Value | Action |
|-------|-------|--------|
| Max order size | 0.01 BTC | REJECT |
| Max order value | $500 | REJECT |
| Max orders/minute | 10 per strategy | REJECT |
| Price collar | ±1% from market | REJECT |
| Signal age | > 5 seconds | REJECT |

### Risk Limits
| Limit | Value | Action |
|-------|-------|--------|
| Daily loss | $100 | STOP TRADING |
| Consecutive losses | 5 | STOP STRATEGY |
| Drawdown | 5% | CIRCUIT BREAKER |
| Total exposure | $10,000 | REJECT |
| Concentration | 30% per symbol | REJECT |
| Leverage | 2x max | REJECT |

### Performance Limits
| Metric | Target | Alert |
|--------|--------|-------|
| End-to-end latency | < 15ms (p50) | > 30ms |
| Max latency | < 40ms (p99) | > 35ms |
| Throughput | 500 candles/s | < 400/s |
| Error rate | < 0.1% | > 1% |
| Queue depth | < 100 | > 1000 |

---

## ✅ Daily Checklist

### Morning Startup (Before Market Open)
- [ ] Verify time synchronization
- [ ] Check PostgreSQL health
- [ ] Check Redis health
- [ ] Test exchange connectivity
- [ ] Verify kill switches INACTIVE
- [ ] Verify capital available
- [ ] Start application
- [ ] Verify all components healthy
- [ ] Enable trading mode
- [ ] Log startup

### Hourly Monitoring
- [ ] Check Grafana dashboard (no alerts)
- [ ] Verify PnL within expected range
- [ ] Verify positions match expectations
- [ ] Check logs for errors/warnings
- [ ] Log hourly check

### Evening Shutdown
- [ ] Disable trading mode
- [ ] Wait for open orders to complete
- [ ] Reconcile positions with exchange
- [ ] Stop application
- [ ] Create database backup
- [ ] Log shutdown

---

## 🔍 Monitoring Dashboard

### Critical Metrics (Check Every Hour)
```
Latency (p99):     ____ ms   (Target: < 40ms)
Throughput:        ____ /s   (Target: > 500/s)
Error Rate:        ____ %    (Target: < 1%)
Queue Depth:       ____      (Target: < 1000)
Daily PnL:         $____     (Target: > -$100)
Active Positions:  ____      (Target: < 10)
Kill Switch:       [ ] ACTIVE [ ] INACTIVE
```

### Alert Thresholds
| Alert | Level | Response Time |
|-------|-------|--------------|
| Kill switch activated | CRITICAL | Immediate |
| Latency > 100ms | HIGH | < 5 minutes |
| Error rate > 5% | HIGH | < 5 minutes |
| Latency > 40ms | MEDIUM | < 15 minutes |
| Queue depth > 1000 | MEDIUM | < 15 minutes |

---

## 🧪 Testing Schedule

### Before Any Live Trading
- [ ] All unit tests passing (100% coverage)
- [ ] All integration tests passing
- [ ] All failure mode tests passing
- [ ] Performance tests passing
- [ ] Stress tests completed
- [ ] Endurance test (24 hours) passed

### Ongoing
- [ ] Weekly: Test emergency stop procedure
- [ ] Monthly: Test exchange failover
- [ ] Monthly: Test backup restoration
- [ ] Quarterly: Full disaster recovery test

---

## 📞 Escalation Contacts

| Issue | Contact | Response Time |
|-------|---------|--------------|
| System crash | [Senior Dev Name/Phone] | Immediate |
| Exchange outage | [Trading Lead Name/Phone] | < 15 minutes |
| Security breach | [Security Team Name/Phone] | Immediate |
| Unexplained losses | [Risk Manager Name/Phone] | < 5 minutes |

---

## 🛠️ Common Issues & Quick Fixes

### Issue: High Latency (> 100ms)
**Immediate Action:**
1. Check queue depths
2. Check CPU/memory usage
3. Consider pausing trading
4. Investigate root cause

### Issue: Exchange Disconnected
**Immediate Action:**
1. Activate exchange kill switch
2. Check exchange status page
3. Verify pending orders
4. Wait for restoration
5. Reconcile positions before resuming

### Issue: Data Corruption Detected
**Immediate Action:**
1. Pause affected strategies
2. Check data source (single exchange or all?)
3. Switch to backup data source if available
4. Investigate root cause

### Issue: Unexpected Loss
**Immediate Action:**
1. STOP TRADING (emergency stop)
2. Document current state
3. Reconcile positions with exchange
4. Review logs
5. Investigate before resuming

---

## 🔐 Security Reminders

### API Key Management
- [ ] Keys stored in environment variables (not code)
- [ ] Keys have trading-only permissions (NO WITHDRAWALS)
- [ ] IP whitelisting enabled on exchange
- [ ] Keys rotated every 90 days
- [ ] Access logged and audited

### Access Control
- [ ] Only authorized personnel can enable trading
- [ ] Kill switch accessible to all operators
- [ ] Configuration changes require approval
- [ ] All actions logged with operator ID

---

## 📈 Capital Management

### Phase Allocation
| Phase | Capital | Duration | Criteria to Advance |
|-------|---------|----------|---------------------|
| Paper | $0 (simulated) | 2 weeks | Profitable, no major issues |
| Live 1 | 1% | 1 week | Profitable, all systems stable |
| Live 2 | 5% | 2 weeks | Consistent performance |
| Live 3 | 10% | 1 month | Proven track record |
| Full | 100% | Ongoing | 3+ months profitable |

**NEVER skip phases. NEVER rush.**

---

## 🎯 Golden Rules

1. **Survival first, profit second**
2. **When in doubt, stop trading**
3. **Never override safety controls**
4. **Always reconcile positions daily**
5. **Document everything**
6. **Test before deploying**
7. **Start small, scale gradually**
8. **Know your breaking points**
9. **Have an exit plan for every trade**
10. **If it feels wrong, it probably is**

---

## 📚 Reference Documents

| Document | Purpose | Location |
|----------|---------|----------|
| Step 0 | Safety infrastructure specs | `specs/Step0.md` |
| Step 0.1 | Testing requirements | `specs/Step0.1.md` |
| Step 0.2 | Operational runbooks | `specs/Step0.2.md` |
| Step 0.3 | Performance testing | `specs/Step0.3.md` |
| Architectural Critique | Risk analysis | `specs/ARCHITECTURAL_CRITIQUE.md` |
| Runbooks | Detailed procedures | `specs/runbooks/` |

---

**Print this card and keep it at your trading desk.**

**Last updated:** 2026-03-16
**Next review:** Before each trading session
