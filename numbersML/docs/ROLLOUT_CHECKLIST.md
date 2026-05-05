# Algorithm System Rollout Checklist

## Pre-Flight Checklist

### 1. Environment Verification
- [ ] Database migrations applied
- [ ] Redis connectivity confirmed
- [ ] API health endpoints responding
- [ ] Dashboard accessible
- [ ] LLM service connectivity (if applicable)

### 2. Test Suite Status
- [ ] All unit tests passing (≥75% coverage)
- [ ] All integration tests passing
- [ ] E2E workflow tests passing
- [ ] Safety critical tests passing
- [ ] Rollback procedure tested

### 3. Configuration Verification
- [ ] Risk limits configured (daily loss, max positions)
- [ ] Emergency stop contacts configured
- [ ] Paper trading mode available
- [ ] Live trading credentials secured (not in repo)
- [ ] Audit logging enabled

---

## Phase 1: Paper Trading Soak (Days 1-7)

### Objective
Validate system stability with simulated trading before any real capital exposure.

### Entry Criteria
| Gate | Criteria | Status |
|------|----------|--------|
| Code Quality | All CI gates passing | ⬜ |
| Test Coverage | ≥75% overall, 100% safety-critical | ⬜ |
| Documentation | Runbook accessible to operators | ⬜ |

### Activities
- [ ] Deploy to staging/paper environment
- [ ] Create 3-5 test algorithms (different types: RSI, MACD, Bollinger)
- [ ] Run algorithms for 7 days continuously
- [ ] Monitor error rates (< 0.1% acceptable)
- [ ] Verify audit logs are complete
- [ ] Test emergency stop at least once
- [ ] Generate and review backtests for all algorithms

### Success Metrics
| Metric | Target | Actual |
|--------|--------|--------|
| Uptime | > 99.5% | |
| Signal Generation | > 1000 signals/day | |
| Error Rate | < 0.1% | |
| Backtest Completeness | 100% | |
| Emergency Stop Latency | < 5 seconds | |

### Exit Criteria
- [ ] Zero critical errors
- [ ] All algorithms generated expected signals
- [ ] Emergency stop tested and working
- [ ] Operator team trained on runbook
- [ ] Go/No-go decision meeting held

---

## Phase 2: Limited Live Pilot (Days 8-14)

### Objective
Validate live trading with minimal capital exposure (≤ $1000 total).

### Entry Criteria
- [ ] Phase 1 success metrics met
- [ ] Operator sign-off from Phase 1
- [ ] Capital allocation approved (≤ $1000)
- [ ] Exchange API keys configured and tested

### Activities
- [ ] Deploy to production
- [ ] Activate 1 algorithm in live mode (smallest allocation)
- [ ] Monitor fills vs expected prices (< 1% slippage)
- [ ] Verify P&L tracking accuracy
- [ ] Test daily loss limit triggers
- [ ] Confirm kill switches work in live mode

### Risk Controls
| Control | Setting |
|---------|---------|
| Max Daily Loss | $50 per algorithm |
| Max Position Size | 10% of allocation |
| Max Orders/Hour | 5 |
| Global Kill | Any operator can trigger |

### Success Metrics
| Metric | Target | Actual |
|--------|--------|--------|
| Order Fill Rate | > 95% | |
| Slippage | < 1% | |
| P&L Accuracy | 100% | |
| No Emergency Stops | 7 days | |

### Exit Criteria
- [ ] All orders filled as expected
- [ ] P&L tracking matches exchange
- [ ] No unexpected kill switch triggers
- [ ] Operator confidence high

---

## Phase 3: Gradual Expansion (Days 15-30)

### Objective
Increase capital allocation and algorithm count gradually.

### Entry Criteria
- [ ] Phase 2 completed successfully
- [ ] No incidents in pilot week
- [ ] Risk team approval for expansion

### Activities
- [ ] Increase allocation to $5000
- [ ] Add 2-3 additional algorithms
- [ ] Run algorithms with different timeframes
- [ ] Monitor correlation between algorithms
- [ ] Review and tune risk parameters

### Expansion Schedule
| Day | Capital | Algorithms | Notes |
|-----|---------|------------|-------|
| 15 | $2000 | 2 | Add second algorithm |
| 20 | $3500 | 3 | Add third algorithm |
| 25 | $5000 | 4 | Full pilot allocation |
| 30 | Review | Review | Go/No-go for full rollout |

### Risk Controls (Tightened)
| Control | Setting |
|---------|---------|
| Max Daily Loss | 2% of allocation |
| Max Total Exposure | 50% of allocation |
| Max Correlated Exposure | 30% of allocation |

### Success Metrics
| Metric | Target | Actual |
|--------|--------|--------|
| Sharpe Ratio | > 1.0 | |
| Max Drawdown | < 5% | |
| Win Rate | > 50% | |
| Algorithm Correlation | < 0.7 | |

### Exit Criteria
- [ ] Positive risk-adjusted returns
- [ ] Risk controls working as designed
- [ ] No correlation-induced drawdowns
- [ ] Full operator competency demonstrated

---

## Phase 4: Full Production Rollout

### Objective
Deploy system with full capital allocation and all planned algorithms.

### Entry Criteria
- [ ] Phase 3 success metrics met
- [ ] Risk committee approval
- [ ] Executive sign-off
- [ ] Incident response plan tested

### Activities
- [ ] Scale to full capital allocation
- [ ] Deploy all approved algorithms
- [ ] Implement continuous monitoring
- [ ] Schedule weekly risk reviews
- [ ] Establish monthly algorithm reviews

### Ongoing Monitoring
| Metric | Frequency | Alert Threshold |
|--------|-----------|-----------------|
| Daily P&L | Real-time | Loss > limit |
| Error Rate | Hourly | > 0.5% |
| Latency | Real-time | > 500ms |
| Signal Quality | Daily | Drift > 20% |

### Success Criteria (90 Days)
- [ ] System uptime > 99.9%
- [ ] Risk-adjusted returns positive
- [ ] Zero critical incidents
- [ ] All operators trained and certified
- [ ] Documentation current and complete

---

## Rollout Sign-Off

| Phase | Lead | Date | Status |
|-------|------|------|--------|
| Pre-Flight | | | |
| Phase 1: Paper | | | |
| Phase 2: Pilot | | | |
| Phase 3: Expansion | | | |
| Phase 4: Full | | | |

**Final Approval:**

Name: _________________  Date: _______

Signature: _________________
