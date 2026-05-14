"""Unit tests for StrategyBacktestService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
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
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition


@pytest.fixture
def mock_strategy_repo() -> AsyncMock:
    """Mock strategy repository."""
    return AsyncMock(spec=StrategyRepository)


@pytest.fixture
def mock_backtest_repo() -> AsyncMock:
    """Mock backtest repository."""
    return AsyncMock()


@pytest.fixture
def mock_backtest_engine() -> AsyncMock:
    """Mock backtest engine."""
    engine = AsyncMock()
    engine.run_backtest = AsyncMock()
    return engine


class TestStrategyBacktestService:
    """Test backtest orchestration and persistence."""

    @pytest.mark.asyncio
    async def test_run_backtest_persists_active_version(
        self,
        mock_strategy_repo: AsyncMock,
        mock_backtest_repo: AsyncMock,
        mock_backtest_engine: AsyncMock,
    ) -> None:
        """Backtests should resolve the active version and persist with its UUID."""
        strategy_id = uuid4()
        version_id = uuid4()
        now = datetime.now(UTC)
        strategy_def = StrategyDefinition(
            id=strategy_id,
            name="Backtest Service Test",
            description="Test",
            mode="paper",
            status="active",
            current_version=2,
            created_by="test",
            created_at=now,
            updated_at=now,
        )
        config_version = StrategyConfigVersion(
            id=version_id,
            strategy_id=strategy_id,
            version=2,
            schema_version=1,
            config={
                "strategy_type": "class",
                "class_path": "src.strategies.user.example_rsi_strategy.ExampleRSIStrategy",
                "universe": {"symbols": ["BTC/USDC"]},
                "signal": {"type": "rsi", "params": {"period": 14}},
            },
            is_active=True,
            created_by="test",
            created_at=now,
        )
        result = BacktestResult(
            run_id=uuid4(),
            strategy_id=strategy_id,
            strategy_version=2,
            config_snapshot=config_version.config,
            start_time=now - timedelta(days=7),
            end_time=now,
            initial_balance=10000.0,
            final_balance=10100.0,
            metrics=BacktestMetrics(total_return=100.0, total_return_pct=1.0, total_trades=1),
            trades=[
                TradeRecord(
                    entry_time=now - timedelta(days=1),
                    exit_time=now,
                    symbol="BTC/USDC",
                    entry_price=50000.0,
                    exit_price=50500.0,
                    quantity=0.02,
                    pnl=100.0,
                    pnl_pct=1.0,
                    fees=10.0,
                    exit_reason="signal",
                )
            ],
            equity_curve=[
                EquityPoint(now - timedelta(days=7), 10000.0, 10000.0, 0.0, 0.0),
                EquityPoint(now, 10100.0, 10100.0, 0.0, 0.0),
            ],
            price_series=[PricePoint(now, 50500.0, 50550.0, 50450.0, 50500.0)],
            debug_messages=[DebugMessage(now, "INFO", "closed trade")],
            parameters={"fee_bps": 10.0},
        )

        mock_strategy_repo.get_by_id.return_value = strategy_def
        mock_strategy_repo.list_versions.return_value = [config_version]
        mock_backtest_engine.run_backtest.return_value = result

        service = StrategyBacktestService(
            strategy_repository=mock_strategy_repo,
            backtest_repository=mock_backtest_repo,
            backtest_engine=mock_backtest_engine,
            actor="test",
        )

        backtest = await service.run_backtest(
            strategy_id=strategy_id,
            strategy_version=None,
            start_time=result.start_time,
            end_time=result.end_time,
            initial_balance=10000.0,
            symbol="BTC/USDC",
        )

        assert backtest is result
        mock_backtest_engine.run_backtest.assert_awaited_once()
        _, kwargs = mock_backtest_engine.run_backtest.await_args
        assert kwargs["strategy_version"] == 2
        assert kwargs["symbols"] == ["BTC/USDC"]

        mock_backtest_repo.save.assert_awaited_once()
        _, save_kwargs = mock_backtest_repo.save.await_args
        assert save_kwargs["strategy_version_id"] == version_id
        assert save_kwargs["metrics"]["total_return_pct"] == 1.0
        assert save_kwargs["created_by"] == "test"

    @pytest.mark.asyncio
    async def test_run_backtest_raises_for_missing_version(
        self,
        mock_strategy_repo: AsyncMock,
        mock_backtest_repo: AsyncMock,
        mock_backtest_engine: AsyncMock,
    ) -> None:
        """Unknown versions should fail fast with a clear error."""
        strategy_id = uuid4()
        mock_strategy_repo.get_by_id.return_value = StrategyDefinition(
            id=strategy_id,
            name="Missing Version",
            description="Test",
            created_by="test",
        )
        mock_strategy_repo.list_versions.return_value = []

        service = StrategyBacktestService(
            strategy_repository=mock_strategy_repo,
            backtest_repository=mock_backtest_repo,
            backtest_engine=mock_backtest_engine,
        )

        with pytest.raises(ValueError, match="No versions found"):
            await service.run_backtest(
                strategy_id=strategy_id,
                strategy_version=7,
                start_time=datetime.now(UTC) - timedelta(days=1),
                end_time=datetime.now(UTC),
                initial_balance=10000.0,
            )
