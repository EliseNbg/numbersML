# Phase 4: Strategy Management & Backtesting Dashboard

## Overview
Phase 4 focuses on creating a robust, decoupled management system for trading strategies. It introduces the concept of `ConfigurationSet` to separate algorithm logic from runtime parameters, and provides a rich dashboard for orchestration, monitoring, and backtesting.

## 1. ConfigurationSet & Strategy Instance Management

### 1.1 Data Models
*   **ConfigurationSet**:
    *   `id`: UUID
    *   `name`: String
    *   `description`: String
    *   `config`: JSONB (symbol, thresholds, risk, initial_balance, etc.)
    *   `created_at`, `updated_at`: Timestamps
*   **StrategyInstance**:
    *   `id`: UUID
    *   `strategy_id`: UUID (FK to `strategies`)
    *   `config_set_id`: UUID (FK to `configuration_sets`)
    *   `status`: String (stopped, running, error)
    *   `last_run_at`: Timestamp
    *   `statistics`: JSONB (PnL, trades, etc.)

### 1.2 Backend Tasks
*   [ ] SQL Migration: Create `configuration_sets` and `strategy_instances` tables.
*   [ ] Domain Layer: Implement `ConfigurationSet` and `StrategyInstance` entities.
*   [ ] Repository Layer: Implement PostgreSQL repositories for the new entities.
*   [ ] API Layer:
    *   `GET /api/config-sets`: List all configuration sets.
    *   `POST /api/config-sets`: Create new configuration set.
    *   `PUT /api/config-sets/{id}`: Update configuration set.
    *   `DELETE /api/config-sets/{id}`: Remove configuration set.
    *   `POST /api/strategy-instances`: Link a Strategy with a ConfigurationSet.
    *   `POST /api/strategy-instances/{id}/start`: Start (hot-plug) instance.
    *   `POST /api/strategy-instances/{id}/stop`: Stop (unplug) instance.

### 1.3 Frontend Tasks
*   [ ] **ConfigurationSet Dashboard**:
    *   CRUD interface for config sets.
    *   Dynamic parameter editing (Add/Remove parameters).
*   [ ] **Strategy Management**:
    *   CRUD interface for Strategy definitions (from Phase 3).
*   [ ] **Strategy Instance Dashboard**:
    *   Table showing linked Strategy/Config pairs.
    *   Hot-plug toggle (Start/Stop).
    *   Real-time stats display (PnL, Uptime, buying/selling points).

## 2. Advanced Backtesting Integration

### 2.1 Backend Tasks
*   [ ] Update `BacktestEngine` to accept a `StrategyInstance`.
*   [ ] Ensure `BacktestEngine` uses the Phase 3 `MarketService` and `Ticker` data.
*   [ ] **No Recalculation Rule**: Indicators MUST be read from `candle_indicators` (Ticker) and not recalculated during backtest.
*   [ ] API for backtest execution:
    *   `POST /api/strategy-instances/{id}/backtest`: Start backtest with range (4h, 12h, 1d, 3d, 7d, 1m).
    *   `GET /api/backtests/{job_id}`: Get progress and results.

### 2.2 Frontend Tasks
*   [ ] **Backtest Result Page**:
    *   Price chart with buy/sell markers.
    *   Equity curve chart.
    *   Detailed metrics table (PnL, Sharpe, Drawdown, etc.).
    *   Time range selector.

## 3. Simple Grid Strategy & Integration Testing

### 3.1 Grid Strategy
*   [ ] Implement `SimpleGridStrategy` in `src/domain/strategies/grid.py`.
*   [ ] Logic: Buy at low grid lines, sell at high grid lines based on price oscillations.

### 3.2 Integration & Test Data
*   [ ] Create a default `ConfigurationSet` for `TEST/USDT`.
*   [ ] Synthetic Data: Ensure "noised sin" data generates positive PnL for the grid strategy.
*   [ ] Update `migrations/test_data.sql`: Add `SimpleGridStrategy` and its `ConfigurationSet` for `TEST/USDT`.
*   [ ] Automated Test: Verify that starting the Grid strategy on `TEST/USDT` produces signals and positive PnL in a short integration run.

## 4. Acceptance Criteria
1.  User can create a `ConfigurationSet` with custom parameters via Dashboard.
2.  User can link a `Strategy` to a `ConfigurationSet` and start it without restarting the pipeline.
3.  Backtest for a Strategy-Config pair can be executed and visualized on a chart.
4.  The system uses existing indicators from the DB during backtests.
5.  `SimpleGridStrategy` is functional and included in the default test data.
