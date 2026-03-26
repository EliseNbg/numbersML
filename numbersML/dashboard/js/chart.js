/**
 * Chart JavaScript
 * 
 * Handles:
 * - TradingView Lightweight Charts integration
 * - Candlestick chart display
 * - Indicator overlays (SMA, EMA, RSI)
 */

// API Base URL
const API_BASE = '/api';

// Chart instance
let chart = null;
let candleSeries = null;
let indicatorSeries = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Chart page initialized');
    
    // Initialize chart
    initChart();
    
    // Load symbols for dropdown
    loadSymbols();
    
    // Setup event handlers
    setupEventHandlers();
});

/**
 * Initialize TradingView chart
 */
function initChart() {
    const container = document.getElementById('chart-container');
    
    if (!container) return;
    
    // Create chart
    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 600,
        layout: {
            backgroundColor: '#ffffff',
            textColor: '#333',
        },
        grid: {
            vertLines: {
                color: '#f0f0f0',
            },
            horzLines: {
                color: '#f0f0f0',
            },
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
            secondsVisible: false,
        },
    });
    
    // Create candlestick series
    candleSeries = chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
    });
    
    // Handle resize
    window.addEventListener('resize', () => {
        chart.resize(container.clientWidth, 600);
    });
}

/**
 * Load symbols for dropdown
 */
async function loadSymbols() {
    try {
        const response = await fetch(`${API_BASE}/symbols?active_only=true`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const symbols = await response.json();
        
        const select = document.getElementById('chart-symbol');
        select.innerHTML = '<option value="">Select symbol...</option>' +
            symbols.map(s => `<option value="${s.symbol}">${s.symbol}</option>`).join('');
        
    } catch (error) {
        console.error('Failed to load symbols:', error);
    }
}

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    document.getElementById('btn-load-chart')?.addEventListener('click', loadChartData);
    document.getElementById('btn-add-sma')?.addEventListener('click', () => addIndicator('SMA'));
    document.getElementById('btn-add-ema')?.addEventListener('click', () => addIndicator('EMA'));
    document.getElementById('btn-add-rsi')?.addEventListener('click', () => addIndicator('RSI'));
}

/**
 * Load chart data
 */
async function loadChartData() {
    const symbol = document.getElementById('chart-symbol')?.value;
    const range = document.getElementById('chart-range')?.value || '1h';
    
    if (!symbol) {
        alert('Please select a symbol');
        return;
    }
    
    console.log(`Loading chart for ${symbol} (${range})`);
    
    // TODO: Implement API endpoint for chart data
    // For now, show sample data
    loadSampleData();
}

/**
 * Load sample data (placeholder until API is ready)
 */
function loadSampleData() {
    const now = Math.floor(Date.now() / 1000);
    const data = [];
    
    let price = 50000;
    for (let i = 100; i >= 0; i--) {
        const time = now - (i * 3600);
        const change = (Math.random() - 0.5) * 1000;
        
        const open = price;
        const close = price + change;
        const high = Math.max(open, close) + Math.random() * 500;
        const low = Math.min(open, close) - Math.random() * 500;
        
        data.push({
            time,
            open,
            high,
            low,
            close,
        });
        
        price = close;
    }
    
    candleSeries.setData(data);
    
    // Update title
    document.getElementById('chart-title').textContent = 'Sample Data - Select API endpoint';
}

/**
 * Add indicator overlay
 */
function addIndicator(type) {
    console.log(`Adding indicator: ${type}`);
    
    // TODO: Calculate indicator values
    // For now, show placeholder
    alert(`${type} indicator - API endpoint needed for calculation`);
    
    // Update active indicators list
    const container = document.getElementById('active-indicators');
    const badge = document.createElement('span');
    badge.className = 'badge bg-primary';
    badge.textContent = type;
    container.innerHTML = '';
    container.appendChild(badge);
}

/**
 * Calculate SMA
 */
function calculateSMA(data, period) {
    const result = [];
    
    for (let i = period - 1; i < data.length; i++) {
        const sum = data.slice(i - period + 1, i + 1)
            .reduce((acc, d) => acc + d.close, 0);
        
        result.push({
            time: data[i].time,
            value: sum / period,
        });
    }
    
    return result;
}

/**
 * Calculate EMA
 */
function calculateEMA(data, period) {
    const result = [];
    const k = 2 / (period + 1);
    
    // First EMA is SMA
    let ema = data.slice(0, period)
        .reduce((acc, d) => acc + d.close, 0) / period;
    
    result.push({
        time: data[period - 1].time,
        value: ema,
    });
    
    // Calculate remaining EMAs
    for (let i = period; i < data.length; i++) {
        ema = data[i].close * k + ema * (1 - k);
        result.push({
            time: data[i].time,
            value: ema,
        });
    }
    
    return result;
}

/**
 * Calculate RSI
 */
function calculateRSI(data, period = 14) {
    const result = [];
    let gains = 0;
    let losses = 0;
    
    // Calculate initial average gain/loss
    for (let i = 1; i <= period; i++) {
        const change = data[i].close - data[i - 1].close;
        if (change > 0) {
            gains += change;
        } else {
            losses -= change;
        }
    }
    
    let avgGain = gains / period;
    let avgLoss = losses / period;
    
    // First RSI
    const rs = avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));
    
    result.push({
        time: data[period].time,
        value: rsi,
    });
    
    // Calculate remaining RSIs
    for (let i = period + 1; i < data.length; i++) {
        const change = data[i].close - data[i - 1].close;
        
        if (change > 0) {
            avgGain = (avgGain * (period - 1) + change) / period;
            avgLoss = (avgLoss * (period - 1)) / period;
        } else {
            avgGain = (avgGain * (period - 1)) / period;
            avgLoss = (avgLoss * (period - 1) - change) / period;
        }
        
        const rs = avgGain / avgLoss;
        const rsi = 100 - (100 / (1 + rs));
        
        result.push({
            time: data[i].time,
            value: rsi,
        });
    }
    
    return result;
}
