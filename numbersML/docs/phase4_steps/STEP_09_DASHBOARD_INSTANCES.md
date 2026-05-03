# Step 9: Dashboard - StrategyInstance Management#

## Objective#
Create dashboard page for managing StrategyInstances (linking Algorithm + ConfigurationSet) with hot-plug controls.

## Context#
- Step 4-5 complete: StrategyInstance entity, repository, and API exist
- Step 8 complete: ConfigurationSet dashboard page exists
- Need to show StrategyInstances with status, runtime stats, and hot-plug controls#

## DDD Architecture Decision (ADR)#

**Decision**: StrategyInstance dashboard shows linked entities#
- **Table Columns**: Algorithm Name, Config Set Name, Status, Runtime Stats, Actions#
- **Hot-Plug**: Start/Stop/Pause/Resume buttons#
- **Real-time Stats**: PnL, trades, uptime (poll every 5 seconds)#
- **Link to Backtest**: Button to navigate to backtest page#

**Key Features**:#
- Dropdown selectors for Algorithm and ConfigurationSet when creating#
- Status badges with colors (running=green, stopped=gray, paused=yellow, error=red)#
- Real-time statistics panel#
- Navigation to backtest page with pre-filled StrategyInstance#

## TDD Approach#

1. **Manual Testing Checklist**: Create HTML/JS, test all interactions#
2. **Integration Test**: Test API calls to StrategyInstance endpoints#
3. **State Management**: Test start/stop/pause/resume transitions#

## Implementation Files#

### 1. `dashboard/strategy-instances.html`#

HTML page following existing pattern:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Algorithm Instances - Crypto Trading Dashboard</title>
    
    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Bootstrap Icons -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
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
                        <a class="nav-link active" href="strategy-instances.html">
                            <i class="bi bi-diagram-3"></i> Instances
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="backtest.html">
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
                <h1><i class="bi bi-diagram-3"></i> Algorithm Instances</h1>
                <p class="text-muted">Manage deployed strategies with specific configurations</p>
            </div>
        </div>

        <!-- Alerts -->
        <div id="alert-container"></div>

        <!-- Action Bar -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-body d-flex justify-content-between align-items-center">
                        <div>
                            <button id="btn-create" class="btn btn-primary me-2">
                                <i class="bi bi-plus-lg"></i> New Instance
                            </button>
                            <button id="btn-refresh" class="btn btn-outline-secondary">
                                <i class="bi bi-arrow-clockwise"></i> Refresh
                            </button>
                        </div>
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="show-inactive">
                            <label class="form-check-label" for="show-inactive">Show Inactive</label>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Instances Table -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-list"></i> Algorithm Instances
                        <span id="instance-count" class="badge bg-secondary ms-2">0</span>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover" id="instances-table">
                                <thead>
                                    <tr>
                                        <th>Algorithm</th>
                                        <th>Config Set</th>
                                        <th>Status</th>
                                        <th>PnL</th>
                                        <th>Trades</th>
                                        <th>Uptime</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="instances-tbody">
                                    <tr>
                                        <td colspan="7" class="text-center text-muted py-4">
                                            <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                                            Loading instances...
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Create Instance Modal -->
    <div class="modal fade" id="instanceModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-diagram-3"></i> Create Algorithm Instance</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="instance-form">
                        <div class="mb-3">
                            <label class="form-label">Algorithm *</label>
                            <select class="form-select" id="instance-strategy" required>
                                <option value="">Select a strategy...</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Configuration Set *</label>
                            <select class="form-select" id="instance-config-set" required>
                                <option value="">Select a config set...</option>
                            </select>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" id="btn-save">
                        <i class="bi bi-save"></i> Create Instance
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Statistics Modal -->
    <div class="modal fade" id="statsModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-bar-chart"></i> Runtime Statistics</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="row">
                        <div class="col-md-3">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h3 id="stat-pnl">$0</h3>
                                    <small class="text-muted">PnL</small>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h3 id="stat-trades">0</h3>
                                    <small class="text-muted">Total Trades</small>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h3 id="stat-win-rate">0%</h3>
                                    <small class="text-muted">Win Rate</small>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="card bg-light">
                                <div class="card-body text-center">
                                    <h3 id="stat-uptime">0s</h3>
                                    <small class="text-muted">Uptime</small>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="mt-3">
                        <h6>Last Error</h6>
                        <p id="stat-error" class="text-muted">None</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <!-- StrategyInstances JS -->
    <script src="js/strategy-instances.js"></script>
</body>
</html>
```

### 2. `dashboard/js/strategy-instances.js`#

JavaScript module:

```javascript
/**
 * StrategyInstance Management Dashboard Module
 * 
 * Handles:
 * - StrategyInstance CRUD operations
 * - Hot-plug (start/stop/pause/resume)
 * - Real-time statistics polling
 * - Navigation to backtest
 */

const API_BASE_URL = '/api';

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
    window.location.href = `backtest.html?instance_id=${instanceId}`;
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
```

## LLM Implementation Prompt#

```text
You are implementing Step 9 of Phase 4: Dashboard - StrategyInstance Management.

## Your Task#

Create dashboard page for managing StrategyInstances with hot-plug controls.

## Context#

- Step 4-5 complete: StrategyInstance entity, repository, and API exist
- Step 8 complete: ConfigurationSet dashboard page exists as pattern
- Use Bootstrap 5 + vanilla JavaScript (no React/Vue)
- Follow existing dashboard styling (css/dashboard.css)

## Requirements#

1. Create `dashboard/strategy-instances.html` with:
   - Navigation bar with "Instances" as active item
   - Action bar: New Instance, Refresh, Show Inactive toggle
   - Table with columns: Algorithm, Config Set, Status, PnL, Trades, Uptime, Actions
   - Create Instance Modal:
     * Dropdown for Algorithm (load from /api/strategies)
     * Dropdown for ConfigurationSet (load from /api/config-sets)
   - Statistics Modal showing PnL, trades, win rate, uptime, last error
   - Update navigation in ALL dashboard pages to include "Instances" link

2. Create `dashboard/js/strategy-instances.js` with:
   - loadInstances(): Fetch from GET /api/strategy-instances
   - loadStrategies(): Load strategies for dropdown
   - loadConfigSets(): Load config sets for dropdown
   - renderInstances(): Display in table with status badges
   - saveInstance(): Create (POST /api/strategy-instances)
   - startInstance(id): Hot-plug (POST /api/strategy-instances/{id}/start)
   - stopInstance(id): Unplug (POST /api/strategy-instances/{id}/stop)
   - pauseInstance(id): POST /api/strategy-instances/{id}/pause
   - resumeInstance(id): POST /api/strategy-instances/{id}/resume
   - viewStats(id): Show statistics modal
   - runBacktest(id): Navigate to backtest.html?instance_id=...
   - deleteInstance(id): DELETE /api/strategy-instances/{id}
   - startPolling(): Poll every 5s for running instances

3. Key Features:
   - Status badges: running=green, stopped=gray, paused=yellow, error=red
   - PnL formatting with color (green for positive, red for negative)
   - Uptime formatting (seconds → minutes → hours)
   - Real-time polling for running instances (every 5 seconds)
   - Link to backtest page with pre-filled instance

## Constraints#

- Follow existing Bootstrap 5 + vanilla JS pattern
- Use fetch() API for all backend calls
- Use Bootstrap modals for create and statistics
- CSS: Use existing dashboard.css
- Icons: Use Bootstrap Icons (bi-* classes)
- Responsive design (mobile-friendly table)

## Acceptance Criteria#

1. Can create StrategyInstance (link Algorithm + ConfigSet)
2. Table shows all instances with correct data
3. Start/Stop/Pause/Resume buttons work (hot-plug)
4. Real-time stats polling for running instances
5. Statistics modal shows PnL, trades, win rate, uptime
6. Navigation updated in all dashboard pages
7. Link to backtest page works with instance pre-filled
8. Delete button removes instance

## Manual Testing Checklist#

```bash
# Start the dashboard
cd /home/andy/projects/numbers/numbersML
.venv/bin/uvicorn src.infrastructure.api.app:app --reload

# Open browser to http://localhost:8000/dashboard/strategy-instances.html

# Test cases:
1. Click "New Instance" → Select strategy + config set → Save → Verify appears in table
2. Click Start button (play icon) → Verify status changes to "Running"
3. Click Pause button → Verify status changes to "Paused"
4. Click Resume button → Verify status changes back to "Running"
5. Click Stop button → Verify status changes to "Stopped"
6. Click Statistics button (bar chart icon) → Verify modal shows runtime stats
7. Click Backtest button (graph icon) → Verify navigates to backtest page
8. Click Delete button (trash icon) → Confirm → Verify removed
9. Toggle "Show Inactive" → Verify inactive appear
```

## Output#

1. List of files created/modified
2. Screenshot or description of UI
3. Any issues encountered and how resolved
```

## Success Criteria#

- [ ] strategy-instances.html created with all UI elements
- [ ] strategy-instances.js created with all operations
- [ ] Hot-plug controls working (start/stop/pause/resume)
- [ ] Real-time polling for running instances
- [ ] Statistics modal with PnL, trades, uptime
- [ ] Navigation updated in all dashboard pages
- [ ] Link to backtest page with instance pre-filled
- [ ] All manual tests pass
- [ ] Responsive design (mobile-friendly)
