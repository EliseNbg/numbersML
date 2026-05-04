/**
 * Backtest Dashboard Module
 * 
 * Handles:
 * - Backtest job submission
 * - Job status polling
 * - Results display with charts
 * - Trade blotter
 */

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
