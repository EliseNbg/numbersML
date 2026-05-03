"""
Backtest Engine - Event-driven strategy backtesting with detailed statistics.

Provides:
- Chronological event-driven backtest loop
- Paper-like execution semantics (fees, slippage)
- Comprehensive metrics calculation
- Trade blotter and equity curve tracking
- Deterministic, reproducible results
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

import numpy as np

from src.domain.strategies.base import (
    EnrichedTick,
    Signal,
    SignalType,
)

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Single trade record from backtest."""

    entry_time: datetime
    exit_time: Optional[datetime] = None
    symbol: str = ""
    side: str = "LONG"  # LONG or SHORT
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0
    exit_reason: str = ""  # signal, stop_loss, take_profit, end_of_test


@dataclass
class EquityPoint:
    """Single point on equity curve."""

    timestamp: datetime
    equity: float
    cash: float
    positions_value: float
    drawdown: float


@dataclass
class BacktestMetrics:
    """Comprehensive backtest performance metrics."""

    # Returns
    total_return: float = 0.0
    total_return_pct: float = 0.0
    cagr: float = 0.0
    annualized_return: float = 0.0

    # Risk
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration: timedelta = field(default_factory=lambda: timedelta(0))
    volatility: float = 0.0
    volatility_annualized: float = 0.0

    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    avg_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    expectancy_pct: float = 0.0

    # Trade duration
    avg_trade_duration: timedelta = field(default_factory=lambda: timedelta(0))
    avg_win_duration: timedelta = field(default_factory=lambda: timedelta(0))
    avg_loss_duration: timedelta = field(default_factory=lambda: timedelta(0))
    max_trade_duration: timedelta = field(default_factory=lambda: timedelta(0))

    # Exposure
    avg_exposure_pct: float = 0.0
    max_exposure_pct: float = 0.0
    time_in_market_pct: float = 0.0

    # Costs
    total_fees: float = 0.0
    avg_fee_per_trade: float = 0.0

    # Consecutive streaks
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Monthly/period breakdown
    positive_periods: int = 0
    negative_periods: int = 0

    # Benchmark (if provided)
    alpha: Optional[float] = None
    beta: Optional[float] = None
    correlation_to_benchmark: Optional[float] = None


@dataclass
class BacktestResult:
    """Complete backtest result."""

    run_id: UUID
    strategy_id: UUID
    strategy_version: int
    config_snapshot: dict[str, Any]

    start_time: datetime
    end_time: datetime
    initial_balance: float
    final_balance: float

    metrics: BacktestMetrics
    trades: list[TradeRecord]
    equity_curve: list[EquityPoint]

    parameters: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class PaperExecutionSimulator:
    """
    Simulates order execution with realistic fees and slippage.

    Simulates:
    - Trading fees (maker/taker)
    - Slippage based on volatility and order size
    - Fill probability based on limit price proximity
    """

    def __init__(
        self,
        fee_bps: float = 10.0,  # 0.1% default fee
        slippage_bps: float = 5.0,  # 0.05% default slippage
        market_impact_factor: float = 0.1,
    ) -> None:
        self.fee_rate = fee_bps / 10000.0
        self.slippage_rate = slippage_bps / 10000.0
        self.market_impact_factor = market_impact_factor
        self._total_fees = 0.0

    def simulate_market_order(
        self,
        price: float,
        quantity: float,
        side: str,  # BUY or SELL
        volatility: float = 0.0,
    ) -> tuple[float, float]:
        """
        Simulate market order execution.

        Args:
            price: Current market price
            quantity: Order quantity
            side: BUY or SELL
            volatility: Current volatility (for slippage calc)

        Returns:
            (executed_price, fees_paid)
        """
        # Calculate slippage (higher volatility = more slippage)
        vol_slippage = volatility * self.market_impact_factor
        base_slippage = self.slippage_rate
        total_slippage = base_slippage + vol_slippage

        # Market orders have negative slippage (worse price)
        if side == "BUY":
            executed_price = price * (1 + total_slippage)
        else:
            executed_price = price * (1 - total_slippage)

        # Calculate fees
        notional = executed_price * quantity
        fees = notional * self.fee_rate
        self._total_fees += fees

        return executed_price, fees

    def simulate_limit_order(
        self,
        price: float,
        limit_price: float,
        quantity: float,
        side: str,
        volatility: float = 0.0,
    ) -> tuple[Optional[float], float]:
        """
        Simulate limit order execution.

        Args:
            price: Current market price
            limit_price: Order limit price
            quantity: Order quantity
            side: BUY or SELL
            volatility: Current volatility

        Returns:
            (executed_price or None if not filled, fees_paid)
        """
        # Check if limit order would fill
        if side == "BUY" and price <= limit_price:
            # Price is at or below limit, order fills
            executed_price = min(price, limit_price)
            # Lower slippage for limit orders (maker fee)
            maker_fee_rate = self.fee_rate * 0.5  # 50% discount for maker
            notional = executed_price * quantity
            fees = notional * maker_fee_rate
            self._total_fees += fees
            return executed_price, fees

        elif side == "SELL" and price >= limit_price:
            # Price is at or above limit, order fills
            executed_price = max(price, limit_price)
            maker_fee_rate = self.fee_rate * 0.5
            notional = executed_price * quantity
            fees = notional * maker_fee_rate
            self._total_fees += fees
            return executed_price, fees

        # Order doesn't fill
        return None, 0.0

    @property
    def total_fees(self) -> float:
        return self._total_fees

    def reset(self) -> None:
        self._total_fees = 0.0


class BacktestMetricsCalculator:
    """Calculate comprehensive backtest metrics from trade history."""

    @staticmethod
    def calculate(
        trades: list[TradeRecord],
        equity_curve: list[EquityPoint],
        initial_balance: float,
        total_fees: float,
        start_time: datetime,
        end_time: datetime,
    ) -> BacktestMetrics:
        """Calculate all metrics from backtest data."""
        metrics = BacktestMetrics()

        if not equity_curve:
            return metrics

        # Basic counts
        closed_trades = [t for t in trades if t.exit_time is not None]
        metrics.total_trades = len(closed_trades)

        if closed_trades:
            # PnL statistics
            winning_trades = [t for t in closed_trades if t.pnl > 0]
            losing_trades = [t for t in closed_trades if t.pnl < 0]

            metrics.winning_trades = len(winning_trades)
            metrics.losing_trades = len(losing_trades)
            metrics.win_rate = (
                metrics.winning_trades / metrics.total_trades if metrics.total_trades > 0 else 0
            )
            metrics.loss_rate = 1 - metrics.win_rate

            # PnL amounts
            gross_profit = sum(t.pnl for t in winning_trades)
            gross_loss = abs(sum(t.pnl for t in losing_trades))

            metrics.avg_trade = sum(t.pnl for t in closed_trades) / len(closed_trades)
            metrics.avg_win = gross_profit / len(winning_trades) if winning_trades else 0
            metrics.avg_loss = gross_loss / len(losing_trades) if losing_trades else 0

            metrics.largest_win = max((t.pnl for t in winning_trades), default=0)
            metrics.largest_loss = min((t.pnl for t in losing_trades), default=0)

            metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

            # Expectancy
            metrics.expectancy = (metrics.win_rate * metrics.avg_win) - (
                metrics.loss_rate * abs(metrics.avg_loss)
            )

        # Returns (can be calculated without trades if equity curve exists)
        final_equity = equity_curve[-1].equity
        metrics.total_return = final_equity - initial_balance
        metrics.total_return_pct = (metrics.total_return / initial_balance) * 100

        # Time-based metrics
        duration_days = (end_time - start_time).days
        if duration_days > 0:
            # CAGR calculation
            years = duration_days / 365.25
            metrics.cagr = (
                ((final_equity / initial_balance) ** (1 / years) - 1) * 100 if years > 0 else 0
            )
            metrics.annualized_return = metrics.total_return_pct / years if years > 0 else 0

        # Calculate drawdown
        peak = equity_curve[0].equity
        max_dd = 0.0
        dd_start = equity_curve[0].timestamp
        max_dd_duration = timedelta(0)

        in_drawdown = False
        current_dd_start = None

        for point in equity_curve:
            if point.equity > peak:
                peak = point.equity
                if in_drawdown:
                    # Drawdown ended
                    dd_duration = point.timestamp - current_dd_start
                    if dd_duration > max_dd_duration:
                        max_dd_duration = dd_duration
                    in_drawdown = False
            else:
                dd = (peak - point.equity) / peak
                if dd > max_dd:
                    max_dd = dd
                if not in_drawdown:
                    in_drawdown = True
                    current_dd_start = point.timestamp

        metrics.max_drawdown = max_dd * initial_balance  # Dollar amount
        metrics.max_drawdown_pct = max_dd * 100
        metrics.max_drawdown_duration = max_dd_duration

        # Volatility (from equity curve returns)
        equity_values = np.array([p.equity for p in equity_curve])
        if len(equity_values) > 1:
            returns = np.diff(equity_values) / equity_values[:-1]
            metrics.volatility = np.std(returns)

            # Annualize (assuming daily data points)
            periods_per_year = 252  # Trading days
            metrics.volatility_annualized = metrics.volatility * np.sqrt(periods_per_year)

            # Sharpe ratio (assuming 0% risk-free rate for simplicity)
            avg_return = np.mean(returns)
            if metrics.volatility > 0:
                metrics.sharpe_ratio = (
                    avg_return * periods_per_year
                ) / metrics.volatility_annualized

            # Sortino ratio (downside deviation only)
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0:
                downside_std = np.std(downside_returns) * np.sqrt(periods_per_year)
                if downside_std > 0:
                    metrics.sortino_ratio = (avg_return * periods_per_year) / downside_std

        # Calmar ratio (CAGR / Max Drawdown)
        if metrics.max_drawdown_pct > 0:
            metrics.calmar_ratio = metrics.cagr / metrics.max_drawdown_pct

        # Trade durations
        durations = []
        win_durations = []
        loss_durations = []

        for trade in closed_trades:
            if trade.exit_time and trade.entry_time:
                duration = trade.exit_time - trade.entry_time
                durations.append(duration)
                if trade.pnl > 0:
                    win_durations.append(duration)
                else:
                    loss_durations.append(duration)

        if durations:
            metrics.avg_trade_duration = sum(durations, timedelta(0)) / len(durations)
            metrics.max_trade_duration = max(durations)

        if win_durations:
            metrics.avg_win_duration = sum(win_durations, timedelta(0)) / len(win_durations)

        if loss_durations:
            metrics.avg_loss_duration = sum(loss_durations, timedelta(0)) / len(loss_durations)

        # Consecutive wins/losses
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in closed_trades:
            if trade.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)

        metrics.max_consecutive_wins = max_consecutive_wins
        metrics.max_consecutive_losses = max_consecutive_losses

        # Costs
        metrics.total_fees = total_fees
        metrics.avg_fee_per_trade = total_fees / len(closed_trades) if closed_trades else 0

        # Exposure calculations
        if equity_curve:
            position_values = [p.positions_value for p in equity_curve]
            equities = [p.equity for p in equity_curve]

            exposures = [
                pos_val / equity if equity > 0 else 0
                for pos_val, equity in zip(position_values, equities)
            ]

            metrics.avg_exposure_pct = np.mean(exposures) * 100 if exposures else 0
            metrics.max_exposure_pct = max(exposures) * 100 if exposures else 0
            metrics.time_in_market_pct = (sum(1 for e in exposures if e > 0) / len(exposures)) * 100

        return metrics


class BacktestEngine:
    """
    Event-driven backtesting engine for trading strategies.

    Features:
    - Chronological event processing (no lookahead bias)
    - Realistic execution simulation (fees, slippage)
    - Comprehensive metrics calculation
    - Deterministic results for reproducibility
    """

    def __init__(
        self,
        db_pool,
        fee_bps: float = 10.0,
        slippage_bps: float = 5.0,
    ) -> None:
        self.db_pool = db_pool
        self.execution_sim = PaperExecutionSimulator(fee_bps, slippage_bps)
        self.metrics_calc = BacktestMetricsCalculator()

    async def run_backtest(
        self,
        strategy_id: UUID,
        strategy_version: int,
        config: dict[str, Any],
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
        initial_balance: float = 10000.0,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> BacktestResult:
        """
        Run a complete backtest for a strategy.

        Args:
            strategy_id: Strategy ID
            strategy_version: Strategy version number
            config: Strategy configuration
            symbols: List of symbols to trade
            start_time: Backtest start time
            end_time: Backtest end time
            initial_balance: Starting capital
            progress_callback: Optional callback(progress_0_to_1)

        Returns:
            Complete backtest result with metrics
        """
        run_id = uuid4()
        logger.info(f"Starting backtest {run_id}: {strategy_id} v{strategy_version}")

        # Reset simulator
        self.execution_sim.reset()

        # Load historical data
        candles = await self._load_historical_data(symbols[0], start_time, end_time)

        if not candles:
            raise ValueError("No historical data found for backtest period")

        logger.info(f"Loaded {len(candles)} candles for backtest")

        # Initialize tracking
        cash = initial_balance
        positions: dict[str, dict[str, Any]] = {}  # symbol -> position info
        trades: list[TradeRecord] = []
        equity_curve: list[EquityPoint] = []

        # Add initial equity point
        equity_curve.append(
            EquityPoint(
                timestamp=start_time,
                equity=initial_balance,
                cash=initial_balance,
                positions_value=0.0,
                drawdown=0.0,
            )
        )

        # Run simulation
        total_candles = len(candles)

        for i, candle in enumerate(candles):
            # Update progress
            if progress_callback and i % 100 == 0:
                progress_callback(i / total_candles)

            # Create enriched tick from candle
            tick = self._create_enriched_tick(candle)

            # Process any existing positions (check stop loss, take profit)
            for symbol, pos in list(positions.items()):
                current_price = float(candle["close"])

                # Check stop loss
                stop_loss = pos.get("stop_loss")
                if stop_loss and pos["side"] == "LONG" and current_price <= stop_loss:
                    # Close position at stop loss
                    cash, trade = self._close_position(
                        pos, current_price, cash, candle["time"], "stop_loss"
                    )
                    trades.append(trade)
                    del positions[symbol]
                    continue

                # Check take profit
                take_profit = pos.get("take_profit")
                if take_profit and pos["side"] == "LONG" and current_price >= take_profit:
                    # Close position at take profit
                    cash, trade = self._close_position(
                        pos, current_price, cash, candle["time"], "take_profit"
                    )
                    trades.append(trade)
                    del positions[symbol]
                    continue

            # Generate signal (simplified - would use actual strategy)
            signal = self._generate_signal(config, candle, positions)

            if signal:
                # Execute signal
                if signal.signal_type == SignalType.BUY and not positions.get(signal.symbol):
                    # Open long position
                    cash, pos, trade = self._open_position(signal, candle, cash, config)
                    if pos:
                        positions[signal.symbol] = pos
                        if trade:
                            trades.append(trade)

                elif signal.signal_type == SignalType.SELL and positions.get(signal.symbol):
                    # Close position
                    pos = positions[signal.symbol]
                    cash, trade = self._close_position(
                        pos, float(candle["close"]), cash, candle["time"], "signal"
                    )
                    trades.append(trade)
                    del positions[signal.symbol]

            # Calculate current equity
            positions_value = sum(
                p["quantity"] * float(candle["close"]) for p in positions.values()
            )
            total_equity = cash + positions_value

            # Calculate drawdown
            peak = max(p.equity for p in equity_curve)
            drawdown = (peak - total_equity) / peak if peak > 0 else 0.0

            # Add equity point (sample every N candles to reduce size)
            if i % 10 == 0 or i == total_candles - 1:
                equity_curve.append(
                    EquityPoint(
                        timestamp=candle["time"],
                        equity=total_equity,
                        cash=cash,
                        positions_value=positions_value,
                        drawdown=drawdown,
                    )
                )

        # Close any remaining positions at final price
        final_price = float(candles[-1]["close"])
        for symbol, pos in list(positions.items()):
            cash, trade = self._close_position(
                pos, final_price, cash, candles[-1]["time"], "end_of_test"
            )
            trades.append(trade)

        # Final equity
        final_balance = cash

        # Calculate metrics
        metrics = self.metrics_calc.calculate(
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=initial_balance,
            total_fees=self.execution_sim.total_fees,
            start_time=start_time,
            end_time=end_time,
        )

        logger.info(
            f"Backtest {run_id} complete: "
            f"Return={metrics.total_return_pct:.2f}%, "
            f"Trades={metrics.total_trades}, "
            f"WinRate={metrics.win_rate:.1%}, "
            f"MaxDD={metrics.max_drawdown_pct:.2f}%"
        )

        if progress_callback:
            progress_callback(1.0)

        return BacktestResult(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            config_snapshot=config,
            start_time=start_time,
            end_time=end_time,
            initial_balance=initial_balance,
            final_balance=final_balance,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            parameters={
                "fee_bps": 10.0,
                "slippage_bps": 5.0,
                "symbols": symbols,
            },
        )

    async def _load_historical_data(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Load historical candle data from database."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.time, c.open, c.high, c.low, c.close, c.volume,
                       ci.values as indicators
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                LEFT JOIN candle_indicators ci ON ci.time = c.time AND ci.symbol_id = c.symbol_id
                WHERE s.symbol = $1 AND c.time >= $2 AND c.time <= $3
                ORDER BY c.time ASC
                """,
                symbol,
                start_time,
                end_time,
            )

        candles = []
        for row in rows:
            indicators = row["indicators"] if row["indicators"] else {}
            if isinstance(indicators, str):
                import json

                try:
                    indicators = json.loads(indicators)
                except:
                    indicators = {}

            candles.append(
                {
                    "time": row["time"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "indicators": indicators,
                }
            )

        return candles

    def _create_enriched_tick(self, candle: dict[str, Any]) -> EnrichedTick:
        """Create EnrichedTick from candle data."""
        return EnrichedTick(
            symbol="BTC/USDC",  # Would be parameterized
            price=Decimal(str(candle["close"])),
            volume=Decimal(str(candle["volume"])),
            time=candle["time"],
            indicators=candle.get("indicators", {}),
        )

    def _generate_signal(
        self,
        config: dict[str, Any],
        candle: dict[str, Any],
        positions: dict[str, dict[str, Any]],
    ) -> Optional[Signal]:
        """
        Generate trading signal based on config.

        Simplified implementation - would use actual strategy logic.
        """
        signal_config = config.get("signal", {})
        signal_type = signal_config.get("type", "rsi")
        params = signal_config.get("params", {})

        indicators = candle.get("indicators", {})

        # Simple RSI signal
        if signal_type == "rsi":
            rsi_key = f'rsiindicator_period{params.get("period", 14)}_rsi'
            rsi_value = indicators.get(rsi_key)

            if rsi_value is not None:
                oversold = params.get("oversold", 30)
                overbought = params.get("overbought", 70)

                if rsi_value < oversold and not positions:
                    # Buy signal
                    return Signal(
                        strategy_id="backtest",
                        symbol="BTC/USDC",
                        signal_type=SignalType.BUY,
                        price=Decimal(str(candle["close"])),
                        confidence=0.7,
                        metadata={"rsi": rsi_value},
                    )
                elif rsi_value > overbought and positions:
                    # Sell signal
                    return Signal(
                        strategy_id="backtest",
                        symbol="BTC/USDC",
                        signal_type=SignalType.SELL,
                        price=Decimal(str(candle["close"])),
                        confidence=0.7,
                        metadata={"rsi": rsi_value},
                    )

        return None

    def _open_position(
        self,
        signal: Signal,
        candle: dict[str, Any],
        cash: float,
        config: dict[str, Any],
    ) -> tuple[float, Optional[dict[str, Any]], Optional[TradeRecord]]:
        """Open a new position."""
        risk_config = config.get("risk", {})
        max_position_pct = risk_config.get("max_position_size_pct", 10) / 100

        price = float(candle["close"])

        # Calculate position size
        position_value = cash * max_position_pct
        quantity = position_value / price

        # Simulate execution
        executed_price, fees = self.execution_sim.simulate_market_order(
            price=price,
            quantity=quantity,
            side="BUY",
        )

        total_cost = executed_price * quantity + fees

        if total_cost > cash:
            # Not enough cash
            return cash, None, None

        new_cash = cash - total_cost

        position = {
            "symbol": signal.symbol,
            "side": "LONG",
            "entry_price": executed_price,
            "quantity": quantity,
            "entry_time": candle["time"],
            "stop_loss": risk_config.get("stop_loss_pct")
            and executed_price * (1 - risk_config.get("stop_loss_pct", 0) / 100),
            "take_profit": risk_config.get("take_profit_pct")
            and executed_price * (1 + risk_config.get("take_profit_pct", 0) / 100),
        }

        trade = TradeRecord(
            entry_time=candle["time"],
            symbol=signal.symbol,
            side="LONG",
            entry_price=executed_price,
            quantity=quantity,
            fees=fees,
            exit_reason="open",
        )

        return new_cash, position, trade

    def _close_position(
        self,
        position: dict[str, Any],
        price: float,
        cash: float,
        exit_time: datetime,
        exit_reason: str,
    ) -> tuple[float, TradeRecord]:
        """Close an existing position."""
        quantity = position["quantity"]
        entry_price = position["entry_price"]

        # Simulate execution
        executed_price, fees = self.execution_sim.simulate_market_order(
            price=price,
            quantity=quantity,
            side="SELL",
        )

        # Calculate PnL
        gross_proceeds = executed_price * quantity
        net_proceeds = gross_proceeds - fees
        entry_cost = entry_price * quantity
        pnl = net_proceeds - entry_cost
        pnl_pct = (pnl / entry_cost) * 100 if entry_cost > 0 else 0

        new_cash = cash + net_proceeds

        trade = TradeRecord(
            entry_time=position["entry_time"],
            exit_time=exit_time,
            symbol=position["symbol"],
            side="LONG",
            entry_price=entry_price,
            exit_price=executed_price,
            quantity=quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fees=fees,
            exit_reason=exit_reason,
        )

        return new_cash, trade
