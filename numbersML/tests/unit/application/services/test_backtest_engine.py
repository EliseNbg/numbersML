"""
Unit tests for BacktestEngine.

Tests:
- Deterministic execution (same inputs = same outputs)
- Metrics calculation correctness
- Fee and slippage application
- Edge cases (no trades, all losses, flat market)
- Drawdown calculation
- Sharpe/Sortino ratio calculation
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.services.backtest_engine import (
    BacktestEngine,
    BacktestMetricsCalculator,
    EquityPoint,
    PaperExecutionSimulator,
    TradeRecord,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db_pool():
    """Create mock database pool."""
    pool = MagicMock()
    conn = AsyncMock()

    # Create proper async context manager
    async def acquire_context():
        return conn

    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)

    return pool


@pytest.fixture
def sample_candles():
    """Generate sample candle data."""
    base_time = datetime(2024, 1, 1, 12, 0, 0)
    candles = []

    for i in range(100):
        # Create oscillating price pattern for RSI signals
        price = 50000 + (i % 20 - 10) * 100

        candles.append(
            {
                "time": base_time + timedelta(minutes=i),
                "open": price - 50,
                "high": price + 100,
                "low": price - 100,
                "close": price,
                "volume": 1.5,
                "indicators": {
                    "rsiindicator_period14_rsi": 30.0 if i % 20 < 10 else 70.0,  # Oscillating RSI
                },
            }
        )

    return candles


@pytest.fixture
def engine(mock_db_pool):
    """Create BacktestEngine instance."""
    return BacktestEngine(
        db_pool=mock_db_pool,
        fee_bps=10.0,
        slippage_bps=5.0,
    )


# ============================================================================
# PaperExecutionSimulator Tests
# ============================================================================


class TestPaperExecutionSimulator:
    """Test order execution simulation."""

    def test_market_order_buy(self):
        """Test market order execution for buy."""
        sim = PaperExecutionSimulator(fee_bps=10, slippage_bps=5)

        executed_price, fees = sim.simulate_market_order(
            price=50000.0,
            quantity=0.1,
            side="BUY",
        )

        # Should have slippage (worse price for buyer)
        assert executed_price > 50000.0
        # Fee should be 0.1% of notional
        expected_fee = executed_price * 0.1 * 0.001
        assert abs(fees - expected_fee) < 0.01

    def test_market_order_sell(self):
        """Test market order execution for sell."""
        sim = PaperExecutionSimulator(fee_bps=10, slippage_bps=5)

        executed_price, fees = sim.simulate_market_order(
            price=50000.0,
            quantity=0.1,
            side="SELL",
        )

        # Should have slippage (worse price for seller)
        assert executed_price < 50000.0

    def test_limit_order_fill(self):
        """Test limit order that fills."""
        sim = PaperExecutionSimulator(fee_bps=10, slippage_bps=5)

        executed_price, fees = sim.simulate_limit_order(
            price=49000.0,  # Current price
            limit_price=50000.0,  # Buy limit above current
            quantity=0.1,
            side="BUY",
        )

        # Should fill
        assert executed_price is not None
        # Maker fee should be lower (50% discount)
        notional = executed_price * 0.1
        assert fees == notional * 0.0005  # Half of 0.1%

    def test_limit_order_no_fill(self):
        """Test limit order that doesn't fill."""
        sim = PaperExecutionSimulator(fee_bps=10, slippage_bps=5)

        executed_price, fees = sim.simulate_limit_order(
            price=51000.0,  # Current price
            limit_price=50000.0,  # Buy limit below current
            quantity=0.1,
            side="BUY",
        )

        # Should not fill
        assert executed_price is None
        assert fees == 0.0

    def test_volatility_impacts_slippage(self):
        """Test that higher volatility increases slippage."""
        sim = PaperExecutionSimulator(fee_bps=10, slippage_bps=5, market_impact_factor=0.1)

        # Low volatility
        price1, _ = sim.simulate_market_order(
            price=50000.0, quantity=0.1, side="BUY", volatility=0.01
        )

        # High volatility
        price2, _ = sim.simulate_market_order(
            price=50000.0, quantity=0.1, side="BUY", volatility=0.05
        )

        # Higher volatility should result in more slippage (higher buy price)
        assert price2 > price1

    def test_total_fees_tracking(self):
        """Test that total fees are tracked correctly."""
        sim = PaperExecutionSimulator(fee_bps=10)

        sim.simulate_market_order(price=50000, quantity=0.1, side="BUY")
        sim.simulate_market_order(price=51000, quantity=0.1, side="SELL")

        assert sim.total_fees > 0

        sim.reset()
        assert sim.total_fees == 0.0


# ============================================================================
# BacktestMetricsCalculator Tests
# ============================================================================


class TestBacktestMetricsCalculator:
    """Test metrics calculation."""

    def test_basic_metrics(self):
        """Test basic metrics calculation."""
        calc = BacktestMetricsCalculator()

        trades = [
            TradeRecord(
                entry_time=datetime(2024, 1, 1),
                exit_time=datetime(2024, 1, 2),
                symbol="BTC/USDC",
                side="LONG",
                entry_price=50000,
                exit_price=51000,
                quantity=0.1,
                pnl=100,
                pnl_pct=2.0,
                fees=5,
            ),
            TradeRecord(
                entry_time=datetime(2024, 1, 3),
                exit_time=datetime(2024, 1, 4),
                symbol="BTC/USDC",
                side="LONG",
                entry_price=51000,
                exit_price=50500,
                quantity=0.1,
                pnl=-50,
                pnl_pct=-1.0,
                fees=5,
            ),
        ]

        equity_curve = [
            EquityPoint(datetime(2024, 1, 1), 10000, 10000, 0, 0),
            EquityPoint(datetime(2024, 1, 2), 10095, 9100, 995, 0),
            EquityPoint(datetime(2024, 1, 4), 10040, 10040, 0, 0),
        ]

        metrics = calc.calculate(
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=10000,
            total_fees=10,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 4),
        )

        assert metrics.total_trades == 2
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 0.5
        assert metrics.profit_factor == 100 / 50  # Gross profit / Gross loss

    def test_drawdown_calculation(self):
        """Test drawdown calculation."""
        calc = BacktestMetricsCalculator()

        equity_curve = [
            EquityPoint(datetime(2024, 1, 1), 10000, 10000, 0, 0),
            EquityPoint(datetime(2024, 1, 2), 11000, 10000, 1000, 0),  # Peak
            EquityPoint(datetime(2024, 1, 3), 10500, 10000, 500, 0.045),
            EquityPoint(datetime(2024, 1, 4), 9500, 9500, 0, 0.136),  # Max DD
            EquityPoint(datetime(2024, 1, 5), 10000, 10000, 0, 0),
        ]

        metrics = calc.calculate(
            trades=[],
            equity_curve=equity_curve,
            initial_balance=10000,
            total_fees=0,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 5),
        )

        # Max drawdown from peak of 11000 to 9500 = (11000-9500)/11000 = 13.636%
        assert abs(metrics.max_drawdown_pct - 13.636) < 0.1

    def test_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        calc = BacktestMetricsCalculator()

        # Generate equity curve with positive trend
        base_time = datetime(2024, 1, 1)
        equity_curve = []
        equity = 10000.0

        for i in range(100):
            # Small daily gains
            equity += 10 + (i % 5)  # Deterministic growth
            equity_curve.append(EquityPoint(base_time + timedelta(days=i), equity, equity, 0, 0))

        metrics = calc.calculate(
            trades=[],
            equity_curve=equity_curve,
            initial_balance=10000,
            total_fees=0,
            start_time=base_time,
            end_time=base_time + timedelta(days=99),
        )

        # Should have some Sharpe ratio
        assert metrics.sharpe_ratio != 0
        assert metrics.volatility_annualized > 0

    def test_no_trades(self):
        """Test metrics with no trades."""
        calc = BacktestMetricsCalculator()

        metrics = calc.calculate(
            trades=[],
            equity_curve=[
                EquityPoint(datetime(2024, 1, 1), 10000, 10000, 0, 0),
                EquityPoint(datetime(2024, 1, 2), 10000, 10000, 0, 0),
            ],
            initial_balance=10000,
            total_fees=0,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
        )

        assert metrics.total_trades == 0
        assert metrics.total_return == 0

    def test_consecutive_wins_losses(self):
        """Test consecutive streaks tracking."""
        calc = BacktestMetricsCalculator()

        # Create pattern: 3 wins, 2 losses, 4 wins, 1 loss
        now = datetime(2024, 1, 1)
        trades = [
            TradeRecord(entry_time=now, pnl=100, exit_time=now + timedelta(minutes=30)),  # Win
            TradeRecord(entry_time=now, pnl=100, exit_time=now + timedelta(minutes=30)),  # Win
            TradeRecord(entry_time=now, pnl=100, exit_time=now + timedelta(minutes=30)),  # Win
            TradeRecord(entry_time=now, pnl=-50, exit_time=now + timedelta(minutes=30)),  # Loss
            TradeRecord(entry_time=now, pnl=-50, exit_time=now + timedelta(minutes=30)),  # Loss
            TradeRecord(entry_time=now, pnl=100, exit_time=now + timedelta(minutes=30)),  # Win
            TradeRecord(entry_time=now, pnl=100, exit_time=now + timedelta(minutes=30)),  # Win
            TradeRecord(entry_time=now, pnl=100, exit_time=now + timedelta(minutes=30)),  # Win
            TradeRecord(entry_time=now, pnl=100, exit_time=now + timedelta(minutes=30)),  # Win
            TradeRecord(entry_time=now, pnl=-50, exit_time=now + timedelta(minutes=30)),  # Loss
        ]
        for i, t in enumerate(trades):
            t.entry_time = datetime(2024, 1, 1) + timedelta(hours=i)
            t.exit_time = t.entry_time + timedelta(minutes=30)

        equity_curve = [EquityPoint(datetime(2024, 1, 1), 10000, 10000, 0, 0)]
        # Need at least 2 points for calculate not to return early if no trades, but here we HAVE trades

        metrics = calc.calculate(
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=10000,
            total_fees=0,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 1),
        )

        assert metrics.max_consecutive_wins == 4
        assert metrics.max_consecutive_losses == 2


# ============================================================================
# BacktestEngine Tests
# ============================================================================


class TestBacktestEngine:
    """Test backtest engine."""

    @pytest.mark.asyncio
    async def test_deterministic_execution(self, mock_db_pool, sample_candles):
        """Test that same inputs produce same outputs."""
        # Setup mock to return sample candles
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "time": c["time"],
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"],
                    "indicators": c["indicators"],
                }
                for c in sample_candles
            ]
        )

        # Update context manager to return mock_conn
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        engine = BacktestEngine(mock_db_pool)

        config = {
            "meta": {"name": "Test", "description": "Test", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {"period": 14, "oversold": 35, "overbought": 65}},
            "risk": {"max_position_size_pct": 10, "max_daily_loss_pct": 5},
            "execution": {"order_type": "market", "slippage_bps": 5, "fee_bps": 10},
            "mode": "paper",
            "status": "active",
        }

        # Run twice with same inputs
        result1 = await engine.run_backtest(
            algorithm_id=uuid4(),
            algorithm_version=1,
            config=config,
            symbols=["BTC/USDC"],
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
            initial_balance=10000,
        )

        result2 = await engine.run_backtest(
            algorithm_id=uuid4(),
            algorithm_version=1,
            config=config,
            symbols=["BTC/USDC"],
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
            initial_balance=10000,
        )

        # Results should be identical (deterministic)
        assert result1.final_balance == result2.final_balance
        assert result1.metrics.total_trades == result2.metrics.total_trades

    @pytest.mark.asyncio
    async def test_fee_application(self, mock_db_pool, sample_candles):
        """Test that fees are correctly applied."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "time": c["time"],
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"],
                    "indicators": c["indicators"],
                }
                for c in sample_candles
            ]
        )
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        engine = BacktestEngine(mock_db_pool, fee_bps=10, slippage_bps=0)

        config = {
            "meta": {"name": "Test", "description": "Test", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {"period": 14, "oversold": 35, "overbought": 65}},
            "risk": {"max_position_size_pct": 10, "max_daily_loss_pct": 5},
            "execution": {"order_type": "market", "slippage_bps": 0, "fee_bps": 10},
            "mode": "paper",
            "status": "active",
        }

        result = await engine.run_backtest(
            algorithm_id=uuid4(),
            algorithm_version=1,
            config=config,
            symbols=["BTC/USDC"],
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
            initial_balance=10000,
        )

        # Should have paid some fees
        assert result.metrics.total_fees > 0

        # Total fees should be the sum of all fees from all trade legs
        total_fees = sum(t.fees for t in result.trades)
        assert abs(result.metrics.total_fees - total_fees) < 0.01

    @pytest.mark.asyncio
    async def test_no_trades_scenario(self, mock_db_pool):
        """Test backtest with no trading signals."""
        # Create candles without RSI indicators (no signals)
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "time": datetime(2024, 1, 1) + timedelta(minutes=i),
                    "open": 50000.0,
                    "high": 50100.0,
                    "low": 49900.0,
                    "close": 50000.0,
                    "volume": 1.0,
                    "indicators": {},  # No indicators = no signals
                }
                for i in range(50)
            ]
        )
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        engine = BacktestEngine(mock_db_pool)

        config = {
            "meta": {"name": "Test", "description": "Test", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {"period": 14, "oversold": 30, "overbought": 70}},
            "risk": {"max_position_size_pct": 10},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "active",
        }

        result = await engine.run_backtest(
            algorithm_id=uuid4(),
            algorithm_version=1,
            config=config,
            symbols=["BTC/USDC"],
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
            initial_balance=10000,
        )

        # Should have no trades
        assert result.metrics.total_trades == 0
        assert len([t for t in result.trades if t.exit_time]) == 0

    @pytest.mark.asyncio
    async def test_progress_callback(self, mock_db_pool, sample_candles):
        """Test that progress callback is called."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "time": c["time"],
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"],
                    "indicators": c["indicators"],
                }
                for c in sample_candles
            ]
        )
        mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        engine = BacktestEngine(mock_db_pool)

        progress_calls = []

        def callback(progress):
            progress_calls.append(progress)

        config = {
            "meta": {"name": "Test", "description": "Test", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {"period": 14, "oversold": 35, "overbought": 65}},
            "risk": {"max_position_size_pct": 10},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "active",
        }

        await engine.run_backtest(
            algorithm_id=uuid4(),
            algorithm_version=1,
            config=config,
            symbols=["BTC/USDC"],
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
            initial_balance=10000,
            progress_callback=callback,
        )

        # Progress should have been called multiple times
        assert len(progress_calls) > 0
        assert progress_calls[0] >= 0
        assert progress_calls[-1] == 1.0


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_equity_curve(self):
        """Test metrics with empty equity curve."""
        calc = BacktestMetricsCalculator()

        metrics = calc.calculate(
            trades=[],
            equity_curve=[],
            initial_balance=10000,
            total_fees=0,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
        )

        assert metrics.total_trades == 0
        assert metrics.total_return == 0
        assert metrics.sharpe_ratio == 0

    def test_single_point_equity_curve(self):
        """Test metrics with single equity point."""
        calc = BacktestMetricsCalculator()

        metrics = calc.calculate(
            trades=[],
            equity_curve=[EquityPoint(datetime(2024, 1, 1), 10000, 10000, 0, 0)],
            initial_balance=10000,
            total_fees=0,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 2),
        )

        assert metrics.total_trades == 0
        # Can't calculate volatility with single point
        assert metrics.volatility == 0

    def test_all_losses(self):
        """Test metrics when all trades are losses."""
        calc = BacktestMetricsCalculator()

        trades = [
            TradeRecord(
                entry_time=datetime(2024, 1, 1),
                exit_time=datetime(2024, 1, 2),
                pnl=-100,
                entry_price=50000,
                exit_price=49000,
            ),
            TradeRecord(
                entry_time=datetime(2024, 1, 3),
                exit_time=datetime(2024, 1, 4),
                pnl=-50,
                entry_price=49000,
                exit_price=48500,
            ),
        ]

        equity_curve = [
            EquityPoint(datetime(2024, 1, 1), 10000, 10000, 0, 0),
            EquityPoint(datetime(2024, 1, 2), 9900, 9900, 0, 0.01),
            EquityPoint(datetime(2024, 1, 4), 9850, 9850, 0, 0.015),
        ]

        metrics = calc.calculate(
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=10000,
            total_fees=0,
            start_time=datetime(2024, 1, 1),
            end_time=datetime(2024, 1, 4),
        )

        assert metrics.win_rate == 0
        assert metrics.profit_factor == 0  # No wins
        assert metrics.total_return < 0
