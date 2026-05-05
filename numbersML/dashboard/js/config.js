/**
 * Configuration Management JavaScript
 * 
 * Handles:
 * - Load configuration tables
 * - Edit table cells
 * - Insert new rows
 * - Save changes
 */

// Current table data
let currentTable = null;
let tableData = [];
let tableColumns = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Config page initialized');
    
    // Setup event handlers
    setupEventHandlers();
});

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    document.getElementById('btn-load-table')?.addEventListener('click', loadTable);
    document.getElementById('btn-add-row')?.addEventListener('click', addRow);
    document.getElementById('btn-save-changes')?.addEventListener('click', saveChanges);
}

/**
 * Load table data
 */
async function loadTable() {
    const tableName = document.getElementById('table-selector')?.value;
    
    if (!tableName) {
        alert('Please select a table');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/config/${tableName}?limit=100`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        tableData = await response.json();
        currentTable = tableName;
        
        if (tableData.length > 0) {
            tableColumns = Object.keys(tableData[0]);
        }
        
        renderTable();
        enableButtons();
        
    } catch (error) {
        console.error('Failed to load table:', error);
        alert(`Failed to load table: ${error.message}`);
    }
}

/**
 * Render table
 */
function renderTable() {
    const thead = document.getElementById('config-table-head');
    const tbody = document.getElementById('config-table-body');
    
    // Update title
    document.getElementById('table-title').textContent = 
        currentTable ? `${currentTable} (${tableData.length} rows)` : 'Data Grid';
    
    // Render header
    if (tableColumns.length > 0) {
        thead.innerHTML = tableColumns.map(col => `<th>${col}</th>`).join('');
    }
    
    // Render body
    if (tableData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="${tableColumns.length || 1}" class="text-center text-muted">
                    No data in table
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = tableData.map((row, rowIndex) => `
        <tr>
            ${tableColumns.map(col => `
                <td class="editable-cell" 
                    data-row="${rowIndex}" 
                    data-col="${col}"
                    contenteditable="true"
                    onblur="updateCell(${rowIndex}, '${col}', this.textContent)">
                    ${formatCellValue(row[col])}
                </td>
            `).join('')}
        </tr>
    `).join('');
}

/**
 * Format cell value for display
 */
function formatCellValue(value) {
    if (value === null || value === undefined) {
        return '<span class="text-muted">null</span>';
    }
    
    if (typeof value === 'object') {
        return `<code>${JSON.stringify(value)}</code>`;
    }
    
    if (typeof value === 'boolean') {
        return value 
            ? '<span class="badge bg-success">true</span>' 
            : '<span class="badge bg-secondary">false</span>';
    }
    
    return value;
}

/**
 * Update cell value
 */
function updateCell(rowIndex, col, value) {
    if (tableData[rowIndex]) {
        tableData[rowIndex][col] = value;
        console.log(`Updated ${currentTable}[${rowIndex}].${col} = ${value}`);
    }
}

/**
 * Enable action buttons
 */
function enableButtons() {
    document.getElementById('btn-add-row').disabled = false;
    document.getElementById('btn-save-changes').disabled = false;
}

/**
 * Add new row
 */
function addRow() {
    if (!currentTable || tableColumns.length === 0) {
        alert('Please load a table first');
        return;
    }
    
    // Create empty row
    const newRow = {};
    tableColumns.forEach(col => {
        newRow[col] = null;
    });
    
    // Set default for common fields
    if (newRow.is_active !== undefined) {
        newRow.is_active = true;
    }
    if (newRow.is_allowed !== undefined) {
        newRow.is_allowed = true;
    }
    
    tableData.push(newRow);
    renderTable();
    
    console.log('Added new row');
}

/**
 * Save changes
 */
async function saveChanges() {
    if (!currentTable) {
        alert('No table loaded');
        return;
    }
    
    if (!confirm(`Save changes to ${currentTable}?`)) {
        return;
    }
    
    try {
        // Save each row
        let saved = 0;
        let errors = 0;
        
        for (const row of tableData) {
            // Determine ID field
            const idField = getIdField(currentTable);
            const entryId = row[idField];
            
            if (entryId) {
                // Update existing
                const response = await fetch(`${API_BASE}/config/${currentTable}/${entryId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(row),
                });
                
                if (response.ok) {
                    saved++;
                } else {
                    errors++;
                }
            } else {
                // Insert new
                const response = await fetch(`${API_BASE}/config/${currentTable}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(row),
                });
                
                if (response.ok) {
                    const result = await response.json();
                    row[idField] = result.id;
                    saved++;
                } else {
                    errors++;
                }
            }
        }
        
        alert(`Saved: ${saved} rows\nErrors: ${errors}`);
        
        // Reload table
        await loadTable();
        
    } catch (error) {
        console.error('Failed to save changes:', error);
        alert(`Failed to save changes: ${error.message}`);
    }
}

/**
 * Get ID field for table
 */
function getIdField(tableName) {
    const idFields = {
        'system_config': 'id',
        'collection_config': 'symbol_id',
        'symbols': 'id',
        'indicator_definitions': 'name',
    };
    
    return idFields[tableName] || 'id';
}
