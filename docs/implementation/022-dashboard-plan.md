# Step 022: Web Dashboard - Architecture & Implementation Plan

**Status**: 📋 PLANNING  
**Priority**: HIGH  
**Effort**: 15-20 hours  

---

## 🎯 Objective

Build a simple, stable, fast web dashboard for monitoring and controlling the crypto trading data pipeline.

---

## 🏗️ Architecture

### Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Backend** | FastAPI | Simple, Python-native, auto OpenAPI docs |
| **Frontend** | HTML + Vanilla JS | No build tools, no npm chaos |
| **CSS** | Bootstrap 5 | Stable, well-documented |
| **Chart** | TradingView Lightweight Charts | Fast, lightweight, financial charts |
| **Database** | PostgreSQL (existing) | pipeline_metrics, symbols, indicator_definitions |

### Architecture Principles

Per CODING-STANDARDS.md:
- ✅ **KISS**: Simple HTML + Vanilla JS, no React/Vue complexity
- ✅ **DDD**: Backend follows Domain → Application → Infrastructure layers
- ✅ **Type hints**: All Python functions fully typed
- ✅ **Docstrings**: Comprehensive documentation
- ✅ **Error handling**: Explicit with context
- ✅ **Testable**: Backend endpoints unit-testable

---

## 📐 System Design

### Backend Structure

```
src/
├── domain/
│   └── models/
│       ├── dashboard.py          # Dashboard entities (Status, Metrics)
│       └── config.py             # Configuration entities
│
├── application/
│   └── services/
│       ├── pipeline_monitor.py   # Check collector status, start/stop
│       ├── symbol_manager.py     # Activate/deactivate symbols
│       ├── indicator_manager.py  # Register/unregister indicators
│       └── config_manager.py     # Load/save configuration
│
├── infrastructure/
│   ├── api/
│   │   └── routes/
│   │       ├── dashboard.py      # Dashboard endpoints
│   │       ├── symbols.py        # Symbol management endpoints
│   │       ├── indicators.py     # Indicator management endpoints
│   │       └── config.py         # Configuration endpoints
│   └── repositories/
│       ├── pipeline_metrics_repo.py  # Metrics data access
│       ├── symbol_repo.py            # Symbol data access
│       └── indicator_repo.py         # Indicator data access
│
└── cli/
    └── start_dashboard.py        # Dashboard CLI entry point
```

### Frontend Structure

```
dashboard/
├── index.html                    # Main dashboard (service status + SLA chart)
├── symbols.html                  # Symbol management
├── indicators.html               # Indicator management
├── chart.html                    # Candlestick chart with indicators
├── config.html                   # Configuration editor
├── css/
│   └── dashboard.css             # Custom styles (minimal)
└── js/
    ├── dashboard.js              # Dashboard logic
    ├── symbols.js                # Symbol management logic
    ├── indicators.js             # Indicator management logic
    ├── chart.js                  # Chart logic (TradingView)
    └── config.js                 # Configuration logic
```

---

## 📊 Pages Design

### 1. Dashboard (index.html)

**Purpose**: Real-time monitoring

**Components**:
- **Service Status Card**
  - collect_ticker_24hr.py running? (green/red indicator)
  - Start/Stop button
  - Uptime counter
  - Last tick timestamp

- **SLA Compliance Chart**
  - Line chart: pipeline processing time (last 60 seconds)
  - Target line: 1000ms (1-second SLA)
  - Color coding: green (<500ms), yellow (500-1000ms), red (>1000ms)
  - Data source: `pipeline_metrics` table

- **Quick Stats**
  - Ticks processed (last minute)
  - Average processing time
  - SLA violations (last minute)
  - Active symbols count
  - Active indicators count

---

### 2. Symbol Management (symbols.html)

**Purpose**: Control which symbols are collected

**Components**:
- **Symbol Table**
  - Columns: Symbol, Base Asset, Quote Asset, Is Active, Is Allowed, Actions
  - Filter: Search by symbol name
  - Sort: By any column

- **Actions**
  - Toggle Active (checkbox or switch)
  - Edit symbol details
  - View symbol statistics

- **Bulk Actions**
  - Activate all
  - Deactivate all
  - Activate EU-compliant only

---

### 3. Indicator Management (indicators.html)

**Purpose**: Register and control which indicators are calculated

**Components**:
- **Indicator Table**
  - Columns: Name, Class, Category, Is Active, Parameters, Actions
  - Filter: By category, by active status
  - Sort: By name, category

- **Actions**
  - Toggle Active (checkbox or switch)
  - Edit parameters (JSON editor)
  - Register new indicator (form)
  - Unregister (soft delete - set is_active=false)

- **Register New Indicator Form**
  - Name (e.g., 'rsi_14')
  - Class Name (e.g., 'RSIIndicator')
  - Module Path (e.g., 'src.indicators.momentum')
  - Category (dropdown: momentum, trend, volatility, volume)
  - Parameters (JSON editor)
  - Is Active (checkbox)

---

### 4. Chart (chart.html)

**Purpose**: Visualize symbol data with indicators

**Components**:
- **Symbol Selector**
  - Dropdown: All active symbols
  - Time range: 1min, 5min, 15min, 1hr, 4hr, 1day

- **Candlestick Chart** (TradingView Lightweight Charts)
  - Candlesticks: OHLC data
  - Overlay indicators: SMA, EMA (lines)
  - Separate panels: RSI, MACD, Volume

- **Indicator Overlays**
  - Checkboxes: Select which indicators to show
  - Color picker: Customize indicator colors
  - Parameter adjustment: Period, std dev, etc.

---

### 5. Configuration (config.html)

**Purpose**: Edit system configuration tables

**Components**:
- **Table Selector**
  - Dropdown: system_config, collection_config, symbols, indicator_definitions

- **Data Grid**
  - Editable cells
  - Add row button
  - Delete row button
  - Save/Cancel buttons

- **Validation**
  - Required fields highlighted
  - Type validation (number, string, boolean, JSON)
  - Save confirmation dialog

---

## 🔌 API Endpoints

### Dashboard Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/status` | Get collector service status |
| POST | `/api/dashboard/collector/start` | Start collector |
| POST | `/api/dashboard/collector/stop` | Stop collector |
| GET | `/api/dashboard/metrics` | Get pipeline metrics (last N seconds) |
| GET | `/api/dashboard/stats` | Get quick statistics |

### Symbol Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/symbols` | List all symbols |
| PUT | `/api/symbols/{id}/activate` | Activate symbol |
| PUT | `/api/symbols/{id}/deactivate` | Deactivate symbol |
| PUT | `/api/symbols/{id}` | Update symbol |
| POST | `/api/symbols` | Create new symbol |

### Indicator Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/indicators` | List all indicators |
| PUT | `/api/indicators/{name}/activate` | Activate indicator |
| PUT | `/api/indicators/{name}/deactivate` | Deactivate indicator |
| PUT | `/api/indicators/{name}` | Update indicator |
| POST | `/api/indicators` | Register new indicator |
| DELETE | `/api/indicators/{name}` | Unregister indicator |

### Chart Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/chart/{symbol}/candles` | Get candlestick data |
| GET | `/api/chart/{symbol}/indicators` | Get indicator data |

### Configuration Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config/{table}` | Get table data |
| PUT | `/api/config/{table}` | Update table data |
| POST | `/api/config/{table}` | Insert row |
| DELETE | `/api/config/{table}/{id}` | Delete row |

---

## 📝 Database Queries

### SLA Metrics (Last 60 Seconds)

```sql
SELECT 
    DATE_TRUNC('second', timestamp) as second,
    AVG(total_time_ms) as avg_time_ms,
    MAX(total_time_ms) as max_time_ms,
    COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations
FROM pipeline_metrics
WHERE timestamp > NOW() - INTERVAL '60 seconds'
GROUP BY DATE_TRUNC('second', timestamp)
ORDER BY second;
```

### Active Symbols

```sql
SELECT 
    id, symbol, base_asset, quote_asset,
    is_active, is_allowed,
    created_at, updated_at
FROM symbols
ORDER BY is_active DESC, symbol;
```

### Registered Indicators

```sql
SELECT 
    name, class_name, module_path, category,
    params, is_active,
    created_at, updated_at
FROM indicator_definitions
ORDER BY category, name;
```

---

## ✅ Acceptance Criteria

### Backend

- [ ] FastAPI application with all endpoints
- [ ] DDD layer separation (Domain → Application → Infrastructure)
- [ ] Type hints on all functions
- [ ] Comprehensive docstrings
- [ ] Error handling with context
- [ ] Unit tests for services (80%+ coverage)
- [ ] Integration tests for API endpoints
- [ ] OpenAPI docs available at `/docs`

### Frontend

- [ ] All 5 pages implemented
- [ ] Bootstrap 5 for styling
- [ ] TradingView chart working
- [ ] Real-time updates (polling every 5 seconds)
- [ ] No build tools required
- [ ] Works in modern browsers

### Integration

- [ ] Dashboard shows correct collector status
- [ ] Start/Stop collector works
- [ ] SLA chart displays real-time data
- [ ] Symbol activation/deactivation works
- [ ] Indicator registration/activation works
- [ ] Chart displays candlesticks + indicators
- [ ] Configuration editor saves changes

---

## 📋 Implementation Plan

### Phase 1: Backend Foundation (4-5 hours)

1. **Step 022.1**: Create domain models
   - `src/domain/models/dashboard.py`
   - `src/domain/models/config.py`

2. **Step 022.2**: Create application services
   - `src/application/services/pipeline_monitor.py`
   - `src/application/services/symbol_manager.py`
   - `src/application/services/indicator_manager.py`
   - `src/application/services/config_manager.py`

3. **Step 022.3**: Create infrastructure repositories
   - `src/infrastructure/repositories/pipeline_metrics_repo.py`
   - `src/infrastructure/repositories/symbol_repo.py`
   - `src/infrastructure/repositories/indicator_repo.py`

4. **Step 022.4**: Create FastAPI routes
   - `src/infrastructure/api/routes/dashboard.py`
   - `src/infrastructure/api/routes/symbols.py`
   - `src/infrastructure/api/routes/indicators.py`
   - `src/infrastructure/api/routes/config.py`

5. **Step 022.5**: Create FastAPI application
   - `src/infrastructure/api/app.py`
   - `src/cli/start_dashboard.py`

### Phase 2: Frontend Foundation (4-5 hours)

6. **Step 022.6**: Create HTML templates
   - `dashboard/index.html`
   - `dashboard/symbols.html`
   - `dashboard/indicators.html`
   - `dashboard/chart.html`
   - `dashboard/config.html`

7. **Step 022.7**: Create JavaScript modules
   - `dashboard/js/dashboard.js`
   - `dashboard/js/symbols.js`
   - `dashboard/js/indicators.js`
   - `dashboard/js/chart.js`
   - `dashboard/js/config.js`

8. **Step 022.8**: Add CSS styling
   - `dashboard/css/dashboard.css`

### Phase 3: Integration & Testing (3-4 hours)

9. **Step 022.9**: Write backend unit tests
   - `tests/unit/application/services/test_pipeline_monitor.py`
   - `tests/unit/application/services/test_symbol_manager.py`
   - `tests/unit/application/services/test_indicator_manager.py`

10. **Step 022.10**: Write API integration tests
    - `tests/integration/api/test_dashboard_api.py`
    - `tests/integration/api/test_symbols_api.py`
    - `tests/integration/api/test_indicators_api.py`

11. **Step 022.11**: Manual testing
    - Test all pages in browser
    - Verify real-time updates
    - Test all CRUD operations

### Phase 4: Documentation (1-2 hours)

12. **Step 022.12**: Create documentation
    - `docs/implementation/022-dashboard.md`
    - Update README.md with dashboard info

---

## 🚀 Usage

### Start Dashboard

```bash
cd numbersML
.venv/bin/python src/cli/start_dashboard.py
```

Access at: `http://localhost:8000`

### API Documentation

OpenAPI docs: `http://localhost:8000/docs`

---

## 📊 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Page Load Time** | < 2 seconds | Browser DevTools |
| **API Response Time** | < 200ms (p95) | FastAPI metrics |
| **Chart Update Frequency** | Every 5 seconds | Visual inspection |
| **Test Coverage** | 80%+ | pytest --cov |
| **Zero Build Steps** | Yes | No npm, no webpack |

---

## 🔧 Maintenance

### Adding New Pages

1. Create HTML file in `dashboard/`
2. Create JS module in `dashboard/js/`
3. Add navigation link in all pages
4. Add API endpoints if needed

### Adding New Indicators

1. Implement indicator class in `src/indicators/`
2. Register in `indicator_definitions` table via dashboard
3. Activate via dashboard
4. Available for calculation immediately

---

## 📝 Notes

- **No build tools**: All frontend code is vanilla JS, no transpilation needed
- **Bootstrap CDN**: Load from CDN for simplicity
- **TradingView CDN**: Load charting library from CDN
- **Auto-reload**: Use `uvicorn --reload` for development
- **CORS**: Configure for local development only

---

**Last Updated**: March 24, 2026  
**Status**: 📋 PLANNING  
**Next**: Create LLM Coder Agent prompts for each step
