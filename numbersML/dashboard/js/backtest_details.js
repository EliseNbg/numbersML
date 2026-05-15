/**
 * Strategy Backtest Details Dashboard Module
 *
 * Handles:
 * - Loading backtest details from API
 * - Rendering candlestick chart with trade markers
 * - Displaying trade blotter
 * - Showing debug logs
 */

// API Configuration
const API_BASE = "/api";

// State
let chart = null;
let candlestickSeries = null;
let currentBacktestId = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", async () => {
    console.log("Backtest details module initialized");

    // Get backtest_id from URL
    const urlParams = new URLSearchParams(window.location.search);
    currentBacktestId = urlParams.get("backtest_id");

    if (!currentBacktestId) {
        showError("No backtest ID provided in URL");
        return;
    }

    await loadBacktestDetails(currentBacktestId);
});

/**
 * Load backtest details from API
 */
async function loadBacktestDetails(backtestId) {
    try {
        const response = await fetch(`${API_BASE}/strategy-backtests/results/${backtestId}`);
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error("Backtest not found");
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        renderBacktestDetails(data);

    } catch (error) {
        console.error("Failed to load backtest details:", error);
        showError(`Failed to load backtest: ${error.message}`);
    }
}

/**
 * Render backtest details to the page
 */
function renderBacktestDetails(data) {
    // Hide loading, show results
    document.getElementById("loading-panel").style.display = "none";
    document.getElementById("results-panel").style.display = "block";

    // Update header meta
    document.getElementById("backtest-meta").textContent =
        `${data.strategy_name || "Unknown"} v${data.strategy_version || "-"} | ${data.symbol || "-"} | ${formatDateShort(data.time_range_start)} - ${formatDateShort(data.time_range_end)}`;

    // Update metrics
    updateMetrics(data.metrics);

    // Render chart
    renderCandlestickChart(data.price_series, data.trades);

    // Render trades
    renderTradesTable(data.trades);

    // Render debug log
    renderDebugLog(data.debug_messages);

    // Render detailed metrics
    renderDetailedMetrics(data.metrics, data.parameters);
}

/**
 * Update main metric cards
 */
function updateMetrics(metrics) {
    if (!metrics) return;

    const returnEl = document.getElementById("metric-return");
    const returnPct = metrics.total_return_pct || 0;
    returnEl.textContent = `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}%`;
    returnEl.className = `metric-value ${returnPct >= 0 ? "positive" : "negative"}`;

    const ddEl = document.getElementById("metric-drawdown");
    const dd = metrics.max_drawdown_pct || 0;
    ddEl.textContent = `${dd.toFixed(2)}%`;
    ddEl.className = "metric-value negative";

    document.getElementById("metric-sharpe").textContent = (metrics.sharpe_ratio || 0).toFixed(2);
    document.getElementById("metric-winrate").textContent = `${((metrics.win_rate || 0) * 100).toFixed(1)}%`;
    document.getElementById("metric-trades").textContent = metrics.total_trades || 0;
    document.getElementById("metric-profit-factor").textContent = (metrics.profit_factor || 0).toFixed(2);
}

/**
 * Render candlestick chart with trade markers
 */
function renderCandlestickChart(priceSeries, trades) {
    const container = document.getElementById("backtest-chart");

    if (!priceSeries || priceSeries.length === 0) {
        container.innerHTML = '<div class="text-center text-muted p-5">No price data available</div>';
        return;
    }

    // Initialize chart if not exists
    if (!chart) {
        const containerWidth = Math.max(container.clientWidth || 800, 800);
        chart = LightweightCharts.createChart(container, {
            width: containerWidth,
            height: 500,
            layout: {
                backgroundColor: "#ffffff",
                textColor: "#000000",
            },
            grid: {
                vertLines: { visible: false },
                horzLines: { visible: false },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: "#cccccc",
            },
            timeScale: {
                borderColor: "#cccccc",
            },
        });

        candlestickSeries = chart.addCandlestickSeries({
            upColor: "#26a69a",
            downColor: "#ef5350",
            borderDownColor: "#ef5350",
            borderUpColor: "#26a69a",
            wickDownColor: "#ef5350",
            wickUpColor: "#26a69a",
        });
    }

    // Prepare candlestick data - downsample if too many points for performance
    // Use ?? (nullish coalescing) - NOT || - so that legitimate 0 prices are
    // preserved and only null / undefined values fall back.
    let candleData = priceSeries
        .map(p => ({
            time: formatTimeForChart(p.timestamp),
            open: p.open ?? p.close,
            high: p.high ?? p.close,
            low:  p.low  ?? p.close,
            close: p.close,
        }))
        // Drop rows with null close or non-finite time — Lightweight Charts
        // throws "Value is null" on either condition.
        .filter(c => c.close != null && isFinite(c.time));

    // Downsample to max 5000 points for chart performance
    if (candleData.length > 5000) {
        const factor = Math.ceil(candleData.length / 5000);
        candleData = candleData.filter((_, i) => i % factor === 0);
    }

    candlestickSeries.setData(candleData);

    // Create trade markers using the downsampled data's available times
    const markers = createTradeMarkers(trades, candleData);

    // Debug: log marker shape to console
    console.log("markers:", markers.length, markers.slice(0, 2));

    candlestickSeries.setMarkers(markers);
}

/**
 * Create trade markers for chart
 * Adjusts timestamps to match nearest available candle for visibility
 * @param trades - Array of trade objects with entry_time, exit_time, entry_price, exit_price, pnl
 * @param priceSeries - Array of candle data with 'time' property (already converted to Unix timestamp)
 */
function createTradeMarkers(trades, priceSeries) {
    if (!trades || trades.length === 0) return [];
    if (!priceSeries || priceSeries.length === 0) return [];

    // Build a set of available timestamps from candle data
    const availableTimes = new Set(priceSeries.map(p => p.time));

    // Limit to 50 most recent trades for performance
    const limitedTrades = trades.slice(-50);

    const markers = [];

    limitedTrades.forEach(trade => {
        // Build entry marker when entry price and time are both valid
        if (trade.entry_price != null) {
            const entryTime = formatTimeForChart(trade.entry_time);
            if (isFinite(entryTime) && isFinite(trade.entry_price)) {
                const t = availableTimes.has(entryTime)
                    ? entryTime : findNearestTime(entryTime, availableTimes);
                markers.push({
                    time: t,
                    position: "belowBar",
                    color: "#26a69a",
                    shape: "circle",
                    text: "BUY",
                    price: trade.entry_price,
                    tradeId: trade.entry_time,
                });
            }
        }

        // Build exit marker when exit data is present and valid
        if (trade.exit_time && trade.exit_price != null) {
            const exitTime = formatTimeForChart(trade.exit_time);
            if (isFinite(exitTime) && isFinite(trade.exit_price)) {
                const t = availableTimes.has(exitTime)
                    ? exitTime : findNearestTime(exitTime, availableTimes);
                const isProfit = trade.pnl >= 0;
                markers.push({
                    time: t,
                    position: "aboveBar",
                    color: isProfit ? "#26a69a" : "#ef5350",
                    shape: "square",
                    text: isProfit ? "SELL" : "LOSS",
                    price: trade.exit_price,
                    tradeId: trade.exit_time,
                });
            }
        }
    });

    console.assert(Array.isArray(markers), "createTradeMarkers must return an array");
    return markers;
}

/**
 * Find nearest available time for marker alignment
 */
function findNearestTime(targetTime, availableTimes) {
    const times = Array.from(availableTimes).sort((a, b) => a - b);
    let nearest = times[0];
    let minDiff = Math.abs(targetTime - nearest);

    for (const t of times) {
        const diff = Math.abs(targetTime - t);
        if (diff < minDiff) {
            minDiff = diff;
            nearest = t;
        }
    }
    return nearest;
}

/**
 * Format timestamp for Lightweight Charts
 * Returns Unix timestamp (seconds) for proper intraday charting
 */
function formatTimeForChart(timestamp) {
    if (typeof timestamp === "number") {
        return timestamp;
    }
    if (typeof timestamp === "string") {
        // Check if already in YYYY-MM-DD format (daily) - keep as-is
        if (/^\d{4}-\d{2}-\d{2}$/.test(timestamp)) {
            return timestamp;
        }
        // For ISO datetime strings, convert to Unix timestamp
        const date = new Date(timestamp);
        return Math.floor(date.getTime() / 1000);
    }
    const date = new Date(timestamp);
    return Math.floor(date.getTime() / 1000);
}

/**
 * Render trades table
 */
function renderTradesTable(trades) {
    const tbody = document.getElementById("trades-tbody");
    const countBadge = document.getElementById("trade-count");

    tbody.innerHTML = "";

    if (!trades || trades.length === 0) {
        countBadge.textContent = "0 trades";
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No trades</td></tr>';
        return;
    }

    countBadge.textContent = `${trades.length} trades`;

    trades.forEach(trade => {
        const row = document.createElement("tr");
        row.className = trade.pnl >= 0 ? "trade-row-buy" : "trade-row-sell";

        const pnlClass = trade.pnl >= 0 ? "positive" : "negative";
        const pnlSign = trade.pnl >= 0 ? "+" : "";

        const duration = trade.exit_time && trade.entry_time
            ? calculateDuration(trade.entry_time, trade.exit_time)
            : "-";

        row.innerHTML = `
            <td>${formatDateShort(trade.entry_time)}</td>
            <td>${trade.exit_time ? formatDateShort(trade.exit_time) : "-"}</td>
            <td>${trade.symbol || "-"}</td>
            <td>${trade.entry_price?.toFixed(4) || "-"}</td>
            <td>${trade.exit_price?.toFixed(4) || "-"}</td>
            <td class="${pnlClass}">${pnlSign}$${trade.pnl?.toFixed(2) || "0.00"}</td>
            <td>${duration}</td>
            <td><span class="badge bg-secondary">${trade.exit_reason || "unknown"}</span></td>
        `;

        tbody.appendChild(row);
    });
}

/**
 * Calculate duration between two timestamps
 */
function calculateDuration(start, end) {
    const startTime = new Date(start);
    const endTime = new Date(end);
    const diffMs = endTime - startTime;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) {
        return `${diffDays}d ${diffHours % 24}h`;
    } else if (diffHours > 0) {
        return `${diffHours}h ${diffMins % 60}m`;
    } else {
        return `${diffMins}m`;
    }
}

/**
 * Render debug log
 */
function renderDebugLog(messages) {
    const container = document.getElementById("debug-log-container");

    if (!messages || messages.length === 0) {
        container.innerHTML = '<div class="text-muted">No debug messages</div>';
        return;
    }

    container.innerHTML = messages.map(msg => `
        <div class="mb-1">
            <span class="timestamp">${formatTime(msg.timestamp)}</span>
            <span class="level-${msg.level?.toLowerCase() || "info"}">[${msg.level || "INFO"}]</span>
            <span>${escapeHtml(msg.message)}</span>
        </div>
    `).join("");
}

/**
 * Render detailed metrics
 */
function renderDetailedMetrics(metrics, parameters) {
    const container = document.getElementById("detailed-metrics-container");

    if (!metrics) {
        container.innerHTML = '<div class="col-12 text-muted">No metrics available</div>';
        return;
    }

    const metricItems = [
        { label: "Annualized Return", value: `${(metrics.annualized_return || 0).toFixed(2)}%` },
        { label: "CAGR", value: `${(metrics.cagr || 0).toFixed(2)}%` },
        { label: "Volatility (Ann.)", value: `${(metrics.volatility_annualized || 0).toFixed(2)}%` },
        { label: "Sortino Ratio", value: (metrics.sortino_ratio || 0).toFixed(2) },
        { label: "Calmar Ratio", value: (metrics.calmar_ratio || 0).toFixed(2) },
        { label: "Expectancy", value: `$${(metrics.expectancy || 0).toFixed(2)}` },
        { label: "Avg Trade", value: `$${(metrics.avg_trade || 0).toFixed(2)}` },
        { label: "Avg Win", value: `$${(metrics.avg_win || 0).toFixed(2)}` },
        { label: "Avg Loss", value: `$${(metrics.avg_loss || 0).toFixed(2)}` },
        { label: "Largest Win", value: `$${(metrics.largest_win || 0).toFixed(2)}` },
        { label: "Largest Loss", value: `$${(metrics.largest_loss || 0).toFixed(2)}` },
        { label: "Total Fees", value: `$${(metrics.total_fees || 0).toFixed(2)}` },
        { label: "Winning Trades", value: metrics.winning_trades || 0 },
        { label: "Losing Trades", value: metrics.losing_trades || 0 },
        { label: "Max Consecutive Wins", value: metrics.max_consecutive_wins || 0 },
        { label: "Max Consecutive Losses", value: metrics.max_consecutive_losses || 0 },
        { label: "Time in Market", value: `${(metrics.time_in_market_pct || 0).toFixed(1)}%` },
        { label: "Avg Exposure", value: `${(metrics.avg_exposure_pct || 0).toFixed(1)}%` },
    ];

    if (parameters) {
        Object.entries(parameters).forEach(([key, value]) => {
            if (typeof value !== "object") {
                metricItems.push({ label: `Param: ${key}`, value: String(value) });
            }
        });
    }

    container.innerHTML = metricItems.map(item => `
        <div class="col-md-3 mb-2">
            <small class="text-muted">${item.label}</small>
            <div class="fw-bold">${item.value}</div>
        </div>
    `).join("");
}

/**
 * Show error message
 */
function showError(message) {
    document.getElementById("loading-panel").style.display = "none";
    document.getElementById("error-panel").style.display = "block";
    document.getElementById("error-message").textContent = message;
}

/**
 * Format date for display (short)
 */
function formatDateShort(dateStr) {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

/**
 * Format time only
 */
function formatTime(dateStr) {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return date.toLocaleTimeString("en-US", { hour12: false });
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}