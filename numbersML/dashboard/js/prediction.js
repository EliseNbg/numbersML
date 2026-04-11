/**
 * ML Prediction Chart Page
 *
 * Displays candlestick chart with:
 * - OHLC candlestick data (left price scale)
 * - Target values (orange line, right price scale)
 * - ML predictions (blue line, right price scale)
 */

const API_BASE = '/api';

let chart = null;
let candleSeries = null;
let targetSeries = null;
let predictionSeries = null;

/**
 * Initialize the page when DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
    loadSymbols();
    loadModels();
    setupEventHandlers();
});

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    document.getElementById('btn-load-prediction')?.addEventListener('click', loadPrediction);
    document.getElementById('btn-predict-save')?.addEventListener('click', predictAndSave);
}

/**
 * Load available symbols and populate dropdown
 */
async function loadSymbols() {
    const select = document.getElementById('prediction-symbol');
    if (!select) return;

    try {
        const response = await fetch(`${API_BASE}/symbols`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const symbols = await response.json();
        
        // Filter to active symbols only
        const activeSymbols = symbols.filter(s => s.is_active);
        
        select.innerHTML = '<option value="">Select symbol...</option>';
        activeSymbols.forEach(s => {
            const option = document.createElement('option');
            option.value = s.symbol;
            option.textContent = s.symbol;
            select.appendChild(option);
        });

        // Auto-select first symbol
        if (activeSymbols.length > 0) {
            select.value = activeSymbols[0].symbol;
        }
    } catch (error) {
        console.error('Failed to load symbols:', error);
        select.innerHTML = '<option value="">Error loading symbols</option>';
    }
}

/**
 * Load available models and populate dropdown
 */
async function loadModels() {
    const select = document.getElementById('prediction-model');
    if (!select) return;

    try {
        const response = await fetch(`${API_BASE}/ml/models`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const models = await response.json();
        
        select.innerHTML = '<option value="">Select model...</option>';
        models.forEach(m => {
            const option = document.createElement('option');
            option.value = m.name;
            option.textContent = `${m.label} - ${m.name} (${m.size_mb} MB)`;
            select.appendChild(option);
        });

        // Auto-select first model
        if (models.length > 0) {
            select.value = models[0].name;
        }
    } catch (error) {
        console.error('Failed to load models:', error);
        select.innerHTML = '<option value="">No models available</option>';
    }
}

/**
 * Initialize TradingView chart
 */
function initChart() {
    if (chart) {
        chart.remove();
    }

    const container = document.getElementById('chart-container');
    if (!container) return;

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 600,
        layout: {
            background: { type: 'solid', color: '#ffffff' },
            textColor: '#333',
        },
        grid: {
            vertLines: { color: '#f0f0f0' },
            horzLines: { color: '#f0f0f0' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        leftPriceScale: {
            borderColor: '#ccc',
            visible: true,
            scaleMargins: {
                top: 0.1,
                bottom: 0.1,
            },
        },
        rightPriceScale: {
            borderColor: '#FF9800',
            visible: true,
            scaleMargins: {
                top: 0.05,
                bottom: 0.05,
            },
            autoScale: true,
        },
        timeScale: {
            borderColor: '#ccc',
            timeVisible: true,
            secondsVisible: true,
        },
    });

    // Candlestick series (left price scale)
    candleSeries = chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceScaleId: 'left',
    });

    // Target price return line (orange, right price scale)
    targetSeries = chart.addLineSeries({
        color: '#FF9800',
        lineWidth: 3,
        title: 'Target Return',
        priceLineVisible: true,
        lastValueVisible: true,
        priceLineColor: '#FF9800',
        priceScaleId: 'right',
    });

    // ML prediction line (blue, right price scale)
    predictionSeries = chart.addLineSeries({
        color: '#2196F3',
        lineWidth: 3,
        title: 'ML Return Prediction',
        priceLineVisible: true,
        lastValueVisible: true,
        priceLineColor: '#2196F3',
        priceScaleId: 'right',
    });

    // Handle resize
    window.addEventListener('resize', () => {
        if (chart && container) {
            chart.resize(container.clientWidth, 600);
        }
    });
}

/**
 * Load prediction data and update chart
 */
async function loadPrediction() {
    const symbol = document.getElementById('prediction-symbol')?.value;
    const model = document.getElementById('prediction-model')?.value;
    const hours = document.getElementById('prediction-hours')?.value;
    const horizon = document.getElementById('prediction-horizon')?.value || 30;
    const ensembleSize = document.getElementById('ensemble-size')?.value || 5;

    if (!symbol) {
        updateStatus('Please select a symbol', 'warning');
        return;
    }

    if (!model) {
        updateStatus('Please select a model', 'warning');
        return;
    }
    
    // Validate minimum time range (need at least 120 vectors = ~2 minutes)
    const hoursNum = parseFloat(hours);
    if (hoursNum < 0.033) {
        updateStatus('Time range too short. Minimum is 2 minutes (120 vectors required)', 'warning');
        return;
    }

    updateStatus('Loading prediction...', 'info');
    const btn = document.getElementById('btn-load-prediction');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
    }

    try {
        const url = `${API_BASE}/ml/predict?symbol=${encodeURIComponent(symbol)}&model=${encodeURIComponent(model)}&hours=${hours}&horizon=${horizon}&ensemble_size=${ensembleSize}`;
        console.log('Fetching:', url);

        // Add timeout controller for long-running request
        // CNN+GRU models are slow on CPU - adjust timeout based on time range
        const hoursNum = parseFloat(hours);
        let timeoutMs = 120000; // Default 2 minutes
        
        if (hoursNum <= 0.05) {
            timeoutMs = 60000; // 1 minute for very short ranges
        } else if (hoursNum <= 1) {
            timeoutMs = 1800000; // 30 minutes for short ranges
        } else if (hoursNum <= 24) {
            timeoutMs = 3000000; // 50 minutes for medium ranges
        } else {
            timeoutMs = 6010000; // 100 minutes for long ranges
        }
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        updateStatus(`Loading prediction... (timeout: ${Math.round(timeoutMs/1000)}s)`, 'info');

        const response = await fetch(url, {
            signal: controller.signal,
            headers: { 'Accept': 'application/json' }
        });

        clearTimeout(timeoutId);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();
        console.log('Response received:', data);
        
        // Initialize chart
        initChart();

        // Set candlestick data
        if (data.candles && data.candles.length > 0) {
            console.log('Setting candle data:', data.candles.length, 'points');
            candleSeries.setData(data.candles);
        }

        // Set target value data (normalized 0-1)
        if (data.targets && data.targets.length > 0) {
            console.log('Setting target data:', data.targets.length, 'points');
            console.log('Sample target:', data.targets[0]);
            
            // Ensure targets are properly formatted for lightweight charts
            const targetData = data.targets.map(t => ({
                time: t.time,
                value: t.value
            }));
            targetSeries.setData(targetData);
        } else {
            console.log('No target values to display');
        }

        // Set prediction data
        if (data.predictions && data.predictions.length > 0) {
            console.log('Setting prediction data:', data.predictions.length, 'points');
            console.log('First prediction:', data.predictions[0]);
            // Convert prediction format for lightweight charts
            const predictionData = data.predictions.map(p => ({
                time: p.time,
                value: p.predicted_target
            }));
            predictionSeries.setData(predictionData);
        } else {
            console.log('No predictions to display');
        }

        // Update statistics
        document.getElementById('stat-candles').textContent = data.candles_count;
        document.getElementById('stat-targets').textContent = data.targets_count;
        document.getElementById('stat-vectors').textContent = data.vectors_count || 0;
        document.getElementById('stat-predictions').textContent = data.predictions_count;

        // Fit content to show all series
        chart.timeScale().fitContent();
        
        // Auto-scale price axis to include all data
        chart.priceScale('right').applyOptions({
            autoScale: true,
            scaleMargins: {
                top: 0.1,
                bottom: 0.1,
            },
        });

        updateStatus(
            `Loaded ${data.candles_count} candles, ${data.targets_count} targets, ${data.predictions_count} predictions`,
            'success'
        );

    } catch (error) {
        console.error('Failed to load prediction:', error);
        if (error.name === 'AbortError') {
            updateStatus('Request timed out. Try a shorter time range.', 'danger');
        } else {
            updateStatus(`Error: ${error.message}`, 'danger');
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-play-fill"></i> Load & Predict';
        }
    }
}

/**
 * Predict and save results to DB
 */
async function predictAndSave() {
    const symbol = document.getElementById('prediction-symbol')?.value;
    const model = document.getElementById('prediction-model')?.value;
    const hours = document.getElementById('prediction-hours')?.value;
    const horizon = document.getElementById('prediction-horizon')?.value || 30;
    const ensembleSize = document.getElementById('ensemble-size')?.value || 5;

    if (!symbol) { updateStatus('Please select a symbol', 'warning'); return; }
    if (!model) { updateStatus('Please select a model', 'warning'); return; }

    updateStatus('Starting prediction task...', 'info');
    const btn = document.getElementById('btn-predict-save');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Running...';
    }

    try {
        const url = `${API_BASE}/ml/predict-and-save?symbol=${encodeURIComponent(symbol)}&model=${encodeURIComponent(model)}&hours=${hours}&horizon=${horizon}&ensemble_size=${ensembleSize}`;
        const resp = await fetch(url, { method: 'POST' });
        if (!resp.ok) {
            const error = await resp.json();
            throw new Error(error.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        const taskId = data.task_id;

        updateStatus(`Task started: ${taskId}. Polling status...`, 'info');

        // Poll for completion
        const pollInterval = setInterval(async () => {
            try {
                const statusResp = await fetch(`${API_BASE}/ml/task-status?task_id=${encodeURIComponent(taskId)}`);
                const statusData = await statusResp.json();

                if (statusData.status === 'completed') {
                    clearInterval(pollInterval);
                    updateStatus(
                        `Completed! Stored ${statusData.predictions_stored} predictions in ${statusData.elapsed_seconds}s.`,
                        'success'
                    );
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="bi bi-save"></i> Predict & Save';
                    }
                } else if (statusData.status === 'failed') {
                    clearInterval(pollInterval);
                    updateStatus(`Failed: ${statusData.error}`, 'danger');
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="bi bi-save"></i> Predict & Save';
                    }
                } else {
                    updateStatus(`Running... (${statusData.status})`, 'info');
                }
            } catch (e) {
                // Still polling, ignore errors
            }
        }, 2000);

        // Timeout after 10 minutes
        setTimeout(() => {
            clearInterval(pollInterval);
            if (btn && btn.disabled) {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-save"></i> Predict & Save';
            }
        }, 600000);

    } catch (error) {
        console.error('Failed to start prediction:', error);
        updateStatus(`Error: ${error.message}`, 'danger');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-save"></i> Predict & Save';
        }
    }
}

/**
 * Update status message
 */
function updateStatus(message, type = 'info') {
    const status = document.getElementById('prediction-status');
    if (!status) return;

    const icons = {
        info: 'bi-info-circle',
        success: 'bi-check-circle',
        warning: 'bi-exclamation-triangle',
        danger: 'bi-x-circle',
    };

    status.className = `text-${type}`;
    status.innerHTML = `<i class="bi ${icons[type] || icons.info}"></i> ${message}`;
}
