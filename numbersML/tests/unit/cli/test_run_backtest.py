"""
Unit tests for run_backtest CLI.

Tests:
- Argument parsing
- Timestamp handling
- Output formatting
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cli.run_backtest import parse_args, print_results, run_backtest_async


class TestParseArgs:
    """Test argument parsing."""

    def test_required_strategy_id(self):
        """Test that at least one of --strategy-id or --strategy-name is required."""
        with patch("sys.argv", ["run_backtest"]):
            args = parse_args()
            assert args.strategy_id is None
            assert args.strategy_name is None

    def test_strategy_id_parsing(self):
        """Test strategy ID is parsed correctly."""
        with patch(
            "sys.argv", ["run_backtest", "--strategy-id", "dcb32c52-cc78-4e2f-91e6-76287cc345ee"]
        ):
            args = parse_args()
            assert args.strategy_id == "dcb32c52-cc78-4e2f-91e6-76287cc345ee"

    def test_strategy_name_parsing(self):
        """Test strategy name is parsed correctly."""
        with patch(
            "sys.argv", ["run_backtest", "--strategy-name", "MACD_Momentum_ATOM"]
        ):
            args = parse_args()
            assert args.strategy_name == "MACD_Momentum_ATOM"

    def test_version_parsing(self):
        """Test version parsing."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--version",
                "2",
            ],
        ):
            args = parse_args()
            assert args.version == 2

    def test_symbol_parsing(self):
        """Test symbol parsing."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--symbol",
                "DOGE/USDC",
            ],
        ):
            args = parse_args()
            assert args.symbol == "DOGE/USDC"

    def test_initial_balance_default(self):
        """Test default initial balance."""
        with patch(
            "sys.argv", ["run_backtest", "--strategy-id", "dcb32c52-cc78-4e2f-91e6-76287cc345ee"]
        ):
            args = parse_args()
            assert args.initial_balance == 10000.0

    def test_initial_balance_custom(self):
        """Test custom initial balance."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--initial-balance",
                "5000.50",
            ],
        ):
            args = parse_args()
            assert args.initial_balance == 5000.50

    def test_wait_flag(self):
        """Test wait flag."""
        with patch(
            "sys.argv",
            ["run_backtest", "--strategy-id", "dcb32c52-cc78-4e2f-91e6-76287cc345ee", "--wait"],
        ):
            args = parse_args()
            assert args.wait is True

    def test_output_flag(self):
        """Test output flag."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--output",
                "results.json",
            ],
        ):
            args = parse_args()
            assert args.output == "results.json"

    def test_no_equity_curve_flag(self):
        """Test --no-equity-curve flag."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--no-equity-curve",
            ],
        ):
            args = parse_args()
            assert args.include_equity_curve is False

    def test_no_trades_flag(self):
        """Test --no-trades flag."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--no-trades",
            ],
        ):
            args = parse_args()
            assert args.include_trades is False


class TestRunBacktestAsync:
    """Test run_backtest_async function."""

    @pytest.mark.asyncio
    async def test_invalid_strategy_id(self):
        """Test invalid strategy ID raises error."""
        with patch("sys.argv", ["run_backtest", "--strategy-id", "not-a-uuid"]):
            args = parse_args()
            with pytest.raises(ValueError, match="Invalid strategy ID"):
                await run_backtest_async(args)

    @pytest.mark.asyncio
    async def test_invalid_start_time(self):
        """Test invalid start time raises error."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--start-time",
                "invalid-date",
            ],
        ):
            args = parse_args()
            with pytest.raises(ValueError, match="Invalid start-time"):
                await run_backtest_async(args)

    @pytest.mark.asyncio
    async def test_invalid_end_time(self):
        """Test invalid end time raises error."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--end-time",
                "invalid-date",
            ],
        ):
            args = parse_args()
            with pytest.raises(ValueError, match="Invalid end-time"):
                await run_backtest_async(args)

    @pytest.mark.asyncio
    async def test_end_time_before_start_time(self):
        """Test end time before start time raises error."""
        with patch(
            "sys.argv",
            [
                "run_backtest",
                "--strategy-id",
                "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
                "--start-time",
                "2026-05-05T00:00:00",
                "--end-time",
                "2026-05-01T00:00:00",
            ],
        ):
            args = parse_args()
            with pytest.raises(ValueError, match="End time must be after start time"):
                await run_backtest_async(args)

    @pytest.mark.asyncio
    async def test_database_not_initialized(self):
        """Test database not initialized raises error."""
        with patch(
            "sys.argv", ["run_backtest", "--strategy-id", "dcb32c52-cc78-4e2f-91e6-76287cc345ee"]
        ):
            args = parse_args()
            # No mock for db_pool, should raise RuntimeError
            with pytest.raises(RuntimeError, match="Database pool not initialized"):
                await run_backtest_async(args)

    @pytest.mark.asyncio
    async def test_strategy_name_resolves_to_id(self):
        """Test --strategy-name resolves to a strategy ID via repository."""
        from uuid import uuid4

        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()

        mock_repo = AsyncMock()
        mock_repo.get_by_name.return_value = mock_strategy

        mock_pool = MagicMock()

        async def mock_get_db_pool():
            return mock_pool

        mock_backtest_service = AsyncMock()
        mock_backtest_service.run_backtest.side_effect = RuntimeError("Database pool not initialized")

        with patch("sys.argv", ["run_backtest", "--strategy-name", "TestStrategy"]):
            args = parse_args()
            with (
                patch("src.cli.run_backtest.get_db_pool_async", side_effect=mock_get_db_pool),
                patch("src.cli.run_backtest.StrategyRepositoryPG", return_value=mock_repo),
                patch("src.cli.run_backtest.StrategyBacktestService", return_value=mock_backtest_service),
            ):
                with pytest.raises(RuntimeError, match="Database pool not initialized"):
                    await run_backtest_async(args)
                mock_repo.get_by_name.assert_called_once_with("TestStrategy")

    @pytest.mark.asyncio
    async def test_strategy_name_not_found(self):
        """Test --strategy-name with nonexistent name raises ValueError."""
        mock_repo = AsyncMock()
        mock_repo.get_by_name.return_value = None

        with patch("sys.argv", ["run_backtest", "--strategy-name", "NonexistentStrategy"]):
            args = parse_args()
            with (
                patch("src.cli.run_backtest.get_db_pool_async", new_callable=AsyncMock),
                patch("src.cli.run_backtest.StrategyRepositoryPG", return_value=mock_repo),
            ):
                with pytest.raises(ValueError, match="Strategy not found with name"):
                    await run_backtest_async(args)

    @pytest.mark.asyncio
    async def test_neither_id_nor_name_raises(self):
        """Test that providing neither --strategy-id nor --strategy-name raises error."""
        with patch("sys.argv", ["run_backtest"]):
            args = parse_args()
            with pytest.raises(ValueError, match="Either --strategy-id or --strategy-name"):
                await run_backtest_async(args)


class TestPrintResults:
    """Test print_results output formatting."""

    def test_print_results_basic(self, capsys):
        """Test basic result printing."""
        result = {
            "strategy_id": "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
            "strategy_version": "active",
            "time_range_start": "2026-05-04T06:53:00",
            "time_range_end": "2026-05-11T06:53:00",
            "initial_balance": 10000.0,
            "final_balance": 11000.0,
            "metrics": {
                "total_return_pct": 10.0,
                "max_drawdown_pct": 2.5,
                "sharpe_ratio": 1.5,
                "win_rate": 0.6,
                "total_trades": 10,
                "profit_factor": 1.8,
            },
            "symbol": "BTC/USDC",
        }

        print_results(result)
        captured = capsys.readouterr()

        assert "BACKTEST RESULTS" in captured.out
        assert "Strategy ID" in captured.out
        assert "10000" in captured.out
        assert "11000" in captured.out
        assert "10.00%" in captured.out

    def test_print_results_with_trades(self, capsys):
        """Test result printing with trades."""
        result = {
            "strategy_id": "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
            "strategy_version": 2,
            "time_range_start": "2026-05-04T06:53:00",
            "time_range_end": "2026-05-11T06:53:00",
            "initial_balance": 10000.0,
            "final_balance": 10500.0,
            "metrics": {},
            "trades": [
                {
                    "entry_time": "2026-05-04T07:00:00",
                    "exit_time": "2026-05-04T08:00:00",
                    "symbol": "BTC/USDC",
                    "side": "BUY",
                    "entry_price": 50000.0,
                    "exit_price": 51000.0,
                    "pnl": 1000.0,
                    "pnl_pct": 2.0,
                    "exit_reason": "take_profit",
                },
            ],
            "equity_curve": [],
        }

        print_results(result)
        captured = capsys.readouterr()

        assert "TRADES" in captured.out
        assert "BUY" in captured.out
        assert "50000" in captured.out

    def test_print_results_no_trades(self, capsys):
        """Test result printing without trades."""
        result = {
            "strategy_id": "dcb32c52-cc78-4e2f-91e6-76287cc345ee",
            "strategy_version": "active",
            "time_range_start": "2026-05-04T06:53:00",
            "time_range_end": "2026-05-11T06:53:00",
            "initial_balance": 10000.0,
            "final_balance": 10000.0,
            "metrics": {},
            "trades": None,
        }

        print_results(result)
        captured = capsys.readouterr()

        assert "TRADES" not in captured.out
