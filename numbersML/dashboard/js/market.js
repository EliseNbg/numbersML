/**
 * Market Dashboard Module
 * 
 * Handles:
 * - Balance display
 * - Position tracking
 * - Order management
 * - Mode switching (paper/live)
 */

// API Configuration
const API_BASE_URL = '/api';

// State
let currentMode = 'paper';
let balances = [];
let positions = [];
let orders = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    bindEventListeners();
    loadAllData();
    
    // Auto-refresh every 30 seconds
    setInterval(loadAllData, 30000);
});

/**
 * Bind event listeners
 */
function bindEventListeners() {
    // Mode toggle
    document.querySelectorAll('input[name="trading-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            currentMode = e.target.value;
            updateModeDisplay();
            loadAllData();
        });
    });
    
    // Order type change
    document.querySelector('select[name="order_type"]').addEventListener('change', (e) => {
        const priceGroup = document.getElementById('limit-price-group');
        priceGroup.style.display = e.target.value === 'limit' ? 'block' : 'none';
    });
    
    // Submit order
    document.getElementById('btn-submit-order').addEventListener('click', submitOrder);
}

/**
 * Update mode display
 */
function updateModeDisplay() {
    const badge = document.getElementById('mode-badge');
    if (currentMode === 'live') {
        badge.className = 'badge bg-danger fs-6';
        badge.textContent = 'Live Trading';
        showAlert('warning', 'You are now in LIVE trading mode. Orders will execute with real funds!', 3000);
    } else {
        badge.className = 'badge bg-info fs-6';
        badge.textContent = 'Paper Trading';
    }
}

/**
 * Load all market data
 */
async function loadAllData() {
    await Promise.all([
        loadBalances(),
        loadPositions(),
        loadOrders()
    ]);
    updateSummaryCards();
}

/**
 * Load balances
 */
async function loadBalances() {
    try {
        const response = await fetch(`${API_BASE_URL}/market/balances?mode=${currentMode}`);
        if (response.ok) {
            balances = await response.json();
            renderBalances();
        }
    } catch (error) {
        console.error('Failed to load balances:', error);
    }
}

/**
 * Render balances table
 */
function renderBalances() {
    const tbody = document.getElementById('balances-tbody');
    
    if (balances.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted py-3">
                    No balances available
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = balances.map(b => `
        <tr>
            <td><strong>${escapeHtml(b.asset)}</strong></td>
            <td>${formatNumber(b.free)}</td>
            <td>${formatNumber(b.locked)}</td>
            <td><strong>${formatNumber(b.total)}</strong></td>
        </tr>
    `).join('');
}

/**
 * Load positions
 */
async function loadPositions() {
    try {
        const response = await fetch(`${API_BASE_URL}/market/positions?mode=${currentMode}`);
        if (response.ok) {
            positions = await response.json();
            renderPositions();
        }
    } catch (error) {
        console.error('Failed to load positions:', error);
    }
}

/**
 * Render positions table
 */
function renderPositions() {
    const tbody = document.getElementById('positions-tbody');
    
    if (positions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted py-3">
                    No open positions
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = positions.map(p => {
        const pnlClass = p.unrealized_pnl >= 0 ? 'text-success' : 'text-danger';
        const pnlIcon = p.unrealized_pnl >= 0 ? 'bi-arrow-up' : 'bi-arrow-down';
        
        return `
            <tr>
                <td>${escapeHtml(p.symbol)}</td>
                <td>
                    <span class="badge bg-${p.side === 'LONG' ? 'success' : 'danger'}">
                        ${p.side}
                    </span>
                </td>
                <td>${formatNumber(p.quantity)}</td>
                <td class="${pnlClass}">
                    <i class="bi ${pnlIcon}"></i>
                    $${formatNumber(Math.abs(p.unrealized_pnl))}
                </td>
            </tr>
        `;
    }).join('');
}

/**
 * Load orders
 */
async function loadOrders() {
    try {
        // Try to get orders from API
        const response = await fetch(`${API_BASE_URL}/market/orders?mode=${currentMode}`);
        if (response.ok) {
            orders = await response.json();
        } else {
            // Fallback to empty list
            orders = [];
        }
        renderOrders();
    } catch (error) {
        console.error('Failed to load orders:', error);
        orders = [];
        renderOrders();
    }
}

/**
 * Render orders table
 */
function renderOrders() {
    const tbody = document.getElementById('orders-tbody');
    
    if (orders.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center text-muted py-4">
                    <i class="bi bi-inbox" style="font-size: 2rem;"></i>
                    <p class="mt-2">No orders yet</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = orders.map(o => {
        const statusBadge = getOrderStatusBadge(o.status);
        const sideBadge = o.side === 'BUY' 
            ? '<span class="badge bg-success">Buy</span>' 
            : '<span class="badge bg-danger">Sell</span>';
        
        return `
            <tr>
                <td><code>${escapeHtml(o.id?.slice(0, 12) || 'N/A')}</code></td>
                <td>${escapeHtml(o.symbol)}</td>
                <td>${sideBadge}</td>
                <td>${escapeHtml(o.order_type)}</td>
                <td>${formatNumber(o.quantity)}</td>
                <td>${o.price ? formatNumber(o.price) : '<span class="text-muted">Market</span>'}</td>
                <td>${statusBadge}</td>
                <td>${o.created_at ? new Date(o.created_at).toLocaleString() : '-'}</td>
                <td>
                    ${o.status === 'PENDING' ? `
                        <button class="btn btn-sm btn-outline-danger" onclick="cancelOrder('${o.id}')">
                            <i class="bi bi-x"></i>
                        </button>
                    ` : '-'}
                </td>
            </tr>
        `;
    }).join('');
}

/**
 * Get order status badge
 */
function getOrderStatusBadge(status) {
    const badges = {
        PENDING: '<span class="badge bg-warning">Pending</span>',
        FILLED: '<span class="badge bg-success">Filled</span>',
        PARTIAL: '<span class="badge bg-info">Partial</span>',
        CANCELLED: '<span class="badge bg-secondary">Cancelled</span>',
        REJECTED: '<span class="badge bg-danger">Rejected</span>'
    };
    return badges[status] || `<span class="badge bg-secondary">${status}</span>`;
}

/**
 * Submit new order
 */
async function submitOrder() {
    const form = document.getElementById('create-order-form');
    const formData = new FormData(form);
    
    const payload = {
        symbol: formData.get('symbol'),
        side: formData.get('side'),
        order_type: formData.get('order_type'),
        quantity: parseFloat(formData.get('quantity')),
        price: formData.get('price') ? parseFloat(formData.get('price')) : null
    };
    
    // Validation
    if (payload.order_type === 'limit' && !payload.price) {
        showAlert('danger', 'Limit price is required for limit orders');
        return;
    }
    
    try {
        const btn = document.getElementById('btn-submit-order');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Submitting...';
        
        const response = await fetch(`${API_BASE_URL}/market/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ...payload,
                mode: currentMode
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('createOrderModal')).hide();
        form.reset();
        
        showAlert('success', `Order ${result.id?.slice(0, 8)} submitted successfully`);
        loadOrders();
        
    } catch (error) {
        showAlert('danger', `Order failed: ${error.message}`);
    } finally {
        const btn = document.getElementById('btn-submit-order');
        btn.disabled = false;
        btn.innerHTML = 'Submit Order';
    }
}

/**
 * Cancel order
 */
async function cancelOrder(orderId) {
    if (!confirm('Are you sure you want to cancel this order?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/market/orders/${orderId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        showAlert('success', 'Order cancelled');
        loadOrders();
    } catch (error) {
        showAlert('danger', `Cancel failed: ${error.message}`);
    }
}

/**
 * Update summary cards
 */
function updateSummaryCards() {
    // Calculate total balance
    const totalBalance = balances.reduce((sum, b) => sum + b.total, 0);
    document.getElementById('total-balance').textContent = `$${formatNumber(totalBalance, 2)}`;
    
    // Count open positions
    document.getElementById('open-positions').textContent = positions.length;
    
    // Count pending orders
    const pendingCount = orders.filter(o => o.status === 'PENDING').length;
    document.getElementById('pending-orders').textContent = pendingCount;
    
    // Calculate PnL
    const totalPnL = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
    const pnlElement = document.getElementById('today-pnl');
    pnlElement.textContent = `${totalPnL >= 0 ? '+' : '-'}$${formatNumber(Math.abs(totalPnL), 2)}`;
    pnlElement.className = totalPnL >= 0 ? 'text-white' : 'text-danger';
}

/**
 * Refresh functions
 */
function refreshBalances() {
    loadBalances();
}

function refreshPositions() {
    loadPositions();
}

function refreshOrders() {
    loadOrders();
}

/**
 * Show alert
 */
function showAlert(type, message, duration = 5000) {
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
    }, duration);
}

/**
 * Format number
 */
function formatNumber(value, decimals = 4) {
    if (value === null || value === undefined) return '-';
    const num = parseFloat(value);
    if (isNaN(num)) return '-';
    return num.toLocaleString('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: decimals
    });
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
