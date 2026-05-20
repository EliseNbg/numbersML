#!/usr/bin/env python3
"""
Run Backtest CLI

Runs a strategy backtest from the command line.

Usage:
    python -m src.cli.run_backtest --strategy-id UUID [options]

Options:
    --strategy-id UUID      Strategy ID to backtest (required)
    --version INT           Specific strategy version (defaults to active)
    --symbol SYMBOL         Symbol to backtest (e.g., BTC/USDC)
    --start-time TIMESTAMP  Start time (ISO format, defaults to 7 days ago)
    --end-time TIMESTAMP    End time (ISO format, defaults to now)
    --initial-balance FLOAT Initial capital (default: 10000)
    --include-equity-curve  Include equity curve in output (default: true)
    --include-trades        Include individual trades in output (default: true)
    --output FILE           Output file for results (JSON format)
    --wait                  Wait for completion and show results
    --timeout SECONDS       Timeout for waiting (default: 300)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

# Add user site-packages AND .venv FIRST (before local package imports)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

# Add .venv site-packages if it exists
venv_site = os.path.join(project_root, ".venv", "lib", "python3.13", "site-packages")
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)

# Add user site-packages as fallback
USER_SITE = "/home/andy/.local/lib/python3.13/site-packages"
if USER_SITE not in sys.path:
    sys.path.insert(0, USER_SITE)

from dotenv import load_dotenv  # noqa: E402

# Load environment variables from .env file
load_dotenv()

from src.application.services.backtest_engine import BacktestEngine
from src.application.services.strategy_backtest_service import StrategyBacktestService
from src.infrastructure.database import get_db_pool_async, set_db_pool
from src.infrastructure.repositories.strategy_repository_pg import StrategyRepositoryPG
from src.infrastructure.repositories.strategy_backtest_repository_pg import (
    StrategyBacktestRepositoryPG,
)


# Database initialization
async def init_db_pool():
    """Initialize database pool from environment or defaults."""
    import asyncpg

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    database = os.getenv("DB_NAME", "crypto_trading")
    user = os.getenv("DB_USER", "crypto")
    password = os.getenv("DB_PASS", "crypto_secret")

    pool = await asyncpg.create_pool(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        min_size=1,
        max_size=10,
    )
    set_db_pool(pool)
    return pool


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Run Strategy Backtest from Command Line",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run backtest with defaults (last 7 days)
  python3 -m src.cli.run_backtest --strategy-id 123e4567-e89b-12d3-a456-426614174000

  # Run backtest with specific parameters
  python3 -m src.cli.run_backtest \\
    --strategy-id 123e4567-e89b-12d3-a456-426614174000 \\
    --symbol BTC/USDC \\
    --start-time "2026-05-01T00:00:00" \\
    --end-time "2026-05-08T00:00:00" \\
    --initial-balance 10000 \\
    --wait

  # Run backtest and save results to file
  python3 -m src.cli.run_backtest \\
    --strategy-id 123e4567-e89b-12d3-a456-426614174000 \\
    --output backtest_results.json
        """,
    )

    parser.add_argument(
        "--strategy-id",
        type=str,
        required=True,
        help="Strategy ID to backtest (required)",
    )

    parser.add_argument(
        "--version",
        type=int,
        help="Specific strategy version (defaults to active)",
    )

    parser.add_argument(
        "--symbol",
        type=str,
        help="Symbol to backtest (e.g., BTC/USDC)",
    )

    parser.add_argument(
        "--start-time",
        type=str,
        help="Start time (ISO format, defaults to 7 days ago)",
    )

    parser.add_argument(
        "--end-time",
        type=str,
        help="End time (ISO format, defaults to now)",
    )

    parser.add_argument(
        "--initial-balance",
        type=float,
        default=10000.0,
        help="Initial capital (default: 10000)",
    )

    parser.add_argument(
        "--include-equity-curve",
        action="store_true",
        default=True,
        help="Include equity curve in output (default: true)",
    )

    parser.add_argument(
        "--no-equity-curve",
        dest="include_equity_curve",
        action="store_false",
        help="Exclude equity curve from output",
    )

    parser.add_argument(
        "--include-trades",
        action="store_true",
        default=True,
        help="Include individual trades in output (default: true)",
    )

    parser.add_argument(
        "--no-trades",
        dest="include_trades",
        action="store_false",
        help="Exclude individual trades from output",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (JSON format)",
    )

    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for completion and show results",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout for waiting in seconds (default: 300)",
    )

    parser.add_argument(
        "--validate-with-binance",
        action="store_true",
        help="Validate orders against Binance testnet endpoint",
    )

    return parser.parse_args()


async def run_backtest_async(args: argparse.Namespace) -> dict:
    """
    Run the backtest asynchronously.

    Args:
        args: Parsed command line arguments

    Returns:
        Backtest results dictionary
    """
    try:
        # Parse strategy ID
        try:
            strategy_id = UUID(args.strategy_id)
        except ValueError:
            raise ValueError(f"Invalid strategy ID format: {args.strategy_id}")

        # Parse timestamps
        if args.start_time:
            try:
                start_time = datetime.fromisoformat(args.start_time.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid start-time format: {args.start_time}")
        else:
            start_time = datetime.now(UTC) - timedelta(days=7)

        if args.end_time:
            try:
                end_time = datetime.fromisoformat(args.end_time.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid end-time format: {args.end_time}")
        else:
            end_time = datetime.now(UTC)

        # Validate time range
        if end_time <= start_time:
            raise ValueError("End time must be after start time")

        # Initialize services
        db_pool = await get_db_pool_async()
        strategy_repo = StrategyRepositoryPG(db_pool)
        backtest_repo = StrategyBacktestRepositoryPG(db_pool)

        binance_test_client = None
        if args.validate_with_binance:
            from src.infrastructure.market.binance_exchange_client import (
                BINANCE_TESTNET,
                BinanceExchangeClient,
            )

            api_key = os.getenv("BINANCE_TESTNET_API_KEY")
            api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
            if not api_key or not api_secret:
                raise ValueError(
                    "BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET "
                    "environment variables are required for Binance validation"
                )
            binance_test_client = BinanceExchangeClient(
                api_key=api_key,
                api_secret=api_secret,
                environment=BINANCE_TESTNET,
            )
            logger.info("Binance testnet validation enabled")

            # Enable HTTP request/response logging
            logging.getLogger("aiohttp.client").setLevel(logging.DEBUG)
            logging.getLogger("aiohttp.websocket").setLevel(logging.DEBUG)

        backtest_engine = BacktestEngine(db_pool=db_pool, binance_test_client=binance_test_client)
        backtest_service = StrategyBacktestService(
            strategy_repository=strategy_repo,
            backtest_repository=backtest_repo,
            backtest_engine=backtest_engine,
            actor="cli",
        )

        logger.info(f"Starting backtest for strategy {strategy_id}")
        logger.info(f"Time range: {start_time} to {end_time}")
        logger.info(f"Symbol: {args.symbol or 'All'}")
        logger.info(f"Initial balance: {args.initial_balance}")

        # Run backtest
        result = await backtest_service.run_backtest(
            strategy_id=strategy_id,
            strategy_version=args.version,
            start_time=start_time,
            end_time=end_time,
            initial_balance=args.initial_balance,
            symbol=args.symbol,
            progress_callback=lambda p: (
                logger.info(f"Backtest progress: {p*100:.1f}%") if args.wait else None
            ),
        )

        # Serialize result
        from src.application.services.backtest_engine import (
            serialize_metrics,
            serialize_equity_point,
            serialize_price_point,
            serialize_trade_record,
            serialize_debug_message,
        )

        serialized_result = {
            "strategy_id": str(strategy_id),
            "strategy_version": args.version or "active",
            "time_range_start": start_time.isoformat(),
            "time_range_end": end_time.isoformat(),
            "initial_balance": args.initial_balance,
            "final_balance": result.final_balance,
            "metrics": serialize_metrics(result.metrics),
            "parameters": result.parameters,
            "trades": (
                [serialize_trade_record(t) for t in result.trades]
                if args.include_trades and result.trades
                else None
            ),
            "equity_curve": (
                [serialize_equity_point(p) for p in result.equity_curve]
                if args.include_equity_curve and result.equity_curve
                else None
            ),
            "price_series": (
                [serialize_price_point(p) for p in result.price_series]
                if result.price_series
                else None
            ),
            "debug_messages": (
                [serialize_debug_message(m) for m in result.debug_messages]
                if result.debug_messages
                else None
            ),
            "completed_at": datetime.now(UTC).isoformat(),
        }

        return serialized_result

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        raise


def print_results(result: dict):
    """
    Print formatted backtest results to console.

    Args:
        result: Backtest results dictionary
    """
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"Strategy ID: {result['strategy_id']}")
    print(f"Version: {result['strategy_version']}")
    print(f"Period: {result['time_range_start']} to {result['time_range_end']}")
    print(f"Symbol: {result.get('symbol', 'All')}")
    print(f"Initial Balance: ${result['initial_balance']:.2f}")
    print(f"Final Balance: ${result['final_balance']:.2f}")
    print(f"Total Return: {result['metrics'].get('total_return_pct', 0):+.2f}%")
    print(f"Max Drawdown: {result['metrics'].get('max_drawdown_pct', 0):.2f}%")
    print(f"Sharpe Ratio: {result['metrics'].get('sharpe_ratio', 0):.2f}")
    print(f"Win Rate: {result['metrics'].get('win_rate', 0)*100:.1f}%")
    print(f"Total Trades: {result['metrics'].get('total_trades', 0)}")
    print(f"Profit Factor: {result['metrics'].get('profit_factor', 0):.2f}")

    if result.get("trades"):
        print("\n" + "-" * 60)
        print("TRADES")
        print("-" * 60)
        for i, trade in enumerate(result["trades"], 1):
            print(
                f"{i:3d}. {trade['entry_time']} -> {trade['exit_time'] or 'OPEN'} "
                f"{trade['symbol']} {trade['side']} "
                f"@{trade['entry_price']:.4f} -> {trade['exit_price'] or 'N/A':>8} "
                f"PnL: ${trade['pnl']:>8.2f} ({trade['pnl_pct']:+.2f}%) "
                f"[{trade['exit_reason']}]"
            )

    if result.get("equity_curve"):
        print("\n" + "-" * 60)
        print("EQUITY CURVE (last 5 points)")
        print("-" * 60)
        for point in result["equity_curve"][-5:]:
            print(
                f"{point['timestamp']}: Equity ${point['equity']:.2f} "
                f"(DD: {point.get('drawdown_pct', 0):.2f}%)"
            )

    print("=" * 60)


async def main_async() -> int:
    """
    Async main entry point with DB initialization.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    try:
        # Initialize database pool
        logger.info("Initializing database connection...")
        await init_db_pool()

        # Run backtest
        result = await run_backtest_async(args)

        # Output results
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
            logger.info(f"Results saved to {args.output}")

        if args.wait or not args.output:
            print_results(result)

        return 0

    except Exception as e:
        logger.error(f"Failed to run backtest: {e}")
        return 1


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
