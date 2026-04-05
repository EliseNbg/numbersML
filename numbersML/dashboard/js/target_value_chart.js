/**
 * Target Value Chart JavaScript
 *
 * Handles:
 * - Symbol selection from active symbols
 * - Time range selection
 * - Response time configuration (Kalman Filter)
 * - Target value calculation trigger
 * - Candlestick + target value chart display with dual price scales
 */

const API_BASE = '/api';

let chart = null;
let candleSeries = null;
let targetSeries = null;
let normalizedSeries = null;

const RANGE_HOURS = {
    '2': 2,
    '12': 12,
    '24': 24,
    '72': 72,
    '168': 168,
};

document.addEventListener('DOMContentLoaded', function() {
    initChart();
    loadSymbols();
    setupEventHandlers();
});

function initChart() {
    const container = document.getElementById('chart-container');
    if (!container) return;

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 500,
        layout: {
            backgroundColor: '#ffffff',
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
                top: 0.1,
                bottom: 0.1,
            },
        },
        timeScale: {
            borderColor: '#ccc',
            timeVisible: true,
            secondsVisible: true,
        },
    });

    candleSeries = chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceScaleId: 'left',
    });

    targetSeries = chart.addLineSeries({
        color: '#FF9800',
        lineWidth: 3,
        title: 'Target Value (Filtered)',
        priceScaleId: 'right',
    });

    // Normalized value series (0-1 range)
    normalizedSeries = chart.addLineSeries({
        color: '#4CAF50',
        lineWidth: 2,
        title: 'Normalized (0-1)',
        priceScaleId: 'right',
    });

    window.addEventListener('resize', () => {
        chart.resize(container.clientWidth, 500);
    });
}

async function loadSymbols() {
    try {
        const response = await fetch(`${API_BASE}/symbols`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const symbols = await response.json();
        const activeSymbols = symbols.filter(s => s.is_active);

        const select = document.getElementById('target-symbol');
        select.innerHTML = '<option value="">Select symbol...</option>' +
            activeSymbols.map(s => `<option value="${s.symbol}">${s.symbol}</option>`).join('');

    } catch (error) {
        console.error('Failed to load symbols:', error);
    }
}

function setupEventHandlers() {
    document.getElementById('btn-load-chart')?.addEventListener('click', loadChartData);
    document.getElementById('btn-calculate')?.addEventListener('click', calculateTargetValues);
}

async function loadChartData() {
    const symbol = document.getElementById('target-symbol')?.value;
    const hours = document.getElementById('target-range')?.value || '2';
    const responseTime = document.getElementById('target-window')?.value || '600';
    const method = document.getElementById('target-method')?.value || 'savgol';
    const useFuture = document.getElementById('use-future')?.checked || false;
    const normWindow = document.getElementById('norm-window')?.value || '600';

    if (!symbol) {
        candleSeries.setData([]);
        targetSeries.setData([]);
        if (normalizedSeries) normalizedSeries.setData([]);
        return;
    }

    try {
        const url = `${API_BASE}/target-values?symbol=${encodeURIComponent(symbol)}&hours=${hours}&response_time=${responseTime}&method=${method}&use_future=${useFuture}&norm_window=${normWindow}`;
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (data.length === 0) {
            candleSeries.setData([]);
            targetSeries.setData([]);
            if (normalizedSeries) normalizedSeries.setData([]);
            document.getElementById('chart-title').textContent = `${symbol} - No data`;
            return;
        }

        // Candlestick data
        const candleData = data.map(c => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        }));
        candleSeries.setData(candleData);

        // Target value line - use filtered_value for WAVES (smooth trend)
        const targetData = data
            .filter(c => c.target_value !== null && c.target_value.filtered_value !== null)
            .map(c => ({
                time: c.time,
                value: c.target_value.filtered_value,
                trend: c.target_value.trend,
                diff: c.target_value.diff,
                velocity: c.target_value.velocity,
            }));
        targetSeries.setData(targetData);

        // Normalized value line (0-1 range)
        const normalizedData = data
            .filter(c => c.target_value !== null && c.target_value.normalized_value !== null)
            .map(c => ({
                time: c.time,
                value: c.target_value.normalized_value,
            }));
        normalizedSeries.setData(normalizedData);

        chart.timeScale().fitContent();

        // Count trends for display
        const trendCounts = { up: 0, down: 0, flat: 0 };
        targetData.forEach(t => { if (trendCounts[t.trend] !== undefined) trendCounts[t.trend]++; });

        document.getElementById('chart-title').textContent =
            `${symbol} - ${data.length} candles | ` +
            `↑${trendCounts.up} ↓${trendCounts.down} →${trendCounts.flat} | ` +
            `${method}${useFuture ? ' + future' : ''} window=${responseTime} | ` +
            `norm=${normWindow}`;

    } catch (error) {
        console.error('Failed to load chart data:', error);
        document.getElementById('chart-title').textContent = `Error: ${error.message}`;
    }
}

async function calculateTargetValues() {
    const symbol = document.getElementById('target-symbol')?.value;
    const hours = document.getElementById('target-range')?.value || '2';
    const responseTime = document.getElementById('target-window')?.value || '600';
    const method = document.getElementById('target-method')?.value || 'savgol';
    const useFuture = document.getElementById('use-future')?.checked || false;
    const normWindow = document.getElementById('norm-window')?.value || '600';
    const status = document.getElementById('calculate-status');

    if (!symbol) {
        status.textContent = 'Select a symbol first';
        status.className = 'text-danger';
        return;
    }

    status.textContent = `Calculating last ${hours} hours (${method}${useFuture ? ' + future' : ''})...`;
    status.className = 'text-warning';

    try {
        const url = `${API_BASE}/target-values/calculate?symbol=${encodeURIComponent(symbol)}&response_time=${responseTime}&method=${method}&use_future=${useFuture}&norm_window=${normWindow}&hours=${hours}`;
        const resp = await fetch(url, { method: 'POST' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const result = await resp.json();

        status.textContent = `Done: ${result.updated} candles updated (${result.time_range_candles} in range, ${method}${useFuture ? ' + future' : ''} window=${responseTime}, norm=${normWindow})`;
        status.className = 'text-success';

        // Reload chart
        loadChartData();

    } catch (error) {
        status.textContent = `Error: ${error.message}`;
        status.className = 'text-danger';
    }
}
