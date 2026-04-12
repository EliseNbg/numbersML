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

    // Scaled return target line (orange, right price scale)
    targetSeries = chart.addLineSeries({
        color: '#FF9800',
        lineWidth: 3,
        title: 'Target Return (0-1)',
        priceLineVisible: true,
        lastValueVisible: true,
        priceLineColor: '#FF9800',
        priceScaleId: 'right',
    });

    // ML prediction line (blue, right price scale)
    predictionSeries = chart.addLineSeries({
        color: '#2196F3',
        lineWidth: 3,
        title: 'ML Return Prediction (0-1)',
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
    const useSaved = document.getElementById('use-saved')?.checked ?? true;

    if (!symbol) {
        updateStatus('Please select a symbol', 'warning');
        return;
    }

    updateStatus('Loading prediction...', 'info');
    const btn = document.getElementById('btn-load-prediction');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
    }

    try {
        const url = `${API_BASE}/ml/predict?symbol=${encodeURIComponent(symbol)}&model=${encodeURIComponent(model)}&hours=${hours}&horizon=${horizon}&ensemble_size=${ensembleSize}&use_saved=${useSaved}`;
        console.log('Fetching:', url);

        // Add timeout controller for long-running request
        // Saved predictions load instantly, ML inference can be slow
        const hoursNum = parseFloat(hours);
        let timeoutMs = useSaved ? 30000 : (hoursNum <= 0.05 ? 60000 : 180000);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        updateStatus(`Loading prediction... (timeout: ${Math.round(timeoutMs/1000)}s)`, 'info');

        // Show progress with elapsed time
        const startTime = Date.now();
        const progressBar = document.getElementById('prediction-progress-bar');
        const progressRow = document.getElementById('progress-row');
        const progressTime = document.getElementById('progress-time');
        const progressStep = document.getElementById('progress-step');

        if (progressRow) progressRow.style.display = '';
        const progressInterval = setInterval(() => {
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
            const dots = '.'.repeat(Math.floor((Date.now() - startTime) / 500) % 4);
            updateStatus(`Running ML inference${dots}`, 'warning');
            if (progressTime) progressTime.textContent = `${elapsed}s elapsed`;
            if (progressBar) {
                // Animate bar from 20% to 90% (we don't know exact progress)
                const pct = Math.min(90, 20 + (Date.now() - startTime) / 300);
                progressBar.style.width = `${pct}%`;
            }
        }, 200);

        const response = await fetch(url, {
            signal: controller.signal,
            headers: { 'Accept': 'application/json' }
        });

        clearInterval(progressInterval);
        if (progressBar) progressBar.style.width = '100%';
        if (progressStep) progressStep.textContent = 'Rendering chart...';

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

        // Hide progress bar
        setTimeout(() => {
            if (progressRow) progressRow.style.display = 'none';
        }, 500);

    } catch (error) {
        console.error('Failed to load prediction:', error);
        if (error.name === 'AbortError') {
            updateStatus('Request timed out. Try a shorter time range.', 'danger');
        } else {
            updateStatus(`Error: ${error.message}`, 'danger');
        }
        // Hide progress bar on error
        setTimeout(() => {
            if (progressRow) progressRow.style.display = 'none';
        }, 500);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-play-fill"></i> Load';
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

    // Show progress bar
    const progressBar = document.getElementById('prediction-progress-bar');
    const progressRow = document.getElementById('progress-row');
    const progressTime = document.getElementById('progress-time');
    const progressStep = document.getElementById('progress-step');
    if (progressRow) progressRow.style.display = '';
    if (progressBar) progressBar.style.width = '10%';
    if (progressStep) progressStep.textContent = 'Starting prediction task';

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
        if (progressStep) progressStep.textContent = 'Running ML inference';

        // Poll for completion with progress animation
        const startTime = Date.now();
        const pollInterval = setInterval(async () => {
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
            if (progressTime) progressTime.textContent = `${elapsed}s elapsed`;

            try {
                const statusResp = await fetch(`${API_BASE}/ml/task-status?task_id=${encodeURIComponent(taskId)}`);
                const statusData = await statusResp.json();

                if (statusData.status === 'completed') {
                    clearInterval(pollInterval);
                    if (progressBar) progressBar.style.width = '100%';
                    updateStatus(
                        `Completed! Stored ${statusData.predictions_stored} predictions in ${statusData.elapsed_seconds}s.`,
                        'success'
                    );
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="bi bi-save"></i> Save';
                    }
                    // Reload chart to show saved predictions alongside target values
                    loadPrediction();
                    setTimeout(() => { if (progressRow) progressRow.style.display = 'none'; }, 500);
                } else if (statusData.status === 'failed') {
                    clearInterval(pollInterval);
                    updateStatus(`Failed: ${statusData.error}`, 'danger');
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="bi bi-save"></i> Save';
                    }
                    setTimeout(() => { if (progressRow) progressRow.style.display = 'none'; }, 500);
                } else {
                    if (progressBar) {
                        const pct = Math.min(90, 10 + (Date.now() - startTime) / 500);
                        progressBar.style.width = `${pct}%`;
                    }
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
                btn.innerHTML = '<i class="bi bi-save"></i> Save';
            }
            updateStatus('Prediction timed out after 10 minutes', 'warning');
            setTimeout(() => { if (progressRow) progressRow.style.display = 'none'; }, 500);
        }, 600000);

    } catch (error) {
        console.error('Failed to start prediction:', error);
        updateStatus(`Error: ${error.message}`, 'danger');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-save"></i> Save';
        }
        setTimeout(() => { if (progressRow) progressRow.style.display = 'none'; }, 500);
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
