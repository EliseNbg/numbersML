# Trading Algorithm Management Platform - Next Phase Plan

## Overview
This plan details the implementation of a complete trading algorithm management system with web GUI, market service, algorithm activation/deactivation, and backtesting capabilities.

## Architecture

### Core Components to Build

#### 1. Algorithm Configuration & Persistence Layer
**Objective**: Store, retrieve, and manage trading algorithms in the database

**Database Schema Additions**:
```sql
CREATE TABLE trading_algorithms (
    id SERIAL PRIMARY KEY,
    algorithm_id VARCHAR(100) UNIQUE NOT NULL,
    algorithm_type VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    symbols TEXT[] NOT NULL,
    parameters JSONB NOT NULL,
    is_active BOOLEAN DEFAULT false NOT NULL,
    confidence_threshold FLOAT DEFAULT 0.5,
    risk_level VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    version INTEGER DEFAULT 1
);

CREATE TABLE algorithm_execution_log (
    id BIGSERIAL PRIMARY KEY,
    algorithm_id VARCHAR(100) NOT NULL,
    execution_mode VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    signal_price NUMERIC(20,10),
    execution_price NUMERIC(20,10),
    quantity NUMERIC(20,10),
    pnl NUMERIC(20,10),
    pnl_percent NUMERIC(10,4),
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending',
    metadata JSONB
);

CREATE TABLE backtest_results (
    id SERIAL PRIMARY KEY,
    algorithm_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    initial_capital NUMERIC(20,2) NOT NULL,
    final_capital NUMERIC(20,2) NOT NULL,
    total_return NUMERIC(20,4),
    total_return_pct NUMERIC(10,4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate NUMERIC(10,4),
    profit_factor NUMERIC(10,4),
    sharpe_ratio NUMERIC(10,4),
    max_drawdown NUMERIC(10,4),
    avg_trade_duration INTERVAL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    parameters_snapshot JSONB
);
```

#### 2. Algorithm Management Service (Application Layer)
**File**: `src/application/services/algorithm_manager.py`

```python
class AlgorithmManager:
    async def create_algorithm(self, algorithm_data: Dict) -> Dict
    async def update_algorithm(self, algorithm_id: str, updates: Dict) -> bool
    async def delete_algorithm(self, algorithm_id: str) -> bool
    async def get_algorithm(self, algorithm_id: str) -> Dict
    async def list_algorithms(self, active_only: bool = False) -> List[Dict]
    async def activate_algorithm(self, algorithm_id: str) -> bool
    async def deactivate_algorithm(self, algorithm_id: str) -> bool
    async def execute_algorithm(self, algorithm_id: str, mode: str) -> Signal
    async def get_algorithm_stats(self, algorithm_id: str) -> Dict
```

#### 3. Market Service (Trading Execution)
**File**: `src/infrastructure/exchanges/market_service.py`

```python
class MarketService:
    def __init__(self, mode: str = 'test'):
        self.mode = mode
        self.balance = 100000.0
        self.positions = {}
    
    async def place_order(self, order: OrderRequest) -> OrderResponse
    async def get_market_price(self, symbol: str) -> float
    async def get_order_book(self, symbol: str, depth: int) -> Dict
    async def get_position(self, symbol: str) -> Optional[Position]
    async def close_position(self, symbol: str) -> OrderResponse
```

#### 4. Backtesting Engine
**File**: `src/application/services/backtest_engine.py`

```python
class BacktestEngine:
    async def run_backtest(
        self, algorithm_id: str, symbol: str,
        start_time: datetime, end_time: datetime,
        initial_capital: float
    ) -> BacktestResult
    
    def calculate_statistics(self, trades: List[Trade]) -> Dict
    async def generate_report(self, result: BacktestResult) -> Dict
```

#### 5. Dashboard API Routes
- `src/infrastructure/api/routes/algorithms.py`
- `src/infrastructure/api/routes/market.py`
- `src/infrastructure/api/routes/backtest.py` (extend)

#### 6. Web GUI Components
- `dashboard/algorithm-manager.html`
- `dashboard/market-controls.html`
- `dashboard/backtest-interface.html`
- `dashboard/algorithm-activator.html`
- `dashboard/js/algorithm-manager.js`
- `dashboard/js/market-service.js`
- `dashboard/js/backtest-runner.js`

## Implementation Phases

### Phase 1: Database & Domain Layer (Week 1)
**Tasks**:
1. Add algorithm tables to database schema
2. Create database migration scripts
3. Update domain models for algorithms
4. Implement algorithm repository pattern

**Files**:
- `migrations/` - Migration SQL files
- `src/domain/models/algorithm.py` - New model
- `src/domain/algorithms/base.py` - Enhance base class
- `src/domain/repositories/algorithm_repo.py` - Repository

### Phase 2: Service Layer (Week 1-2)
**Tasks**:
1. Implement AlgorithmManager service
2. Implement MarketService with test/prod modes
3. Implement BacktestEngine
4. Integrate with existing AlgorithmRunner

**Files to create**:
- `src/application/services/algorithm_manager.py`
- `src/infrastructure/exchanges/market_service.py`
- `src/application/services/backtest_engine.py`

**Files to modify**:
- `src/application/services/algorithm_runner.py`
- `src/domain/algorithms/__init__.py`

### Phase 3: API Layer (Week 2)
**Tasks**:
1. Create Algorithm API routes (CRUD, activate/deactivate)
2. Create Market Service API routes
3. Create Backtest API routes
4. Add routes to FastAPI app

**Files to create**:
- `src/infrastructure/api/routes/algorithms.py`
- `src/infrastructure/api/routes/market.py`

**Files to modify**:
- `src/infrastructure/api/routes/backtest.py`
- `src/infrastructure/api/routes/__init__.py`
- `src/infrastructure/api/app.py`

### Phase 4: Web GUI (Week 2-3)
**Tasks**:
1. Create HTML templates for algorithm management
2. Create market controls interface
3. Create backtesting interface
4. Add JavaScript for API interactions
5. Style with existing CSS framework

**Files to create**:
- `dashboard/algorithm-manager.html`
- `dashboard/market-controls.html`
- `dashboard/backtest-interface.html`
- `dashboard/algorithm-activator.html`
- `dashboard/js/algorithm-manager.js`
- `dashboard/js/market-service.js`
- `dashboard/js/backtest-runner.js`
- `dashboard/css/algorithm-styles.css`

### Phase 5: Integration & Testing (Week 3)
**Tasks**:
1. Unit tests for new services
2. Integration tests for API
3. End-to-end tests for full flow
4. Documentation updates

**Files to create**:
- `tests/unit/test_algorithm_manager.py`
- `tests/unit/test_market_service.py`
- `tests/unit/test_backtest_engine.py`
- `tests/integration/test_algorithm_flow.py`

## API Endpoints

### Algorithm Management
```
GET    /api/algorithms              - List all algorithms
POST   /api/algorithms              - Create new algorithm
GET    /api/algorithms/{id}         - Get algorithm details
PUT    /api/algorithms/{id}         - Update algorithm
DELETE /api/algorithms/{id}         - Delete algorithm
POST   /api/algorithms/{id}/activate   - Activate algorithm
POST   /api/algorithms/{id}/deactivate - Deactivate algorithm
POST   /api/algorithms/{id}/execute    - Execute algorithm (test/prod)
GET    /api/algorithms/{id}/stats   - Get algorithm statistics
```

### Market Service
```
GET    /api/market/price/{symbol}       - Get current price
POST   /api/market/order                - Place order
GET    /api/market/orderbook/{symbol}   - Get order book
GET    /api/market/position/{symbol}    - Get position
POST   /api/market/close/{symbol}       - Close position
POST   /api/market/mode                 - Set mode (test/prod)
```

### Backtesting
```
POST   /api/backtest_ml/run                - Run backtest
GET    /api/backtest_ml/results/{id}       - Get backtest results
GET    /api/backtest_ml/list               - List all backtests
POST   /api/backtest_ml/compare            - Compare multiple algorithms
```

## Database Schema Details

### trading_algorithms table
```sql
CREATE TABLE trading_algorithms (
    id SERIAL PRIMARY KEY,
    algorithm_id VARCHAR(100) UNIQUE NOT NULL,
    algorithm_type VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    symbols TEXT[] NOT NULL,
    parameters JSONB NOT NULL,
    is_active BOOLEAN DEFAULT false,
    confidence_threshold FLOAT DEFAULT 0.5,
    risk_level VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    version INTEGER DEFAULT 1
);

CREATE INDEX idx_algorithms_active ON trading_algorithms(is_active) WHERE is_active = true;
CREATE INDEX idx_algorithms_type ON trading_algorithms(algorithm_type);
```

### algorithm_execution_log table
```sql
CREATE TABLE algorithm_execution_log (
    id BIGSERIAL PRIMARY KEY,
    algorithm_id VARCHAR(100) NOT NULL,
    execution_mode VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    signal_price NUMERIC(20,10),
    execution_price NUMERIC(20,10),
    quantity NUMERIC(20,10),
    pnl NUMERIC(20,10),
    pnl_percent NUMERIC(10,4),
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending',
    metadata JSONB,
    FOREIGN KEY (algorithm_id) REFERENCES trading_algorithms(algorithm_id)
);

CREATE INDEX idx_exec_log_algorithm ON algorithm_execution_log(algorithm_id);
CREATE INDEX idx_exec_log_time ON algorithm_execution_log(executed_at DESC);
```

### backtest_results table
```sql
CREATE TABLE backtest_results (
    id SERIAL PRIMARY KEY,
    algorithm_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    initial_capital NUMERIC(20,2) NOT NULL,
    final_capital NUMERIC(20,2) NOT NULL,
    total_return NUMERIC(20,4),
    total_return_pct NUMERIC(10,4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate NUMERIC(10,4),
    profit_factor NUMERIC(10,4),
    sharpe_ratio NUMERIC(10,4),
    max_drawdown NUMERIC(10,4),
    avg_trade_duration INTERVAL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    parameters_snapshot JSONB,
    FOREIGN KEY (algorithm_id) REFERENCES trading_algorithms(algorithm_id)
);

CREATE INDEX idx_backtest_algorithm ON backtest_results(algorithm_id);
CREATE INDEX idx_backtest_time ON backtest_results(start_time, end_time);
```

## Best Practices

### Configuration Variables Design
- JSONB for flexible algorithm parameters
- Parameter validation schemas
- Version algorithms for audit trail
- Dynamic parameter updates
- Confidence thresholds

### Integration with Existing System
- Reuses Algorithm base class from domain layer
- Leverages existing Redis pub/sub for tick data
- Uses existing indicator calculator
- Compatible with existing pipeline architecture

### Testing Best Practices
- All tests async with pytest-asyncio
- Mock external API calls
- Test fixtures for database
- Test both test and prod modes
- Coverage > 90% for new code

### Security Measures
- Input validation on all endpoints
- Rate limiting on trading endpoints
- Mode protection (prod vs test separation)
- Audit logging for all trades
- Parameter sanitization

## Rollout Plan

### Week 1: Foundation
- Database schema additions
- Domain layer implementation
- Repository pattern

### Week 2: Core Features
- CRUD APIs complete
- Market service (test mode)
- Backtest engine

### Week 3: Integration
- Web GUI implementation
- Prod mode for market service
- Dashboard integration
- Testing and bug fixes

### Week 4: Polish
- Documentation updates
- Performance optimization
- Security review
- User acceptance testing

## Success Metrics

- All CRUD operations working
- Algorithms can be activated from dashboard
- Backtests complete with >95% accuracy
- Paper trading mode functional
- Live trading mode ready (with safeguards)
- 90%+ test coverage
- <100ms API response time
- Zero data loss or corruption

## Dependencies

- Existing: FastAPI, asyncpg, Redis, PostgreSQL
- No new dependencies required
- Frontend: Vanilla JS + existing CSS framework

## Risk Mitigation

1. **Production Trading Risk**: Test mode by default, confirmation dialogs
2. **Data Integrity**: DB transactions, backup before migrations
3. **Performance**: Proper indexing, async throughout
4. **Security**: Input validation, rate limiting, mode separation
5. **Rollback**: Reversible migrations, versioned algorithms
