/**
 * Indicators Management JavaScript
 * 
 * Handles:
 * - List indicators
 * - Register new indicators
 * - Activate/deactivate indicators
 * - Update indicator parameters
 */

// Current indicators data
let indicatorsData = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Indicators page initialized');
    
    // Load indicators
    loadIndicators();
    
    // Setup event handlers
    setupEventHandlers();
});

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    // Filter controls
    document.getElementById('filter-active')?.addEventListener('change', () => {
        renderIndicatorsTable();
    });
    
    document.getElementById('filter-category')?.addEventListener('change', () => {
        renderIndicatorsTable();
    });
    
    // Register button
    document.getElementById('btn-register-indicator')?.addEventListener('click', registerIndicator);
}

/**
 * Load indicators from API
 */
async function loadIndicators() {
    try {
        const activeOnly = document.getElementById('filter-active')?.checked ?? false;
        const category = document.getElementById('filter-category')?.value ?? '';
        
        let url = `${API_BASE}/indicators?active_only=${activeOnly}`;
        if (category) {
            url += `&category=${category}`;
        }
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        indicatorsData = await response.json();
        renderIndicatorsTable();
        
    } catch (error) {
        console.error('Failed to load indicators:', error);
        document.getElementById('indicators-table-body').innerHTML = `
            <tr>
                <td colspan="7" class="text-center">
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle"></i>
                        Failed to load indicators: ${error.message}
                    </div>
                </td>
            </tr>
        `;
    }
}

/**
 * Render indicators table
 */
function renderIndicatorsTable() {
    const tbody = document.getElementById('indicators-table-body');
    const activeOnly = document.getElementById('filter-active')?.checked ?? false;
    const category = document.getElementById('filter-category')?.value ?? '';
    
    // Filter data
    let filtered = indicatorsData;
    if (activeOnly) {
        filtered = filtered.filter(i => i.is_active);
    }
    if (category) {
        filtered = filtered.filter(i => i.category === category);
    }
    
    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted">
                    No indicators found
                </td>
            </tr>
        `;
        return;
    }
    
    // Render rows
    tbody.innerHTML = filtered.map(indicator => `
        <tr>
            <td><strong>${indicator.name}</strong></td>
            <td>${indicator.class_name}</td>
            <td>${indicator.module_path}</td>
            <td>
                <span class="badge bg-${getCategoryColor(indicator.category)}">
                    ${indicator.category}
                </span>
            </td>
            <td>
                <code>${JSON.stringify(indicator.params || {})}</code>
            </td>
            <td>
                ${indicator.is_active 
                    ? '<span class="badge bg-success">Active</span>' 
                    : '<span class="badge bg-secondary">Inactive</span>'}
            </td>
            <td>
                ${indicator.is_active
                    ? `<button class="btn btn-sm btn-warning" onclick="deactivateIndicator('${indicator.name}')">
                        <i class="bi bi-x-circle"></i> Deactivate
                       </button>`
                    : `<button class="btn btn-sm btn-success" onclick="activateIndicator('${indicator.name}')">
                        <i class="bi bi-check-circle"></i> Activate
                       </button>`
                }
                <button class="btn btn-sm btn-danger" onclick="unregisterIndicator('${indicator.name}')">
                    <i class="bi bi-trash"></i> Unregister
                </button>
            </td>
        </tr>
    `).join('');
}

/**
 * Get category color
 */
function getCategoryColor(category) {
    const colors = {
        'momentum': 'primary',
        'trend': 'success',
        'volatility': 'warning',
        'volume': 'info',
    };
    return colors[category] || 'secondary';
}

/**
 * Activate indicator
 */
async function activateIndicator(name) {
    try {
        const response = await fetch(`${API_BASE}/indicators/${name}/activate`, {
            method: 'PUT',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload indicators
        await loadIndicators();
        
    } catch (error) {
        alert(`Failed to activate indicator: ${error.message}`);
    }
}

/**
 * Deactivate indicator
 */
async function deactivateIndicator(name) {
    try {
        const response = await fetch(`${API_BASE}/indicators/${name}/deactivate`, {
            method: 'PUT',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload indicators
        await loadIndicators();
        
    } catch (error) {
        alert(`Failed to deactivate indicator: ${error.message}`);
    }
}

/**
 * Unregister indicator
 */
async function unregisterIndicator(name) {
    if (!confirm(`Unregister indicator "${name}"? This will deactivate it.`)) return;
    
    try {
        const response = await fetch(`${API_BASE}/indicators/${name}`, {
            method: 'DELETE',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload indicators
        await loadIndicators();
        
    } catch (error) {
        alert(`Failed to unregister indicator: ${error.message}`);
    }
}

/**
 * Register new indicator
 */
async function registerIndicator() {
    // Get form values
    const name = document.getElementById('indicator-name')?.value;
    const className = document.getElementById('indicator-class')?.value;
    const modulePath = document.getElementById('indicator-module')?.value;
    const category = document.getElementById('indicator-category')?.value;
    const paramsStr = document.getElementById('indicator-params')?.value;
    const isActive = document.getElementById('indicator-active')?.checked ?? true;
    
    // Validate
    if (!name || !className || !modulePath || !category) {
        alert('Please fill in all required fields');
        return;
    }
    
    // Parse params
    let params = {};
    if (paramsStr) {
        try {
            params = JSON.parse(paramsStr);
        } catch (e) {
            alert('Invalid JSON in parameters field');
            return;
        }
    }
    
    try {
        const response = await fetch(`${API_BASE}/indicators`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                class_name: className,
                module_path: modulePath,
                category,
                params,
                is_active: isActive,
            }),
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('registerIndicatorModal'));
        modal.hide();
        
        // Clear form
        document.getElementById('register-indicator-form')?.reset();
        
        // Reload indicators
        await loadIndicators();
        
        alert('Indicator registered successfully!');
        
    } catch (error) {
        alert(`Failed to register indicator: ${error.message}`);
    }
}
