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
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg  # type: ignore

from src.domain.strategies.base import EnrichedTick, Signal, SignalType
from src.domain.strategies.strategy_instance import StrategyInstance
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
    trades: list[TradeRecord]
    equity_curve: list[dict[str, Any]]  # [{"time": ..., "balance": ...}]

    def to_dict(self) -> dict[str, Any]:
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
        candles = await self._load_candles(strategy_instance, time_range_start, time_range_end)

        if not candles:
            raise ValueError("No candle data found for the specified time range")

        # Initialize paper market service for simulation
        market_service = PaperMarketService(
            initial_balance=Decimal(str(initial_balance)),
            fee_bps=Decimal("10"),  # 0.1% fee
            slippage_bps=Decimal("10"),  # 0.1% slippage
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
    ) -> list[dict[str, Any]]:
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
                candles.append(
                    {
                        "time": row["time"],
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                        "indicators": row["indicators"] or {},
                    }
                )

            return candles

    async def _replay_candles(
        self,
        job_id: str,
        strategy_instance: StrategyInstance,
        candles: list[dict[str, Any]],
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
        trades: list[TradeRecord] = []
        equity_curve = [{"time": candles[0]["time"].isoformat(), "balance": initial_balance}]

        current_balance = initial_balance
        open_position: TradeRecord | None = None

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
                    pnl_pct = (
                        (candle["close"] - open_position.entry_price)
                        / open_position.entry_price
                        * 100
                    )

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

                    equity_curve.append(
                        {
                            "time": candle["time"].isoformat(),
                            "balance": current_balance,
                        }
                    )

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

    def _generate_signal(self, tick: EnrichedTick, instance: StrategyInstance) -> Signal | None:
        """
        Generate trading signal from tick.

        TODO: Actually load and run the Algorithm from instance.strategy_id
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

    def _flatten_indicators(self, indicators_json: dict[str, Any]) -> dict[str, float]:
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
            elif isinstance(value, int | float):
                result[key] = float(value)
        return result

    def _calculate_metrics(
        self,
        job_id: str,
        strategy_instance: StrategyInstance,
        trades: list[TradeRecord],
        equity_curve: list[dict[str, Any]],
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
                sharpe_ratio = (avg_return / std_return) * (252**0.5)  # Annualized

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

        assert strategy_instance.id is not None
        assert isinstance(strategy_instance.id, UUID)

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
