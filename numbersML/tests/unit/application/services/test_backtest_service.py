"""
Unit tests for BacktestService.

Follows TDD: tests first, then implementation.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from src.application.services.backtest_service import (
    BacktestResult,
    BacktestService,
    TradeRecord,
)
from src.domain.algorithms.strategy_instance import StrategyInstance


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
        algorithm_id=uuid4(),
        config_set_id=uuid4(),
    )


@pytest.fixture
def sample_candles():
    """Create sample candle data with indicators."""
    base_time = datetime(2024, 1, 1, tzinfo=UTC)
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
        mock_conn.fetch.side_effect = [
            [{"id": 1, "symbol": "BTC/USDT"}],  # Symbol query
            [  # Candle query
                {
                    "time": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 50000.0,
                    "high": 50100.0,
                    "low": 49900.0,
                    "close": 50050.0,
                    "volume": 100.0,
                    "indicators": {"rsi": {"value": 50.0}},
                }
            ],
        ]

        # Mock pool.acquire to return async context manager
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        backtest_service._pool.acquire.return_value = mock_cm

        candles = await backtest_service._load_candles(
            sample_strategy_instance,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 2, tzinfo=UTC),
        )

        assert len(candles) == 1
        assert candles[0]["close"] == 50050.0

    @pytest.mark.asyncio
    async def test_load_candles_no_data(self, backtest_service, sample_strategy_instance):
        """Test loading when no data exists."""
        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = [
            [],  # No symbols found
            [],  # No candles
        ]

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        backtest_service._pool.acquire.return_value = mock_cm

        candles = await backtest_service._load_candles(
            sample_strategy_instance,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 2, tzinfo=UTC),
        )

        assert len(candles) == 0


class TestCalculateMetrics:
    """Tests for _calculate_metrics method."""

    def test_calculate_with_trades(self, backtest_service, sample_strategy_instance):
        """Test calculating metrics with winning and losing trades."""
        trades = [
            TradeRecord(
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                side="LONG",
                entry_price=50000.0,
                exit_price=51000.0,
                quantity=0.1,
                pnl=100.0,
                pnl_percent=2.0,
                reason="signal",
            ),
            TradeRecord(
                entry_time=datetime(2024, 1, 3, tzinfo=UTC),
                exit_time=datetime(2024, 1, 4, tzinfo=UTC),
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
            time_range_start=datetime(2024, 1, 1, tzinfo=UTC),
            time_range_end=datetime(2024, 1, 4, tzinfo=UTC),
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
            time_range_start=datetime(2024, 1, 1, tzinfo=UTC),
            time_range_end=datetime(2024, 1, 4, tzinfo=UTC),
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
            time_range_start=datetime(2024, 1, 1, tzinfo=UTC),
            time_range_end=datetime(2024, 1, 4, tzinfo=UTC),
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
