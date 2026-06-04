/**
 * Dashboard JavaScript
 * 
 * Handles:
 * - Collector status monitoring
 * - SLA metrics chart
 * - Quick stats display
 * - Auto-refresh every 5 seconds
 */

// API Base URL
const API_BASE = '/api';

// Chart instance
let slaChart = null;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard initialized');
    
    // Load initial data
    loadCollectorStatus();
    loadQuickStats();
    loadSLAMetrics();
    loadPositions();
    loadRecentOrders();
    
    // Auto-refresh every 5 seconds
    setInterval(() => {
        loadCollectorStatus();
        loadQuickStats();
        loadSLAMetrics();
        loadPositions();
        loadRecentOrders();
    }, 5000);
    
    // Setup button handlers
    setupButtonHandlers();
});

/**
 * Setup button event handlers
 */
function setupButtonHandlers() {
    document.getElementById('btn-start-collector')?.addEventListener('click', startCollector);
    document.getElementById('btn-stop-collector')?.addEventListener('click', stopCollector);
}

/**
 * Load pipeline status (replaces old collector status)
 */
async function loadCollectorStatus() {
    try {
        const response = await fetch(`${API_BASE}/pipeline/status`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const status = await response.json();
        renderCollectorStatus(status);

    } catch (error) {
        console.error('Failed to load pipeline status:', error);
        document.getElementById('collector-status').innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i>
                Failed to load status: ${error.message}
            </div>
        `;
    }
}

/**
 * Render pipeline status
 */
function renderCollectorStatus(status) {
    const container = document.getElementById('collector-status');
    const startBtn = document.getElementById('btn-start-collector');
    const stopBtn = document.getElementById('btn-stop-collector');

    if (status.is_running) {
        container.innerHTML = `
            <div class="row align-items-center">
                <div class="col-md-12">
                    <p><strong>Status:</strong> <span class="status-running">
                        <i class="bi bi-check-circle-fill"></i> Running
                    </span></p>
                    <p><strong>Symbols:</strong> ${(status.symbols || []).length} active</p>
                    <p><strong>Trades Processed:</strong> ${status.trades_processed?.toLocaleString() || 0}</p>
                    <p><strong>Candles Written:</strong> ${status.candles_written?.toLocaleString() || 0}</p>
                    <p><strong>Uptime:</strong> ${formatUptime(status.uptime_seconds)}</p>
                </div>
            </div>
        `;

        startBtn.disabled = true;
        stopBtn.disabled = false;

    } else {
        container.innerHTML = `
            <div class="text-center">
                <p class="status-stopped">
                    <i class="bi bi-x-circle-fill"></i> Stopped
                </p>
                <p class="text-muted">Collector is not running</p>
            </div>
        `;
        
        startBtn.disabled = false;
        stopBtn.disabled = true;
    }
}

/**
 * Load quick statistics
 */
async function loadQuickStats() {
    try {
        const response = await fetch(`${API_BASE}/dashboard/stats`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const stats = await response.json();
        renderQuickStats(stats);
        
    } catch (error) {
        console.error('Failed to load quick stats:', error);
    }
}

/**
 * Render quick statistics
 */
function renderQuickStats(stats) {
    const container = document.getElementById('quick-stats');
    
    container.innerHTML = `
        <div class="row">
            <div class="col-6">
                <p class="mb-1"><small class="text-muted">Ticks/Min</small></p>
                <h4>${stats.ticks_per_minute?.toLocaleString() || 0}</h4>
            </div>
            <div class="col-6">
                <p class="mb-1"><small class="text-muted">Avg Time</small></p>
                <h4>${stats.avg_processing_time_ms?.toFixed(1) || 0} ms</h4>
            </div>
            <div class="col-6">
                <p class="mb-1"><small class="text-muted">SLA Compliance</small></p>
                <h4 class="${getComplianceColor(stats.sla_compliance_pct)}">
                    ${stats.sla_compliance_pct?.toFixed(1) || 100}%
                </h4>
            </div>
            <div class="col-6">
                <p class="mb-1"><small class="text-muted">Active Symbols</small></p>
                <h4>${stats.active_symbols_count || 0}</h4>
            </div>
        </div>
    `;
    
    // Update metric cards
    document.getElementById('avg-response-time').textContent = 
        `${(stats.avg_processing_time_ms || 0).toFixed(1)} ms`;
    
    document.getElementById('sla-violations').textContent = 
        stats.sla_compliance_pct < 100 ? '⚠️' : '✅';
}

/**
 * Load SLA metrics
 */
async function loadSLAMetrics() {
    try {
        const response = await fetch(`${API_BASE}/dashboard/metrics?seconds=60`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const metrics = await response.json();
        renderSLAChart(metrics);
        updateSLABadge(metrics);
        updatePerformanceMetrics(metrics);
        
    } catch (error) {
        console.error('Failed to load SLA metrics:', error);
    }
}

/**
 * Render SLA chart
 */
function renderSLAChart(metrics) {
    const ctx = document.getElementById('sla-chart').getContext('2d');
    
    // Prepare data
    const labels = metrics.map(m => {
        const date = new Date(m.timestamp);
        return date.getSeconds().toString().padStart(2, '0');
    });
    
    const avgTimes = metrics.map(m => m.avg_time_ms);
    const maxTimes = metrics.map(m => m.max_time_ms);
    
    // Destroy existing chart
    if (slaChart) {
        slaChart.destroy();
    }
    
    // Create new chart
    slaChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Avg Time (ms)',
                    data: avgTimes,
                    borderColor: '#0d6efd',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    tension: 0.4,
                    fill: true,
                },
                {
                    label: 'Max Time (ms)',
                    data: maxTimes,
                    borderColor: '#dc3545',
                    borderDash: [5, 5],
                    tension: 0.4,
                    fill: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                },
                annotation: {
                    annotations: {
                        line1: {
                            type: 'line',
                            yMin: 1000,
                            yMax: 1000,
                            borderColor: '#dc3545',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            label: {
                                content: 'SLA Target (1000ms)',
                                enabled: true,
                            },
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Time (ms)',
                    },
                },
                x: {
                    title: {
                        display: true,
                        text: 'Seconds ago',
                    },
                },
            },
        },
    });
}

/**
 * Update SLA compliance badge
 */
function updateSLABadge(metrics) {
    const totalViolations = metrics.reduce((sum, m) => sum + (m.sla_violations || 0), 0);
    const totalTicks = metrics.reduce((sum, m) => sum + (m.ticks_processed || 0), 0);
    
    const compliance = totalTicks > 0 
        ? ((totalTicks - totalViolations) / totalTicks * 100)
        : 100;
    
    const badge = document.getElementById('sla-compliance-badge');
    badge.textContent = `${compliance.toFixed(1)}%`;
    
    if (compliance >= 99) {
        badge.className = 'badge bg-success';
    } else if (compliance >= 95) {
        badge.className = 'badge bg-warning';
    } else {
        badge.className = 'badge bg-danger';
    }
}

/**
 * Update performance metrics
 */
function updatePerformanceMetrics(metrics) {
    const totalViolations = metrics.reduce((sum, m) => sum + (m.sla_violations || 0), 0);
    const maxTime = Math.max(...metrics.map(m => m.max_time_ms || 0));
    
    document.getElementById('max-response-time').textContent = `${maxTime.toFixed(1)} ms`;
    document.getElementById('sla-violations').textContent = totalViolations;
}

/**
 * Start pipeline (replaces old collector)
 */
async function startCollector() {
    try {
        const response = await fetch(`${API_BASE}/pipeline/start`, {
            method: 'POST',
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || `HTTP ${response.status}`);
        }

        const result = await response.json();
        alert(`Pipeline started: ${result.message}`);

        // Reload status
        loadCollectorStatus();

    } catch (error) {
        alert(`Failed to start pipeline: ${error.message}`);
    }
}

/**
 * Stop pipeline (replaces old collector)
 */
async function stopCollector() {
    if (!confirm('Are you sure you want to stop the pipeline?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/pipeline/stop`, {
            method: 'POST',
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || `HTTP ${response.status}`);
        }

        const result = await response.json();
        alert(`Pipeline stopped: ${result.message}`);

        // Reload status
        loadCollectorStatus();

    } catch (error) {
        alert(`Failed to stop pipeline: ${error.message}`);
    }
}

/**
 * Format uptime seconds to human readable
 */
function formatUptime(seconds) {
    if (!seconds) return 'N/A';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

/**
 * Format datetime
 */
function formatDateTime(isoString) {
    if (!isoString) return 'N/A';
    
    const date = new Date(isoString);
    return date.toLocaleString();
}

/**
 * Get compliance color class
 */
function getComplianceColor(compliance) {
    if (compliance >= 99) return 'text-success';
    if (compliance >= 95) return 'text-warning';
    return 'text-danger';
}

/**
 * Load open positions with unrealized P&L
 */
async function loadPositions() {
    try {
        const response = await fetch(`${API_BASE}/market/positions`);
        if (!response.ok) {
            document.getElementById('positions-body').innerHTML =
                `<tr><td colspan="4" class="text-center text-muted">API unavailable</td></tr>`;
            return;
        }
        const positions = await response.json();
        renderPositions(positions);
    } catch (error) {
        console.error('Failed to load positions:', error);
        document.getElementById('positions-body').innerHTML =
            `<tr><td colspan="4" class="text-center text-muted">Failed to load</td></tr>`;
    }
}

/**
 * Render open positions
 */
function renderPositions(positions) {
    const tbody = document.getElementById('positions-body');

    if (!positions || positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No open positions</td></tr>`;
        document.getElementById('total-pnl').textContent = '$0.00';
        return;
    }

    let totalPnL = 0;
    tbody.innerHTML = positions.map(p => {
        const pnl = parseFloat(p.unrealized_pnl) || 0;
        totalPnL += pnl;
        const pnlClass = pnl >= 0 ? 'text-success' : 'text-danger';
        const pnlIcon = pnl >= 0 ? 'bi-arrow-up-short' : 'bi-arrow-down-short';
        return `
            <tr>
                <td>${escapeHtml(p.symbol)}</td>
                <td><span class="badge bg-${p.side === 'LONG' ? 'success' : 'danger'}">${escapeHtml(p.side)}</span></td>
                <td>${formatNumber(p.quantity)}</td>
                <td class="${pnlClass}"><i class="bi ${pnlIcon}"></i> $${formatNumber(Math.abs(pnl))}</td>
            </tr>
        `;
    }).join('');

    const totalClass = totalPnL >= 0 ? 'text-success' : 'text-danger';
    document.getElementById('total-pnl').innerHTML =
        `<span class="${totalClass}">${totalPnL >= 0 ? '+' : '-'}$${formatNumber(Math.abs(totalPnL))}</span>`;
}

/**
 * Load recent orders
 */
async function loadRecentOrders() {
    try {
        const response = await fetch(`${API_BASE}/orders/dashboard`);
        if (!response.ok) {
            document.getElementById('orders-body').innerHTML =
                `<tr><td colspan="4" class="text-center text-muted">API unavailable</td></tr>`;
            return;
        }
        const data = await response.json();
        renderRecentOrders(data.orders || []);
        renderOrderStats(data.stats || {});
    } catch (error) {
        console.error('Failed to load orders:', error);
        document.getElementById('orders-body').innerHTML =
            `<tr><td colspan="4" class="text-center text-muted">Failed to load</td></tr>`;
    }
}

/**
 * Render recent orders table
 */
function renderRecentOrders(orders) {
    const tbody = document.getElementById('orders-body');

    if (orders.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No orders yet</td></tr>`;
        return;
    }

    // Show latest 5 orders
    tbody.innerHTML = orders.slice(0, 5).map(o => {
        const statusColors = {
            FILLED: 'success', REJECTED: 'danger', CANCELED: 'warning',
            PENDING: 'info', PARTIALLY_FILLED: 'primary', NEW: 'info',
        };
        const statusColor = statusColors[o.status] || 'secondary';
        return `
            <tr>
                <td>${escapeHtml(o.symbol)}</td>
                <td><span class="badge bg-${o.side === 'BUY' ? 'success' : 'danger'}">${escapeHtml(o.side)}</span></td>
                <td>${formatNumber(o.quantity)}</td>
                <td><span class="badge bg-${statusColor}">${escapeHtml(o.status)}</span></td>
            </tr>
        `;
    }).join('');
}

/**
 * Render order stats footer
 */
function renderOrderStats(stats) {
    document.getElementById('orders-filled').textContent = `${stats.filled || 0} filled`;
    document.getElementById('orders-rejected').textContent = `${stats.rejected || 0} rejected`;
    document.getElementById('orders-cancelled').textContent = `${stats.cancelled || 0} cancelled`;
}

/**
 * Format number with commas and decimals
 */
function formatNumber(value, decimals = 4) {
    if (value === null || value === undefined) return '-';
    const num = parseFloat(value);
    if (isNaN(num)) return '-';
    return num.toLocaleString('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: decimals,
    });
}

/**
 * Escape HTML entities
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
