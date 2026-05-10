/**
 * Strategy Backtest Dashboard Module
 *
 * Handles:
 * - Backtest job submission and polling
 * - Results display with metrics, charts, trades, debug logs
 * - Backtest history management
 * - Chart rendering for price series with buy/sell markers
 */

// API Configuration
const API_BASE = '/api';
const POLL_INTERVAL = 1000; // 1 second

// State
let currentJobId = null;
let pollTimer = null;
let isLogPaused = false;
let priceChart = null;
let equityChart = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Strategy backtest module initialized');
    
    // Set default date range (last 7 days)
    setDefaultDateRange();
    
    // Load strategies
    await loadStrategies();
    
    // Load symbols
    await loadSymbols();
    
    // Load backtest history
    await loadBacktestHistory();
    
    // Bind event listeners
    bindEventListeners();
    
    // Handle strategy_id parameter in URL
    const urlParams = new URLSearchParams(window.location.search);
    const strategyId = urlParams.get('strategy_id');
    if (strategyId) {
        const strategySelect = document.getElementById('strategy-select');
        strategySelect.value = strategyId;
        // Trigger change event to load versions
        strategySelect.dispatchEvent(new Event('change'));
    }
});

/**
 * Set default date range (last 7 days)
 */
function setDefaultDateRange() {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 7);
    
    document.getElementById('end-time').value = formatDateTimeLocal(end);
    document.getElementById('start-time').value = formatDateTimeLocal(start);
}

/**
 * Format date for datetime-local input
 */
function formatDateTimeLocal(date) {
    const pad = (n) => n.toString().padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * Bind all event listeners
 */
function bindEventListeners() {
    // Form submission
    document.getElementById('backtest-config-form').addEventListener('submit', (e) => {
        e.preventDefault();
        runBacktest();
    });
    
    // Strategy selection change - load versions
    document.getElementById('strategy-select').addEventListener('change', onStrategyChange);
    
    // Log controls
    document.getElementById('btn-pause-log').addEventListener('click', toggleLogPause);
    document.getElementById('btn-clear-log').addEventListener('click', clearLog);
    
    // History refresh
    document.getElementById('btn-refresh-history').addEventListener('click', loadBacktestHistory);
    
    // CLI command button
    document.getElementById('btn-show-cli-command').addEventListener('click', toggleCliCommand);
    document.getElementById('btn-copy-cli-command').addEventListener('click', copyCliCommand);
}

/**
 * Load all strategies for dropdown
 */
async function loadStrategies() {
    try {
        const response = await fetch(`${API_BASE}/strategies`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const strategies = await response.json();
        const select = document.getElementById('strategy-select');
        
        // Keep first option, remove others
        while (select.options.length > 1) {
            select.remove(1);
        }
        
        strategies.forEach(strategy => {
            const option = document.createElement('option');
            option.value = strategy.id;
            option.textContent = `${strategy.name} (${strategy.strategy_type || 'unknown'})`;
            option.dataset.strategy = JSON.stringify(strategy);
            select.appendChild(option);
        });
        
        console.log(`Loaded ${strategies.length} strategies`);
        
    } catch (error) {
        console.error('Failed to load strategies:', error);
        showToast('Failed to load strategies', 'error');
    }
}

/**
 * Load symbols for dropdown
 */
async function loadSymbols() {
    try {
        const response = await fetch(`${API_BASE}/symbols`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const symbols = await response.json();
        const allowedSymbols = symbols.filter(s => s.is_allowed && s.is_active);
        
        const select = document.getElementById('symbol-select');
        select.innerHTML = '<option value="">Select...</option>' +
            allowedSymbols.map(s => `<option value="${s.symbol}">${s.symbol}</option>`).join('');
        
        console.log(`Loaded ${allowedSymbols.length} allowed and active symbols`);
        
    } catch (error) {
        console.error('Failed to load symbols:', error);
        showToast('Failed to load symbols', 'error');
    }
}

/**
 * Handle strategy selection change
 */
async function onStrategyChange() {
    const strategyId = document.getElementById('strategy-select').value;
    const versionSelect = document.getElementById('version-select');
    
    // Reset version dropdown
    versionSelect.innerHTML = '<option value="">Active (default)</option>';
    
    if (!strategyId) return;
    
    try {
        const response = await fetch(`${API_BASE}/strategies/${strategyId}/versions`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const versions = await response.json();
        
        versions.forEach(version => {
            const option = document.createElement('option');
            option.value = version.version;
            option.textContent = `Version ${version.version}${version.is_active ? ' (active)' : ''}`;
            versionSelect.appendChild(option);
        });
        
    } catch (error) {
        console.error('Failed to load versions:', error);
    }
}

/**
 * Run backtest job
 */
async function runBacktest() {
    const strategyId = document.getElementById('strategy-select').value;
    const version = document.getElementById('version-select').value;
    const symbol = document.getElementById('symbol-select').value;
    const initialBalance = parseFloat(document.getElementById('initial-balance').value);
    const startTime = new Date(document.getElementById('start-time').value);
    const endTime = new Date(document.getElementById('end-time').value);
    const includeEquityCurve = document.getElementById('include-equity-curve').checked;
    const includeTrades = document.getElementById('include-trades').checked;
    
    // Validation
    if (!strategyId || !symbol || !startTime || !endTime) {
        showToast('Please fill in all required fields', 'error');
        return;
    }
    
    if (endTime <= startTime) {
        showToast('End time must be after start time', 'error');
        return;
    }
    
    // Disable submit button
    const submitBtn = document.getElementById('btn-run-backtest');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Submitting...';
    
    try {
        const response = await fetch(`${API_BASE}/strategy-backtests/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                strategy_id: strategyId,
                strategy_version: version ? parseInt(version) : null,
                time_range_start: startTime.toISOString(),
                time_range_end: endTime.toISOString(),
                initial_balance: initialBalance,
                symbol: symbol,
                include_equity_curve: includeEquityCurve,
                include_trades: includeTrades,
            }),
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        currentJobId = result.job_id;
        
        // Show job status panel
        document.getElementById('job-status-panel').style.display = 'block';
        document.getElementById('results-panel').style.display = 'none';
        document.getElementById('job-id-display').textContent = `Job ID: ${currentJobId}`;
        updateJobStatus('pending', 0);
        
        // Start polling
        startPolling();
        
        showToast(`Backtest job ${currentJobId} submitted`, 'success');
        
    } catch (error) {
        console.error('Failed to submit backtest:', error);
        showToast(`Failed to submit: ${error.message}`, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="bi bi-play-fill"></i> Run Backtest';
    }
}

/**
 * Start polling for job status
 */
function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollJobStatus, POLL_INTERVAL);
}

/**
 * Stop polling
 */
function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

/**
 * Poll job status
 */
async function pollJobStatus() {
    if (!currentJobId) return;
    
    try {
        const response = await fetch(`${API_BASE}/strategy-backtests/jobs/${currentJobId}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const job = await response.json();
        
        updateJobStatus(job.status, job.progress || 0, job.error);
        
        if (job.status === 'completed') {
            stopPolling();
            displayResults(job);
            loadBacktestHistory(); // Refresh history
        } else if (job.status === 'failed') {
            stopPolling();
            showToast(`Backtest failed: ${job.error}`, 'error');
        }
        
    } catch (error) {
        console.error('Failed to poll job status:', error);
    }
}

/**
 * Update job status UI
 */
function updateJobStatus(status, progress, error = null) {
    const badge = document.getElementById('job-status-badge');
    const progressBar = document.getElementById('job-progress-bar');
    const progressText = document.getElementById('job-progress-text');
    const errorDiv = document.getElementById('job-error-message');
    
    // Update badge
    badge.className = `badge bg-${getStatusColor(status)} job-status-${status}`;
    badge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    
    // Update progress
    const pct = Math.round(progress * 100);
    progressBar.style.width = `${pct}%`;
    progressBar.setAttribute('aria-valuenow', pct);
    progressText.textContent = `${pct}%`;
    
    // Show/hide error
    if (error) {
        errorDiv.textContent = error;
        errorDiv.style.display = 'block';
    } else {
        errorDiv.style.display = 'none';
    }
}

/**
 * Get bootstrap color for status
 */
function getStatusColor(status) {
    switch (status) {
        case 'pending': return 'secondary';
        case 'running': return 'primary';
        case 'completed': return 'success';
        case 'failed': return 'danger';
        default: return 'secondary';
    }
}

/**
 * Display backtest results
 */
function displayResults(result) {
    document.getElementById('results-panel').style.display = 'block';
    
    // Update metrics
    updateMetrics(result.metrics);
    
    // Render charts
    renderPriceChart(result.price_series, result.trades);
    renderEquityChart(result.equity_curve);
    
    // Render trades
    renderTrades(result.trades);
    
    // Render debug log
    renderDebugLog(result.debug_messages);
    
    // Render detailed metrics
    renderDetailedMetrics(result.metrics, result.parameters);
}

/**
 * Update main metric cards
 */
function updateMetrics(metrics) {
    if (!metrics) return;
    
    const returnEl = document.getElementById('metric-return');
    const returnPct = metrics.total_return_pct || 0;
    returnEl.textContent = `${returnPct >= 0 ? '+' : ''}${returnPct.toFixed(2)}%`;
    returnEl.className = `metric-value ${returnPct >= 0 ? 'positive' : 'negative'}`;
    
    const ddEl = document.getElementById('metric-drawdown');
    const dd = metrics.max_drawdown_pct || 0;
    ddEl.textContent = `${dd.toFixed(2)}%`;
    ddEl.className = 'metric-value negative';
    
    document.getElementById('metric-sharpe').textContent = (metrics.sharpe_ratio || 0).toFixed(2);
    document.getElementById('metric-winrate').textContent = `${((metrics.win_rate || 0) * 100).toFixed(1)}%`;
    document.getElementById('metric-trades').textContent = metrics.total_trades || 0;
    document.getElementById('metric-profit-factor').textContent = (metrics.profit_factor || 0).toFixed(2);
}

/**
 * Render price chart with trade markers
 */
function renderPriceChart(priceSeries, trades) {
    const ctx = document.getElementById('price-chart').getContext('2d');
    
    if (priceChart) {
        priceChart.destroy();
    }
    
    if (!priceSeries || priceSeries.length === 0) {
        console.warn('No price series data');
        return;
    }
    
    // Prepare datasets
    const labels = priceSeries.map(p => new Date(p.timestamp).toLocaleDateString());
    const prices = priceSeries.map(p => p.close);
    
    // Create buy/sell markers from trades
    const buyPoints = [];
    const sellPoints = [];
    
    if (trades) {
        trades.forEach(trade => {
            const entryIdx = priceSeries.findIndex(p => 
                Math.abs(new Date(p.timestamp) - new Date(trade.entry_time)) < 60000
            );
            if (entryIdx >= 0) {
                buyPoints.push({ x: entryIdx, y: trade.entry_price });
            }
            
            if (trade.exit_time) {
                const exitIdx = priceSeries.findIndex(p => 
                    Math.abs(new Date(p.timestamp) - new Date(trade.exit_time)) < 60000
                );
                if (exitIdx >= 0) {
                    sellPoints.push({ x: exitIdx, y: trade.exit_price });
                }
            }
        });
    }
    
    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Close Price',
                    data: prices,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                },
                {
                    label: 'Buy',
                    data: buyPoints.map(p => ({ x: p.x, y: p.y })),
                    backgroundColor: 'green',
                    pointStyle: 'triangle',
                    pointRadius: 8,
                    pointHoverRadius: 10,
                    showLine: false,
                },
                {
                    label: 'Sell',
                    data: sellPoints.map(p => ({ x: p.x, y: p.y })),
                    backgroundColor: 'red',
                    pointStyle: 'triangle',
                    pointRadius: 8,
                    pointHoverRadius: 10,
                    rotation: 180,
                    showLine: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            plugins: {
                title: {
                    display: false,
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y?.toFixed(4) || '-'}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        maxTicksLimit: 10,
                    },
                },
                y: {
                    title: {
                        display: true,
                        text: 'Price',
                    },
                },
            },
        },
    });
}

/**
 * Render equity curve chart
 */
function renderEquityChart(equityCurve) {
    const ctx = document.getElementById('equity-chart').getContext('2d');
    
    if (equityChart) {
        equityChart.destroy();
    }
    
    if (!equityCurve || equityCurve.length === 0) {
        console.warn('No equity curve data');
        return;
    }
    
    const labels = equityCurve.map(p => new Date(p.timestamp).toLocaleDateString());
    const equity = equityCurve.map(p => p.equity);
    
    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Equity',
                data: equity,
                borderColor: 'rgb(54, 162, 235)',
                backgroundColor: (context) => {
                    const ctx = context.chart.ctx;
                    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
                    gradient.addColorStop(0, 'rgba(54, 162, 235, 0.3)');
                    gradient.addColorStop(1, 'rgba(54, 162, 235, 0.0)');
                    return gradient;
                },
                fill: true,
                tension: 0.1,
                pointRadius: 0,
                pointHoverRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: false,
                },
                legend: {
                    display: false,
                },
            },
            scales: {
                x: {
                    ticks: {
                        maxTicksLimit: 6,
                    },
                },
                y: {
                    title: {
                        display: true,
                        text: 'Equity ($)',
                    },
                },
            },
        },
    });
}

/**
 * Render trades table
 */
function renderTrades(trades) {
    const tbody = document.getElementById('trades-tbody');
    const countBadge = document.getElementById('trade-count');
    
    tbody.innerHTML = '';
    
    if (!trades || trades.length === 0) {
        countBadge.textContent = '0 trades';
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No trades</td></tr>';
        return;
    }
    
    countBadge.textContent = `${trades.length} trades`;
    
    trades.forEach(trade => {
        const row = document.createElement('tr');
        row.className = trade.pnl >= 0 ? 'trade-row-buy' : 'trade-row-sell';
        
        const pnlClass = trade.pnl >= 0 ? 'positive' : 'negative';
        const pnlSign = trade.pnl >= 0 ? '+' : '';
        
        row.innerHTML = `
            <td>${formatDateShort(trade.entry_time)}</td>
            <td>${trade.exit_time ? formatDateShort(trade.exit_time) : '-'}</td>
            <td>${trade.symbol}</td>
            <td>${trade.entry_price?.toFixed(4) || '-'}</td>
            <td>${trade.exit_price?.toFixed(4) || '-'}</td>
            <td class="${pnlClass}">${pnlSign}$${trade.pnl?.toFixed(2) || '0.00'}</td>
            <td><span class="badge bg-secondary">${trade.exit_reason || 'unknown'}</span></td>
        `;
        
        tbody.appendChild(row);
    });
}

/**
 * Render debug log
 */
function renderDebugLog(messages) {
    const container = document.getElementById('debug-log-container');
    
    if (!messages || messages.length === 0) {
        container.innerHTML = '<div class="text-muted">No debug messages</div>';
        return;
    }
    
    container.innerHTML = messages.map(msg => `
        <div class="mb-1">
            <span class="timestamp">${formatTime(msg.timestamp)}</span>
            <span class="level-${msg.level?.toLowerCase() || 'info'}">[${msg.level || 'INFO'}]</span>
            <span>${escapeHtml(msg.message)}</span>
        </div>
    `).join('');
    
    if (!isLogPaused) {
        container.scrollTop = container.scrollHeight;
    }
}

/**
 * Render detailed metrics
 */
function renderDetailedMetrics(metrics, parameters) {
    const container = document.getElementById('detailed-metrics-container');
    
    if (!metrics) {
        container.innerHTML = '<div class="col-12 text-muted">No metrics available</div>';
        return;
    }
    
    const metricItems = [
        { label: 'Annualized Return', value: `${(metrics.annualized_return || 0).toFixed(2)}%` },
        { label: 'CAGR', value: `${(metrics.cagr || 0).toFixed(2)}%` },
        { label: 'Volatility (Ann.)', value: `${(metrics.volatility_annualized || 0).toFixed(2)}%` },
        { label: 'Sortino Ratio', value: (metrics.sortino_ratio || 0).toFixed(2) },
        { label: 'Calmar Ratio', value: (metrics.calmar_ratio || 0).toFixed(2) },
        { label: 'Expectancy', value: `$${(metrics.expectancy || 0).toFixed(2)}` },
        { label: 'Avg Trade', value: `$${(metrics.avg_trade || 0).toFixed(2)}` },
        { label: 'Avg Win', value: `$${(metrics.avg_win || 0).toFixed(2)}` },
        { label: 'Avg Loss', value: `$${(metrics.avg_loss || 0).toFixed(2)}` },
        { label: 'Largest Win', value: `$${(metrics.largest_win || 0).toFixed(2)}` },
        { label: 'Largest Loss', value: `$${(metrics.largest_loss || 0).toFixed(2)}` },
        { label: 'Total Fees', value: `$${(metrics.total_fees || 0).toFixed(2)}` },
        { label: 'Winning Trades', value: metrics.winning_trades || 0 },
        { label: 'Losing Trades', value: metrics.losing_trades || 0 },
        { label: 'Max Consecutive Wins', value: metrics.max_consecutive_wins || 0 },
        { label: 'Max Consecutive Losses', value: metrics.max_consecutive_losses || 0 },
    ];
    
    // Add parameters if available
    if (parameters) {
        Object.entries(parameters).forEach(([key, value]) => {
            if (typeof value !== 'object') {
                metricItems.push({ label: `Param: ${key}`, value: String(value) });
            }
        });
    }
    
    container.innerHTML = metricItems.map(item => `
        <div class="col-md-3 mb-2">
            <small class="text-muted">${item.label}</small>
            <div class="fw-bold">${item.value}</div>
        </div>
    `).join('');
}

/**
 * Load backtest history
 */
async function loadBacktestHistory() {
    try {
        const response = await fetch(`${API_BASE}/strategy-backtests/results?limit=20`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const results = await response.json();
        const tbody = document.getElementById('backtest-history-tbody');
        
        if (!results || results.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No backtests found</td></tr>';
            return;
        }
        
        tbody.innerHTML = results.map(result => {
            const returnPct = result.metrics?.total_return_pct || 0;
            const returnClass = returnPct >= 0 ? 'positive' : 'negative';
            const returnSign = returnPct >= 0 ? '+' : '';
            
            return `
                <tr data-backtest-id="${result.id}">
                    <td>${formatDateShort(result.created_at)}</td>
                    <td>${result.strategy_name || 'Unknown'}</td>
                    <td>${result.strategy_version || '-'}</td>
                    <td>${result.symbol || '-'}</td>
                    <td>${formatDateShort(result.time_range_start)} - ${formatDateShort(result.time_range_end)}</td>
                    <td class="${returnClass}">${returnSign}${returnPct.toFixed(2)}%</td>
                    <td>${result.metrics?.total_trades || 0}</td>
                    <td><span class="badge bg-success">Saved</span></td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Failed to load backtest history:', error);
        document.getElementById('backtest-history-tbody').innerHTML = 
            '<tr><td colspan="8" class="text-center text-danger">Failed to load history</td></tr>';
    }
}

/**
 * Toggle log pause
 */
function toggleLogPause() {
    isLogPaused = !isLogPaused;
    const btn = document.getElementById('btn-pause-log');
    btn.innerHTML = isLogPaused ? '<i class="bi bi-play"></i>' : '<i class="bi bi-pause"></i>';
    btn.classList.toggle('btn-warning', isLogPaused);
}

/**
 * Clear debug log
 */
function clearLog() {
    document.getElementById('debug-log-container').innerHTML = '';
}

/**
 * Format date for display (short)
 */
function formatDateShort(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', { 
        month: 'short', 
        day: 'numeric', 
        hour: '2-digit', 
        minute: '2-digit' 
    });
}

/**
 * Format time only
 */
function formatTime(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', { hour12: false });
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Toggle CLI command visibility
 */
function toggleCliCommand() {
    const container = document.getElementById('cli-command-container');
    const isHidden = container.style.display === 'none' || container.style.display === '';
    container.style.display = isHidden ? 'block' : 'none';
    
    // If showing, generate the command
    if (isHidden) {
        generateCliCommand();
    }
}

/**
 * Generate CLI command based on current form values
 */
function generateCliCommand() {
    const strategyId = document.getElementById('strategy-select').value;
    const version = document.getElementById('version-select').value;
    const symbol = document.getElementById('symbol-select').value;
    const initialBalance = document.getElementById('initial-balance').value;
    const startTime = document.getElementById('start-time').value;
    const endTime = document.getElementById('end-time').value;
    const includeEquityCurve = document.getElementById('include-equity-curve').checked;
    const includeTrades = document.getElementById('include-trades').checked;
    
    if (!strategyId) {
        document.getElementById('cli-command').value = '# Please select a strategy first';
        return;
    }
    
    let cmd = 'python -m src.cli.run_backtest --strategy-id ' + strategyId;
    
    if (version) {
        cmd += ' --version ' + version;
    }
    
    if (symbol) {
        cmd += ' --symbol "' + symbol + '"';
    }
    
    if (initialBalance && initialBalance !== '10000') {
        cmd += ' --initial-balance ' + initialBalance;
    }
    
    if (startTime) {
        cmd += ' --start-time "' + startTime + '"';
    }
    
    if (endTime) {
        cmd += ' --end-time "' + endTime + '"';
    }
    
    if (!includeEquityCurve) {
        cmd += ' --no-equity-curve';
    }
    
    if (!includeTrades) {
        cmd += ' --no-trades';
    }
    
    document.getElementById('cli-command').value = cmd;
}

/**
 * Copy CLI command to clipboard
 */
function copyCliCommand() {
    const cmdInput = document.getElementById('cli-command');
    cmdInput.select();
    document.execCommand('copy');
    
    // Show tooltip
    const btn = document.getElementById('btn-copy-cli-command');
    const originalTitle = btn.title;
    btn.title = 'Copied!';
    
    setTimeout(() => {
        btn.title = originalTitle;
    }, 2000);
    
    showToast('Command copied to clipboard', 'success');
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'primary'}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    // Add to container (create if needed)
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }
    
    container.appendChild(toast);
    
    // Show and auto-remove
    const bsToast = new bootstrap.Toast(toast, { delay: 5000 });
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}
