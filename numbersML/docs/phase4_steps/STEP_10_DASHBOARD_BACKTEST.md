# Step 10: Dashboard - Enhanced Backtest Page#

## Objective#
Create comprehensive backtest dashboard page with charts, statistics, and trade blotter.

## Context#
- Step 6-7 complete: BacktestService and API exist with real data#
- Step 5 complete: StrategyInstance API exists#
- Need to create page with:#

**Key Features**:#
- StrategyInstance selector#
- Time range presets (4h, 12h, 1d, 3d, 7d, 30d) + custom#
- Results display:#

  - Summary metrics cards (Total Return, Sharpe, Max Drawdown, Win Rate)#
  - Equity curve chart (Chart.js)#
  - Price chart with buy/sell markers#
  - Trade blotter table#
- Poll job status for async execution#

## DDD Architecture Decision (ADR)#

**Decision**: Dashboard is Infrastructure Layer (UI)#
- HTML page in `dashboard/backtest.html`#
- JavaScript module in `dashboard/js/backtest.js`#
- Uses Chart.js for visualizations#
- Polls API for job status updates#

**Chart Types**:#
- **Equity Curve**: Line chart (time vs balance)#
- **Price Chart**: Candlestick or line with buy/sell markers#
- **Drawdown Chart**: Area chart showing drawdown over time#

## TDD Approach#

1. **Manual Testing Checklist**: Test all UI interactions#
2. **Chart Testing**: Verify Chart.js renders correctly#
3. **Integration Test**: Submit backtest, verify results display#

## Implementation Files#

### 1. `dashboard/backtest.html`#

HTML page with Chart.js:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest - Crypto Trading Dashboard</title>
    
    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Bootstrap Icons -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <!-- Custom CSS -->
    <link href="css/dashboard.css" rel="stylesheet">
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="index.html">
                <i class="bi bi-speedometer2"></i> Crypto Dashboard
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav">
                    <li class="nav-item">
                        <a class="nav-link" href="index.html">
                            <i class="bi bi-house"></i> Dashboard
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="symbols.html">
                            <i class="bi bi-currency-bitcoin"></i> Symbols
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="strategies.html">
                            <i class="bi bi-cpu"></i> Strategies
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="config_sets.html">
                            <i class="bi bi-sliders"></i> Config Sets
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="strategy-instances.html">
                            <i class="bi bi-diagram-3"></i> Instances
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link active" href="backtest.html">
                            <i class="bi bi-graph-up-arrow"></i> Backtest
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <div class="container-fluid mt-4">
        <!-- Header -->
        <div class="row mb-4">
            <div class="col-12">
                <h1><i class="bi bi-graph-up-arrow"></i> Algorithm Backtest</h1>
                <p class="text-muted">Test strategy performance on historical data</p>
            </div>
        </div>

        <!-- Alerts -->
        <div id="alert-container"></div>

        <!-- Configuration -->
        <div class="row mb-4">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-gear"></i> Backtest Configuration
                    </div>
                    <div class="card-body">
                        <form id="backtest-form">
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Algorithm Instance *</label>
                                    <select class="form-select" id="backtest-instance" required>
                                        <option value="">Select an instance...</option>
                                    </select>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Initial Balance</label>
                                    <input type="number" class="form-control" id="initial-balance" 
                                           value="10000" step="100">
                                </div>
                            </div>

                            <!-- Time Range Presets -->
                            <div class="mb-3">
                                <label class="form-label">Time Range</label>
                                <div class="btn-group" role="group" id="time-range-presets">
                                    <button type="button" class="btn btn-outline-primary active" data-range="4h">4 Hours</button>
                                    <button type="button" class="btn btn-outline-primary" data-range="12h">12 Hours</button>
                                    <button type="button" class="btn btn-outline-primary" data-range="1d">1 Day</button>
                                    <button type="button" class="btn btn-outline-primary" data-range="3d">3 Days</button>
                                    <button type="button" class="btn btn-outline-primary" data-range="7d">7 Days</button>
                                    <button type="button" class="btn btn-outline-primary" data-range="30d">30 Days</button>
                                    <button type="button" class="btn btn-outline-secondary" data-range="custom">Custom</button>
                                </div>
                            </div>

                            <!-- Custom Time Range (hidden by default) -->
                            <div id="custom-range" class="row mb-3" style="display: none;">
                                <div class="col-md-6">
                                    <label class="form-label">Start Time</label>
                                    <input type="datetime-local" class="form-control" id="custom-start">
                                </div>
                                <div class="col-md-6">
                                    <label class="form-label">End Time</label>
                                    <input type="datetime-local" class="form-control" id="custom-end">
                                </div>
                            </div>

                            <!-- Submit Button -->
                            <button type="button" class="btn btn-primary" id="btn-start-backtest">
                                <i class="bi bi-play-fill"></i> Start Backtest
                            </button>
                        </form>
                    </div>
                </div>
            </div>

            <!-- Job Status -->
            <div class="col-md-4">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-activity"></i> Job Status
                    </div>
                    <div class="card-body" id="job-status-card">
                        <p class="text-muted">No active backtest job</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Results Section (hidden by default) -->
        <div id="results-section" style="display: none;">
            <!-- Summary Metrics -->
            <div class="row mb-4">
                <div class="col-md-3">
                    <div class="card bg-light">
                        <div class="card-body text-center">
                            <h3 id="metric-return">0%</h3>
                            <small class="text-muted">Total Return</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card bg-light">
                        <div class="card-body text-center">
                            <h3 id="metric-sharpe">0</h3>
                            <small class="text-muted">Sharpe Ratio</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card bg-light">
                        <div class="card-body text-center">
                            <h3 id="metric-max-drawdown">0%</h3>
                            <small class="text-muted">Max Drawdown</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card bg-light">
                        <div class="card-body text-center">
                            <h3 id="metric-win-rate">0%</h3>
                            <small class="text-muted">Win Rate</small>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Equity Curve Chart -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header">
                            <i class="bi bi-graph-up"></i> Equity Curve
                        </div>
                        <div class="card-body">
                            <canvas id="equity-chart"></canvas>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Trade Blotter -->
            <div class="row">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header">
                            <i class="bi bi-list-ul"></i> Trade Blotter
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm" id="trades-table">
                                    <thead>
                                        <tr>
                                            <th>Entry Time</th>
                                            <th>Exit Time</th>
                                            <th>Side</th>
                                            <th>Entry Price</th>
                                            <th>Exit Price</th>
                                            <th>Quantity</th>
                                            <th>PnL</th>
                                            <th>PnL %</th>
                                            <th>Reason</th>
                                        </tr>
                                    </thead>
                                    <tbody id="trades-tbody">
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <!-- Backtest JS -->
    <script src="js/backtest.js"></script>
</body>
</html>
```

### 2. `dashboard/js/backtest.js`#

JavaScript module with Chart.js:

```javascript
/**
 * Backtest Dashboard Module
 * 
 * Handles:
 * - Backtest job submission
 * - Job status polling
 * - Results display with charts
 * - Trade blotter
 */

const API_BASE_URL = '/api';

// State
let instances = [];
let currentJobId = null;
let pollInterval = null;
let equityChart = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadInstances();
    bindEventListeners();
    
    // Check for instance_id in URL params
    const urlParams = new URLSearchParams(window.location.search);
    const instanceId = urlParams.get('instance_id');
    if (instanceId) {
        // Wait for instances to load, then select
        setTimeout(() => {
            const select = document.getElementById('backtest-instance');
            select.value = instanceId;
        }, 1000);
    }
});

/**
 * Bind all event listeners
 */
function bindEventListeners() {
    // Instance selector
    document.getElementById('backtest-instance').addEventListener('change', () => {
        // Enable/disable start button based on selection
        const btnStart = document.getElementById('btn-start-backtest');
        btnStart.disabled = !document.getElementById('backtest-instance').value;
    });
    
    // Time range presets
    document.querySelectorAll('#time-range-presets button').forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Update active state
            document.querySelectorAll('#time-range-presets button').forEach(b => 
                b.classList.remove('active')
            );
            e.target.classList.add('active');
            
            // Show/hide custom range
            const customRange = document.getElementById('custom-range');
            if (e.target.dataset.range === 'custom') {
                customRange.style.display = 'flex';
            } else {
                customRange.style.display = 'none';
            }
        });
    });
    
    // Start backtest button
    document.getElementById('btn-start-backtest').addEventListener('click', startBacktest);
}

/**
 * Load StrategyInstances for dropdown
 */
async function loadInstances() {
    try {
        const response = await fetch(`${API_BASE_URL}/strategy-instances`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        instances = await response.json();
        const select = document.getElementById('backtest-instance');
        
        // Clear existing options (except first)
        while (select.options.length > 1) {
            select.remove(1);
        }
        
        // Add instances
        instances.forEach(instance => {
            const option = document.createElement('option');
            option.value = instance.id;
            option.textContent = `Instance ${instance.id.slice(0, 8)}... (${instance.status})`;
            select.appendChild(option);
        });
        
    } catch (error) {
        showAlert('danger', `Failed to load instances: ${error.message}`);
    }
}

/**
 * Start backtest job
 */
async function startBacktest() {
    const instanceId = document.getElementById('backtest-instance').value;
    const initialBalance = parseFloat(document.getElementById('initial-balance').value);
    
    if (!instanceId) {
        showAlert('warning', 'Please select a Algorithm Instance');
        return;
    }
    
    // Get selected time range
    const activeBtn = document.querySelector('#time-range-presets button.active');
    const timeRange = activeBtn.dataset.range;
    
    let requestBody = {
        strategy_instance_id: instanceId,
        time_range: timeRange,
        initial_balance: initialBalance,
    };
    
    // Handle custom range
    if (timeRange === 'custom') {
        const customStart = document.getElementById('custom-start').value;
        const customEnd = document.getElementById('custom-end').value;
        
        if (!customStart || !customEnd) {
            showAlert('warning', 'Please select custom start and end times');
            return;
        }
        
        requestBody.custom_start = new Date(customStart).toISOString();
        requestBody.custom_end = new Date(customEnd).toISOString();
    }
    
    try {
        const btnStart = document.getElementById('btn-start-backtest');
        btnStart.disabled = true;
        btnStart.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Submitting...';
        
        const response = await fetch(`${API_BASE_URL}/strategy-backtests/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        currentJobId = result.job_id;
        
        showAlert('success', `Backtest job ${currentJobId} submitted successfully`);
        
        // Start polling for job status
        startPolling();
        
    } catch (error) {
        showAlert('danger', `Failed to start backtest: ${error.message}`);
    } finally {
        const btnStart = document.getElementById('btn-start-backtest');
        btnStart.disabled = false;
        btnStart.innerHTML = '<i class="bi bi-play-fill"></i> Start Backtest';
    }
}

/**
 * Start polling for job status
 */
function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    
    // Poll every 2 seconds
    pollInterval = setInterval(checkJobStatus, 2000);
    checkJobStatus(); // Initial check
}

/**
 * Check job status
 */
async function checkJobStatus() {
    if (!currentJobId) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategy-backtests/jobs/${currentJobId}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const job = await response.json();
        updateJobStatusCard(job);
        
        // If completed or failed, stop polling
        if (job.status === 'completed' || job.status === 'failed') {
            clearInterval(pollInterval);
            pollInterval = null;
            
            if (job.status === 'completed' && job.result) {
                displayResults(job.result);
            } else if (job.status === 'failed') {
                showAlert('danger', `Backtest failed: ${job.error || 'Unknown error'}`);
            }
        }
        
    } catch (error) {
        console.error('Failed to check job status:', error);
    }
}

/**
 * Update job status card
 */
function updateJobStatusCard(job) {
    const card = document.getElementById('job-status-card');
    
    let statusColor = 'secondary';
    let statusText = job.status;
    
    if (job.status === 'pending') {
        statusColor = 'warning';
        statusText = 'Pending...';
    } else if (job.status === 'running') {
        statusColor = 'primary';
        statusText = `Running (${(job.progress * 100).toFixed(0)}%)`;
    } else if (job.status === 'completed') {
        statusColor = 'success';
        statusText = 'Completed';
    } else if (job.status === 'failed') {
        statusColor = 'danger';
        statusText = 'Failed';
    }
    
    card.innerHTML = `
        <div class="text-center">
            <h5><span class="badge bg-${statusColor}">${statusText}</span></h5>
            <p class="text-muted mb-1">Job ID: ${job.job_id}</p>
            ${job.status === 'running' ? `
                <div class="progress">
                    <div class="progress-bar" role="progressbar" 
                         style="width: ${job.progress * 100}%" 
                         aria-valuenow="${job.progress * 100}" 
                         aria-valuemin="0" aria-valuemax="100">
                        ${(job.progress * 100).toFixed(0)}%
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

/**
 * Display backtest results
 */
function displayResults(result) {
    const metrics = result.metrics || result; // Handle both formats
    
    // Show results section
    document.getElementById('results-section').style.display = 'block';
    
    // Update summary metrics
    const totalReturn = metrics.total_return_pct || 0;
    const returnElem = document.getElementById('metric-return');
    returnElem.textContent = `${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%`;
    returnElem.className = totalReturn >= 0 ? 'text-success' : 'text-danger';
    
    document.getElementById('metric-sharpe').textContent = (metrics.sharpe_ratio || 0).toFixed(2);
    
    const maxDrawdown = metrics.max_drawdown_pct || 0;
    document.getElementById('metric-max-drawdown').textContent = `${maxDrawdown.toFixed(2)}%`;
    
    const winRate = metrics.win_rate || 0;
    document.getElementById('metric-win-rate').textContent = `${winRate.toFixed(1)}%`;
    
    // Render equity curve
    renderEquityCurve(metrics.equity_curve || []);
    
    // Render trade blotter
    renderTradeBlotter(metrics.trades || []);
}

/**
 * Render equity curve chart
 */
function renderEquityCurve(equityCurve) {
    const ctx = document.getElementById('equity-chart').getContext('2d');
    
    // Destroy existing chart
    if (equityChart) {
        equityChart.destroy();
    }
    
    if (equityCurve.length === 0) {
        return;
    }
    
    const labels = equityCurve.map(point => new Date(point.time).toLocaleString());
    const data = equityCurve.map(point => point.balance);
    
    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Balance',
                data: data,
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.1,
                fill: true,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: 'Balance ($)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    }
                }
            }
        }
    });
}

/**
 * Render trade blotter table
 */
function renderTradeBlotter(trades) {
    const tbody = document.getElementById('trades-tbody');
    
    if (trades.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center text-muted py-4">
                    No trades executed during this backtest
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = trades.map(trade => `
        <tr>
            <td>${new Date(trade.entry_time).toLocaleString()}</td>
            <td>${new Date(trade.exit_time).toLocaleString()}</td>
            <td>
                <span class="badge ${trade.side === 'LONG' ? 'bg-success' : 'bg-danger'}">
                    ${trade.side}
                </span>
            </td>
            <td>$${trade.entry_price?.toFixed(2) || 'N/A'}</td>
            <td>$${trade.exit_price?.toFixed(2) || 'N/A'}</td>
            <td>${trade.quantity?.toFixed(4) || 'N/A'}</td>
            <td>
                <span class="${trade.pnl >= 0 ? 'text-success' : 'text-danger'}">
                    $${trade.pnl?.toFixed(2) || '0.00'}
                </span>
            </td>
            <td>
                <span class="${trade.pnl_percent >= 0 ? 'text-success' : 'text-danger'}">
                    ${trade.pnl_percent?.toFixed(2) || '0.00'}%
                </span>
            </td>
            <td>${trade.reason || 'signal'}</td>
        </tr>
    `).join('');
}

/**
 * Show alert message
 */
function showAlert(type, message) {
    const container = document.getElementById('alert-container');
    const alertId = 'alert-' + Date.now();
    
    const alertHtml = `
        <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', alertHtml);
    
    setTimeout(() => {
        const alert = document.getElementById(alertId);
        if (alert) {
            bootstrap.Alert.getOrCreateInstance(alert).close();
        }
    }, 5000);
}
```

## LLM Implementation Prompt#

```text
You are implementing Step 10 of Phase 4: Dashboard - Enhanced Backtest Page.

## Your Task#

Create comprehensive backtest dashboard with charts, statistics, and trade blotter.

## Context#

- Step 6-7 complete: BacktestService and API exist
- Step 5 complete: StrategyInstance API exists
- Use Bootstrap 5 + vanilla JavaScript + Chart.js
- Follow existing dashboard pattern (see dashboard/strategies.html)

## Requirements#

1. Create `dashboard/backtest.html` with:
   - Navigation with "Backtest" as active item
   - Configuration section:
     * StrategyInstance selector (dropdown)
     * Initial Balance input
     * Time range presets: 4h, 12h, 1d, 3d, 7d, 30d
     * Custom range toggle (datetime-local inputs)
     * Start Backtest button
   - Job Status card (poll progress)
   - Results section (hidden until complete):
     * Summary metrics cards: Total Return, Sharpe, Max Drawdown, Win Rate
     * Equity Curve chart (Chart.js line chart)
     * Trade Blotter table with all trade details

2. Create `dashboard/js/backtest.js` with:
   - loadInstances(): Fetch from GET /api/strategy-instances
   - startBacktest(): POST /api/strategy-backtests/jobs
   - startPolling(): Poll every 2s for job status
   - checkJobStatus(): GET /api/strategy-backtests/jobs/{id}
   - updateJobStatusCard(): Display progress/status
   - displayResults(metrics): Show summary + charts + trades
   - renderEquityCurve(data): Chart.js line chart
   - renderTradeBlotter(trades): Populate table
   - Check URL params for instance_id (pre-select)

3. Key Features:
   - Read instance_id from URL: backtest.html?instance_id=...
   - Poll job status every 2 seconds
   - Chart.js for equity curve visualization
   - Trade blotter with PnL coloring (green/red)
   - Progress bar for running jobs
   - Auto-stop polling when complete/failed

## Constraints#

- Follow existing Bootstrap 5 + vanilla JS pattern
- Use Chart.js v4 for charts (CDN link included)
- Use fetch() API for all backend calls
- CSS: Use existing dashboard.css
- Icons: Use Bootstrap Icons (bi-* classes)
- Responsive design (mobile-friendly)

## Acceptance Criteria#

1. Can select StrategyInstance from dropdown
2. Time range presets work (4h, 12h, 1d, 3d, 7d, 30d)
3. Custom time range works with datetime-local inputs
4. Backtest job submitted successfully
5. Job status polling works (progress updates)
6. Results display with metrics cards
7. Equity curve chart renders correctly
8. Trade blotter shows all trades with PnL
9. URL param instance_id pre-selects instance

## Manual Testing Checklist#

```bash
# Start the dashboard
cd /home/andy/projects/numbers/numbersML
.venv/bin/uvicorn src.infrastructure.api.app:app --reload

# Open browser to http://localhost:8000/dashboard/backtest.html

# Test cases:
1. Page loads → Verify instances loaded in dropdown
2. Click "4 Hours" preset → Verify custom range hidden
3. Click "Custom" → Verify datetime inputs appear
4. Select instance + preset → Click "Start Backtest" → Verify job submitted
5. Watch job status card → Verify progress updates
6. When complete → Verify results section appears
7. Verify metrics cards show correct values
8. Verify equity curve chart renders
9. Verify trade blotter shows trades
10. Test with URL param: backtest.html?instance_id=...
```

## Output#

1. List of files created/modified
2. Screenshot or description of UI
3. Any issues encountered and how resolved
```

## Success Criteria#

- [ ] backtest.html created with all UI elements
- [ ] backtest.js created with all functions
- [ ] Chart.js equity curve renders correctly
- [ ] Job status polling works (every 2 seconds)
- [ ] Trade blotter displays all trades
- [ ] Summary metrics calculated and displayed
- [ ] URL param instance_id pre-selects instance
- [ ] All manual tests pass
- [ ] Responsive design (mobile-friendly)
