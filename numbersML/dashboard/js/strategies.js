/**
 * Strategy Management Dashboard Module
 * 
 * Handles:
 * - Strategy CRUD operations
 * - LLM-assisted creation/modification
 * - Activation/deactivation controls
 * - Version history and events
 * - Backtest integration
 */

// API Configuration
const API_BASE_URL = '/api';

// State
let strategies = [];
let currentStrategyId = null;
let currentStrategy = null;
let generatedConfig = null;
let modifiedConfig = null;

// Bootstrap Modals
let createModal, llmCreateModal, detailModal, modifyModal, liveConfirmModal;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initModals();
    bindEventListeners();
    loadStrategies();
});

/**
 * Initialize Bootstrap modals
 */
function initModals() {
    createModal = new bootstrap.Modal(document.getElementById('createStrategyModal'));
    llmCreateModal = new bootstrap.Modal(document.getElementById('llmCreateModal'));
    detailModal = new bootstrap.Modal(document.getElementById('strategyDetailModal'));
    modifyModal = new bootstrap.Modal(document.getElementById('modifyStrategyModal'));
    liveConfirmModal = new bootstrap.Modal(document.getElementById('liveConfirmModal'));
}

/**
 * Bind all event listeners
 */
function bindEventListeners() {
    // Action buttons
    document.getElementById('btn-create-strategy').addEventListener('click', () => {
        loadConfigTemplate('rsi');
        createModal.show();
    });
    
    document.getElementById('btn-llm-create').addEventListener('click', () => {
        llmCreateModal.show();
    });
    
    document.getElementById('btn-refresh').addEventListener('click', loadStrategies);
    
    document.getElementById('show-inactive').addEventListener('change', renderStrategies);
    
    // Save buttons
    document.getElementById('btn-save-strategy').addEventListener('click', createStrategy);
    document.getElementById('btn-generate-config').addEventListener('click', generateLLMConfig);
    document.getElementById('btn-save-llm-strategy').addEventListener('click', saveLLMStrategy);
    
    // Detail actions
    document.getElementById('btn-activate').addEventListener('click', () => activateStrategy(false));
    document.getElementById('btn-deactivate').addEventListener('click', deactivateStrategy);
    document.getElementById('btn-pause').addEventListener('click', pauseStrategy);
    document.getElementById('btn-resume').addEventListener('click', resumeStrategy);
    document.getElementById('btn-delete').addEventListener('click', deleteStrategy);
    document.getElementById('btn-modify').addEventListener('click', () => {
        detailModal.hide();
        modifyModal.show();
    });
    document.getElementById('btn-llm-suggest').addEventListener('click', getLLMSuggestions);
    document.getElementById('btn-backtest').addEventListener('click', () => {
        window.location.href = `backtest.html?strategy_id=${currentStrategyId}`;
    });
    
    // Modify modal
    document.getElementById('btn-apply-modify').addEventListener('click', applyLLMModify);
    document.getElementById('btn-save-modify').addEventListener('click', saveModifiedStrategy);
    
    // Template links
    document.getElementById('load-template-rsi').addEventListener('click', (e) => {
        e.preventDefault();
        loadConfigTemplate('rsi');
    });
    document.getElementById('load-template-macd').addEventListener('click', (e) => {
        e.preventDefault();
        loadConfigTemplate('macd');
    });
    document.getElementById('load-template-bollinger').addEventListener('click', (e) => {
        e.preventDefault();
        loadConfigTemplate('bollinger');
    });
    
    // Live confirmation
    document.getElementById('live-confirm-input').addEventListener('input', (e) => {
        document.getElementById('btn-confirm-live').disabled = e.target.value !== 'LIVE';
    });
    
    document.getElementById('btn-confirm-live').addEventListener('click', () => {
        liveConfirmModal.hide();
        activateStrategy(true);
    });
}

/**
 * Load configuration template
 */
function loadConfigTemplate(type) {
    const templates = {
        rsi: {
            meta: { name: "RSI Strategy", description: "RSI oversold/overbought", schema_version: 1 },
            universe: { symbols: ["BTC/USDC"], timeframe: "1M" },
            signal: { type: "rsi", params: { period: 14, oversold: 30, overbought: 70 } },
            risk: { max_position_size_pct: 10, max_daily_loss_pct: 5, stop_loss_pct: 2, take_profit_pct: 4 },
            execution: { order_type: "market", slippage_bps: 10, fee_bps: 10 },
            mode: "paper",
            status: "draft"
        },
        macd: {
            meta: { name: "MACD Strategy", description: "MACD crossover", schema_version: 1 },
            universe: { symbols: ["BTC/USDC"], timeframe: "1M" },
            signal: { type: "macd", params: { fast: 12, slow: 26, signal: 9 } },
            risk: { max_position_size_pct: 10, max_daily_loss_pct: 5, stop_loss_pct: 2, take_profit_pct: 4 },
            execution: { order_type: "market", slippage_bps: 10, fee_bps: 10 },
            mode: "paper",
            status: "draft"
        },
        bollinger: {
            meta: { name: "Bollinger Strategy", description: "Bollinger Bands mean reversion", schema_version: 1 },
            universe: { symbols: ["BTC/USDC"], timeframe: "1M" },
            signal: { type: "bollinger", params: { period: 20, std_dev: 2.0 } },
            risk: { max_position_size_pct: 10, max_daily_loss_pct: 5, stop_loss_pct: 2, take_profit_pct: 4 },
            execution: { order_type: "market", slippage_bps: 10, fee_bps: 10 },
            mode: "paper",
            status: "draft"
        }
    };
    
    const template = templates[type];
    if (template) {
        document.getElementById('config-json').value = JSON.stringify(template, null, 2);
    }
}

/**
 * Load all strategies from API
 */
async function loadStrategies() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/strategies`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        strategies = await response.json();
        renderStrategies();
        updateStrategyCount();
    } catch (error) {
        showAlert('danger', `Failed to load strategies: ${error.message}`);
    }
}

/**
 * Render strategies table
 */
function renderStrategies() {
    const tbody = document.getElementById('strategies-tbody');
    const showInactive = document.getElementById('show-inactive').checked;
    
    let filtered = strategies;
    if (!showInactive) {
        filtered = strategies.filter(s => s.status !== 'archived');
    }
    
    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted py-4">
                    <i class="bi bi-inbox" style="font-size: 2rem;"></i>
                    <p class="mt-2">No strategies found</p>
                    <button class="btn btn-sm btn-primary" onclick="document.getElementById('btn-create-strategy').click()">
                        <i class="bi bi-plus-lg"></i> Create your first strategy
                    </button>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = filtered.map(strategy => `
        <tr class="strategy-row" data-id="${strategy.id}">
            <td>
                <strong>${escapeHtml(strategy.name)}</strong>
                ${strategy.description ? `<br><small class="text-muted">${escapeHtml(strategy.description)}</small>` : ''}
            </td>
            <td>${getSignalType(strategy)}</td>
            <td>${getSymbols(strategy)}</td>
            <td>${renderModeBadge(strategy.mode)}</td>
            <td>${renderStatusBadge(strategy.status)}</td>
            <td>v${strategy.current_version}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="viewStrategy('${strategy.id}')">
                    <i class="bi bi-eye"></i>
                </button>
                ${strategy.status === 'active' ? `
                    <button class="btn btn-sm btn-warning me-1" onclick="quickDeactivate('${strategy.id}')">
                        <i class="bi bi-stop-fill"></i>
                    </button>
                ` : `
                    <button class="btn btn-sm btn-success me-1" onclick="quickActivate('${strategy.id}')">
                        <i class="bi bi-play-fill"></i>
                    </button>
                `}
            </td>
        </tr>
    `).join('');
    
    // Add click handlers for rows
    document.querySelectorAll('.strategy-row').forEach(row => {
        row.addEventListener('click', (e) => {
            if (!e.target.closest('button')) {
                viewStrategy(row.dataset.id);
            }
        });
    });
}

/**
 * Get signal type from strategy config
 */
function getSignalType(strategy) {
    // This would need to fetch the version config
    // For now, return placeholder
    return '<span class="badge bg-secondary">Unknown</span>';
}

/**
 * Get symbols from strategy
 */
function getSymbols(strategy) {
    // Would need config to get actual symbols
    return '<span class="text-muted">-</span>';
}

/**
 * Render mode badge
 */
function renderModeBadge(mode) {
    const classes = {
        paper: 'bg-info',
        live: 'bg-danger'
    };
    const icons = {
        paper: 'bi-cash',
        live: 'bi-currency-dollar'
    };
    return `<span class="badge ${classes[mode] || 'bg-secondary'}"><i class="bi ${icons[mode] || ''}"></i> ${mode}</span>`;
}

/**
 * Render status badge
 */
function renderStatusBadge(status) {
    const classes = {
        draft: 'bg-secondary',
        validated: 'bg-info',
        active: 'bg-success',
        paused: 'bg-warning',
        archived: 'bg-dark'
    };
    const icons = {
        draft: 'bi-pencil',
        validated: 'bi-check',
        active: 'bi-play-fill',
        paused: 'bi-pause-fill',
        archived: 'bi-archive'
    };
    return `<span class="badge ${classes[status] || 'bg-secondary'}"><i class="bi ${icons[status] || ''}"></i> ${status}</span>`;
}

/**
 * Update strategy count badge
 */
function updateStrategyCount() {
    const activeCount = strategies.filter(s => s.status === 'active').length;
    const totalCount = strategies.length;
    document.getElementById('strategy-count').textContent = `${activeCount} active / ${totalCount} total`;
}

/**
 * View strategy details
 */
async function viewStrategy(strategyId) {
    currentStrategyId = strategyId;
    currentStrategy = strategies.find(s => s.id === strategyId);
    
    if (!currentStrategy) {
        showAlert('danger', 'Strategy not found');
        return;
    }
    
    document.getElementById('detail-title').textContent = currentStrategy.name;
    
    // Load runtime status
    await loadRuntimeStatus(strategyId);
    
    // Load config
    await loadStrategyConfig(strategyId);
    
    // Load versions
    await loadVersions(strategyId);
    
    // Load events
    await loadEvents(strategyId);
    
    // Update button states
    updateActionButtons(currentStrategy.status);
    
    detailModal.show();
}

/**
 * Load runtime status
 */
async function loadRuntimeStatus(strategyId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${strategyId}/runtime`);
        if (response.ok) {
            const status = await response.json();
            document.getElementById('runtime-status').innerHTML = `
                <span class="badge bg-${getRuntimeColor(status.state)}">${status.state}</span>
                <br><small class="text-muted">Version: ${status.version}</small>
                ${status.error_count > 0 ? `<br><span class="badge bg-danger">${status.error_count} errors</span>` : ''}
            `;
        } else {
            document.getElementById('runtime-status').innerHTML = '<span class="badge bg-secondary">Stopped</span>';
        }
    } catch (error) {
        document.getElementById('runtime-status').innerHTML = '<span class="badge bg-secondary">Unknown</span>';
    }
}

/**
 * Get runtime state color
 */
function getRuntimeColor(state) {
    const colors = {
        RUNNING: 'success',
        PAUSED: 'warning',
        STOPPED: 'secondary',
        ERROR: 'danger'
    };
    return colors[state] || 'secondary';
}

/**
 * Load strategy configuration
 */
async function loadStrategyConfig(strategyId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${strategyId}/versions`);
        if (response.ok) {
            const versions = await response.json();
            const activeVersion = versions.find(v => v.is_active) || versions[versions.length - 1];
            if (activeVersion) {
                document.getElementById('detail-config').textContent = JSON.stringify(activeVersion.config, null, 2);
            }
        }
    } catch (error) {
        document.getElementById('detail-config').textContent = 'Failed to load config';
    }
}

/**
 * Load version history
 */
async function loadVersions(strategyId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${strategyId}/versions`);
        if (response.ok) {
            const versions = await response.json();
            document.getElementById('versions-list').innerHTML = versions.map(v => `
                <div class="card mb-2 ${v.is_active ? 'border-success' : ''}">
                    <div class="card-body py-2">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <strong>Version ${v.version}</strong>
                                ${v.is_active ? '<span class="badge bg-success ms-2">Active</span>' : ''}
                                <br>
                                <small class="text-muted">By ${v.created_by} on ${new Date(v.created_at).toLocaleString()}</small>
                            </div>
                            ${!v.is_active ? `
                                <button class="btn btn-sm btn-outline-primary" onclick="activateVersion('${strategyId}', ${v.version})">
                                    Activate
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        document.getElementById('versions-list').innerHTML = '<p class="text-muted">Failed to load versions</p>';
    }
}

/**
 * Load lifecycle events
 */
async function loadEvents(strategyId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${strategyId}/events`);
        if (response.ok) {
            const events = await response.json();
            document.getElementById('events-list').innerHTML = events.slice(0, 10).map(e => `
                <div class="border-bottom py-2">
                    <div class="d-flex justify-content-between">
                        <span class="badge bg-${getEventColor(e.to_state)}">${e.to_state}</span>
                        <small class="text-muted">${new Date(e.occurred_at).toLocaleString()}</small>
                    </div>
                    <small class="text-muted">${e.trigger} by ${e.details?.actor || 'system'}</small>
                </div>
            `).join('');
        }
    } catch (error) {
        document.getElementById('events-list').innerHTML = '<p class="text-muted">Failed to load events</p>';
    }
}

/**
 * Get event state color
 */
function getEventColor(state) {
    return getRuntimeColor(state);
}

/**
 * Update action button states based on status
 */
function updateActionButtons(status) {
    const btnActivate = document.getElementById('btn-activate');
    const btnDeactivate = document.getElementById('btn-deactivate');
    const btnPause = document.getElementById('btn-pause');
    const btnResume = document.getElementById('btn-resume');
    
    // Reset all
    btnActivate.disabled = true;
    btnDeactivate.disabled = true;
    btnPause.disabled = true;
    btnResume.disabled = true;
    
    switch (status) {
        case 'draft':
        case 'validated':
            btnActivate.disabled = false;
            break;
        case 'active':
            btnDeactivate.disabled = false;
            btnPause.disabled = false;
            break;
        case 'paused':
            btnDeactivate.disabled = false;
            btnResume.disabled = false;
            break;
    }
}

/**
 * Create new strategy
 */
async function createStrategy() {
    const form = document.getElementById('create-strategy-form');
    const formData = new FormData(form);
    
    // Parse config JSON
    let config;
    try {
        config = JSON.parse(document.getElementById('config-json').value);
    } catch (e) {
        showAlert('danger', 'Invalid JSON in configuration');
        return;
    }
    
    const payload = {
        name: formData.get('name'),
        description: formData.get('description'),
        mode: formData.get('mode'),
        config: config,
        created_by: 'dashboard'
    };
    
    // Add meta/universe from form
    config.meta = config.meta || {};
    config.meta.name = payload.name;
    config.meta.description = payload.description || '';
    
    config.universe = config.universe || {};
    config.universe.timeframe = formData.get('timeframe');
    config.universe.symbols = formData.get('symbols').split(',').map(s => s.trim()).filter(s => s);
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        createModal.hide();
        form.reset();
        showAlert('success', `Strategy "${result.name}" created successfully`);
        loadStrategies();
    } catch (error) {
        showAlert('danger', `Failed to create strategy: ${error.message}`);
    }
}

/**
 * Generate config via LLM
 */
async function generateLLMConfig() {
    const form = document.getElementById('llm-create-form');
    const formData = new FormData(form);
    
    const payload = {
        description: formData.get('description'),
        symbols: formData.get('symbols').split(',').map(s => s.trim()).filter(s => s),
        timeframe: formData.get('timeframe'),
        mode: formData.get('mode'),
        save_draft: false  // We'll save manually after review
    };
    
    const btn = document.getElementById('btn-generate-config');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generating...';
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.message || `HTTP ${response.status}`);
        }
        
        generatedConfig = result.config;
        
        // Display result
        document.getElementById('llm-config-display').textContent = JSON.stringify(result.config, null, 2);
        
        // Show validation issues if any
        const issuesDiv = document.getElementById('llm-validation-issues');
        if (result.validation_issues && result.validation_issues.length > 0) {
            issuesDiv.innerHTML = `
                <div class="alert alert-warning">
                    <h6>Validation Issues:</h6>
                    <ul>
                        ${result.validation_issues.map(i => `<li>${i.path}: ${i.message}</li>`).join('')}
                    </ul>
                </div>
            `;
        } else {
            issuesDiv.innerHTML = '<div class="alert alert-success">Configuration is valid</div>';
        }
        
        document.getElementById('llm-result').classList.remove('d-none');
        
        if (result.success) {
            document.getElementById('btn-save-llm-strategy').classList.remove('d-none');
        }
        
    } catch (error) {
        showAlert('danger', `LLM generation failed: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-robot"></i> Generate';
    }
}

/**
 * Save LLM-generated strategy
 */
async function saveLLMStrategy() {
    if (!generatedConfig) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: generatedConfig.meta.name,
                description: generatedConfig.meta.description,
                mode: generatedConfig.mode,
                config: generatedConfig,
                created_by: 'llm_dashboard'
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        llmCreateModal.hide();
        document.getElementById('llm-create-form').reset();
        document.getElementById('llm-result').classList.add('d-none');
        document.getElementById('btn-save-llm-strategy').classList.add('d-none');
        generatedConfig = null;
        
        showAlert('success', `Strategy "${result.name}" created from AI suggestion`);
        loadStrategies();
    } catch (error) {
        showAlert('danger', `Failed to save strategy: ${error.message}`);
    }
}

/**
 * Apply LLM modification
 */
async function applyLLMModify() {
    const changeRequest = document.getElementById('modify-request').value;
    if (!changeRequest.trim()) {
        showAlert('warning', 'Please enter a change request');
        return;
    }
    
    const btn = document.getElementById('btn-apply-modify');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Modifying...';
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}/modify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                change_request: changeRequest,
                save_as_new_version: document.getElementById('save-as-version').checked
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.message || `HTTP ${response.status}`);
        }
        
        modifiedConfig = result.config;
        
        document.getElementById('modify-config-display').textContent = JSON.stringify(result.config, null, 2);
        document.getElementById('modify-result').classList.remove('d-none');
        
        if (result.success) {
            document.getElementById('btn-save-modify').classList.remove('d-none');
        }
        
    } catch (error) {
        showAlert('danger', `Modification failed: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-robot"></i> AI Modify';
    }
}

/**
 * Save modified strategy
 */
async function saveModifiedStrategy() {
    if (!modifiedConfig) return;
    
    const saveAsVersion = document.getElementById('save-as-version').checked;
    
    try {
        if (saveAsVersion) {
            const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}/versions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    config: modifiedConfig,
                    schema_version: 1,
                    created_by: 'llm_modify_dashboard'
                })
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            showAlert('success', 'New version created successfully');
        } else {
            // Just update current - would need a PUT endpoint
            showAlert('info', 'Changes applied to current version');
        }
        
        modifyModal.hide();
        document.getElementById('modify-result').classList.add('d-none');
        document.getElementById('btn-save-modify').classList.add('d-none');
        modifiedConfig = null;
        
        loadStrategies();
        if (currentStrategyId) {
            viewStrategy(currentStrategyId);
        }
    } catch (error) {
        showAlert('danger', `Failed to save: ${error.message}`);
    }
}

/**
 * Activate strategy
 */
async function activateStrategy(confirmed = false) {
    if (!currentStrategy) return;
    
    // Check for live mode confirmation
    if (currentStrategy.mode === 'live' && !confirmed) {
        liveConfirmModal.show();
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}/activate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version: currentStrategy.current_version })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        showAlert('success', `Strategy "${currentStrategy.name}" activated`);
        detailModal.hide();
        loadStrategies();
    } catch (error) {
        showAlert('danger', `Activation failed: ${error.message}`);
    }
}

/**
 * Quick activate from table
 */
async function quickActivate(strategyId) {
    const strategy = strategies.find(s => s.id === strategyId);
    if (!strategy) return;
    
    if (strategy.mode === 'live') {
        currentStrategyId = strategyId;
        currentStrategy = strategy;
        liveConfirmModal.show();
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${strategyId}/activate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Strategy activated');
        loadStrategies();
    } catch (error) {
        showAlert('danger', `Activation failed: ${error.message}`);
    }
}

/**
 * Deactivate strategy
 */
async function deactivateStrategy() {
    if (!currentStrategyId) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}/deactivate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Strategy deactivated');
        detailModal.hide();
        loadStrategies();
    } catch (error) {
        showAlert('danger', `Deactivation failed: ${error.message}`);
    }
}

/**
 * Quick deactivate from table
 */
async function quickDeactivate(strategyId) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${strategyId}/deactivate`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Strategy deactivated');
        loadStrategies();
    } catch (error) {
        showAlert('danger', `Deactivation failed: ${error.message}`);
    }
}

/**
 * Pause strategy
 */
async function pauseStrategy() {
    if (!currentStrategyId) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}/pause`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Strategy paused');
        loadStrategies();
        viewStrategy(currentStrategyId);
    } catch (error) {
        showAlert('danger', `Pause failed: ${error.message}`);
    }
}

/**
 * Resume strategy
 */
async function resumeStrategy() {
    if (!currentStrategyId) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}/resume`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Strategy resumed');
        loadStrategies();
        viewStrategy(currentStrategyId);
    } catch (error) {
        showAlert('danger', `Resume failed: ${error.message}`);
    }
}

/**
 * Delete strategy
 */
async function deleteStrategy() {
    if (!currentStrategyId) return;
    
    if (!confirm('Are you sure you want to delete this strategy? This cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Strategy deleted');
        detailModal.hide();
        loadStrategies();
    } catch (error) {
        showAlert('danger', `Delete failed: ${error.message}`);
    }
}

/**
 * Get LLM suggestions
 */
async function getLLMSuggestions() {
    if (!currentStrategyId) return;
    
    const btn = document.getElementById('btn-llm-suggest');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Analyzing...';
    
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${currentStrategyId}/suggest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const result = await response.json();
        
        if (!response.ok) throw new Error(result.message || `HTTP ${response.status}`);
        
        // Show suggestions in a modal or alert
        const suggestionsHtml = `
            <div class="alert alert-info">
                <h6><i class="bi bi-robot"></i> AI Suggestions</h6>
                <pre class="mb-0">${escapeHtml(result.suggestions)}</pre>
            </div>
        `;
        
        // Insert into detail modal
        const configTab = document.getElementById('tab-config');
        configTab.insertAdjacentHTML('afterbegin', suggestionsHtml);
        
    } catch (error) {
        showAlert('danger', `Failed to get suggestions: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-robot"></i> AI Suggestions';
    }
}

/**
 * Activate specific version
 */
async function activateVersion(strategyId, version) {
    try {
        const response = await fetch(`${API_BASE_URL}/strategies/${strategyId}/versions/${version}/activate`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', `Version ${version} activated`);
        loadVersions(strategyId);
    } catch (error) {
        showAlert('danger', `Failed to activate version: ${error.message}`);
    }
}

/**
 * Show loading state
 */
function showLoading() {
    document.getElementById('strategies-tbody').innerHTML = `
        <tr>
            <td colspan="7" class="text-center text-muted py-4">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-2">Loading strategies...</p>
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
    
    // Auto-dismiss after 5 seconds
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
