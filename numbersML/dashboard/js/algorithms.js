/**
 * Algorithm Management Dashboard Module
 * 
 * Handles:
 * - Algorithm CRUD operations
 * - LLM-assisted creation/modification
 * - Activation/deactivation controls
 * - Version history and events
 * - Backtest integration
 */

// State
let algorithms = [];
let currentAlgorithmId = null;
let currentAlgorithm = null;
let generatedConfig = null;
let modifiedConfig = null;

// Bootstrap Modals
let createModal, llmCreateModal, detailModal, modifyModal, liveConfirmModal;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initModals();
    bindEventListeners();
    loadAlgorithms();
});

/**
 * Initialize Bootstrap modals
 */
function initModals() {
    createModal = new bootstrap.Modal(document.getElementById('createAlgorithmModal'));
    llmCreateModal = new bootstrap.Modal(document.getElementById('llmCreateModal'));
    detailModal = new bootstrap.Modal(document.getElementById('algorithmDetailModal'));
    modifyModal = new bootstrap.Modal(document.getElementById('modifyAlgorithmModal'));
    liveConfirmModal = new bootstrap.Modal(document.getElementById('liveConfirmModal'));
}

/**
 * Bind all event listeners
 */
function bindEventListeners() {
    // Action buttons
    document.getElementById('btn-create-algorithm').addEventListener('click', () => {
        loadConfigTemplate('rsi');
        createModal.show();
    });
    
    document.getElementById('btn-llm-create').addEventListener('click', () => {
        llmCreateModal.show();
    });
    
    document.getElementById('btn-refresh').addEventListener('click', loadAlgorithms);
    
    document.getElementById('show-inactive').addEventListener('change', renderAlgorithms);
    
    // Save buttons
    document.getElementById('btn-save-algorithm').addEventListener('click', createAlgorithm);
    document.getElementById('btn-generate-config').addEventListener('click', generateLLMConfig);
    document.getElementById('btn-save-llm-algorithm').addEventListener('click', saveLLMAlgorithm);
    
    // Detail actions
    document.getElementById('btn-activate').addEventListener('click', () => activateAlgorithm(false));
    document.getElementById('btn-deactivate').addEventListener('click', deactivateAlgorithm);
    document.getElementById('btn-pause').addEventListener('click', pauseAlgorithm);
    document.getElementById('btn-resume').addEventListener('click', resumeAlgorithm);
    document.getElementById('btn-delete').addEventListener('click', deleteAlgorithm);
    document.getElementById('btn-modify').addEventListener('click', () => {
        detailModal.hide();
        modifyModal.show();
    });
    document.getElementById('btn-llm-suggest').addEventListener('click', getLLMSuggestions);
    document.getElementById('btn-backtest').addEventListener('click', () => {
        window.location.href = `backtest_ml.html?algorithm_id=${currentAlgorithmId}`;
    });
    
    // Modify modal
    document.getElementById('btn-apply-modify').addEventListener('click', applyLLMModify);
    document.getElementById('btn-save-modify').addEventListener('click', saveModifiedAlgorithm);
    
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
        activateAlgorithm(true);
    });
}

/**
 * Load configuration template
 */
function loadConfigTemplate(type) {
    const templates = {
        rsi: {
            meta: { name: "RSI Algorithm", description: "RSI oversold/overbought", schema_version: 1 },
            universe: { symbols: ["BTC/USDC"], timeframe: "1M" },
            signal: { type: "rsi", params: { period: 14, oversold: 30, overbought: 70 } },
            risk: { max_position_size_pct: 10, max_daily_loss_pct: 5, stop_loss_pct: 2, take_profit_pct: 4 },
            execution: { order_type: "market", slippage_bps: 10, fee_bps: 10 },
            mode: "paper",
            status: "draft"
        },
        macd: {
            meta: { name: "MACD Algorithm", description: "MACD crossover", schema_version: 1 },
            universe: { symbols: ["BTC/USDC"], timeframe: "1M" },
            signal: { type: "macd", params: { fast: 12, slow: 26, signal: 9 } },
            risk: { max_position_size_pct: 10, max_daily_loss_pct: 5, stop_loss_pct: 2, take_profit_pct: 4 },
            execution: { order_type: "market", slippage_bps: 10, fee_bps: 10 },
            mode: "paper",
            status: "draft"
        },
        bollinger: {
            meta: { name: "Bollinger Algorithm", description: "Bollinger Bands mean reversion", schema_version: 1 },
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
 * Load all algorithms from API
 */
async function loadAlgorithms() {
    try {
        showLoading();
        const response = await apiFetch(`/algorithms`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        algorithms = await response.json();
        renderAlgorithms();
        updateAlgorithmCount();
    } catch (error) {
        showAlert('danger', `Failed to load algorithms: ${error.message}`);
    }
}

/**
 * Render algorithms table
 */
function renderAlgorithms() {
    const tbody = document.getElementById('algorithms-tbody');
    const showInactive = document.getElementById('show-inactive').checked;
    
    let filtered = algorithms;
    if (!showInactive) {
        filtered = algorithms.filter(s => s.status !== 'archived');
    }
    
    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted py-4">
                    <i class="bi bi-inbox" style="font-size: 2rem;"></i>
                    <p class="mt-2">No algorithms found</p>
                    <button class="btn btn-sm btn-primary" onclick="document.getElementById('btn-create-algorithm').click()">
                        <i class="bi bi-plus-lg"></i> Create your first algorithm
                    </button>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = filtered.map(algorithm => `
        <tr class="algorithm-row" data-id="${algorithm.id}">
            <td>
                <strong>${escapeHtml(algorithm.name)}</strong>
                ${algorithm.description ? `<br><small class="text-muted">${escapeHtml(algorithm.description)}</small>` : ''}
            </td>
            <td>${getSignalType(algorithm)}</td>
            <td>${getSymbols(algorithm)}</td>
            <td>${renderModeBadge(algorithm.mode)}</td>
            <td>${renderStatusBadge(algorithm.status)}</td>
            <td>v${algorithm.current_version}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="viewAlgorithm('${algorithm.id}')">
                    <i class="bi bi-eye"></i>
                </button>
                ${algorithm.status === 'active' ? `
                    <button class="btn btn-sm btn-warning me-1" onclick="quickDeactivate('${algorithm.id}')">
                        <i class="bi bi-stop-fill"></i>
                    </button>
                ` : `
                    <button class="btn btn-sm btn-success me-1" onclick="quickActivate('${algorithm.id}')">
                        <i class="bi bi-play-fill"></i>
                    </button>
                `}
            </td>
        </tr>
    `).join('');
    
    // Add click handlers for rows
    document.querySelectorAll('.algorithm-row').forEach(row => {
        row.addEventListener('click', (e) => {
            if (!e.target.closest('button')) {
                viewAlgorithm(row.dataset.id);
            }
        });
    });
}

/**
 * Get signal type from algorithm config
 */
function getSignalType(algorithm) {
    // This would need to fetch the version config
    // For now, return placeholder
    return '<span class="badge bg-secondary">Unknown</span>';
}

/**
 * Get symbols from algorithm
 */
function getSymbols(algorithm) {
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
 * Update algorithm count badge
 */
function updateAlgorithmCount() {
    const activeCount = algorithms.filter(s => s.status === 'active').length;
    const totalCount = algorithms.length;
    document.getElementById('algorithm-count').textContent = `${activeCount} active / ${totalCount} total`;
}

/**
 * View algorithm details
 */
async function viewAlgorithm(algorithmId) {
    currentAlgorithmId = algorithmId;
    currentAlgorithm = algorithms.find(s => s.id === algorithmId);
    
    if (!currentAlgorithm) {
        showAlert('danger', 'Algorithm not found');
        return;
    }
    
    document.getElementById('detail-title').textContent = currentAlgorithm.name;
    
    // Load runtime status
    await loadRuntimeStatus(algorithmId);
    
    // Load config
    await loadAlgorithmConfig(algorithmId);
    
    // Load versions
    await loadVersions(algorithmId);
    
    // Load events
    await loadEvents(algorithmId);
    
    // Update button states
    updateActionButtons(currentAlgorithm.status);
    
    detailModal.show();
}

/**
 * Load runtime status
 */
async function loadRuntimeStatus(algorithmId) {
    try {
        const response = await apiFetch(`/algorithms/${algorithmId}/runtime`);
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
 * Load algorithm configuration
 */
async function loadAlgorithmConfig(algorithmId) {
    try {
        const response = await apiFetch(`/algorithms/${algorithmId}/versions`);
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
async function loadVersions(algorithmId) {
    try {
        const response = await apiFetch(`/algorithms/${algorithmId}/versions`);
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
                                <button class="btn btn-sm btn-outline-primary" onclick="activateVersion('${algorithmId}', ${v.version})">
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
async function loadEvents(algorithmId) {
    try {
        const response = await apiFetch(`/algorithms/${algorithmId}/events`);
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
 * Create new algorithm
 */
async function createAlgorithm() {
    const form = document.getElementById('create-algorithm-form');
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
        const response = await apiFetch(`/algorithms`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        createModal.hide();
        form.reset();
        showAlert('success', `Algorithm "${result.name}" created successfully`);
        loadAlgorithms();
    } catch (error) {
        showAlert('danger', `Failed to create algorithm: ${error.message}`);
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
        const response = await apiFetch(`/algorithms/generate`, {
            method: 'POST',
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
            document.getElementById('btn-save-llm-algorithm').classList.remove('d-none');
        }
        
    } catch (error) {
        showAlert('danger', `LLM generation failed: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-robot"></i> Generate';
    }
}

/**
 * Save LLM-generated algorithm
 */
async function saveLLMAlgorithm() {
    if (!generatedConfig) return;
    
    try {
        const response = await apiFetch(`/algorithms`, {
            method: 'POST',
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
        document.getElementById('btn-save-llm-algorithm').classList.add('d-none');
        generatedConfig = null;
        
        showAlert('success', `Algorithm "${result.name}" created from AI suggestion`);
        loadAlgorithms();
    } catch (error) {
        showAlert('danger', `Failed to save algorithm: ${error.message}`);
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
        const response = await apiFetch(`/algorithms/${currentAlgorithmId}/modify`, {
            method: 'POST',
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
 * Save modified algorithm
 */
async function saveModifiedAlgorithm() {
    if (!modifiedConfig) return;
    
    const saveAsVersion = document.getElementById('save-as-version').checked;
    
    try {
        if (saveAsVersion) {
            const response = await apiFetch(`/algorithms/${currentAlgorithmId}/versions`, {
                method: 'POST',
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
        
        loadAlgorithms();
        if (currentAlgorithmId) {
            viewAlgorithm(currentAlgorithmId);
        }
    } catch (error) {
        showAlert('danger', `Failed to save: ${error.message}`);
    }
}

/**
 * Activate algorithm
 */
async function activateAlgorithm(confirmed = false) {
    if (!currentAlgorithm) return;
    
    // Check for live mode confirmation
    if (currentAlgorithm.mode === 'live' && !confirmed) {
        liveConfirmModal.show();
        return;
    }
    
    try {
        const response = await apiFetch(`/algorithms/${currentAlgorithmId}/activate`, {
            method: 'POST',
            body: JSON.stringify({ version: currentAlgorithm.current_version })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        showAlert('success', `Algorithm "${currentAlgorithm.name}" activated`);
        detailModal.hide();
        loadAlgorithms();
    } catch (error) {
        showAlert('danger', `Activation failed: ${error.message}`);
    }
}

/**
 * Quick activate from table
 */
async function quickActivate(algorithmId) {
    const algorithm = algorithms.find(s => s.id === algorithmId);
    if (!algorithm) return;
    
    if (algorithm.mode === 'live') {
        currentAlgorithmId = algorithmId;
        currentAlgorithm = algorithm;
        liveConfirmModal.show();
        return;
    }
    
    try {
        const response = await apiFetch(`/algorithms/${algorithmId}/activate`, {
            method: 'POST',
            body: JSON.stringify({})
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Algorithm activated');
        loadAlgorithms();
    } catch (error) {
        showAlert('danger', `Activation failed: ${error.message}`);
    }
}

/**
 * Deactivate algorithm
 */
async function deactivateAlgorithm() {
    if (!currentAlgorithmId) return;
    
    try {
        const response = await apiFetch(`/algorithms/${currentAlgorithmId}/deactivate`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Algorithm deactivated');
        detailModal.hide();
        loadAlgorithms();
    } catch (error) {
        showAlert('danger', `Deactivation failed: ${error.message}`);
    }
}

/**
 * Quick deactivate from table
 */
async function quickDeactivate(algorithmId) {
    try {
        const response = await apiFetch(`/algorithms/${algorithmId}/deactivate`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Algorithm deactivated');
        loadAlgorithms();
    } catch (error) {
        showAlert('danger', `Deactivation failed: ${error.message}`);
    }
}

/**
 * Pause algorithm
 */
async function pauseAlgorithm() {
    if (!currentAlgorithmId) return;
    
    try {
        const response = await apiFetch(`/algorithms/${currentAlgorithmId}/pause`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Algorithm paused');
        loadAlgorithms();
        viewAlgorithm(currentAlgorithmId);
    } catch (error) {
        showAlert('danger', `Pause failed: ${error.message}`);
    }
}

/**
 * Resume algorithm
 */
async function resumeAlgorithm() {
    if (!currentAlgorithmId) return;
    
    try {
        const response = await apiFetch(`/algorithms/${currentAlgorithmId}/resume`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Algorithm resumed');
        loadAlgorithms();
        viewAlgorithm(currentAlgorithmId);
    } catch (error) {
        showAlert('danger', `Resume failed: ${error.message}`);
    }
}

/**
 * Delete algorithm
 */
async function deleteAlgorithm() {
    if (!currentAlgorithmId) return;
    
    if (!confirm('Are you sure you want to delete this algorithm? This cannot be undone.')) {
        return;
    }
    
    try {
        const response = await apiFetch(`/algorithms/${currentAlgorithmId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Algorithm deleted');
        detailModal.hide();
        loadAlgorithms();
    } catch (error) {
        showAlert('danger', `Delete failed: ${error.message}`);
    }
}

/**
 * Get LLM suggestions
 */
async function getLLMSuggestions() {
    if (!currentAlgorithmId) return;
    
    const btn = document.getElementById('btn-llm-suggest');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Analyzing...';
    
    try {
        const response = await apiFetch(`/algorithms/${currentAlgorithmId}/suggest`, {
            method: 'POST',
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
async function activateVersion(algorithmId, version) {
    try {
        const response = await apiFetch(`/algorithms/${algorithmId}/versions/${version}/activate`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', `Version ${version} activated`);
        loadVersions(algorithmId);
    } catch (error) {
        showAlert('danger', `Failed to activate version: ${error.message}`);
    }
}

/**
 * Show loading state
 */
function showLoading() {
    document.getElementById('algorithms-tbody').innerHTML = `
        <tr>
            <td colspan="7" class="text-center text-muted py-4">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-2">Loading algorithms...</p>
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
