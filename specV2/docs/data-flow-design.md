# Crypto Trading System - Data Flow Architecture

## Overview

Four-stage streaming pipeline:
1. **Data Collection Service** → 2. **Store Tick Data** → 3. **Data Enrichment Service** → 4. **Call Strategies**

**Key Decisions:**
- Real-time indicator calculation (dynamic indicators)
- **Dynamic indicator definitions** (Python code, git-versioned)
- **Automatic recalculation** when indicators change
- Store indicator values in PostgreSQL (flexible schema)
- Message queue for strategy communication
- Unified code for backtest and live trading

---

## 1. Complete Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW (Detailed)                                 │
└──────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐
  │   Binance       │
  │   WebSocket     │
  │   stream        │
  └────────┬────────┘
           │  WebSocket messages (trades, orderbook)
           ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  STAGE 1: Data Collection Service                                            │
  │  ┌───────────────────────────────────────────────────────────────────────┐  │
  │  │  - Connect to Binance WebSocket                                        │  │
  │  │  - Receive trade events (real-time)                                    │  │
  │  │  - Validate, normalize, deduplicate                                    │  │
  │  │  - Batch insert into PostgreSQL (trades table)                         │  │
  │  │  - Emit PostgreSQL NOTIFY: "new_tick"                                  │  │
  │  └───────────────────────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────────────────────┘
           │
           │  INSERT into trades table
           │  NOTIFY new_tick
           ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  STAGE 2: PostgreSQL - Raw Tick Storage                                      │
  │                                                                              │
  │  trades table:                                                               │
  │  - time, symbol_id, trade_id, price, quantity, side, is_buyer_maker         │
  │                                                                              │
  │  ~100 ticks/second per symbol                                                │
  └─────────────────────────────────────────────────────────────────────────────┘
           │
           │  PostgreSQL LISTEN new_tick
           ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  STAGE 3: Data Enrichment Service                                            │
  │  ┌───────────────────────────────────────────────────────────────────────┐  │
  │  │  - Listen for "new_tick" notifications                                 │  │
  │  │  - On notification:                                                    │  │
  │  │    1. Load recent tick window (e.g., last 1000 ticks)                  │  │
  │  │    2. Calculate 50 technical indicators (TA-Lib)                       │  │
  │  │    3. Store enriched record in tick_indicators table                   │  │
  │  │    4. Publish to Redis: "enriched_tick"                                │  │
  │  └───────────────────────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────────────────────┘
           │
           │  INSERT into tick_indicators table
           │  Redis PUBLISH enriched_tick
           ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  STAGE 4: Message Queue (Redis Pub/Sub)                                      │
  │                                                                              │
  │  Channels:                                                                   │
  │  - enriched_tick:{symbol}  (per-symbol channels)                            │
  │  - enriched_tick:*         (wildcard for all)                               │
  │                                                                              │
  │  Message format (JSON):                                                      │
  │  {                                                                           │
  │    "time": "...",                                                            │
  │    "symbol": "BTC/USDT",                                                     │
  │    "price": 50000.00,                                                        │
  │    "indicators": { "sma_20": ..., "rsi": ..., ... }                          │
  │  }                                                                           │
  └─────────────────────────────────────────────────────────────────────────────┘
           │
           │  Redis SUBSCRIBE enriched_tick:{symbol}
           ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  Strategy Processes (isolated)                                               │
  │                                                                              │
  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
  │  │  Strategy:       │  │  Strategy:       │  │  Strategy:       │          │
  │  │  Market Maker    │  │  Trend Follow    │  │  Mean Reversion  │          │
  │  │                  │  │                  │  │                  │          │
  │  │  - Subscribe to  │  │  - Subscribe to  │  │  - Subscribe to  │          │
  │  │    Redis channel │  │    Redis channel │  │    Redis channel │          │
  │  │  - Process tick  │  │  - Process tick  │  │  - Process tick  │          │
  │  │  - Generate      │  │  - Generate      │  │  - Generate      │          │
  │  │    orders        │  │    orders        │  │    orders        │          │
  │  │  - Publish to    │  │  - Publish to    │  │  - Publish to    │          │
  │  │    orders queue  │  │    orders queue  │  │    orders queue  │          │
  │  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
  └─────────────────────────────────────────────────────────────────────────────┘
           │
           │  Redis PUBLISH orders:{strategy_id}
           ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  Order Execution Service (Future - Phase 2)                                  │
  │  - Subscribe to order queues                                                 │
  │  - Risk checks                                                               │
  │  - Execute on Binance                                                        │
  └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. PostgreSQL Schema (Dynamic Indicators)

### 2.1 Design Philosophy

**Dynamic Indicators Requirements:**
1. Add/remove indicators without schema changes
2. Change indicator parameters freely
3. Recalculate all historical data on definition change
4. Track indicator versions and calculation status

**Solution:**
- Indicator definitions stored in DB (metadata)
- Indicator **code** in Python modules (git-versioned)
- Indicator **values** in flexible storage (JSONB or EAV)
- Automatic recalculation trigger on code change

### 2.2 Core Tables

```sql
-- =============================================================================
-- REFERENCE DATA
-- =============================================================================

CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,           -- e.g., "BTC/USDT"
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'binance',
    tick_size NUMERIC(20,10) NOT NULL,
    step_size NUMERIC(20,10) NOT NULL,
    min_notional NUMERIC(20,10) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- RAW TICK DATA
-- =============================================================================

CREATE TABLE trades (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    trade_id TEXT NOT NULL,
    price NUMERIC(20,10) NOT NULL,
    quantity NUMERIC(20,10) NOT NULL,
    side TEXT NOT NULL,
    is_buyer_maker BOOLEAN NOT NULL,
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_time_symbol ON trades(time DESC, symbol_id);
CREATE UNIQUE INDEX idx_trades_unique ON trades(trade_id, symbol_id);

-- =============================================================================
-- DYNAMIC INDICATOR DEFINITIONS
-- =============================================================================

-- Indicator registry (metadata)
CREATE TABLE indicator_definitions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,             -- e.g., "rsi_14", "sma_20"
    class_name TEXT NOT NULL,              -- Python class: "RSIIndicator"
    module_path TEXT NOT NULL,             -- Python module: "indicators.momentum"
    category TEXT NOT NULL,                -- 'trend', 'momentum', 'volatility', 'volume'
    
    -- Parameters (JSON schema for validation)
    params_schema JSONB NOT NULL,          -- JSON Schema for params validation
    /* Example:
    {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "period": {"type": "integer", "minimum": 2, "default": 14}
        },
        "required": ["period"]
    }
    */
    
    params JSONB NOT NULL,                 -- Actual parameters
    /* Example: {"period": 14} */
    
    -- Code versioning (for auto-recalc trigger)
    code_hash TEXT NOT NULL,               -- SHA256 of Python source
    code_version INTEGER NOT NULL DEFAULT 1,  -- Incremented on change
    
    -- Metadata
    description TEXT,
    input_fields JSONB NOT NULL,           -- Required input: ["price", "volume"]
    output_fields JSONB NOT NULL,          -- Output: ["rsi"]
    
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_calculated_at TIMESTAMP,          -- When was this indicator last calculated
    
    CONSTRAINT unique_indicator_name_version UNIQUE (name, code_version)
);

CREATE INDEX idx_indicators_category ON indicator_definitions(category);
CREATE INDEX idx_indicators_active ON indicator_definitions(is_active);

-- Indicator code change log (audit trail)
CREATE TABLE indicator_change_log (
    id BIGSERIAL PRIMARY KEY,
    indicator_id INTEGER NOT NULL REFERENCES indicator_definitions(id),
    change_type TEXT NOT NULL,             -- 'created', 'params_changed', 'code_changed'
    old_code_hash TEXT,
    new_code_hash TEXT NOT NULL,
    old_params JSONB,
    new_params JSONB,
    changed_by TEXT,                       -- User or system
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    recalc_status TEXT DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'
    recalc_started_at TIMESTAMP,
    recalc_completed_at TIMESTAMP
);

CREATE INDEX idx_change_log_indicator ON indicator_change_log(indicator_id);
CREATE INDEX idx_change_log_status ON indicator_change_log(recalc_status);

-- =============================================================================
-- INDICATOR VALUES (Flexible Storage)
-- =============================================================================

-- Option 1: JSONB storage (RECOMMENDED for dynamic indicators)
-- Flexible, supports any number of indicators, easy to query
CREATE TABLE tick_indicators (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    
    -- Raw price data (for quick access)
    price NUMERIC(20,10) NOT NULL,
    volume NUMERIC(20,10) NOT NULL,
    
    -- All indicator values as JSONB
    values JSONB NOT NULL DEFAULT '{}',
    /* Example:
    {
        "rsi_14": 55.5,
        "sma_20": 50123.45,
        "macd": 123.45,
        "macd_signal": 120.00,
        "bollinger_upper": 50500.00,
        "bollinger_lower": 49500.00
    }
    */
    
    -- Track which indicators are included (for fast lookup)
    indicator_keys TEXT[] NOT NULL,
    
    -- Versioning
    indicator_version INTEGER NOT NULL DEFAULT 1,  -- Matches indicator_definitions.code_version
    
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (time, symbol_id)
);

-- Indexes for performance
CREATE INDEX idx_tick_ind_time_symbol ON tick_indicators(time DESC, symbol_id);
CREATE INDEX idx_tick_ind_symbol_time ON tick_indicators(symbol_id, time DESC);

-- GIN index for JSONB queries (query by indicator values)
CREATE INDEX idx_tick_ind_values_gin ON tick_indicators USING GIN (values);

-- Index for array containment (query by indicator_keys)
CREATE INDEX idx_tick_ind_keys ON tick_indicators USING GIN (indicator_keys);

-- =============================================================================
-- Alternative Option 2: EAV (Entity-Attribute-Value)
-- More normalized, better for specific queries, but slower
-- =============================================================================

CREATE TABLE tick_indicator_values (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    indicator_id INTEGER NOT NULL REFERENCES indicator_definitions(id),
    
    value NUMERIC(20,10) NOT NULL,         -- Single indicator value
    
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE(time, symbol_id, indicator_id)
);

CREATE INDEX idx_tick_eav_time_symbol ON tick_indicator_values(time DESC, symbol_id);
CREATE INDEX idx_tick_eav_indicator ON tick_indicator_values(indicator_id, time DESC);

-- RECOMMENDATION: Use tick_indicators (JSONB) for performance + flexibility
-- Use tick_indicator_values only for specific analytical queries

-- =============================================================================
-- RECALCULATION JOBS
-- =============================================================================

CREATE TABLE recalculation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- What to recalculate
    indicator_id INTEGER REFERENCES indicator_definitions(id),
    indicator_name TEXT NOT NULL,          -- Denormalized for history
    
    -- Scope
    symbol_id INTEGER REFERENCES symbols(id),  -- NULL = all symbols
    time_start TIMESTAMP,                  -- NULL = from beginning
    time_end TIMESTAMP,                    -- NULL = until now
    
    -- Status
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed
    progress_percent NUMERIC(5,2) DEFAULT 0,
    
    -- Statistics
    ticks_processed BIGINT DEFAULT 0,
    ticks_total BIGINT,
    errors_count INTEGER DEFAULT 0,
    last_error TEXT,
    
    -- Timing
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTERVAL,
    
    -- Trigger
    triggered_by TEXT NOT NULL,            -- 'auto', 'manual', 'api'
    triggered_by_user TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recalc_status ON recalculation_jobs(status);
CREATE INDEX idx_recalc_indicator ON recalculation_jobs(indicator_id);
CREATE INDEX idx_recalc_created ON recalculation_jobs(created_at);

-- =============================================================================
-- COLLECTION STATE & MONITORING
-- =============================================================================

CREATE TABLE collection_state (
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    data_type TEXT NOT NULL,               -- 'trades', 'indicators'
    
    last_collected_time TIMESTAMP,
    last_processed_time TIMESTAMP,
    last_trade_id TEXT,
    
    is_collecting BOOLEAN NOT NULL DEFAULT false,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMP,
    
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (symbol_id, data_type)
);

CREATE TABLE service_health (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL,
    records_processed BIGINT DEFAULT 0,
    indicators_calculated BIGINT DEFAULT 0,
    recalculation_jobs_run BIGINT DEFAULT 0,
    errors_last_hour INTEGER DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE event_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL,
    service TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    log_date DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX idx_event_log_timestamp ON event_log(timestamp);
CREATE INDEX idx_event_log_service ON event_log(service);
CREATE INDEX idx_event_log_date ON event_log(log_date);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

CREATE OR REPLACE FUNCTION get_or_create_symbol(
    p_symbol TEXT, p_base_asset TEXT, p_quote_asset TEXT,
    p_exchange TEXT DEFAULT 'binance'
) RETURNS INTEGER AS $$
DECLARE v_symbol_id INTEGER;
BEGIN
    SELECT id INTO v_symbol_id FROM symbols
    WHERE symbol = p_symbol AND exchange = p_exchange;
    
    IF v_symbol_id IS NULL THEN
        INSERT INTO symbols (symbol, base_asset, quote_asset, exchange)
        VALUES (p_symbol, p_base_asset, p_quote_asset, p_exchange)
        RETURNING id INTO v_symbol_id;
    END IF;
    
    RETURN v_symbol_id;
END;
$$ LANGUAGE plpgsql;

-- Notify listeners of new tick
CREATE OR REPLACE FUNCTION notify_new_tick() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('new_tick', json_build_object(
        'symbol_id', NEW.symbol_id,
        'time', NEW.time,
        'trade_id', NEW.trade_id
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trades_notify_trigger
    AFTER INSERT ON trades
    FOR EACH ROW
    EXECUTE FUNCTION notify_new_tick();

-- Notify on indicator definition change (triggers recalc)
CREATE OR REPLACE FUNCTION notify_indicator_changed() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.code_hash IS DISTINCT FROM NEW.code_hash THEN
        -- Code changed, trigger recalculation
        PERFORM pg_notify('indicator_changed', json_build_object(
            'indicator_id', NEW.id,
            'indicator_name', NEW.name,
            'old_hash', OLD.code_hash,
            'new_hash', NEW.code_hash,
            'change_type', 'code_changed'
        )::text);
    ELSIF TG_OP = 'UPDATE' AND OLD.params IS DISTINCT FROM NEW.params THEN
        -- Params changed, trigger recalculation
        PERFORM pg_notify('indicator_changed', json_build_object(
            'indicator_id', NEW.id,
            'indicator_name', NEW.name,
            'old_params', OLD.params,
            'new_params', NEW.params,
            'change_type', 'params_changed'
        )::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER indicator_changed_trigger
    AFTER UPDATE ON indicator_definitions
    FOR EACH ROW
    EXECUTE FUNCTION notify_indicator_changed();

-- =============================================================================
-- HELPER VIEWS & FUNCTIONS (Active Symbols Only)
-- =============================================================================

-- View: Only active symbols (convenient for queries)
CREATE VIEW active_symbols AS
SELECT id, symbol, base_asset, quote_asset, exchange
FROM symbols
WHERE is_active = true;

-- Function: Get all active symbols for data collection
CREATE OR REPLACE FUNCTION get_active_symbols() 
RETURNS TABLE (
    id INTEGER,
    symbol TEXT,
    base_asset TEXT,
    quote_asset TEXT,
    exchange TEXT
) AS $$
BEGIN
    RETURN QUERY SELECT s.id, s.symbol, s.base_asset, s.quote_asset, s.exchange
    FROM symbols s
    WHERE s.is_active = true;
END;
$$ LANGUAGE plpgsql;

-- Function: Check if symbol is active
CREATE OR REPLACE FUNCTION is_symbol_active(p_symbol TEXT) 
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM symbols 
        WHERE symbol = p_symbol AND is_active = true
    );
END;
$$ LANGUAGE plpgsql;
```

**Important**: All services should ONLY process symbols where `is_active = true`. This is a critical optimization to avoid unnecessary calculations.

-- =============================================================================
-- ORDER BOOK SNAPSHOTS (optional, for more advanced strategies)
-- =============================================================================

CREATE TABLE orderbook_snapshots (
    time TIMESTAMP NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    
    -- Best bid/ask
    best_bid NUMERIC(20,10) NOT NULL,
    best_ask NUMERIC(20,10) NOT NULL,
    bid_qty NUMERIC(20,10) NOT NULL,
    ask_qty NUMERIC(20,10) NOT NULL,
    
    -- Top 10 levels (arrays)
    bids_price NUMERIC(20,10)[],
    bids_qty NUMERIC(20,10)[],
    asks_price NUMERIC(20,10)[],
    asks_qty NUMERIC(20,10)[],
    
    spread NUMERIC(20,10) NOT NULL,
    mid_price NUMERIC(20,10) NOT NULL,
    
    inserted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (time, symbol_id)
);

CREATE INDEX idx_orderbook_time_symbol ON orderbook_snapshots(time DESC, symbol_id);

-- =============================================================================
-- COLLECTION STATE & MONITORING
-- =============================================================================

CREATE TABLE collection_state (
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    data_type TEXT NOT NULL,               -- 'trades', 'orderbook', 'indicators'
    
    last_collected_time TIMESTAMP,
    last_trade_id TEXT,
    last_processed_time TIMESTAMP,         -- For enrichment service
    
    is_collecting BOOLEAN NOT NULL DEFAULT false,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMP,
    
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (symbol_id, data_type)
);

CREATE TABLE service_health (
    service_name TEXT PRIMARY KEY,         -- 'data_collector', 'enrichment'
    status TEXT NOT NULL,                  -- 'healthy', 'degraded', 'down'
    last_heartbeat TIMESTAMP NOT NULL,
    records_processed BIGINT DEFAULT 0,
    indicators_calculated BIGINT DEFAULT 0,
    errors_last_hour INTEGER DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE event_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL,                   -- DEBUG, INFO, WARN, ERROR
    service TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    log_date DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX idx_event_log_timestamp ON event_log(timestamp);
CREATE INDEX idx_event_log_service ON event_log(service);
CREATE INDEX idx_event_log_date ON event_log(log_date);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

CREATE OR REPLACE FUNCTION get_or_create_symbol(
    p_symbol TEXT, p_base_asset TEXT, p_quote_asset TEXT,
    p_exchange TEXT DEFAULT 'binance',
    p_tick_size NUMERIC DEFAULT 0.00000001,
    p_step_size NUMERIC DEFAULT 0.00000001,
    p_min_notional NUMERIC DEFAULT 10
) RETURNS INTEGER AS $$
DECLARE v_symbol_id INTEGER;
BEGIN
    SELECT id INTO v_symbol_id FROM symbols
    WHERE symbol = p_symbol AND exchange = p_exchange;
    
    IF v_symbol_id IS NULL THEN
        INSERT INTO symbols (symbol, base_asset, quote_asset, exchange, tick_size, step_size, min_notional)
        VALUES (p_symbol, p_base_asset, p_quote_asset, p_exchange, p_tick_size, p_step_size, p_min_notional)
        RETURNING id INTO v_symbol_id;
    END IF;
    
    RETURN v_symbol_id;
END;
$$ LANGUAGE plpgsql;

-- Notify listeners of new tick
CREATE OR REPLACE FUNCTION notify_new_tick() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('new_tick', json_build_object(
        'symbol_id', NEW.symbol_id,
        'time', NEW.time,
        'trade_id', NEW.trade_id
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger on trades table
CREATE TRIGGER trades_notify_trigger
    AFTER INSERT ON trades
    FOR EACH ROW
    EXECUTE FUNCTION notify_new_tick();
```

---

## 3. Python Indicator Interface

### 3.1 Base Indicator Class

```python
# src/indicators/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import numpy as np
import hashlib


@dataclass
class IndicatorResult:
    """Result of indicator calculation."""
    name: str
    values: Dict[str, np.ndarray]  # e.g., {"rsi": array([55.5, 56.2, ...])}
    metadata: Dict[str, Any] = None


class Indicator(ABC):
    """
    Base class for all indicators.
    
    Each indicator is a Python class that:
    - Defines its parameters with validation
    - Implements calculation logic
    - Can be serialized/deserialized for versioning
    """
    
    # Class-level metadata
    category: str = None  # 'trend', 'momentum', 'volatility', 'volume'
    description: str = None
    version: str = "1.0.0"
    
    def __init__(self, **params):
        self.params = params
        self._validate_params()
    
    @abstractmethod
    def calculate(self, 
                  prices: np.ndarray, 
                  volumes: np.ndarray,
                  highs: Optional[np.ndarray] = None,
                  lows: Optional[np.ndarray] = None,
                  opens: Optional[np.ndarray] = None,
                  closes: Optional[np.ndarray] = None) -> IndicatorResult:
        """
        Calculate indicator values.
        
        Args:
            prices: Array of prices (required)
            volumes: Array of volumes (required)
            highs: Array of highs (optional, for some indicators)
            lows: Array of lows (optional)
            opens: Array of opens (optional)
            closes: Array of closes (optional)
        
        Returns:
            IndicatorResult with calculated values
        """
        pass
    
    def _validate_params(self):
        """Validate parameters against schema."""
        schema = self.params_schema()
        from jsonschema import validate
        validate(instance=self.params, schema=schema)
    
    @classmethod
    @abstractmethod
    def params_schema(cls) -> Dict:
        """Return JSON Schema for parameter validation."""
        pass
    
    def get_code_hash(self) -> str:
        """Calculate hash of indicator code (for versioning)."""
        import inspect
        source = inspect.getsource(self.__class__)
        return hashlib.sha256(source.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Serialize indicator definition."""
        return {
            'name': self.name,
            'class_name': self.__class__.__name__,
            'module_path': self.__module__,
            'category': self.category,
            'params': self.params,
            'params_schema': self.params_schema(),
            'code_hash': self.get_code_hash(),
            'description': self.description,
        }
    
    @property
    def name(self) -> str:
        """Generate unique name from class + params."""
        params_str = '_'.join(f"{k}{v}" for k, v in sorted(self.params.items()))
        return f"{self.__class__.__name__.lower()}_{params_str}"
```

### 3.2 Example Indicator Implementations

```python
# src/indicators/momentum.py

from .base import Indicator, IndicatorResult
import numpy as np
import talib


class RSIIndicator(Indicator):
    """Relative Strength Index indicator."""
    
    category = 'momentum'
    description = "Measures the speed and magnitude of price changes"
    
    def __init__(self, period: int = 14):
        super().__init__(period=period)
    
    @classmethod
    def params_schema(cls) -> Dict:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "default": 14}
            },
            "required": ["period"]
        }
    
    def calculate(self, prices: np.ndarray, volumes: np.ndarray, **kwargs) -> IndicatorResult:
        rsi = talib.RSI(prices, timeperiod=self.params['period'])
        
        return IndicatorResult(
            name=self.name,
            values={'rsi': rsi},
            metadata={'period': self.params['period']}
        )


class MACDIndicator(Indicator):
    """Moving Average Convergence Divergence."""
    
    category = 'trend'
    description = "Trend-following momentum indicator"
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        super().__init__(
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period
        )
    
    @classmethod
    def params_schema(cls) -> Dict:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "fast_period": {"type": "integer", "minimum": 2, "default": 12},
                "slow_period": {"type": "integer", "minimum": 2, "default": 26},
                "signal_period": {"type": "integer", "minimum": 2, "default": 9}
            },
            "required": ["fast_period", "slow_period", "signal_period"]
        }
    
    def calculate(self, prices: np.ndarray, volumes: np.ndarray, **kwargs) -> IndicatorResult:
        macd, signal, hist = talib.MACD(
            prices,
            fastperiod=self.params['fast_period'],
            slowperiod=self.params['slow_period'],
            signalperiod=self.params['signal_period']
        )
        
        return IndicatorResult(
            name=self.name,
            values={
                'macd': macd,
                'macd_signal': signal,
                'macd_hist': hist
            },
            metadata=self.params
        )
```

### 3.3 Indicator Registry

```python
# src/indicators/registry.py

import importlib
import pkgutil
from typing import Dict, Type, List
from .base import Indicator


class IndicatorRegistry:
    """
    Registry for all available indicators.
    Auto-discovers indicators from modules.
    """
    
    _indicators: Dict[str, Type[Indicator]] = {}
    
    @classmethod
    def discover(cls):
        """Auto-discover all indicator classes."""
        import indicators
        
        for importer, modname, ispkg in pkgutil.iter_modules(indicators.__path__):
            module = importlib.import_module(f"indicators.{modname}")
            
            for name in dir(module):
                obj = getattr(module, name)
                if (isinstance(obj, type) and 
                    issubclass(obj, Indicator) and 
                    obj is not Indicator):
                    cls.register(obj)
    
    @classmethod
    def register(cls, indicator_class: Type[Indicator]):
        """Register an indicator class."""
        instance = indicator_class()
        cls._indicators[instance.name] = indicator_class
    
    @classmethod
    def get(cls, name: str, **params) -> Indicator:
        """Get indicator instance by name."""
        if name not in cls._indicators:
            raise ValueError(f"Unknown indicator: {name}")
        
        indicator_class = cls._indicators[name]
        return indicator_class(**params)
    
    @classmethod
    def list_indicators(cls, category: str = None) -> List[str]:
        """List all registered indicators."""
        if category:
            return [
                name for name, cls in cls._indicators.items()
                if cls.category == category
            ]
        return list(cls._indicators.keys())
```

---

---

## 4. Service Implementations

### 4.1 Data Collection Service (Stage 1)

```python
# src/data_collector/service.py

import asyncio
import asyncpg
import websockets
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional

class DataCollectionService:
    """
    Stage 1: Collect tick data from Binance WebSocket
    and store in PostgreSQL.
    """
    
    def __init__(
        self,
        db_dsn: str,
        symbols: List[str],
        batch_size: int = 500,
        batch_interval: float = 0.5,  # 500ms
    ):
        self.db_dsn = db_dsn
        self.symbols = symbols
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        
        self._db_pool: Optional[asyncpg.Pool] = None
        self._running = False
        self._buffers: Dict[int, List[dict]] = {}  # symbol_id -> trades
        self._symbol_ids: Dict[str, int] = {}
        self._stats = {'records_processed': 0, 'errors': 0}
    
    async def start(self):
        """Start the service."""
        print(f"Starting Data Collection Service...")
        
        # Initialize DB
        self._db_pool = await asyncpg.create_pool(
            self.db_dsn,
            min_size=5,
            max_size=20,
        )
        
        # Initialize symbols
        await self._init_symbols()
        
        self._running = True
        
        # Start tasks
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._collect_trades())
            tg.create_task(self._flush_buffers())
            tg.create_task(self._health_check())
    
    async def stop(self):
        """Stop the service."""
        print("Stopping Data Collection Service...")
        self._running = False
        await self._flush_all_buffers()
        await self._db_pool.close()
    
    async def _init_symbols(self):
        """Initialize symbol mappings (only active symbols)."""
        async with self._db_pool.acquire() as conn:
            # Load only active symbols
            symbols = await conn.fetch(
                "SELECT symbol, base_asset, quote_asset FROM active_symbols"
            )
            
            for row in symbols:
                symbol = row['symbol']
                symbol_id = await conn.fetchval(
                    "SELECT get_or_create_symbol($1, $2, $3)",
                    symbol, row['base_asset'], row['quote_asset']
                )
                self._symbol_ids[symbol] = symbol_id
                self._buffers[symbol_id] = []
        
        print(f"Initialized {len(self._symbol_ids)} active symbols")
    
    async def _collect_trades(self):
        """Connect to Binance WebSocket and collect trades."""
        while self._running:
            try:
                # Build WebSocket URL
                streams = [f"{s.lower().replace('/','')}@trade" for s in self.symbols]
                ws_url = f"wss://stream.binance.com:9443/ws/{'/'.join(streams)}"
                
                async with websockets.connect(ws_url) as ws:
                    print(f"Connected to Binance WebSocket: {ws_url}")
                    
                    while self._running:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        await self._process_trade_msg(msg)
                        
            except Exception as e:
                self._stats['errors'] += 1
                print(f"WebSocket error: {e}")
                await self._log_error('data_collector', f'WebSocket: {e}')
                await asyncio.sleep(5)  # Backoff
    
    async def _process_trade_msg(self, msg: str):
        """Parse and buffer trade message."""
        data = json.loads(msg)
        
        if data.get('e') != 'trade':
            return
        
        # Normalize symbol
        symbol = data['s'].upper()
        symbol = f"{symbol[:3]}/{symbol[3:]}"  # BTCUSDT -> BTC/USDT
        
        if symbol not in self._symbol_ids:
            return
        
        symbol_id = self._symbol_ids[symbol]
        
        # Parse trade
        trade = {
            'time': datetime.fromtimestamp(data['T'] / 1000),
            'symbol_id': symbol_id,
            'trade_id': str(data['t']),
            'price': Decimal(data['p']),
            'quantity': Decimal(data['q']),
            'side': 'SELL' if data['m'] else 'BUY',
            'is_buyer_maker': data['m'],
        }
        
        # Buffer
        self._buffers[symbol_id].append(trade)
        self._stats['records_processed'] += 1
    
    async def _flush_buffers(self):
        """Periodically flush buffers to DB."""
        while self._running:
            await asyncio.sleep(self.batch_interval)
            
            try:
                async with self._db_pool.acquire() as conn:
                    async with conn.transaction():
                        for symbol_id, trades in self._buffers.items():
                            if len(trades) >= 10:  # Small batch for low latency
                                await self._flush_trades(conn, symbol_id, trades)
                                self._buffers[symbol_id] = []
            except Exception as e:
                print(f"Flush error: {e}")
    
    async def _flush_trades(self, conn, symbol_id: int, trades: List[dict]):
        """Batch insert trades."""
        await conn.executemany(
            """
            INSERT INTO trades (time, symbol_id, trade_id, price, quantity, side, is_buyer_maker)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (trade_id, symbol_id) DO NOTHING
            """,
            [
                (t['time'], t['symbol_id'], t['trade_id'], t['price'], 
                 t['quantity'], t['side'], t['is_buyer_maker'])
                for t in trades
            ]
        )
    
    async def _flush_all_buffers(self):
        """Flush all remaining buffers."""
        async with self._db_pool.acquire() as conn:
            for symbol_id, trades in self._buffers.items():
                if trades:
                    await self._flush_trades(conn, symbol_id, trades)
    
    async def _health_check(self):
        """Report health to DB."""
        while self._running:
            await asyncio.sleep(60)
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO service_health 
                    (service_name, status, last_heartbeat, records_processed, updated_at)
                    VALUES ('data_collector', 'healthy', NOW(), $1, NOW())
                    ON CONFLICT (service_name) DO UPDATE SET
                        status = 'healthy',
                        last_heartbeat = NOW(),
                        records_processed = $1,
                        updated_at = NOW()
                    """,
                    self._stats['records_processed']
                )
    
    async def _log_error(self, service: str, message: str):
        """Log error to DB."""
        async with self._db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO event_log (level, service, message, timestamp) VALUES ($1, $2, $3, NOW())",
                'ERROR', service, message
            )
```

### 3.2 Data Enrichment Service (Stage 3)

```python
# src/enrichment/service.py

import asyncio
import asyncpg
import talib  # Technical Analysis Library
import numpy as np
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional
import redis.asyncio as redis

class DataEnrichmentService:
    """
    Stage 3: Listen for new ticks, calculate 50 indicators,
    store in DB, publish to Redis.
    """
    
    def __init__(
        self,
        db_dsn: str,
        redis_url: str,
        window_size: int = 1000,  # Ticks to load for indicator calculation
    ):
        self.db_dsn = db_dsn
        self.redis_url = redis_url
        self.window_size = window_size
        
        self._db_pool: Optional[asyncpg.Pool] = None
        self._redis: Optional[redis.Redis] = None
        self._running = False
        self._stats = {'indicators_calculated': 0, 'errors': 0}
    
    async def start(self):
        """Start the service."""
        print("Starting Data Enrichment Service...")
        
        # Initialize connections
        self._db_pool = await asyncpg.create_pool(self.db_dsn)
        self._redis = redis.from_url(self.redis_url)
        
        self._running = True
        
        # Listen for new ticks
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._listen_ticks())
            tg.create_task(self._health_check())
    
    async def stop(self):
        """Stop the service."""
        print("Stopping Data Enrichment Service...")
        self._running = False
        await self._db_pool.close()
        await self._redis.close()
    
    async def _listen_ticks(self):
        """Listen for PostgreSQL NOTIFY events."""
        async with self._db_pool.acquire() as conn:
            await conn.listen('new_tick')
            print("Listening for new_tick notifications...")
            
            async for notification in conn.notifications():
                if not self._running:
                    break
                
                try:
                    data = json.loads(notification.payload)
                    await self._process_tick(data)
                except Exception as e:
                    self._stats['errors'] += 1
                    print(f"Error processing tick: {e}")
    
    async def _process_tick(self, data: dict):
        """Process new tick: load window, calculate indicators, store, publish."""
        symbol_id = data['symbol_id']
        
        # Load recent tick window
        async with self._db_pool.acquire() as conn:
            ticks = await conn.fetch(
                """
                SELECT time, price, quantity, side
                FROM trades
                WHERE symbol_id = $1
                ORDER BY time DESC
                LIMIT $2
                """,
                symbol_id, self.window_size
            )
        
        if len(ticks) < 50:  # Not enough data
            return
        
        # Reverse to chronological order
        ticks = list(reversed(ticks))
        
        # Extract arrays
        prices = np.array([float(t['price']) for t in ticks])
        volumes = np.array([float(t['quantity']) for t in ticks])
        times = [t['time'] for t in ticks]
        
        # Calculate indicators (TA-Lib)
        indicators = self._calculate_indicators(prices, volumes)
        
        # Get latest tick
        latest = ticks[-1]
        
        # Store enriched record
        async with self._db_pool.acquire() as conn:
            await self._store_indicators(
                conn, symbol_id, latest['time'], 
                latest['price'], latest['quantity'], indicators
            )
        
        # Publish to Redis
        await self._publish_enriched_tick(
            symbol_id, latest['time'], 
            latest['price'], indicators
        )
        
        self._stats['indicators_calculated'] += 1
    
    def _calculate_indicators(self, prices: np.ndarray, volumes: np.ndarray) -> dict:
        """Calculate all 50 indicators using TA-Lib."""
        indicators = {}
        
        # Trend indicators
        indicators['sma_10'] = talib.SMA(prices, timeperiod=10)[-1]
        indicators['sma_20'] = talib.SMA(prices, timeperiod=20)[-1]
        indicators['sma_50'] = talib.SMA(prices, timeperiod=50)[-1]
        indicators['ema_10'] = talib.EMA(prices, timeperiod=10)[-1]
        indicators['ema_20'] = talib.EMA(prices, timeperiod=20)[-1]
        
        macd, macd_signal, macd_hist = talib.MACD(prices)
        indicators['macd'] = macd[-1]
        indicators['macd_signal'] = macd_signal[-1]
        indicators['macd_hist'] = macd_hist[-1]
        
        # Momentum
        indicators['rsi_14'] = talib.RSI(prices, timeperiod=14)[-1]
        slowk, slowd = talib.STOCH(
            prices, prices, prices  # High, Low, Close (using same for tick data)
        )
        indicators['stoch_k'] = slowk[-1]
        indicators['stoch_d'] = slowd[-1]
        
        # Volatility
        bb_upper, bb_middle, bb_lower = talib.BBANDS(prices)
        indicators['bollinger_upper'] = bb_upper[-1]
        indicators['bollinger_middle'] = bb_middle[-1]
        indicators['bollinger_lower'] = bb_lower[-1]
        indicators['atr'] = talib.TRANGE(prices)[-1]  # Simplified
        
        # Volume
        indicators['obv'] = talib.OBV(prices, volumes)[-1]
        indicators['vwap'] = self._calc_vwap(prices, volumes)
        
        # Add more indicators... (all 50)
        
        return indicators
    
    def _calc_vwap(self, prices: np.ndarray, volumes: np.ndarray) -> float:
        """Calculate VWAP."""
        return np.sum(prices * volumes) / np.sum(volumes)
    
    async def _store_indicators(
        self, conn, symbol_id: int, time: datetime,
        price: Decimal, volume: Decimal, indicators: dict
    ):
        """Store enriched tick in DB."""
        await conn.execute(
            """
            INSERT INTO tick_indicators_wide 
            (time, symbol_id, price, volume, sma_10, sma_20, rsi_14, macd, ...)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, ...)
            ON CONFLICT (time, symbol_id) DO NOTHING
            """,
            time, symbol_id, price, volume,
            indicators['sma_10'], indicators['sma_20'], 
            indicators['rsi_14'], indicators['macd'], ...
        )
        
        # Update collection state
        await conn.execute(
            """
            UPDATE collection_state 
            SET last_processed_time = $3, updated_at = NOW()
            WHERE symbol_id = $1 AND data_type = 'indicators'
            """,
            symbol_id, 'indicators', time
        )
    
    async def _publish_enriched_tick(
        self, symbol_id: int, time: datetime,
        price: Decimal, indicators: dict
    ):
        """Publish to Redis for strategies (only if symbol is active)."""
        # Get symbol from DB (only if active)
        async with self._db_pool.acquire() as conn:
            symbol = await conn.fetchval(
                """
                SELECT symbol FROM symbols 
                WHERE id = $1 AND is_active = true
                """,
                symbol_id
            )
        
        # Skip if symbol is not active
        if not symbol:
            return
        
        message = {
            'time': time.isoformat(),
            'symbol': symbol,
            'price': str(price),
            'indicators': indicators,
        }
        
        # Publish to symbol-specific channel
        channel = f"enriched_tick:{symbol}"
        await self._redis.publish(channel, json.dumps(message))
        
        # Also publish to wildcard
        await self._redis.publish("enriched_tick:all", json.dumps(message))
    
    async def _health_check(self):
        """Report health."""
        while self._running:
            await asyncio.sleep(60)
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO service_health 
                    (service_name, status, last_heartbeat, indicators_calculated, updated_at)
                    VALUES ('enrichment', 'healthy', NOW(), $1, NOW())
                    ON CONFLICT (service_name) DO UPDATE SET
                        status = 'healthy',
                        last_heartbeat = NOW(),
                        indicators_calculated = $1,
                        updated_at = NOW()
                    """,
                    self._stats['indicators_calculated']
                )
```

---

## 5. Recalculation Service (Auto-Trigger on Change)

### 5.1 Design

When an indicator definition changes (code or params), the system automatically:
1. Detects the change via PostgreSQL NOTIFY
2. Creates a recalculation job
3. Processes historical data in batches
4. Updates all affected records

### 5.2 Implementation

```python
# src/recalculation/service.py

import asyncio
import asyncpg
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
from indicators.registry import IndicatorRegistry
from indicators.base import Indicator


class RecalculationService:
    """
    Listens for indicator definition changes and triggers
    automatic recalculation of historical data.
    """
    
    def __init__(self, db_dsn: str, batch_size: int = 10000):
        self.db_dsn = db_dsn
        self.batch_size = batch_size
        
        self._db_pool: Optional[asyncpg.Pool] = None
        self._running = False
    
    async def start(self):
        """Start listening for indicator changes."""
        print("Starting Recalculation Service...")
        
        self._db_pool = await asyncpg.create_pool(self.db_dsn)
        self._running = True
        
        # Listen for indicator_changed notifications
        async with self._db_pool.acquire() as conn:
            await conn.listen('indicator_changed')
            print("Listening for indicator_changed notifications...")
            
            async for notification in conn.notifications():
                if not self._running:
                    break
                
                try:
                    data = json.loads(notification.payload)
                    await self._handle_indicator_change(data)
                except Exception as e:
                    print(f"Error handling indicator change: {e}")
    
    async def stop(self):
        """Stop the service."""
        print("Stopping Recalculation Service...")
        self._running = False
        await self._db_pool.close()
    
    async def _handle_indicator_change(self, data: dict):
        """Handle indicator change notification."""
        indicator_id = data['indicator_id']
        indicator_name = data['indicator_name']
        change_type = data['change_type']
        
        print(f"Indicator changed: {indicator_name} ({change_type})")
        
        # Create recalculation job
        job_id = await self._create_recalc_job(indicator_id, indicator_name)
        
        # Start recalculation (async, non-blocking)
        asyncio.create_task(self._run_recalculation(job_id, indicator_id, indicator_name))
    
    async def _create_recalc_job(self, indicator_id: int, indicator_name: str) -> str:
        """Create a recalculation job record."""
        async with self._db_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO recalculation_jobs 
                (indicator_id, indicator_name, status, triggered_by)
                VALUES ($1, $2, 'pending', 'auto')
                RETURNING id
                """,
                indicator_id, indicator_name
            )
            return result['id']
    
    async def _run_recalculation(self, job_id: str, indicator_id: int, indicator_name: str):
        """Run the recalculation process."""
        async with self._db_pool.acquire() as conn:
            # Update status to running
            await conn.execute(
                """
                UPDATE recalculation_jobs 
                SET status = 'running', started_at = NOW()
                WHERE id = $1
                """,
                job_id
            )
            
            try:
                # Get indicator instance
                indicator = IndicatorRegistry.get(indicator_name)
                
                # Get all symbols
                symbols = await conn.fetch(
                    "SELECT id, symbol FROM symbols WHERE is_active = true"
                )
                
                ticks_processed = 0
                
                for symbol_row in symbols:
                    symbol_id = symbol_row['id']
                    symbol = symbol_row['symbol']
                    
                    print(f"Recalculating {indicator_name} for {symbol}...")
                    
                    # Process in batches
                    offset = 0
                    while True:
                        # Load tick data (prices, volumes)
                        ticks = await conn.fetch(
                            """
                            SELECT time, price, quantity
                            FROM trades
                            WHERE symbol_id = $1
                            ORDER BY time
                            LIMIT $2 OFFSET $3
                            """,
                            symbol_id, self.batch_size, offset
                        )
                        
                        if not ticks:
                            break
                        
                        # Calculate indicators
                        prices = np.array([float(t['price']) for t in ticks])
                        volumes = np.array([float(t['quantity']) for t in ticks])
                        
                        result = indicator.calculate(prices, volumes)
                        
                        # Update tick_indicators table
                        await self._update_indicators(
                            conn, symbol_id, ticks, result.values
                        )
                        
                        ticks_processed += len(ticks)
                        offset += self.batch_size
                        
                        # Update progress
                        await conn.execute(
                            """
                            UPDATE recalculation_jobs 
                            SET ticks_processed = $1
                            WHERE id = $2
                            """,
                            ticks_processed, job_id
                        )
                
                # Mark as completed
                await conn.execute(
                    """
                    UPDATE recalculation_jobs 
                    SET status = 'completed', 
                        completed_at = NOW(),
                        duration_seconds = NOW() - started_at,
                        ticks_processed = $1
                    WHERE id = $2
                    """,
                    ticks_processed, job_id
                )
                
                # Update indicator last_calculated_at
                await conn.execute(
                    """
                    UPDATE indicator_definitions 
                    SET last_calculated_at = NOW()
                    WHERE id = $1
                    """,
                    indicator_id
                )
                
                print(f"Recalculation completed: {indicator_name}")
                
            except Exception as e:
                # Mark as failed
                await conn.execute(
                    """
                    UPDATE recalculation_jobs 
                    SET status = 'failed', 
                        errors_count = errors_count + 1,
                        last_error = $1
                    WHERE id = $2
                    """,
                    str(e), job_id
                )
                print(f"Recalculation failed: {indicator_name} - {e}")
    
    async def _update_indicators(
        self, conn, symbol_id: int, ticks: List, indicator_values: Dict[str, np.ndarray]
    ):
        """Update indicator values for a batch of ticks."""
        # Build updates
        updates = []
        for i, tick in enumerate(ticks):
            values_dict = {
                key: float(arr[i]) if not np.isnan(arr[i]) else None
                for key, arr in indicator_values.items()
            }
            
            updates.append((
                tick['time'],
                symbol_id,
                tick['price'],
                tick['quantity'],
                json.dumps(values_dict),
                list(values_dict.keys()),
            ))
        
        # Batch upsert
        await conn.executemany(
            """
            INSERT INTO tick_indicators 
            (time, symbol_id, price, volume, values, indicator_keys, inserted_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (time, symbol_id) DO UPDATE SET
                values = EXCLUDED.values,
                indicator_keys = EXCLUDED.indicator_keys,
                updated_at = NOW()
            """,
            updates
        )
```

### 5.3 Manual Recalculation CLI

```python
# src/cli/recalculate.py

import asyncio
import click
import asyncpg


@click.command()
@click.option('--indicator', '-i', required=True, help='Indicator name')
@click.option('--symbol', '-s', default=None, help='Symbol (default: all)')
@click.option('--days', '-d', default=None, type=int, help='Days to recalculate')
@click.option('--from-date', '-f', default=None, help='Start date (YYYY-MM-DD)')
@click.option('--to-date', '-t', default=None, help='End date (YYYY-MM-DD)')
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
def recalculate(indicator, symbol, days, from_date, to_date, db_dsn):
    """
    Manually trigger indicator recalculation.
    
    Examples:
    
    # Recalculate RSI for all symbols, last 30 days
    recalculate -i rsi_14 --days 30
    
    # Recalculate MACD for BTC/USDT only
    recalculate -i macd -s BTC/USDT
    
    # Recalculate with date range
    recalculate -i bollinger --from-date 2024-01-01 --to-date 2024-01-31
    """
    asyncio.run(_run_recalculate(
        indicator, symbol, days, from_date, to_date, db_dsn
    ))


async def _run_recalculate(indicator, symbol, days, from_date, to_date, db_dsn):
    """Execute recalculation."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            # Get indicator ID
            indicator_id = await conn.fetchval(
                "SELECT id FROM indicator_definitions WHERE name = $1",
                indicator
            )
            
            if not indicator_id:
                print(f"Unknown indicator: {indicator}")
                return
            
            # Get symbol ID (if specified)
            symbol_id = None
            if symbol:
                symbol_id = await conn.fetchval(
                    "SELECT id FROM symbols WHERE symbol = $1",
                    symbol
                )
                if not symbol_id:
                    print(f"Unknown symbol: {symbol}")
                    return
            
            # Calculate date range
            time_start = None
            time_end = None
            
            if days:
                time_start = await conn.fetchval(
                    "SELECT NOW() - INTERVAL '1 day' * $1", days
                )
            
            if from_date:
                time_start = from_date
            
            if to_date:
                time_end = to_date
            
            # Create job
            result = await conn.fetchrow(
                """
                INSERT INTO recalculation_jobs 
                (indicator_id, indicator_name, symbol_id, time_start, time_end,
                 status, triggered_by, triggered_by_user)
                VALUES ($1, $2, $3, $4, $5, 'pending', 'manual', current_user)
                RETURNING id
                """,
                indicator_id, indicator, symbol_id, time_start, time_end
            )
            
            job_id = result['id']
            print(f"Created recalculation job: {job_id}")
            print(f"Indicator: {indicator}")
            print(f"Symbol: {symbol or 'ALL'}")
            print(f"Time range: {time_start} to {time_end}")
            print("\nMonitor progress:")
            print(f"  SELECT * FROM recalculation_jobs WHERE id = '{job_id}';")
    
    finally:
        await pool.close()
```

---

## 6. Performance Considerations

### 6.1 Expected Load

| Metric | Value |
|--------|-------|
| Ticks per second (10 symbols) | ~1,000 |
| Indicators per tick | 50 |
| Indicator calculations/sec | 50,000 |
| DB inserts/sec (trades) | 1,000 |
| DB inserts/sec (indicators) | 1,000 |
| Redis publishes/sec | 1,000 |

### 6.2 Bottlenecks & Solutions

| Bottleneck | Solution |
|------------|----------|
| DB insert rate | Batch inserts, connection pool, partitioning |
| Indicator calculation | TA-Lib (C-based), async processing |
| Memory (window loading) | Keep window in memory per symbol, update incrementally |
| Redis latency | Local Redis, pipelining |

---

## 7. Next Steps

1. **Set up PostgreSQL** with schema
2. **Set up Redis** for message queue
3. **Implement DataCollectionService** - test with 1-2 symbols
4. **Implement DataEnrichmentService** - verify indicator calculation
5. **Implement RecalculationService** - test auto-recalculation
6. **Create indicator library** - implement 5-10 core indicators
7. **Create test strategy** - subscribe to Redis, print ticks
8. **Scale to all symbols** - monitor performance

Shall I proceed with implementing these services?

---

## 8. Managing Active Symbols

### 8.1 Activate/Deactivate Symbols

Symbols can be activated or deactivated at runtime. This controls:
- **Data collection** - Only active symbols collect ticks
- **Indicator calculation** - Only active symbols get indicators calculated
- **Strategy signals** - Strategies only receive ticks for active symbols

```sql
-- Activate a symbol
UPDATE symbols SET is_active = true WHERE symbol = 'BTC/USDT';

-- Deactivate a symbol (stops data collection & indicator calculation)
UPDATE symbols SET is_active = false WHERE symbol = 'OLDPAIR/USDT';

-- List all active symbols
SELECT symbol FROM active_symbols ORDER BY symbol;

-- List all inactive symbols
SELECT symbol FROM symbols WHERE is_active = false ORDER BY symbol;
```

### 8.2 Workflow: Adding a New Symbol

```sql
-- 1. Add symbol to database
INSERT INTO symbols (symbol, base_asset, quote_asset, is_active)
VALUES ('NEW/USDT', 'NEW', 'USDT', false);  -- Start inactive

-- 2. Backfill historical data (run backfill service)
-- python -m cli.backfill --symbol NEW/USDT --days 30

-- 3. Activate symbol (starts live data collection & indicator calculation)
UPDATE symbols SET is_active = true WHERE symbol = 'NEW/USDT';

-- 4. Verify symbol is being processed
SELECT symbol, is_active FROM symbols WHERE symbol = 'NEW/USDT';
SELECT * FROM collection_state 
WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'NEW/USDT');
```

### 8.3 Performance Impact

| Scenario | Symbols | Ticks/sec | Indicator Calcs/sec | DB Inserts/sec |
|----------|---------|-----------|---------------------|----------------|
| Minimal | 1 | ~100 | 5,000 | 200 |
| Recommended | 10 | ~1,000 | 50,000 | 2,000 |
| Maximum | 50 | ~5,000 | 250,000 | 10,000 |

**Recommendation**: Start with 5-10 active symbols, monitor performance, then scale.

### 8.4 Automatic Deactivation

Consider auto-deactivating symbols with:
- No ticks for > 24 hours (dead pair)
- Trading volume < threshold (illiquid pair)
- Delisted from exchange

```sql
-- Example: Find symbols with no recent ticks
SELECT s.symbol, MAX(t.time) AS last_tick
FROM symbols s
LEFT JOIN trades t ON t.symbol_id = s.id
WHERE s.is_active = true
GROUP BY s.symbol
HAVING MAX(t.time) < NOW() - INTERVAL '24 hours';
```
