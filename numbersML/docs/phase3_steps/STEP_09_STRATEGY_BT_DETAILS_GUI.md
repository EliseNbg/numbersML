# Step 9: Strategy Backtest Details Dashboard

## Objective

Create a detailed backtest results page that displays comprehensive trade information and price charts with entry/exit markers when clicking on rows in the "Recent Backtests" table.

## Scope

- Add clickable row navigation in "Recent Backtests" table
- Create new backtest details page (`backtest_details.html`)
- Display detailed trade-level information with PnL and margin metrics
- Render candlestick chart with buy/sell entry/exit markers
- Implement chart markers using Lightweight Charts v4.x API
- Add trade filtering and performance summary

## Out of Scope

- Modifying the backtest engine or API contracts
- Live trading functionality
- Multi-page navigation beyond the details page

## Dependencies

- Step 7 backtest engine (completed) - provides `TradeRecord`, `EquityPoint`, `PricePoint` data
- Step 8 dashboard GUI (completed) - provides existing patterns and API integration
- Existing API endpoints:
  - `GET /api/strategy-backtests/results/{backtest_id}` - get single backtest details (to be added)

## Required API Extension

### Get Single Backtest Result

```http
GET /api/strategy-backtests/results/{backtest_id}
```

Response format (extend `BacktestResultResponse` pattern):
```json
{
  "id": "uuid",
  "strategy_id": "uuid",
  "strategy_name": "string",
  "strategy_version": 1,
  "symbol": "BTC/USDC",
  "time_range_start": "ISO datetime",
  "time_range_end": "ISO datetime",
  "initial_balance": 10000.0,
  "final_balance": 9500.0,
  "metrics": { /* BacktestMetrics */ },
  "trades": [ /* TradeRecord array */ ],
  "equity_curve": [ /* EquityPoint array */ ],
  "price_series": [ /* PricePoint array - needed for chart */ ],
  "debug_messages": [ /* DebugMessage array - optional */ ],
  "parameters": { /* strategy parameters */ },
  "config_snapshot": { /* strategy config */ }
}
```

## Deliverables

1. **Backend**: Add `GET /api/strategy-backtests/results/{backtest_id}` endpoint
2. **Frontend**: New `dashboard/backtest_details.html` page
3. **Frontend JS**: `dashboard/js/backtest_details.js` module
4. **Integration**: Click handlers in `backtest_strategy.js` for history table rows
5. **Chart**: Lightweight Charts v4.x integration with trade markers

## Implementation Checklist

### Phase 1: API Extension
- [ ] Add `get` endpoint to `StrategyBacktestRepositoryPG` for single backtest
- [ ] Add `GET /api/strategy-backtests/results/{backtest_id}` route
- [ ] Return full result data including price_series for charting

### Phase 2: Frontend - Details Page
- [ ] Create `backtest_details.html` with:
  - Header with backtest metadata (strategy, symbol, period)
  - Summary metrics cards
  - Trade blotter table with PnL coloring
  - Candlestick chart container with trade markers
  - Debug log panel (optional)
- [ ] Create `backtest_details.js` with:
  - `loadBacktestDetails(backtestId)` function
  - `renderCandlestickChart(priceSeries, trades)` function
  - `renderTradesTable(trades)` function
  - Trade marker rendering logic

### Phase 3: Navigation Integration
- [ ] Modify `loadBacktestHistory()` in `backtest_strategy.js` to add click handlers
- [ ] Add row click navigation to details page

### Phase 4: Chart Implementation (Lightweight Charts v4.x)
- [ ] Include Lightweight Charts library (v4.x)
- [ ] Create candlestick series
- [ ] Add buy markers (green circles at entry prices)
- [ ] Add sell markers (color-coded: green for profit, red for loss; squares)
- [ ] Add connecting lines between entry/exit (dashed, color-coded by PnL)
- [ ] Implement tooltip for markers showing trade details

## Chart Marker Specification (Lightweight Charts v4.x)

```javascript
// Create candlestick series
const candlestickSeries = chart.addCandlestickSeries();

// Create marker series for buy/sell points
// Note: v4.x uses ISeriesApi with custom markers or separate line series

// Marker data structure
const markers = [
  {
    time: '2024-05-10',  // ISO date or unix timestamp
    position: 'belowBar' | 'aboveBar',
    color: 'green',      // entry marker
    shape: 'circle',     // entry: circle, exit: square
    text: 'BUY',
    tradeId: 'uuid',     // custom field for tooltip
    price: 0.1234,       // marker price (entry_price or exit_price)
  }
];

// Apply markers to series
candlestickSeries.setMarkers(markers);
```

## Trade Information Display

| Field | Description |
|-------|-------------|
| Entry Time | When position opened |
| Exit Time | When position closed |
| Symbol | Trading pair |
| Side | LONG/SHORT |
| Entry Price | Execution price |
| Exit Price | Execution price |
| Quantity | Position size |
| PnL | Profit/Loss in $ |
| PnL % | Profit/Loss percentage |
| Fees | Total transaction fees |
| Exit Reason | signal/stop_loss/take_profit/end_of_test |
| Duration | Time in trade |

## Acceptance Criteria

1. Clicking a row in "Recent Backtests" opens the details page
2. Details page shows:
   - Strategy name, version, symbol, and time period
   - All PnL metrics (total return, max drawdown, Sharpe, etc.)
   - Trade table with PnL-colored rows
   - Candlestick chart with visible buy/sell markers
3. Chart markers are color-coded:
   - Green circle = entry point
   - Green square = profitable exit
   - Red square = losing exit
4. Tooltip on marker hover shows trade details
5. API returns 404 for non-existent backtest_id

## Implementation Prompt (Best Prompt for LLM)

```text
Implement Step 9 only: Strategy backtest details dashboard.

Tasks:
1) Add GET /api/strategy-backtests/results/{backtest_id} endpoint to strategy_backtest.py
2) Create dashboard/backtest_details.html with:
   - Summary metrics cards
   - Trade blotter table
   - Candlestick chart container
   - Debug log panel
3) Create dashboard/js/backtest_details.js with:
   - loadBacktestDetails(backtestId)
   - renderCandlestickChart(priceSeries, trades) with markers
   - renderTradesTable(trades)
4) Modify backtest_strategy.js to make history rows clickable
5) Implement trade markers using Lightweight Charts v4.x:
   - Green circle for entry
   - Green square for profitable exit
   - Red square for losing exit
   - Tooltips with trade details

Constraints:
- Use Lightweight Charts v4.x API (series.setMarkers())
- Follow existing dashboard patterns and styles
- Handle loading, error, and empty states
- Max 50 trades on chart for performance

Output:
- New/changed files
- API contract verification
- Testing notes
```

## Testing Prompt (Best Prompt for LLM)

```text
Validate Step 9 backtest details implementation.

Tasks:
1) Test navigation from history table to details page
2) Verify details page loads for valid backtest_id
3) Verify 404 response for invalid backtest_id
4) Check chart renders with markers for each trade
5) Verify marker colors: green=entry/profit, red=loss
6) Check trade table displays all required columns
7) Verify tooltip shows trade details on marker hover
8) Test error state handling (API failure, missing data)

Deliver:
- Test results checklist
- Data-contract validation
- UX notes
```

## File Changes Summary

| File | Action |
|------|--------|
| `src/infrastructure/api/routes/strategy_backtest.py` | Add get_single_backtest endpoint |
| `src/infrastructure/repositories/strategy_backtest_repository_pg.py` | Use existing `get()` method |
| `dashboard/backtest_details.html` | NEW |
| `dashboard/js/backtest_details.js` | NEW |
| `dashboard/backtest_strategy.js` | Add row click handler |
| `dashboard/css/dashboard.css` | Optional: add detail page styles |

## API Contract

### GET /api/strategy-backtests/results/{backtest_id}

```python
# Response model extension
class BacktestDetailsResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    strategy_name: str
    strategy_version: int
    symbol: str
    time_range_start: datetime
    time_range_end: datetime
    initial_balance: float
    final_balance: float | None
    metrics: dict[str, Any]
    trades: list[dict[str, Any]] | None
    equity_curve: list[dict[str, Any]] | None
    price_series: list[dict[str, Any]] | None  # Added for chart
    debug_messages: list[dict[str, Any]] | None
    parameters: dict[str, Any]
    config_snapshot: dict[str, Any]
    created_at: datetime
```

## Lightweight Charts v4.x Integration Notes

The current dashboard uses Chart.js for the price chart. For Step 9, we need to migrate to TradingView Lightweight Charts for proper candlestick support and marker primitives.

Include in HTML:
```html
<script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
```

Chart initialization pattern:
```javascript
const chart = LightweightCharts.createChart(container, {
  width: container.clientWidth,
  height: 400,
  layout: { backgroundColor: '#ffffff', textColor: '#000000' },
  grid: { vertLines: { visible: false }, horzLines: { visible: false } },
});

const candlestickSeries = chart.addCandlestickSeries({
  upColor: '#26a69a',
  downColor: '#ef5350',
  borderDownColor: '#ef5350',
  borderUpColor: '#26a69a',
  wickDownColor: '#ef5350',
  wickUpColor: '#26a69a',
});

// Apply candlestick data
candlestickSeries.setData(candleData);

// Add trade markers
candlestickSeries.setMarkers(markerData);
```

## Risks and Considerations

1. **Performance**: Limit displayed trades to 50 most recent for chart rendering
2. **Data Completeness**: Not all backtests may have price_series stored; need fallback
3. **Time Zone Handling**: Ensure consistent UTC handling across chart and data
4. **Responsive**: Chart should resize with window