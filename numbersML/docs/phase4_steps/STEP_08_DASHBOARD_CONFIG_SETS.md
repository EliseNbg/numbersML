# Step 8: Dashboard - ConfigurationSet Management

## Objective
Create dashboard page for managing ConfigurationSets (CRUD) with dynamic parameter editing.

## Context
- Step 1-3 complete: ConfigurationSet entity, repository, and API endpoints exist
- Existing dashboard pattern: `dashboard/algorithms.html` and `dashboard/js/algorithms.js`
- Need to follow existing Bootstrap 5 + vanilla JS pattern

## DDD Architecture Decision (ADR)

**Decision**: Dashboard is Infrastructure Layer (UI)
- HTML pages in `dashboard/` directory
- JS modules in `dashboard/js/` directory
- Uses FastAPI backend via fetch() API calls
- Bootstrap 5 for styling (consistent with existing pages)

**Key Features**:
- List all ConfigurationSets in a table
- Create/Edit modal with dynamic parameter editor
- Add/Remove parameters dynamically
- Symbol multi-select from existing symbols
- Risk parameters section
- Initial balance input

## TDD Approach

1. **Manual Testing Checklist**: Create HTML/JS, test all interactions
2. **E2E Tests**: Use Playwright or Selenium (future)
3. **Component Testing**: Test JS functions with Jest (future)

## Implementation Files

### 1. `dashboard/config_sets.html`

HTML page following existing pattern:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Configuration Sets - Crypto Trading Dashboard</title>
    
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
                        <a class="nav-link" href="algorithms.html">
                            <i class="bi bi-cpu"></i> Algorithms
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link active" href="config_sets.html">
                            <i class="bi bi-sliders"></i> Config Sets
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="algorithm-instances.html">
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
                <h1><i class="bi bi-sliders"></i> Configuration Sets</h1>
                <p class="text-muted">Manage reusable configuration parameters for algorithms</p>
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
                                <i class="bi bi-plus-lg"></i> New Config Set
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

        <!-- Config Sets Table -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-list"></i> Configuration Sets
                        <span id="config-count" class="badge bg-secondary ms-2">0</span>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover" id="config-sets-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Description</th>
                                        <th>Symbols</th>
                                        <th>Status</th>
                                        <th>Version</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="config-sets-tbody">
                                    <tr>
                                        <td colspan="6" class="text-center text-muted py-4">
                                            <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                                            Loading configuration sets...
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

    <!-- Create/Edit ConfigSet Modal -->
    <div class="modal fade" id="configSetModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="bi bi-sliders"></i> <span id="modal-title">Create Configuration Set</span></h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="config-set-form">
                        <input type="hidden" id="config-set-id">
                        
                        <div class="mb-3">
                            <label class="form-label">Name *</label>
                            <input type="text" class="form-control" id="config-name" required minlength="1" maxlength="255">
                        </div>
                        
                        <div class="mb-3">
                            <label class="form-label">Description</label>
                            <textarea class="form-control" id="config-description" rows="2" maxlength="2000"></textarea>
                        </div>
                        
                        <div class="mb-3">
                            <label class="form-label">Symbols (comma-separated)</label>
                            <input type="text" class="form-control" id="config-symbols" placeholder="BTC/USDT, ETH/USDT">
                            <div class="form-text">Trading pairs for this configuration</div>
                        </div>
                        
                        <div class="mb-3">
                            <label class="form-label">Initial Balance</label>
                            <input type="number" class="form-control" id="config-initial-balance" value="10000" step="100">
                        </div>
                        
                        <!-- Dynamic Parameters -->
                        <div class="mb-3">
                            <label class="form-label">Custom Parameters</label>
                            <div id="dynamic-params">
                                <!-- Dynamic parameter rows will be added here -->
                            </div>
                            <button type="button" class="btn btn-sm btn-outline-primary" id="btn-add-param">
                                <i class="bi bi-plus"></i> Add Parameter
                            </button>
                        </div>
                        
                        <!-- Risk Parameters -->
                        <div class="mb-3">
                            <label class="form-label">Risk Parameters</label>
                            <div class="row">
                                <div class="col-md-6">
                                    <label class="form-label">Max Position Size (%)</label>
                                    <input type="number" class="form-control" id="risk-max-position" value="10" step="0.1">
                                </div>
                                <div class="col-md-6">
                                    <label class="form-label">Max Daily Loss (%)</label>
                                    <input type="number" class="form-control" id="risk-max-loss" value="5" step="0.1">
                                </div>
                            </div>
                            <div class="row mt-2">
                                <div class="col-md-6">
                                    <label class="form-label">Stop Loss (%)</label>
                                    <input type="number" class="form-control" id="risk-stop-loss" value="2" step="0.1">
                                </div>
                                <div class="col-md-6">
                                    <label class="form-label">Take Profit (%)</label>
                                    <input type="number" class="form-control" id="risk-take-profit" value="4" step="0.1">
                                </div>
                            </div>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" id="btn-save">
                        <i class="bi bi-save"></i> Save
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <!-- ConfigurationSets JS -->
    <script src="js/config_sets.js"></script>
</body>
</html>
```

### 2. `dashboard/js/config_sets.js`

JavaScript module following existing pattern:

```javascript
/**
 * ConfigurationSet Management Dashboard Module
 * 
 * Handles:
 * - ConfigurationSet CRUD operations
 * - Dynamic parameter add/remove
 * - Form validation
 */

// API Configuration
const API_BASE_URL = '/api';

// State
let configSets = [];
let currentConfigSetId = null;

// Bootstrap Modal
let configSetModal;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initModal();
    bindEventListeners();
    loadConfigSets();
});

/**
 * Initialize Bootstrap modal
 */
function initModal() {
    configSetModal = new bootstrap.Modal(document.getElementById('configSetModal'));
}

/**
 * Bind all event listeners
 */
function bindEventListeners() {
    // Action buttons
    document.getElementById('btn-create').addEventListener('click', () => {
        currentConfigSetId = null;
        document.getElementById('modal-title').textContent = 'Create Configuration Set';
        document.getElementById('config-set-form').reset();
        clearDynamicParams();
        configSetModal.show();
    });
    
    document.getElementById('btn-refresh').addEventListener('click', loadConfigSets);
    document.getElementById('show-inactive').addEventListener('change', renderConfigSets);
    
    // Save button
    document.getElementById('btn-save').addEventListener('click', saveConfigSet);
    
    // Add parameter button
    document.getElementById('btn-add-param').addEventListener('click', addDynamicParam);
}

/**
 * Load all ConfigurationSets from API
 */
async function loadConfigSets() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/config-sets`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        configSets = await response.json();
        renderConfigSets();
        updateConfigCount();
    } catch (error) {
        showAlert('danger', `Failed to load configuration sets: ${error.message}`);
    }
}

/**
 * Render ConfigurationSets table
 */
function renderConfigSets() {
    const tbody = document.getElementById('config-sets-tbody');
    const showInactive = document.getElementById('show-inactive').checked;
    
    let filtered = configSets;
    if (!showInactive) {
        filtered = configSets.filter(cs => cs.is_active);
    }
    
    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted py-4">
                    <i class="bi bi-inbox" style="font-size: 2rem;"></i>
                    <p class="mt-2">No configuration sets found</p>
                    <button class="btn btn-sm btn-primary" onclick="document.getElementById('btn-create').click()">
                        <i class="bi bi-plus-lg"></i> Create your first config set
                    </button>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = filtered.map(cs => `
        <tr class="config-set-row" data-id="${cs.id}">
            <td>
                <strong>${escapeHtml(cs.name)}</strong>
                ${!cs.is_active ? '<span class="badge bg-secondary ms-2">Inactive</span>' : ''}
            </td>
            <td>${cs.description ? escapeHtml(cs.description) : '<span class="text-muted">-</span>'}</td>
            <td>${getSymbols(cs)}</td>
            <td>${renderStatusBadge(cs.is_active)}</td>
            <td>v${cs.version}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="editConfigSet('${cs.id}')">
                    <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteConfigSet('${cs.id}')">
                    <i class="bi bi-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

/**
 * Get symbols from config
 */
function getSymbols(configSet) {
    const config = configSet.config || {};
    const symbols = config.symbols || [];
    if (symbols.length === 0) {
        return '<span class="text-muted">-</span>';
    }
    return symbols.map(s => `<span class="badge bg-info me-1">${escapeHtml(s)}</span>`).join('');
}

/**
 * Render status badge
 */
function renderStatusBadge(isActive) {
    if (isActive) {
        return '<span class="badge bg-success">Active</span>';
    }
    return '<span class="badge bg-secondary">Inactive</span>';
}

/**
 * Update config count badge
 */
function updateConfigCount() {
    const activeCount = configSets.filter(cs => cs.is_active).length;
    const totalCount = configSets.length;
    document.getElementById('config-count').textContent = `${activeCount} active / ${totalCount} total`;
}

/**
 * Edit ConfigurationSet
 */
async function editConfigSet(configSetId) {
    currentConfigSetId = configSetId;
    const configSet = configSets.find(cs => cs.id === configSetId);
    
    if (!configSet) {
        showAlert('danger', 'ConfigurationSet not found');
        return;
    }
    
    document.getElementById('modal-title').textContent = 'Edit Configuration Set';
    document.getElementById('config-set-id').value = configSet.id;
    document.getElementById('config-name').value = configSet.name;
    document.getElementById('config-description').value = configSet.description || '';
    
    // Populate config fields
    const config = configSet.config || {};
    document.getElementById('config-symbols').value = (config.symbols || []).join(', ');
    document.getElementById('config-initial-balance').value = config.initial_balance || 10000;
    
    // Risk parameters
    const risk = config.risk || {};
    document.getElementById('risk-max-position').value = risk.max_position_size_pct || 10;
    document.getElementById('risk-max-loss').value = risk.max_daily_loss_pct || 5;
    document.getElementById('risk-stop-loss').value = risk.stop_loss_pct || 2;
    document.getElementById('risk-take-profit').value = risk.take_profit_pct || 4;
    
    // Custom parameters (excluding known keys)
    clearDynamicParams();
    const knownKeys = ['symbols', 'initial_balance', 'risk', 'execution'];
    for (const [key, value] of Object.entries(config)) {
        if (!knownKeys.includes(key) && typeof value !== 'object') {
            addDynamicParam(key, value);
        }
    }
    
    configSetModal.show();
}

/**
 * Save ConfigurationSet (create or update)
 */
async function saveConfigSet() {
    const name = document.getElementById('config-name').value.trim();
    const description = document.getElementById('config-description').value.trim();
    const symbols = document.getElementById('config-symbols').value.split(',').map(s => s.trim()).filter(s => s);
    const initialBalance = parseFloat(document.getElementById('config-initial-balance').value);
    
    if (!name) {
        showAlert('warning', 'Name is required');
        return;
    }
    
    // Build config object
    const config = {
        symbols: symbols,
        initial_balance: initialBalance,
        risk: {
            max_position_size_pct: parseFloat(document.getElementById('risk-max-position').value),
            max_daily_loss_pct: parseFloat(document.getElementById('risk-max-loss').value),
            stop_loss_pct: parseFloat(document.getElementById('risk-stop-loss').value),
            take_profit_pct: parseFloat(document.getElementById('risk-take-profit').value),
        },
        execution: {
            order_type: 'market',
            slippage_bps: 10,
            fee_bps: 10,
        },
    };
    
    // Add dynamic parameters
    const paramRows = document.querySelectorAll('.dynamic-param-row');
    paramRows.forEach(row => {
        const key = row.querySelector('.param-key').value.trim();
        const value = row.querySelector('.param-value').value;
        if (key) {
            config[key] = isNaN(value) ? value : parseFloat(value);
        }
    });
    
    const payload = {
        name: name,
        description: description,
        config: config,
        created_by: 'dashboard',
    };
    
    try {
        const btnSave = document.getElementById('btn-save');
        btnSave.disabled = true;
        btnSave.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Saving...';
        
        let response;
        if (currentConfigSetId) {
            // Update (Note: API doesn't support full update yet, only config update)
            response = await fetch(`${API_BASE_URL}/config-sets/${currentConfigSetId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config: config }),
            });
        } else {
            // Create
            response = await fetch(`${API_BASE_URL}/config-sets`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        configSetModal.hide();
        showAlert('success', `ConfigurationSet "${name}" saved successfully`);
        loadConfigSets();
        
    } catch (error) {
        showAlert('danger', `Failed to save: ${error.message}`);
    } finally {
        const btnSave = document.getElementById('btn-save');
        btnSave.disabled = false;
        btnSave.innerHTML = '<i class="bi bi-save"></i> Save';
    }
}

/**
 * Delete ConfigurationSet (deactivate)
 */
async function deleteConfigSet(configSetId) {
    if (!confirm('Are you sure you want to deactivate this configuration set?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/config-sets/${configSetId}`, {
            method: 'DELETE',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        showAlert('success', 'ConfigurationSet deactivated');
        loadConfigSets();
    } catch (error) {
        showAlert('danger', `Failed to delete: ${error.message}`);
    }
}

/**
 * Add dynamic parameter row
 */
function addDynamicParam(key = '', value = '') {
    const container = document.getElementById('dynamic-params');
    const rowId = `param-${Date.now()}`;
    
    const row = document.createElement('div');
    row.className = 'row mb-2 dynamic-param-row';
    row.id = rowId;
    row.innerHTML = `
        <div class="col-md-5">
            <input type="text" class="form-control form-control-sm param-key" placeholder="Parameter name" value="${escapeHtml(key)}">
        </div>
        <div class="col-md-5">
            <input type="text" class="form-control form-control-sm param-value" placeholder="Value" value="${escapeHtml(String(value))}">
        </div>
        <div class="col-md-2">
            <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeDynamicParam('${rowId}')">
                <i class="bi bi-trash"></i>
            </button>
        </div>
    `;
    
    container.appendChild(row);
}

/**
 * Remove dynamic parameter row
 */
function removeDynamicParam(rowId) {
    const row = document.getElementById(rowId);
    if (row) {
        row.remove();
    }
}

/**
 * Clear all dynamic parameters
 */
function clearDynamicParams() {
    document.getElementById('dynamic-params').innerHTML = '';
}

/**
 * Show loading state
 */
function showLoading() {
    document.getElementById('config-sets-tbody').innerHTML = `
        <tr>
            <td colspan="6" class="text-center text-muted py-4">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-2">Loading configuration sets...</p>
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

## LLM Implementation Prompt

```text
You are implementing Step 8 of Phase 4: Dashboard - ConfigurationSet Management.

## Your Task#

Create dashboard page for managing ConfigurationSets with CRUD and dynamic parameters.

## Context#

- Step 1-3 complete: ConfigurationSet entity, repository, and API endpoints exist
- Existing pattern: `dashboard/algorithms.html` and `dashboard/js/algorithms.js`
- Use Bootstrap 5 + vanilla JavaScript (no React/Vue)
- Follow existing dashboard styling (css/dashboard.css)

## Requirements#

1. Create `dashboard/config_sets.html` with:
   - Navigation bar with link to new page (add "Config Sets" item)
   - Action bar: New Config Set button, Refresh button, Show Inactive toggle
   - Table listing ConfigurationSets:
     * Name, Description, Symbols, Status, Version, Actions
     * Edit and Delete (deactivate) buttons
   - Create/Edit Modal with:
     * Name, Description fields
     * Symbols input (comma-separated)
     * Initial Balance input
     * Dynamic parameter section (Add/Remove buttons)
     * Risk parameters: Max Position, Max Daily Loss, Stop Loss, Take Profit
   - Update navigation in ALL dashboard pages to include "Config Sets" link

2. Create `dashboard/js/config_sets.js` with:
   - loadConfigSets(): Fetch from GET /api/config-sets
   - renderConfigSets(): Display in table
   - editConfigSet(id): Populate modal with existing data
   - saveConfigSet(): Create (POST) or Update (PUT)
   - deleteConfigSet(id): Soft delete (DELETE)
   - addDynamicParam(key, value): Add parameter row
   - removeDynamicParam(rowId): Remove parameter row
   - Form validation before save
   - showAlert(), escapeHtml() utilities

3. Update existing dashboard pages to link to config_sets.html:
   - Update navigation in index.html, algorithms.html, symbols.html, etc.
   - Add "Config Sets" nav item with bi-sliders icon

## Constraints#

- Follow existing Bootstrap 5 + vanilla JS pattern
- Use fetch() API for all backend calls
- Use Bootstrap modals for create/edit
- CSS: Use existing dashboard.css (don't create new styles)
- Icons: Use Bootstrap Icons (bi-* classes)
- Responsive design (mobile-friendly table)

## Acceptance Criteria#

1. Can create ConfigurationSet with name, symbols, risk params
2. Can edit existing ConfigurationSet
3. Can deactivate (soft delete) ConfigurationSet
4. Dynamic parameters can be added/removed
5. Table shows all ConfigurationSets with correct data
6. Navigation updated in all dashboard pages
7. Form validation works (required fields, number validation)
8. Alerts show success/error messages

## Manual Testing Checklist#

```bash
# Start the dashboard
cd /home/andy/projects/numbers/numbersML
.venv/bin/uvicorn src.infrastructure.api.app:app --reload

# Open browser to http://localhost:8000/dashboard/config_sets.html

# Test cases:
1. Click "New Config Set" → Fill form → Save → Verify appears in table
2. Click Edit (pencil icon) → Modify → Save → Verify updates
3. Click Delete (trash icon) → Confirm → Verify deactivated
4. Add dynamic parameter → Save → Verify parameter saved
5. Remove dynamic parameter → Save → Verify parameter removed
6. Toggle "Show Inactive" → Verify inactive appear
7. Test form validation (empty name) → Verify error message
```

## Output#

1. List of files created/modified
2. Screenshot or description of UI
3. Any issues encountered and how resolved
```

## Success Criteria#

- [ ] config_sets.html created with all UI elements
- [ ] config_sets.js created with all CRUD operations
- [ ] Dynamic parameter add/remove working
- [ ] Navigation updated in all dashboard pages
- [ ] Form validation implemented
- [ ] Alerts show success/error messages
- [ ] All manual tests pass
- [ ] Responsive design (mobile-friendly)
