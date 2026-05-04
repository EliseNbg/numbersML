/**
 * StrategyInstance Management Dashboard Module
 *
 * Handles:
 * - StrategyInstance CRUD operations
 * - Hot-plug (start/stop/pause/resume)
 * - Real-time statistics polling
 * - Navigation to backtest
 */

// State
let instances = [];
let strategies = [];
let configSets = [];
let currentInstanceId = null;
let pollInterval = null;

// Bootstrap Modals
let instanceModal, statsModal;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initModals();
    bindEventListeners();
    loadStrategies();
    loadConfigSets();
    loadInstances();
});

/**
 * Initialize Bootstrap modals
 */
function initModals() {
    instanceModal = new bootstrap.Modal(document.getElementById('instanceModal'));
    statsModal = new bootstrap.Modal(document.getElementById('statsModal'));
}

/**
 * Bind all event listeners
 */
function bindEventListeners() {
    document.getElementById('btn-create').addEventListener('click', () => {
        loadStrategies();
        loadConfigSets();
        instanceModal.show();
    });

    document.getElementById('btn-refresh').addEventListener('click', loadInstances);
    document.getElementById('show-inactive').addEventListener('change', renderInstances);
    document.getElementById('btn-save').addEventListener('click', saveInstance);
}

/**
 * Load strategies for dropdown
 */
async function loadStrategies() {
    try {
        const response = await fetch(`${API_BASE_URL}/strategies?status=validated`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        strategies = await response.json();

        const select = document.getElementById('instance-strategy');
        select.innerHTML = '<option value="">Select a strategy...</option>';
        strategies.forEach(s => {
            const option = document.createElement('option');
            option.value = s.id;
            option.textContent = s.name;
            select.appendChild(option);
        });
    } catch (error) {
        showAlert('warning', `Failed to load strategies: ${error.message}`);
    }
}

/**
 * Load config sets for dropdown
 */
async function loadConfigSets() {
    try {
        const response = await fetch(`${API_BASE_URL}/config-sets?active_only=true`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        configSets = await response.json();

        const select = document.getElementById('instance-config-set');
        select.innerHTML = '<option value="">Select a config set...</option>';
        configSets.forEach(cs => {
            const option = document.createElement('option');
            option.value = cs.id;
            option.textContent = cs.name;
            select.appendChild(option);
        });
    } catch (error) {
        showAlert('warning', `Failed to load config sets: ${error.message}`);
    }
}

/**
 * Load all StrategyInstances from API
 */
async function loadInstances() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/strategy-instances`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        instances = await response.json();
        renderInstances();
        updateInstanceCount();

        // Start polling for running instances
        startPolling();
    } catch (error) {
        showAlert('danger', `Failed to load instances: ${error.message}`);
    }
}

/**
 * Render StrategyInstances table
 */
function renderInstances() {
    const tbody = document.getElementById('instances-tbody');
    const showInactive = document.getElementById('show-inactive').checked;

    let filtered = instances;
    if (!showInactive) {
        filtered = instances.filter(i => i.status === 'running' || i.status === 'paused');
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted py-4">
                    <i class="bi bi-inbox" style="font-size: 2rem;"></i>
                    <p class="mt-2">No instances found</p>
                    <button class="btn btn-sm btn-primary" onclick="document.getElementById('btn-create').click()">
                        <i class="bi bi-plus-lg"></i> Create your first instance
                    </button>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = filtered.map(instance => `
        <tr class="instance-row" data-id="${instance.id}">
            <td>
                <strong>${getStrategyName(instance.strategy_id)}</strong>
            </td>
            <td>${getConfigSetName(instance.config_set_id)}</td>
            <td>${renderStatusBadge(instance.status)}</td>
            <td>${formatPnl(instance.runtime_stats?.pnl || 0)}</td>
            <td>${instance.runtime_stats?.total_trades || 0}</td>
            <td>${formatUptime(instance.runtime_stats?.uptime_seconds || 0)}</td>
            <td>
                ${instance.status === 'stopped' ? `
                    <button class="btn btn-sm btn-success me-1" onclick="startInstance('${instance.id}')">
                        <i class="bi bi-play-fill"></i>
                    </button>
                ` : ''}
                ${instance.status === 'running' ? `
                    <button class="btn btn-sm btn-warning me-1" onclick="pauseInstance('${instance.id}')">
                        <i class="bi bi-pause-fill"></i>
                    </button>
                    <button class="btn btn-sm btn-danger me-1" onclick="stopInstance('${instance.id}')">
                        <i class="bi bi-stop-fill"></i>
                    </button>
                ` : ''}
                ${instance.status === 'paused' ? `
                    <button class="btn btn-sm btn-success me-1" onclick="resumeInstance('${instance.id}')">
                        <i class="bi bi-play-fill"></i>
                    </button>
                    <button class="btn btn-sm btn-danger me-1" onclick="stopInstance('${instance.id}')">
                        <i class="bi bi-stop-fill"></i>
                    </button>
                ` : ''}
                <button class="btn btn-sm btn-info me-1" onclick="viewStats('${instance.id}')">
                    <i class="bi bi-bar-chart"></i>
                </button>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="runBacktest('${instance.id}')">
                    <i class="bi bi-graph-up"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteInstance('${instance.id}')">
                    <i class="bi bi-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

/**
 * Get strategy name by ID
 */
function getStrategyName(strategyId) {
    const strategy = strategies.find(s => s.id === strategyId);
    return strategy ? escapeHtml(strategy.name) : '<span class="text-muted">Unknown</span>';
}

/**
 * Get config set name by ID
 */
function getConfigSetName(configSetId) {
    const cs = configSets.find(c => c.id === configSetId);
    return cs ? escapeHtml(cs.name) : '<span class="text-muted">Unknown</span>';
}

/**
 * Render status badge
 */
function renderStatusBadge(status) {
    const badges = {
        'stopped': '<span class="badge bg-secondary">Stopped</span>',
        'running': '<span class="badge bg-success">Running</span>',
        'paused': '<span class="badge bg-warning">Paused</span>',
        'error': '<span class="badge bg-danger">Error</span>',
    };
    return badges[status] || '<span class="badge bg-secondary">Unknown</span>';
}

/**
 * Format PnL with color
 */
function formatPnl(pnl) {
    if (pnl > 0) {
        return `<span class="text-success">+$${pnl.toFixed(2)}</span>`;
    } else if (pnl < 0) {
        return `<span class="text-danger">-$${Math.abs(pnl).toFixed(2)}</span>`;
    }
    return `<span>$${pnl.toFixed(2)}</span>`;
}

/**
 * Format uptime seconds to human-readable
 */
function formatUptime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

/**
 * Save Instance (create)
 */
async function saveInstance() {
    const strategyId = document.getElementById('instance-strategy').value;
    const configSetId = document.getElementById('instance-config-set').value;

    if (!strategyId || !configSetId) {
        showAlert('warning', 'Please select both strategy and config set');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/strategy-instances`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                strategy_id: strategyId,
                config_set_id: configSetId,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        instanceModal.hide();
        document.getElementById('instance-form').reset();
        showAlert('success', 'Algorithm Instance created successfully');
        loadInstances();
    } catch (error) {
        showAlert('danger', `Failed to create instance: ${error.message}`);
    }
}

/**
 * Start Instance (hot-plug)
 */
async function startInstance(instanceId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategy-instances/${instanceId}/start`, {
            method: 'POST',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        showAlert('success', 'Instance started (hot-plugged into pipeline)');
        loadInstances();
    } catch (error) {
        showAlert('danger', `Failed to start instance: ${error.message}`);
    }
}

/**
 * Stop Instance (unplug)
 */
async function stopInstance(instanceId) {
    if (!confirm('Are you sure you want to stop this instance?')) return;

    try {
        const response = await fetch(`${API_BASE_URL}/strategy-instances/${instanceId}/stop`, {
            method: 'POST',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        showAlert('success', 'Instance stopped (unplugged from pipeline)');
        loadInstances();
    } catch (error) {
        showAlert('danger', `Failed to stop instance: ${error.message}`);
    }
}

/**
 * Pause Instance
 */
async function pauseInstance(instanceId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategy-instances/${instanceId}/pause`, {
            method: 'POST',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        showAlert('success', 'Instance paused');
        loadInstances();
    } catch (error) {
        showAlert('danger', `Failed to pause instance: ${error.message}`);
    }
}

/**
 * Resume Instance
 */
async function resumeInstance(instanceId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategy-instances/${instanceId}/resume`, {
            method: 'POST',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        showAlert('success', 'Instance resumed');
        loadInstances();
    } catch (error) {
        showAlert('danger', `Failed to resume instance: ${error.message}`);
    }
}

/**
 * View Statistics
 */
function viewStats(instanceId) {
    const instance = instances.find(i => i.id === instanceId);
    if (!instance) return;

    const stats = instance.runtime_stats || {};

    document.getElementById('stat-pnl').textContent = `$${stats.pnl?.toFixed(2) || '0.00'}`;
    document.getElementById('stat-pnl').className = stats.pnl > 0 ? 'text-success' : stats.pnl < 0 ? 'text-danger' : '';

    document.getElementById('stat-trades').textContent = stats.total_trades || 0;
    document.getElementById('stat-win-rate').textContent = `${(stats.win_rate || 0).toFixed(1)}%`;
    document.getElementById('stat-uptime').textContent = formatUptime(stats.uptime_seconds || 0);
    document.getElementById('stat-error').textContent = stats.last_error || 'None';

    statsModal.show();
}

/**
 * Run Backtest for this instance
 */
function runBacktest(instanceId) {
    window.location.href = `backtest_ml.html?instance_id=${instanceId}`;
}

/**
 * Delete Instance
 */
async function deleteInstance(instanceId) {
    if (!confirm('Are you sure you want to delete this instance?')) return;

    try {
        const response = await fetch(`${API_BASE_URL}/strategy-instances/${instanceId}`, {
            method: 'DELETE',
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        showAlert('success', 'Instance deleted');
        loadInstances();
    } catch (error) {
        showAlert('danger', `Failed to delete: ${error.message}`);
    }
}

/**
 * Start polling for running instances
 */
function startPolling() {
    if (pollInterval) clearInterval(pollInterval);

    // Poll every 5 seconds if there are running instances
    const runningCount = instances.filter(i => i.status === 'running').length;
    if (runningCount > 0) {
        pollInterval = setInterval(loadInstances, 5000);
    }
}

/**
 * Update instance count badge
 */
function updateInstanceCount() {
    const runningCount = instances.filter(i => i.status === 'running').length;
    const totalCount = instances.length;
    document.getElementById('instance-count').textContent = `${runningCount} running / ${totalCount} total`;
}

/**
 * Show loading state
 */
function showLoading() {
    document.getElementById('instances-tbody').innerHTML = `
        <tr>
            <td colspan="7" class="text-center text-muted py-4">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-2">Loading instances...</p>
            </td>
        </tr>
    `;
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

/**
 * Escape HTML entities
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
