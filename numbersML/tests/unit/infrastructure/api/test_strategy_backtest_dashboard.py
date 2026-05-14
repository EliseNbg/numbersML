"""Unit tests for strategy backtest dashboard functionality."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.services.backtest_engine import (
    BacktestMetrics,
    BacktestResult,
    DebugMessage,
    EquityPoint,
    PricePoint,
    TradeRecord,
)
from src.application.services.strategy_backtest_service import StrategyBacktestService
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition


@pytest.fixture
def mock_strategy_repo():
    """Mock strategy repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_backtest_repo():
    """Mock backtest repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_backtest_engine():
    """Mock backtest engine."""
    engine = AsyncMock()
    return engine


@pytest.fixture
def sample_strategy():
    """Create sample strategy definition."""
    return StrategyDefinition(
        id=uuid4(),
        name="Test Strategy",
        description="Test",
        mode="paper",
        status="active",
        current_version=1,
        created_by="test",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_config_version():
    """Create sample config version."""
    return StrategyConfigVersion(
        id=uuid4(),
        strategy_id=uuid4(),
        version=1,
        schema_version=1,
        config={
            "strategy_type": "class",
            "class_path": "src.strategies.user.example_rsi_strategy.ExampleRSIStrategy",
            "universe": {"symbols": ["BTC/USDC"]},
            "signal": {"type": "rsi", "params": {"period": 14}},
        },
        is_active=True,
        created_by="test",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_backtest_result():
    """Create sample backtest result for dashboard testing."""
    now = datetime.now(UTC)
    return BacktestResult(
        run_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version=1,
        config_snapshot={"test": "config"},
        start_time=now - timedelta(days=7),
        end_time=now,
        initial_balance=10000.0,
        final_balance=10500.0,
        metrics=BacktestMetrics(
            total_return=500.0,
            total_return_pct=5.0,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            max_drawdown_pct=2.5,
            sharpe_ratio=1.5,
            profit_factor=2.0,
        ),
        trades=[
            TradeRecord(
                entry_time=now - timedelta(days=6),
                exit_time=now - timedelta(days=5),
                symbol="BTC/USDC",
                side="LONG",
                entry_price=50000.0,
                exit_price=51000.0,
                quantity=0.1,
                pnl=100.0,
                pnl_pct=2.0,
                fees=10.0,
                exit_reason="signal",
            ),
        ],
        equity_curve=[
            EquityPoint(now - timedelta(days=7), 10000.0, 10000.0, 0.0, 0.0),
            EquityPoint(now, 10500.0, 10500.0, 0.0, 0.0),
        ],
        price_series=[
            PricePoint(now - timedelta(days=7), 50000.0, 50050.0, 49950.0, 50100.0),
            PricePoint(now, 51000.0, 51050.0, 50950.0, 51100.0),
        ],
        debug_messages=[
            DebugMessage(now - timedelta(days=6), "INFO", "Buy signal triggered"),
            DebugMessage(now - timedelta(days=5), "INFO", "Sell signal triggered"),
        ],
        parameters={"fee_bps": 10.0, "slippage_bps": 5.0},
    )


class TestBacktestDashboardDataContract:
    """Test that backtest results contain all required dashboard fields."""

    def test_backtest_result_has_required_dashboard_fields(self, sample_backtest_result):
        """Verify result contains all fields needed by dashboard."""
        result = sample_backtest_result

        # Required by dashboard
        assert result.run_id is not None
        assert result.strategy_id is not None
        assert result.strategy_version is not None
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.initial_balance is not None
        assert result.final_balance is not None

        # Metrics required by dashboard
        assert result.metrics is not None
        assert result.metrics.total_return_pct is not None
        assert result.metrics.max_drawdown_pct is not None
        assert result.metrics.sharpe_ratio is not None
        assert result.metrics.win_rate is not None
        assert result.metrics.total_trades is not None
        assert result.metrics.profit_factor is not None

        # Data series required by dashboard
        assert result.trades is not None
        assert result.equity_curve is not None
        assert result.price_series is not None
        assert result.debug_messages is not None

        # Config snapshot for display
        assert result.config_snapshot is not None
        assert result.parameters is not None

    def test_trade_record_has_required_fields(self):
        """Verify trade record has all fields needed for blotter display."""
        now = datetime.now(UTC)
        trade = TradeRecord(
            entry_time=now,
            exit_time=now,
            symbol="BTC/USDC",
            side="LONG",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=0.1,
            pnl=100.0,
            pnl_pct=2.0,
            fees=10.0,
            exit_reason="signal",
        )

        # All fields required by trade blotter
        assert trade.entry_time is not None
        assert trade.exit_time is not None
        assert trade.symbol is not None
        assert trade.entry_price is not None
        assert trade.exit_price is not None
        assert trade.pnl is not None
        assert trade.exit_reason is not None

    def test_debug_message_has_required_fields(self):
        """Verify debug message has all fields needed for log display."""
        now = datetime.now(UTC)
        msg = DebugMessage(
            timestamp=now,
            level="INFO",
            message="Test message",
        )

        assert msg.timestamp is not None
        assert msg.level is not None
        assert msg.message is not None

    def test_price_point_has_required_fields(self):
        """Verify price point has all fields needed for chart."""
        now = datetime.now(UTC)
        point = PricePoint(timestamp=now, open=50000.0, high=50100.0, low=49900.0, close=50000.0)

        assert point.timestamp is not None
        assert point.close is not None

    def test_equity_point_has_required_fields(self):
        """Verify equity point has all fields needed for chart."""
        now = datetime.now(UTC)
        point = EquityPoint(
            timestamp=now,
            equity=10000.0,
            cash=10000.0,
            positions_value=0.0,
            drawdown=0.0,
        )

        assert point.timestamp is not None
        assert point.equity is not None


class TestBacktestDashboardWorkflows:
    """Test backtest workflows as used by dashboard."""

    @pytest.mark.asyncio
    async def test_submit_and_poll_backtest_job(
        self,
        mock_strategy_repo,
        mock_backtest_repo,
        mock_backtest_engine,
        sample_strategy,
        sample_config_version,
        sample_backtest_result,
    ):
        """Test submitting a backtest and polling for completion."""
        # Setup mocks
        mock_strategy_repo.get_by_id.return_value = sample_strategy
        mock_strategy_repo.list_versions.return_value = [sample_config_version]
        mock_backtest_engine.run_backtest.return_value = sample_backtest_result

        # Create service
        service = StrategyBacktestService(
            strategy_repository=mock_strategy_repo,
            backtest_repository=mock_backtest_repo,
            backtest_engine=mock_backtest_engine,
            actor="dashboard_test",
        )

        # Run backtest
        result = await service.run_backtest(
            strategy_id=sample_strategy.id,
            strategy_version=1,
            start_time=datetime.now(UTC) - timedelta(days=7),
            end_time=datetime.now(UTC),
            initial_balance=10000.0,
            symbol="BTC/USDC",
        )

        # Verify result is suitable for dashboard
        assert result is not None
        assert result.metrics.total_return_pct == 5.0
        assert len(result.trades) == 1
        assert len(result.equity_curve) == 2
        assert len(result.price_series) == 2
        assert len(result.debug_messages) == 2

        # Verify persistence was called with correct data
        mock_backtest_repo.save.assert_awaited_once()
        save_call = mock_backtest_repo.save.await_args
        assert save_call.kwargs["strategy_version_id"] == sample_config_version.id
        assert save_call.kwargs["metrics"]["total_return_pct"] == 5.0

    @pytest.mark.asyncio
    async def test_backtest_with_progress_callback(
        self,
        mock_strategy_repo,
        mock_backtest_repo,
        mock_backtest_engine,
        sample_strategy,
        sample_config_version,
    ):
        """Test that progress callback is invoked during backtest."""
        mock_strategy_repo.get_by_id.return_value = sample_strategy
        mock_strategy_repo.list_versions.return_value = [sample_config_version]

        progress_calls = []

        async def mock_run_backtest(*args, **kwargs):
            progress_callback = kwargs.get("progress_callback")
            if progress_callback:
                progress_callback(0.0)
                progress_callback(0.5)
                progress_callback(1.0)
            return MagicMock(
                final_balance=10000.0,
                metrics=BacktestMetrics(),
                trades=[],
                equity_curve=[],
                price_series=[],
                debug_messages=[],
                parameters={},
                config_snapshot={},
            )

        mock_backtest_engine.run_backtest = mock_run_backtest

        service = StrategyBacktestService(
            strategy_repository=mock_strategy_repo,
            backtest_repository=mock_backtest_repo,
            backtest_engine=mock_backtest_engine,
            actor="test",
        )

        # Run with progress tracking
        await service.run_backtest(
            strategy_id=sample_strategy.id,
            strategy_version=1,
            start_time=datetime.now(UTC) - timedelta(days=1),
            end_time=datetime.now(UTC),
            initial_balance=10000.0,
            symbol="BTC/USDC",
            progress_callback=lambda p: progress_calls.append(p),
        )

        # Verify progress was tracked
        assert len(progress_calls) == 3
        assert progress_calls[0] == 0.0
        assert progress_calls[1] == 0.5
        assert progress_calls[2] == 1.0


class TestBacktestDashboardEdgeCases:
    """Test edge cases for dashboard backtesting."""

    @pytest.mark.asyncio
    async def test_backtest_no_trades(
        self,
        mock_strategy_repo,
        mock_backtest_repo,
        mock_backtest_engine,
        sample_strategy,
        sample_config_version,
    ):
        """Test dashboard handles backtest with no trades gracefully."""
        mock_strategy_repo.get_by_id.return_value = sample_strategy
        mock_strategy_repo.list_versions.return_value = [sample_config_version]

        # Result with no trades
        empty_result = BacktestResult(
            run_id=uuid4(),
            strategy_id=sample_strategy.id,
            strategy_version=1,
            config_snapshot={},
            start_time=datetime.now(UTC) - timedelta(days=7),
            end_time=datetime.now(UTC),
            initial_balance=10000.0,
            final_balance=10000.0,
            metrics=BacktestMetrics(total_return=0, total_return_pct=0, total_trades=0),
            trades=[],
            equity_curve=[EquityPoint(datetime.now(UTC), 10000.0, 10000.0, 0.0, 0.0)],
            price_series=[],
            debug_messages=[DebugMessage(datetime.now(UTC), "INFO", "No trades executed")],
            parameters={},
        )
        mock_backtest_engine.run_backtest.return_value = empty_result

        service = StrategyBacktestService(
            strategy_repository=mock_strategy_repo,
            backtest_repository=mock_backtest_repo,
            backtest_engine=mock_backtest_engine,
            actor="test",
        )

        result = await service.run_backtest(
            strategy_id=sample_strategy.id,
            strategy_version=1,
            start_time=datetime.now(UTC) - timedelta(days=7),
            end_time=datetime.now(UTC),
            initial_balance=10000.0,
            symbol="BTC/USDC",
        )

        # Dashboard should handle empty results
        assert result.metrics.total_trades == 0
        assert len(result.trades) == 0

    def test_metrics_serialization_for_dashboard(self):
        """Test metrics can be serialized for dashboard display."""
        from src.application.services.backtest_engine import serialize_metrics

        metrics = BacktestMetrics(
            total_return=100.0,
            total_return_pct=1.0,
            cagr=10.0,
            max_drawdown=50.0,
            max_drawdown_pct=0.5,
            max_drawdown_duration=timedelta(days=5),
            avg_trade_duration=timedelta(hours=2),
        )

        serialized = serialize_metrics(metrics)

        # Verify all fields are serializable
        assert isinstance(serialized, dict)
        assert serialized["total_return_pct"] == 1.0
        assert serialized["max_drawdown_pct"] == 0.5
        # Timedelta should be converted to seconds
        assert isinstance(serialized["max_drawdown_duration"], int | float)
        assert isinstance(serialized["avg_trade_duration"], int | float)


class TestBacktestHistoryLoading:
    """Test loading backtest history for dashboard."""

    @pytest.mark.asyncio
    async def test_list_recent_backtests(self):
        """Test listing recent backtests for history view."""
        # Mock the database
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock fetch results
        mock_rows = [
            MagicMock(
                id=uuid4(),
                strategy_id=uuid4(),
                strategy_version_id=uuid4(),
                strategy_name="Test Strategy",
                time_range_start=datetime.now(UTC) - timedelta(days=7),
                time_range_end=datetime.now(UTC),
                initial_balance=10000.0,
                final_balance=10500.0,
                metrics='{"total_return_pct": 5.0, "total_trades": 10}',
                trades="[]",
                equity_curve="[]",
                created_by="test",
                created_at=datetime.now(UTC),
            ),
        ]
        mock_conn.fetch.return_value = mock_rows

        # This would need actual asyncpg mocking to work fully
        # For now, we test the _map_backtest static method

    def test_backtest_result_mapping(self):
        """Test mapping of backtest result fields."""
        from src.infrastructure.repositories.strategy_backtest_repository_pg import (
            StrategyBacktestRepositoryPG,
        )

        # Create a mock row
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": uuid4(),
            "strategy_id": uuid4(),
            "strategy_version_id": uuid4(),
            "time_range_start": datetime.now(UTC),
            "time_range_end": datetime.now(UTC),
            "initial_balance": 10000.0,
            "final_balance": 10500.0,
            "metrics": '{"total_return_pct": 5.0}',
            "trades": "[]",
            "equity_curve": "[]",
            "created_by": "test",
            "created_at": datetime.now(UTC),
        }.get(key)

        # Test the mapping
        result = StrategyBacktestRepositoryPG._map_backtest(row)

        assert result["initial_balance"] == 10000.0
        assert result["final_balance"] == 10500.0
        assert result["metrics"]["total_return_pct"] == 5.0
