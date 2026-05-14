"""Tests for strategy backtest details API endpoint."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.infrastructure.api.routes import strategy_backtest as backtest_routes


class TestBacktestDetailsEndpoint:
    """Test the GET /results/{backtest_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_saved_backtest_returns_data(self) -> None:
        """Should return backtest data from repository."""
        backtest_id = uuid4()
        start_time = datetime.now(UTC) - timedelta(days=7)
        end_time = datetime.now(UTC)

        mock_repo = AsyncMock()
        mock_repo.get_with_price_series.return_value = {
            "id": backtest_id,
            "strategy_id": uuid4(),
            "strategy_name": "Test Strategy",
            "strategy_version": 1,
            "symbol": "BTC/USDC",
            "time_range_start": start_time,
            "time_range_end": end_time,
            "initial_balance": 10000.0,
            "final_balance": 10500.0,
            "metrics": {"total_return_pct": 5.0, "total_trades": 5},
            "trades": [
                {
                    "entry_time": start_time.isoformat(),
                    "exit_time": end_time.isoformat(),
                    "symbol": "BTC/USDC",
                    "entry_price": 50000.0,
                    "exit_price": 52500.0,
                    "quantity": 0.02,
                    "pnl": 500.0,
                    "pnl_pct": 5.0,
                    "fees": 10.0,
                    "exit_reason": "signal",
                }
            ],
            "equity_curve": [],
            "price_series": [
                {
                    "timestamp": start_time.isoformat(),
                    "open": 50000.0,
                    "high": 51000.0,
                    "low": 49800.0,
                    "close": 50500.0,
                }
            ],
            "parameters": {},
        }

        response = await backtest_routes.get_saved_backtest(
            backtest_id=backtest_id, backtest_repo=mock_repo
        )

        assert response["id"] == backtest_id
        assert response["strategy_name"] == "Test Strategy"
        assert response["symbol"] == "BTC/USDC"
        assert len(response["trades"]) == 1
        assert len(response["price_series"]) == 1
        assert response["price_series"][0]["open"] == 50000.0

    @pytest.mark.asyncio
    async def test_get_saved_backtest_not_found(self) -> None:
        """Should return 404 for non-existent backtest."""
        mock_repo = AsyncMock()
        mock_repo.get_with_price_series.return_value = None

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await backtest_routes.get_saved_backtest(
                backtest_id=uuid4(), backtest_repo=mock_repo
            )

        assert exc_info.value.status_code == 404