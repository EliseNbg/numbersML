"""Focused tests for strategy backtest API execution and serialization."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.application.services.backtest_engine import (
    BacktestMetrics,
    BacktestResult,
    DebugMessage,
    EquityPoint,
    PricePoint,
    TradeRecord,
)
from src.infrastructure.api.app import create_app
from src.infrastructure.api.routes import strategy_backtest as backtest_routes
from src.infrastructure.repositories.strategy_backtest_repository_pg import (
    StrategyBacktestRepositoryPG,
)


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


class TestStrategyBacktestDelete:
    """Test backtest deletion endpoints."""

    @pytest.mark.asyncio
    async def test_delete_saved_backtest_success(self) -> None:
        """Should successfully delete a backtest by ID."""
        backtest_id = uuid4()
        repo = MagicMock(spec=StrategyBacktestRepositoryPG)
        repo.delete.return_value = True

        result = await repo.delete(backtest_id)
        assert result is True
        repo.delete.assert_called_once_with(backtest_id)

    @pytest.mark.asyncio
    async def test_delete_saved_backtest_not_found(self) -> None:
        """Should handle case when backtest not found."""
        backtest_id = uuid4()
        repo = MagicMock(spec=StrategyBacktestRepositoryPG)
        repo.delete.return_value = False

        result = await repo.delete(backtest_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_bulk_delete_backtests_success(self) -> None:
        """Should successfully delete multiple backtests."""
        backtest_ids = [uuid4(), uuid4(), uuid4()]
        repo = MagicMock(spec=StrategyBacktestRepositoryPG)
        repo.delete_multiple.return_value = 3

        result = await repo.delete_multiple(backtest_ids)
        assert result == 3
        repo.delete_multiple.assert_called_once_with(backtest_ids)

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_list(self) -> None:
        """Should handle empty list gracefully."""
        repo = MagicMock(spec=StrategyBacktestRepositoryPG)
        repo.delete_multiple.return_value = 0

        result = await repo.delete_multiple([])
        assert result == 0


class TestStrategyBacktestDeleteEndpoint:
    """Test delete endpoint functions directly with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_delete_endpoint_success(self) -> None:
        """Test DELETE endpoint handler returns None on success."""
        backtest_id = uuid4()
        repo = AsyncMock()
        repo.delete.return_value = True

        # Call endpoint directly
        await backtest_routes.delete_saved_backtest(backtest_id, backtest_repo=repo)
        repo.delete.assert_called_once_with(backtest_id)

    @pytest.mark.asyncio
    async def test_delete_endpoint_not_found(self) -> None:
        """Test DELETE endpoint raises 404 when not found."""
        backtest_id = uuid4()
        repo = AsyncMock()
        repo.delete.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await backtest_routes.delete_saved_backtest(backtest_id, backtest_repo=repo)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_delete_endpoint_success(self) -> None:
        """Test bulk DELETE endpoint handler."""
        backtest_ids = [uuid4(), uuid4()]
        repo = AsyncMock()
        repo.delete_multiple.return_value = 2

        # Call endpoint directly
        await backtest_routes.bulk_delete_backtests(
            {"backtest_ids": backtest_ids}, backtest_repo=repo
        )
        repo.delete_multiple.assert_called_once_with(backtest_ids)

    @pytest.mark.asyncio
    async def test_bulk_delete_endpoint_invalid_request(self) -> None:
        """Test bulk DELETE endpoint raises 400 for invalid request."""
        with pytest.raises(HTTPException) as exc_info:
            await backtest_routes.bulk_delete_backtests(
                {"backtest_ids": []}, backtest_repo=AsyncMock()
            )
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPException) as exc_info:
            await backtest_routes.bulk_delete_backtests(
                {"wrong_key": [uuid4()]}, backtest_repo=AsyncMock()
            )
        assert exc_info.value.status_code == 400
