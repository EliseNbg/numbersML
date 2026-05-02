/**
 * Chart JavaScript
 * 
 * Handles:
 * - TradingView Lightweight Charts integration
 * - Candlestick chart display from /api/candles
 * - Indicator overlays (SMA, EMA, RSI) from /api/candles/indicators
 */

// API Base URL
const API_BASE = '/api';

// Chart instance
let chart = null;
let candleSeries = null;
let indicatorSeries = {};

// Time range to seconds mapping
const RANGE_SECONDS = {
    '1m': 60,
    '5m': 300,
    '15m': 900,
    '1h': 3600,
    '4h': 14400,
    '1d': 86400,
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Chart page initialized');
    initChart();
    loadSymbols();
    setupEventHandlers();
});

function initChart() {
    const container = document.getElementById('chart-container');
    if (!container) return;

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 600,
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
        rightPriceScale: { borderColor: '#ccc' },
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
    });

    window.addEventListener('resize', () => {
        chart.resize(container.clientWidth, 600);
    });
}

async function loadSymbols() {
    try {
        const response = await fetch(`${API_BASE}/symbols`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const symbols = await response.json();
        const activeSymbols = symbols.filter(s => s.is_active);

        const select = document.getElementById('chart-symbol');
        select.innerHTML = '<option value="">Select symbol...</option>' +
            activeSymbols.map(s => `<option value="${s.symbol}">${s.symbol}</option>`).join('');

    } catch (error) {
        console.error('Failed to load symbols:', error);
    }
}

function setupEventHandlers() {
    document.getElementById('btn-load-chart')?.addEventListener('click', loadChartData);
    document.getElementById('chart-symbol')?.addEventListener('change', loadChartData);
    document.getElementById('btn-add-sma')?.addEventListener('click', () => toggleIndicator('sma'));
    document.getElementById('btn-add-ema')?.addEventListener('click', () => toggleIndicator('ema'));
    document.getElementById('btn-add-rsi')?.addEventListener('click', () => toggleIndicator('rsi'));
}

async function loadChartData() {
    const symbol = document.getElementById('chart-symbol')?.value;
    const range = document.getElementById('chart-range')?.value || '1h';

    if (!symbol) {
        candleSeries.setData([]);
        clearIndicators();
        return;
    }

    const seconds = RANGE_SECONDS[range] || 3600;

    try {
        // Load candles
        const candleResp = await fetch(`${API_BASE}/candles?symbol=${encodeURIComponent(symbol)}&seconds=${seconds}`);
        if (!candleResp.ok) throw new Error(`HTTP ${candleResp.status}`);
        const candles = await candleResp.json();

        if (candles.length === 0) {
            candleSeries.setData([]);
            document.getElementById('chart-title').textContent = `${symbol} - No data yet`;
            return;
        }

        // Convert to chart format (seconds timestamps)
        const chartData = candles.map(c => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        }));

        candleSeries.setData(chartData);
        chart.timeScale().fitContent();

        document.getElementById('chart-title').textContent = `${symbol} (${candles.length} candles, ${range})`;

        // Reload indicator overlays
        reloadIndicators(symbol, seconds);

    } catch (error) {
        console.error('Failed to load chart data:', error);
        document.getElementById('chart-title').textContent = `Error: ${error.message}`;
    }
}

// Map short indicator names to full database names (e.g., "sma" -> "sma_20")
function findIndicatorKey(values, shortName) {
    // Try exact match first
    if (values[shortName] !== undefined) return shortName;

    // Prefix match: find key that starts with shortName + "_"
    // Prefer shorter matches (e.g., sma_20 over sma_2000)
    const prefix = shortName + '_';
    const matches = Object.keys(values)
        .filter(key => key.startsWith(prefix))
        .sort((a, b) => a.length - b.length || a.localeCompare(b));

    return matches.length > 0 ? matches[0] : null;
}

async function reloadIndicators(symbol, seconds) {
    try {
        const resp = await fetch(`${API_BASE}/candles/indicators?symbol=${encodeURIComponent(symbol)}&seconds=${seconds}`);
        if (!resp.ok) return;

        const indicators = await resp.json();
        if (indicators.length === 0) return;

        // Update each active indicator overlay
        for (const [name, series] of Object.entries(indicatorSeries)) {
            const data = indicators
                .map(i => {
                    const key = findIndicatorKey(i.values, name);
                    return key && i.values[key] !== null && !isNaN(i.values[key])
                        ? { time: i.time, value: i.values[key] }
                        : null;
                })
                .filter(x => x !== null);

            if (data.length > 0) {
                series.setData(data);
            }
        }

    } catch (error) {
        console.error('Failed to load indicators:', error);
    }
}

function toggleIndicator(name) {
    if (indicatorSeries[name]) {
        // Remove
        chart.removeSeries(indicatorSeries[name]);
        delete indicatorSeries[name];
    } else {
        // Add
        const colors = {
            sma: '#2196F3',
            ema: '#FF9800',
            rsi: '#9C27B0',
            atr: '#795548',
            upper: '#E91E63',
            lower: '#E91E63',
            middle: '#E91E63',
            std: '#607D8B',
            macd: '#3F51B5',
            signal: '#009688',
            histogram: '#FF5722',
        };

        if (name === 'rsi' || name === 'atr') {
            // These need a separate pane - add as line on main chart for now
            indicatorSeries[name] = chart.addLineSeries({
                color: colors[name] || '#999',
                lineWidth: 2,
                priceScaleId: 'right',
                title: name.toUpperCase(),
            });
        } else {
            indicatorSeries[name] = chart.addLineSeries({
                color: colors[name] || '#999',
                lineWidth: 2,
                title: name.toUpperCase(),
            });
        }
    }

    updateIndicatorBadges();

    // Reload data if symbol is selected
    const symbol = document.getElementById('chart-symbol')?.value;
    if (symbol) {
        loadChartData();
    }
}

function clearIndicators() {
    for (const [name, series] of Object.entries(indicatorSeries)) {
        chart.removeSeries(series);
    }
    indicatorSeries = {};
    updateIndicatorBadges();
}

function updateIndicatorBadges() {
    const container = document.getElementById('active-indicators');
    const names = Object.keys(indicatorSeries);

    if (names.length === 0) {
        container.innerHTML = '<span class="text-muted">No indicators added</span>';
        return;
    }

    container.innerHTML = names.map(name => 
        `<span class="badge bg-primary" style="cursor:pointer" onclick="toggleIndicator('${name}')">${name.toUpperCase()} <i class="bi bi-x"></i></span>`
    ).join('');
}
