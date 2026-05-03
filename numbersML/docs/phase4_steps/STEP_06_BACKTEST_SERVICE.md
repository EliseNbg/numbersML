# Step 6: Real Backtest Engine Service

## Objective
Implement a real backtest engine that uses historical data and existing indicators (no recalculation) to simulate strategy performance.

## Context
- Step 1-5 complete: ConfigurationSet and StrategyInstance entities, repositories, and APIs exist
- Phase 3 complete: MarketService (PaperMarketService) exists
- Phase 3 partial: Backtest API exists but uses simulated data (see `src/infrastructure/api/routes/strategy_backtest.py`)
- **Key Requirement**: Use pipeline Ticker, read indicators from `candle_indicators` table (NO recalculation)

## DDD Architecture Decision (ADR)

**Decision**: BacktestEngine is an Application Service
- **Input**: StrategyInstance (Strategy + ConfigurationSet)
- **Data Source**: `candles_1s` + `candle_indicators` tables (historical)
- **Execution**: Replay candles through strategy, simulate trades via PaperMarketService
- **Output**: BacktestResult with PnL, trades, equity curve, metrics

**No Recalculation Rule**:
- Indicators MUST be read from `candle_indicators` (already calculated by pipeline)
- This ensures backtest matches production behavior exactly

## TDD Approach

1. **Red**: Write tests with controlled dataset (known candles + indicators)
2. **Green**: Implement engine to pass tests
3. **Refactor**: Add metrics calculation, optimization

## Implementation Files

### 1. `src/application/services/backtest_service.py`

```python
"""
Real backtest engine service.

Uses historical data and existing indicators to simulate strategy performance.
Follows DDD: Application Layer service.

Key Design:
- Reads candles from candles_1s table
- Reads indicators from candle_indicators table (NO recalculation)
- Replays candles through strategy signal generation
- Simulates trades via PaperMarketService
- Calculates real PnL, Sharpe, max drawdown, etc.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import asyncpg

from src.domain.strategies.base import Strategy, Signal, SignalType, EnrichedTick
from src.domain.strategies.strategy_instance import StrategyInstance, RuntimeStats
from src.infrastructure.database import get_db_pool_async
from src.infrastructure.market.paper_market_service import PaperMarketService

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Record of a single simulated trade."""
    entry_time: datetime
    exit_time: datetime
    side: str  # 'LONG' or 'SHORT'
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    reason: str  # 'signal' or 'stop_loss' or 'take_profit'


@dataclass
class BacktestResult:
    """Complete backtest results."""
    job_id: str
    strategy_instance_id: UUID
    time_range_start: datetime
    time_range_end: datetime
    initial_balance: float
    final_balance: float
    total_return: float
    total_return_pct: float
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Risk metrics
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    profit_factor: float
    
    # Detailed data
    trades: List[TradeRecord]
    equity_curve: List[Dict[str, Any]]  # [{"time": ..., "balance": ...}]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "job_id": self.job_id,
            "strategy_instance_id": str(self.strategy_instance_id),
            "time_range_start": self.time_range_start.isoformat(),
            "time_range_end": self.time_range_end.isoformat(),
            "initial_balance": self.initial_balance,
            "final_balance": self.final_balance,
            "total_return": self.total_return,
            "total_return_pct": self.total_return_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "trades": [vars(t) for t in self.trades],
            "equity_curve": self.equity_curve,
        }


class BacktestService:
    """
    Application service for running backtests.
    
    Uses historical data and existing indicators (no recalculation).
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.
        
        Args:
            db_pool: asyncpg connection pool
        """
        self._pool = db_pool
    
    async def run_backtest(
        self,
        job_id: str,
        strategy_instance: StrategyInstance,
        time_range_start: datetime,
        time_range_end: datetime,
        initial_balance: float = 10000.0,
    ) -> BacktestResult:
        """
        Run a backtest for a StrategyInstance.
        
        Args:
            job_id: Unique job identifier
            strategy_instance: StrategyInstance to backtest
            time_range_start: Start of backtest period
            time_range_end: End of backtest period
            initial_balance: Starting capital
            
        Returns:
            BacktestResult with all metrics and trade data
            
        Raises:
            ValueError: If time range is invalid or no data found
        """
        if time_range_end <= time_range_start:
            raise ValueError("time_range_end must be after time_range_start")
        
        # Load historical candles with indicators (NO recalculation)
        candles = await self._load_candles(
            strategy_instance, time_range_start, time_range_end
        )
        
        if not candles:
            raise ValueError("No candle data found for the specified time range")
        
        # Initialize paper market service for simulation
        market_service = PaperMarketService(
            initial_balance=initial_balance,
            fee_bps=10,  # 0.1% fee
            slippage_bps=10,  # 0.1% slippage
        )
        
        # Replay candles and simulate
        result = await self._replay_candles(
            job_id=job_id,
            strategy_instance=strategy_instance,
            candles=candles,
            market_service=market_service,
            initial_balance=initial_balance,
        )
        
        return result
    
    async def _load_candles(
        self,
        strategy_instance: StrategyInstance,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Load historical candles with indicators from database.
        
        KEY: Reads from candle_indicators table (NO recalculation).
        
        Args:
            strategy_instance: StrategyInstance (provides config_set with symbols)
            start: Start time
            end: End time
            
        Returns:
            List of candle dictionaries with indicators
        """
        async with self._pool.acquire() as conn:
            # Get symbols from ConfigurationSet config
            # Note: This requires loading ConfigurationSet
            # For now, assume we have symbols in config
            symbols = ["BTC/USDT"]  # TODO: Get from config_set
            
            # Fetch symbol IDs
            symbol_rows = await conn.fetch(
                "SELECT id, symbol FROM symbols WHERE symbol = ANY($1)",
                symbols,
            )
            
            if not symbol_rows:
                return []
            
            symbol_ids = [row["id"] for row in symbol_rows]
            
            # Fetch candles with indicators (NO recalculation)
            rows = await conn.fetch(
                """
                SELECT 
                    c.time, c.open, c.high, c.low, c.close, c.volume,
                    ci.values as indicators
                FROM candles_1s c
                LEFT JOIN candle_indicators ci 
                    ON c.time = ci.time AND c.symbol_id = ci.symbol_id
                WHERE c.symbol_id = ANY($1)
                    AND c.time >= $2 
                    AND c.time <= $3
                ORDER BY c.time ASC
                """,
                symbol_ids,
                start,
                end,
            )
            
            candles = []
            for row in rows:
                candles.append({
                    "time": row["time"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "indicators": row["indicators"] or {},
                })
            
            return candles
    
    async def _replay_candles(
        self,
        job_id: str,
        strategy_instance: StrategyInstance,
        candles: List[Dict[str, Any]],
        market_service: PaperMarketService,
        initial_balance: float,
    ) -> BacktestResult:
        """
        Replay candles and simulate trading.
        
        Args:
            job_id: Job identifier
            strategy_instance: StrategyInstance
            candles: Historical candle data with indicators
            market_service: Paper market service for simulation
            initial_balance: Starting balance
            
        Returns:
            BacktestResult with all metrics
        """
        trades: List[TradeRecord] = []
        equity_curve = [{"time": candles[0]["time"].isoformat(), "balance": initial_balance}]
        
        current_balance = initial_balance
        open_position: Optional[TradeRecord] = None
        
        for candle in candles:
            # Create EnrichedTick from candle (with indicators)
            tick = EnrichedTick(
                symbol="BTC/USDT",  # TODO: Get from config
                price=Decimal(str(candle["close"])),
                volume=Decimal(str(candle["volume"])),
                time=candle["time"],
                indicators=self._flatten_indicators(candle["indicators"]),
            )
            
            # Generate signal (would call strategy.on_tick())
            # For now, simulate simple strategy
            signal = self._generate_signal(tick, strategy_instance)
            
            if signal:
                if signal.signal_type == SignalType.BUY and not open_position:
                    # Open long position
                    open_position = TradeRecord(
                        entry_time=candle["time"],
                        exit_time=candle["time"],  # Will update later
                        side="LONG",
                        entry_price=candle["close"],
                        exit_price=candle["close"],
                        quantity=0.01,  # TODO: Calculate from risk params
                        pnl=0.0,
                        pnl_percent=0.0,
                        reason="signal",
                    )
                
                elif signal.signal_type == SignalType.SELL and open_position:
                    # Close long position
                    pnl = (candle["close"] - open_position.entry_price) * open_position.quantity
                    pnl_pct = (candle["close"] - open_position.entry_price) / open_position.entry_price * 100
                    
                    trade = TradeRecord(
                        entry_time=open_position.entry_time,
                        exit_time=candle["time"],
                        side="LONG",
                        entry_price=open_position.entry_price,
                        exit_price=candle["close"],
                        quantity=open_position.quantity,
                        pnl=pnl,
                        pnl_percent=pnl_pct,
                        reason="signal",
                    )
                    trades.append(trade)
                    current_balance += pnl
                    
                    equity_curve.append({
                        "time": candle["time"].isoformat(),
                        "balance": current_balance,
                    })
                    
                    open_position = None
        
        # Close any remaining open position at last price
        if open_position:
            last_candle = candles[-1]
            pnl = (last_candle["close"] - open_position.entry_price) * open_position.quantity
            trade = TradeRecord(
                entry_time=open_position.entry_time,
                exit_time=last_candle["time"],
                side="LONG",
                entry_price=open_position.entry_price,
                exit_price=last_candle["close"],
                quantity=open_position.quantity,
                pnl=pnl,
                pnl_percent=pnl / open_position.entry_price * 100,
                reason="end_of_backtest",
            )
            trades.append(trade)
            current_balance += pnl
        
        # Calculate metrics
        return self._calculate_metrics(
            job_id=job_id,
            strategy_instance=strategy_instance,
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=initial_balance,
            final_balance=current_balance,
            time_range_start=candles[0]["time"],
            time_range_end=candles[-1]["time"],
        )
    
    def _generate_signal(
        self, tick: EnrichedTick, instance: StrategyInstance
    ) -> Optional[Signal]:
        """
        Generate trading signal from tick.
        
        TODO: Actually load and run the Strategy from instance.strategy_id
        For now, implement simple RSI-based strategy for testing.
        """
        rsi = tick.get_indicator("rsiindicator_period14_rsi", 50.0)
        
        if rsi < 30:
            return Signal(
                strategy_id=str(instance.strategy_id),
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                timestamp=tick.time,
            )
        elif rsi > 70:
            return Signal(
                strategy_id=str(instance.strategy_id),
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                timestamp=tick.time,
            )
        
        return None
    
    def _flatten_indicators(self, indicators_json: Dict) -> Dict[str, float]:
        """
        Flatten nested indicator JSON to simple key-value.
        
        Args:
            indicators_json: JSONB from candle_indicators.values
            
        Returns:
            Flattened dictionary {indicator_name: value}
        """
        result = {}
        for key, value in (indicators_json or {}).items():
            if isinstance(value, dict) and "value" in value:
                result[key] = float(value["value"])
            elif isinstance(value, (int, float)):
                result[key] = float(value)
        return result
    
    def _calculate_metrics(
        self,
        job_id: str,
        strategy_instance: StrategyInstance,
        trades: List[TradeRecord],
        equity_curve: List[Dict[str, Any]],
        initial_balance: float,
        final_balance: float,
        time_range_start: datetime,
        time_range_end: datetime,
    ) -> BacktestResult:
        """Calculate all performance metrics."""
        total_return = final_balance - initial_balance
        total_return_pct = (total_return / initial_balance) * 100 if initial_balance > 0 else 0
        
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.pnl > 0])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Sharpe ratio (simplified)
        returns = [t.pnl_percent for t in trades if t.pnl != 0]
        sharpe_ratio = 0.0
        if len(returns) > 1:
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            if std_return > 0:
                sharpe_ratio = (avg_return / std_return) * (252 ** 0.5)  # Annualized
        
        # Max drawdown
        max_balance = initial_balance
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        
        for point in equity_curve:
            balance = point["balance"]
            if balance > max_balance:
                max_balance = balance
            drawdown = max_balance - balance
            drawdown_pct = (drawdown / max_balance) * 100 if max_balance > 0 else 0
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct
        
        # Profit factor
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        
        return BacktestResult(
            job_id=job_id,
            strategy_instance_id=strategy_instance.id,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            profit_factor=profit_factor,
            trades=trades,
            equity_curve=equity_curve,
        )
```

### 2. `tests/unit/application/services/test_backtest_service.py`

```python
"""
Unit tests for BacktestService.

Follows TDD: tests first, then implementation.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4, UUID

from src.application.services.backtest_service import (
    BacktestService,
    BacktestResult,
    TradeRecord,
)
from src.domain.strategies.strategy_instance import StrategyInstance, RuntimeStats


@pytest.fixture
def db_pool():
    """Mock asyncpg pool."""
    pool = AsyncMock(spec=asyncpg.Pool)
    return pool


@pytest.fixture
def backtest_service(db_pool):
    """Create BacktestService with mock pool."""
    return BacktestService(db_pool)


@pytest.fixture
def sample_strategy_instance():
    """Create a sample StrategyInstance."""
    return StrategyInstance(
        strategy_id=uuid4(),
        config_set_id=uuid4(),
    )


@pytest.fixture
def sample_candles():
    """Create sample candle data with indicators."""
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "time": base_time,
            "open": 50000.0,
            "high": 50100.0,
            "low": 49900.0,
            "close": 50050.0,
            "volume": 100.0,
            "indicators": {
                "rsiindicator_period14_rsi": {"value": 25.0},  # Oversold
                "smaindicator_period20_sma": {"value": 50000.0},
            },
        },
        {
            "time": base_time.replace(minute=1),
            "open": 50050.0,
            "high": 50200.0,
            "low": 50000.0,
            "close": 50150.0,
            "volume": 120.0,
            "indicators": {
                "rsiindicator_period14_rsi": {"value": 45.0},
                "smaindicator_period20_sma": {"value": 50025.0},
            },
        },
        {
            "time": base_time.replace(minute=2),
            "open": 50150.0,
            "high": 50300.0,
            "low": 50100.0,
            "close": 50250.0,
            "volume": 130.0,
            "indicators": {
                "rsiindicator_period14_rsi": {"value": 75.0},  # Overbought
                "smaindicator_period20_sma": {"value": 50050.0},
            },
        },
    ]


class TestBacktestServiceInit:
    """Tests for BacktestService initialization."""
    
    def test_create_service(self, db_pool):
        """Test creating BacktestService."""
        service = BacktestService(db_pool)
        assert service._pool == db_pool


class TestLoadCandles:
    """Tests for _load_candles method."""
    
    @pytest.mark.asyncio
    async def test_load_candles_with_data(self, backtest_service, sample_strategy_instance):
        """Test loading candles from database."""
        # Mock database response
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "time": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "open": 50000.0,
                "high": 50100.0,
                "low": 49900.0,
                "close": 50050.0,
                "volume": 100.0,
                "indicators": {"rsi": {"value": 50.0}},
            }
        ]
        mock_conn.fetchrow.return_value = {"id": 1, "symbol": "BTC/USDT"}
        
        async with backtest_service._pool.acquire() as conn:
            # Override acquire to return mock
            backtest_service._pool.acquire = AsyncMock(return_value=mock_conn)
            
            candles = await backtest_service._load_candles(
                sample_strategy_instance,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )
            
            assert len(candles) == 1
            assert candles[0]["close"] == 50050.0
    
    @pytest.mark.asyncio
    async def test_load_candles_no_data(self, backtest_service, sample_strategy_instance):
        """Test loading when no data exists."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        mock_conn.fetchrow.return_value = None
        
        backtest_service._pool.acquire = AsyncMock(return_value=mock_conn)
        
        candles = await backtest_service._load_candles(
            sample_strategy_instance,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
        
        assert len(candles) == 0


class TestCalculateMetrics:
    """Tests for _calculate_metrics method."""
    
    def test_calculate_with_trades(self, backtest_service, sample_strategy_instance):
        """Test calculating metrics with winning and losing trades."""
        trades = [
            TradeRecord(
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                side="LONG",
                entry_price=50000.0,
                exit_price=51000.0,
                quantity=0.1,
                pnl=100.0,
                pnl_percent=2.0,
                reason="signal",
            ),
            TradeRecord(
                entry_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
                exit_time=datetime(2024, 1, 4, tzinfo=timezone.utc),
                side="LONG",
                entry_price=51000.0,
                exit_price=50500.0,
                quantity=0.1,
                pnl=-50.0,
                pnl_percent=-0.98,
                reason="signal",
            ),
        ]
        
        equity_curve = [
            {"time": "2024-01-01T00:00:00+00:00", "balance": 10000.0},
            {"time": "2024-01-02T00:00:00+00:00", "balance": 10100.0},
            {"time": "2024-01-04T00:00:00+00:00", "balance": 10050.0},
        ]
        
        result = backtest_service._calculate_metrics(
            job_id="test-job",
            strategy_instance=sample_strategy_instance,
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=10000.0,
            final_balance=10050.0,
            time_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            time_range_end=datetime(2024, 1, 4, tzinfo=timezone.utc),
        )
        
        assert result.total_trades == 2
        assert result.winning_trades == 1
        assert result.losing_trades == 1
        assert result.win_rate == 50.0
        assert result.total_return == 50.0
        assert result.total_return_pct == 0.5
    
    def test_calculate_no_trades(self, backtest_service, sample_strategy_instance):
        """Test calculating metrics with no trades."""
        result = backtest_service._calculate_metrics(
            job_id="test-job",
            strategy_instance=sample_strategy_instance,
            trades=[],
            equity_curve=[{"time": "2024-01-01T00:00:00+00:00", "balance": 10000.0}],
            initial_balance=10000.0,
            final_balance=10000.0,
            time_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            time_range_end=datetime(2024, 1, 4, tzinfo=timezone.utc),
        )
        
        assert result.total_trades == 0
        assert result.winning_trades == 0
        assert result.win_rate == 0.0
        assert result.total_return == 0.0


class TestFlattenIndicators:
    """Tests for _flatten_indicators method."""
    
    def test_flatten_with_nested_values(self, backtest_service):
        """Test flattening indicators with 'value' key."""
        indicators = {
            "rsiindicator_period14_rsi": {"value": 30.5, "metadata": {}},
            "smaindicator_period20_sma": {"value": 50000.0},
        }
        
        result = backtest_service._flatten_indicators(indicators)
        
        assert result["rsiindicator_period14_rsi"] == 30.5
        assert result["smaindicator_period20_sma"] == 50000.0
    
    def test_flatten_with_simple_values(self, backtest_service):
        """Test flattening indicators with simple values."""
        indicators = {
            "custom_indicator": 42.0,
            "another_indicator": 100.5,
        }
        
        result = backtest_service._flatten_indicators(indicators)
        
        assert result["custom_indicator"] == 42.0
        assert result["another_indicator"] == 100.5
    
    def test_flatten_empty(self, backtest_service):
        """Test flattening empty indicators."""
        result = backtest_service._flatten_indicators({})
        assert result == {}
    
    def test_flatten_none(self, backtest_service):
        """Test flattening None indicators."""
        result = backtest_service._flatten_indicators(None)
        assert result == {}


class TestBacktestResult:
    """Tests for BacktestResult dataclass."""
    
    def test_to_dict(self, sample_strategy_instance):
        """Test converting BacktestResult to dictionary."""
        result = BacktestResult(
            job_id="test-job",
            strategy_instance_id=sample_strategy_instance.id,
            time_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            time_range_end=datetime(2024, 1, 4, tzinfo=timezone.utc),
            initial_balance=10000.0,
            final_balance=10500.0,
            total_return=500.0,
            total_return_pct=5.0,
            total_trades=2,
            winning_trades=1,
            losing_trades=1,
            win_rate=50.0,
            sharpe_ratio=1.5,
            max_drawdown=100.0,
            max_drawdown_pct=1.0,
            profit_factor=2.0,
            trades=[],
            equity_curve=[],
        )
        
        d = result.to_dict()
        
        assert d["job_id"] == "test-job"
        assert d["total_return"] == 500.0
        assert d["win_rate"] == 50.0
        assert "strategy_instance_id" in d
```

## LLM Implementation Prompt

```text
You are implementing Step 6 of Phase 4: Real Backtest Engine Service.

## Your Task

Implement a real backtest engine that uses historical data and existing indicators (no recalculation).

## Context

- Step 1-5 complete: ConfigurationSet and StrategyInstance entities, repos, APIs exist
- Phase 3 complete: MarketService (PaperMarketService) exists
- Phase 3 partial: Backtest API exists but uses SIMULATED data
- **CRITICAL**: Must read indicators from `candle_indicators` table (NO recalculation)

## Requirements

1. Create `src/application/services/backtest_service.py` with:
   - TradeRecord dataclass (entry/exit times, prices, PnL)
   - BacktestResult dataclass (all metrics, trades, equity curve)
   - BacktestService class:
     * __init__(db_pool): Store asyncpg pool
     * run_backtest(job_id, strategy_instance, time_range, initial_balance):
       - Load historical candles from `candles_1s`
       - Load indicators from `candle_indicators` (NO recalculation!)
       - Replay candles, generate signals, simulate trades
       - Calculate all metrics
     * _load_candles(): Fetch from DB (JOIN candles_1s + candle_indicators)
     * _replay_candles(): Main simulation loop
     * _generate_signal(): Call strategy or simulate
     * _calculate_metrics(): Sharpe, max drawdown, profit factor, etc.
     * _flatten_indicators(): Convert JSONB to flat dict

2. Create `tests/unit/application/services/test_backtest_service.py` with TDD:
   - TestBacktestServiceInit: initialization
   - TestLoadCandles: with data, no data
   - TestCalculateMetrics: with trades, no trades
   - TestFlattenIndicators: nested values, simple values, empty
   - TestBacktestResult: to_dict serialization
   - Mock asyncpg connections with AsyncMock

3. Key Implementation Details:
   - Time ranges: 4h, 12h, 1d, 3d, 7d, 30d (convert to timestamps)
   - NO recalculation: Read indicators from candle_indicators.values (JSONB)
   - Use PaperMarketService for trade simulation
   - Equity curve: Track balance over time
   - Trade blotter: Entry/exit with reasons

## Constraints

- Follow AGENTS.md coding standards
- Use type hints on all public methods (mypy strict)
- Use Google-style docstrings
- Line length max 100 characters
- Log errors with logger.error(f"message: {e}")
- Use asyncpg (not psycopg2)
- All methods must be async where appropriate

## Acceptance Criteria

1. BacktestService can load historical candles with indicators
2. Simulation replays candles and generates signals
3. PnL calculated correctly for each trade
4. Metrics calculated: Sharpe, max drawdown, profit factor, win rate
5. Equity curve tracks balance over time
6. NO indicator recalculation (reads from candle_indicators)
7. All unit tests pass
8. mypy passes with no errors
9. ruff check passes with no errors
10. black formatting applied

## Commands to Run

```bash
# Format and lint
black src/application/services/backtest_service.py tests/unit/application/services/test_backtest_service.py
ruff check src/application/services/backtest_service.py tests/unit/application/services/test_backtest_service.py
mypy src/application/services/backtest_service.py

# Run tests
.venv/bin/python -m pytest tests/unit/application/services/test_backtest_service.py -v
```

## Output

1. List of files created/modified
2. Test results (passed/failed count)
3. mypy/ruff output (no errors)
4. Any issues encountered and how resolved
```

## Success Criteria

- [ ] BacktestService implemented with all methods
- [ ] Uses historical data from candles_1s + candle_indicators
- [ ] NO recalculation of indicators
- [ ] All metrics calculated correctly
- [ ] TradeRecord and BacktestResult dataclasses
- [ ] All unit tests pass
- [ ] mypy strict mode passes
- [ ] ruff check passes
- [ ] black formatting applied
