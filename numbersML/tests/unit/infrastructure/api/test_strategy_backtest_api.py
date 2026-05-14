"""Focused tests for strategy backtest API execution and serialization."""

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
from src.infrastructure.api.routes import strategy_backtest as backtest_routes


class TestStrategyBacktestApi:
    """Test async job execution and saved-result listing."""

    @pytest.mark.asyncio
    async def test_execute_backtest_job_stores_real_result(self) -> None:
        """Async executor should store serialized engine output."""
        job_id = "job-test-1"
        strategy_id = uuid4()
        now = datetime.now(UTC)
        result = BacktestResult(
            run_id=uuid4(),
            strategy_id=strategy_id,
            strategy_version=3,
            config_snapshot={"signal": {"type": "rsi"}},
            start_time=now - timedelta(days=2),
            end_time=now,
            initial_balance=10000.0,
            final_balance=10250.0,
            metrics=BacktestMetrics(total_return=250.0, total_return_pct=2.5, total_trades=1),
            trades=[
                TradeRecord(
                    entry_time=now - timedelta(days=1),
                    exit_time=now,
                    symbol="BTC/USDC",
                    entry_price=50000.0,
                    exit_price=51250.0,
                    quantity=0.02,
                    pnl=250.0,
                    pnl_pct=2.5,
                    fees=12.0,
                    exit_reason="signal",
                )
            ],
            equity_curve=[
                EquityPoint(now - timedelta(days=2), 10000.0, 10000.0, 0.0, 0.0),
                EquityPoint(now, 10250.0, 10250.0, 0.0, 0.0),
            ],
            price_series=[PricePoint(now, 51250.0, 52000.0, 51000.0, 51250.0)],
            debug_messages=[DebugMessage(now, "INFO", "trade closed")],
            parameters={"fee_bps": 10.0},
        )
        service = AsyncMock()
        service.run_backtest.return_value = result

        backtest_routes._backtest_jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0.0,
            "strategy_id": strategy_id,
            "strategy_name": "Async Test",
            "strategy_version": 3,
            "time_range_start": result.start_time,
            "time_range_end": result.end_time,
            "initial_balance": 10000.0,
            "symbol": "BTC/USDC",
            "include_equity_curve": True,
            "include_trades": True,
            "metadata": {},
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

        await backtest_routes._execute_backtest_job(job_id, service)

        stored = backtest_routes._backtest_jobs[job_id]
        assert stored["status"] == "completed"
        assert stored["result"]["final_balance"] == 10250.0
        assert stored["result"]["metrics"]["total_return_pct"] == 2.5
        assert stored["result"]["price_series"][0]["close"] == 51250.0
        assert stored["result"]["debug_messages"][0]["message"] == "trade closed"

        backtest_routes._backtest_jobs.clear()

    @pytest.mark.asyncio
    async def test_list_saved_backtests_uses_repository(self) -> None:
        """Saved-results endpoint should return repository payloads."""
        repo = AsyncMock()
        repo.list_recent.return_value = [{"id": str(uuid4()), "metrics": {"total_return_pct": 1.5}}]

        response = await backtest_routes.list_saved_backtests(backtest_repo=repo)

        assert response[0]["metrics"]["total_return_pct"] == 1.5
