/**
 * ML Prediction Chart Page
 * 
 * Displays candlestick chart with:
 * - OHLC candlestick data
 * - Target values (orange line)
 * - ML predictions (blue line)
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
            option.textContent = `${m.label} (${m.size_mb} MB)`;
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
        rightPriceScale: {
            borderColor: '#ccc',
        },
        timeScale: {
            borderColor: '#ccc',
            timeVisible: true,
            secondsVisible: true,
        },
    });

    // Candlestick series
    candleSeries = chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
    });

    // Target value line (orange) - make it more visible
    targetSeries = chart.addLineSeries({
        color: '#FF9800',
        lineWidth: 3,
        title: 'Target Value',
        priceLineVisible: true,
        lastValueVisible: true,
        priceLineColor: '#FF9800',
        priceScaleId: 'right',
    });

    // ML prediction line (blue) - make it more visible
    predictionSeries = chart.addLineSeries({
        color: '#2196F3',
        lineWidth: 3,
        title: 'ML Prediction',
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

    if (!symbol) {
        updateStatus('Please select a symbol', 'warning');
        return;
    }

    if (!model) {
        updateStatus('Please select a model', 'warning');
        return;
    }

    updateStatus('Loading prediction...', 'info');
    const btn = document.getElementById('btn-load-prediction');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
    }

    try {
        const url = `${API_BASE}/ml/predict?symbol=${encodeURIComponent(symbol)}&model=${encodeURIComponent(model)}&hours=${hours}`;
        console.log('Fetching:', url);
        
        // Add timeout controller for long-running request (20 minutes)
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1200000);  // 20 minute timeout
        
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

        // Set target value data
        if (data.targets && data.targets.length > 0) {
            console.log('Setting target data:', data.targets.length, 'points');
            targetSeries.setData(data.targets);
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
