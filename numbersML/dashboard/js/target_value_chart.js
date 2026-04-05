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
        title: 'Target Value (Kalman)',
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
    const responseTime = document.getElementById('target-window')?.value || '200';

    if (!symbol) {
        candleSeries.setData([]);
        targetSeries.setData([]);
        return;
    }

    try {
        const url = `${API_BASE}/target-values?symbol=${encodeURIComponent(symbol)}&hours=${hours}&response_time=${responseTime}&use_kalman=true`;
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (data.length === 0) {
            candleSeries.setData([]);
            targetSeries.setData([]);
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

        // Target value line
        const targetData = data
            .filter(c => c.target_value !== null && !isNaN(c.target_value))
            .map(c => ({ time: c.time, value: c.target_value }));
        targetSeries.setData(targetData);

        chart.timeScale().fitContent();

        document.getElementById('chart-title').textContent =
            `${symbol} - ${data.length} candles, Kalman response_time=${responseTime}`;

    } catch (error) {
        console.error('Failed to load chart data:', error);
        document.getElementById('chart-title').textContent = `Error: ${error.message}`;
    }
}

async function calculateTargetValues() {
    const symbol = document.getElementById('target-symbol')?.value;
    const responseTime = document.getElementById('target-window')?.value || '200';
    const status = document.getElementById('calculate-status');

    if (!symbol) {
        status.textContent = 'Select a symbol first';
        status.className = 'text-danger';
        return;
    }

    status.textContent = 'Calculating...';
    status.className = 'text-warning';

    try {
        const url = `${API_BASE}/target-values/calculate?symbol=${encodeURIComponent(symbol)}&response_time=${responseTime}&use_kalman=true`;
        const resp = await fetch(url, { method: 'POST' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const result = await resp.json();

        status.textContent = `Done: ${result.updated} candles updated (Kalman response_time=${responseTime})`;
        status.className = 'text-success';

        // Reload chart
        loadChartData();

    } catch (error) {
        status.textContent = `Error: ${error.message}`;
        status.className = 'text-danger';
    }
}
