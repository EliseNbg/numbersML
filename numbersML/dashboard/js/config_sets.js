/**
 * ConfigurationSet Management Dashboard Module
 * 
 * Handles:
 * - ConfigurationSet CRUD operations
 * - Dynamic parameter add/remove
 * - Form validation
 */

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
    document.getElementById('btn-add-param').addEventListener('click', () => addDynamicParam());
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
