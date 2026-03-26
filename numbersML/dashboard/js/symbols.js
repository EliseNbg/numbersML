/**
 * Symbols Management JavaScript
 * 
 * Handles:
 * - List symbols
 * - Activate/deactivate symbols
 * - Bulk operations
 */

// API Base URL
const API_BASE = '/api';

// Current symbols data
let symbolsData = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Symbols page initialized');
    
    // Load symbols
    loadSymbols();
    
    // Setup event handlers
    setupEventHandlers();
});

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    // Filter toggle
    document.getElementById('filter-active')?.addEventListener('change', () => {
        renderSymbolsTable();
    });
    
    // Bulk action buttons
    document.getElementById('btn-activate-all')?.addEventListener('click', activateAllSymbols);
    document.getElementById('btn-deactivate-all')?.addEventListener('click', deactivateAllSymbols);
    document.getElementById('btn-activate-eu')?.addEventListener('click', activateEUCompliant);
}

/**
 * Load symbols from API
 */
async function loadSymbols() {
    try {
        const activeOnly = document.getElementById('filter-active')?.checked ?? false;
        const response = await fetch(`${API_BASE}/symbols?active_only=${activeOnly}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        symbolsData = await response.json();
        renderSymbolsTable();
        
    } catch (error) {
        console.error('Failed to load symbols:', error);
        document.getElementById('symbols-table-body').innerHTML = `
            <tr>
                <td colspan="10" class="text-center">
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle"></i>
                        Failed to load symbols: ${error.message}
                    </div>
                </td>
            </tr>
        `;
    }
}

/**
 * Render symbols table
 */
function renderSymbolsTable() {
    const tbody = document.getElementById('symbols-table-body');
    const activeOnly = document.getElementById('filter-active')?.checked ?? false;
    
    // Filter data
    const filtered = activeOnly 
        ? symbolsData.filter(s => s.is_active)
        : symbolsData;
    
    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center text-muted">
                    No symbols found
                </td>
            </tr>
        `;
        return;
    }
    
    // Render rows
    tbody.innerHTML = filtered.map(symbol => `
        <tr>
            <td>${symbol.symbol_id}</td>
            <td><strong>${symbol.symbol}</strong></td>
            <td>${symbol.base_asset}</td>
            <td>${symbol.quote_asset}</td>
            <td>
                ${symbol.is_active 
                    ? '<span class="badge bg-success">Active</span>' 
                    : '<span class="badge bg-secondary">Inactive</span>'}
            </td>
            <td>
                ${symbol.is_allowed 
                    ? '<span class="badge bg-success">Yes</span>' 
                    : '<span class="badge bg-danger">No</span>'}
            </td>
            <td>${symbol.tick_size}</td>
            <td>${symbol.step_size}</td>
            <td>${symbol.min_notional}</td>
            <td>
                ${symbol.is_active
                    ? `<button class="btn btn-sm btn-warning" onclick="deactivateSymbol(${symbol.symbol_id})">
                        <i class="bi bi-x-circle"></i> Deactivate
                       </button>`
                    : `<button class="btn btn-sm btn-success" onclick="activateSymbol(${symbol.symbol_id})">
                        <i class="bi bi-check-circle"></i> Activate
                       </button>`
                }
            </td>
        </tr>
    `).join('');
}

/**
 * Activate symbol
 */
async function activateSymbol(symbolId) {
    try {
        const response = await fetch(`${API_BASE}/symbols/${symbolId}/activate`, {
            method: 'PUT',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload symbols
        await loadSymbols();
        
    } catch (error) {
        alert(`Failed to activate symbol: ${error.message}`);
    }
}

/**
 * Deactivate symbol
 */
async function deactivateSymbol(symbolId) {
    try {
        const response = await fetch(`${API_BASE}/symbols/${symbolId}/deactivate`, {
            method: 'PUT',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload symbols
        await loadSymbols();
        
    } catch (error) {
        alert(`Failed to deactivate symbol: ${error.message}`);
    }
}

/**
 * Activate all symbols
 */
async function activateAllSymbols() {
    if (!confirm('Activate all symbols?')) return;
    
    try {
        const symbolIds = symbolsData.map(s => s.symbol_id);
        
        const response = await fetch(`${API_BASE}/symbols/bulk/activate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(symbolIds),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload symbols
        await loadSymbols();
        
    } catch (error) {
        alert(`Failed to activate symbols: ${error.message}`);
    }
}

/**
 * Deactivate all symbols
 */
async function deactivateAllSymbols() {
    if (!confirm('Deactivate all symbols? This will stop data collection!')) return;
    
    try {
        const symbolIds = symbolsData.map(s => s.symbol_id);
        
        const response = await fetch(`${API_BASE}/symbols/bulk/deactivate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(symbolIds),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload symbols
        await loadSymbols();
        
    } catch (error) {
        alert(`Failed to deactivate symbols: ${error.message}`);
    }
}

/**
 * Activate EU-compliant symbols
 */
async function activateEUCompliant() {
    if (!confirm('Activate only EU-compliant symbols (USDC, EUR, BTC, ETH quotes)?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/symbols/activate-eu-compliant`, {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        // Reload symbols
        await loadSymbols();
        
    } catch (error) {
        alert(`Failed to activate EU-compliant symbols: ${error.message}`);
    }
}
