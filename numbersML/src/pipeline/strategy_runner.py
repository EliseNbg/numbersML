"""Strategy Runner — parallel strategy execution within the pipeline.

Loads active strategies from the database, executes them in parallel
per symbol tick, collects signals, and routes them to MarketService.

Features:
- Parallel execution via asyncio.gather with return_exceptions=True
- Per-strategy timeout (500ms default)
- Hot-reload of active strategies every 5 seconds
- Stdout capture per strategy
- Signal deduplication (same strategy+symbol+side within 60s)
- DB persistence of all signals
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from src.domain.strategies.base import EnrichedTick, Strategy
from src.domain.strategies.signal import SignalStatus, TradeSignal
from src.pipeline.strategy_executor import StrategyExecutor, StrategyResult

logger = logging.getLogger(__name__)


@dataclass
class StrategyContext:
    """Runtime context for a loaded strategy."""

    strategy_id: UUID
    strategy_name: str
    strategy: Strategy
    mode: str = "paper"
    symbols: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    stdout_buffer: list[str] = field(default_factory=list)
    signals_today: int = 0
    last_signal_at: datetime | None = None
    errors_last_hour: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True


class StrategyRunner:
    """Orchestrates parallel strategy execution within the pipeline.

    Attributes:
        db_pool: Database connection pool
        market_service: MarketService for order placement
        timeout_seconds: Per-strategy execution timeout
        reload_interval: Seconds between hot-reload checks
        dedup_window_seconds: Deduplication window for signals
    """

    MAX_STDOUT_BUFFER = 1000  # lines per strategy

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        market_service: Any = None,
        timeout_seconds: float = 0.5,
        reload_interval: float = 5.0,
        dedup_window_seconds: int = 60,
    ) -> None:
        """Initialize strategy runner.

        Args:
            db_pool: Database connection pool
            market_service: MarketService for order placement
            timeout_seconds: Per-strategy execution timeout
            reload_interval: Seconds between hot-reload checks
            dedup_window_seconds: Signal deduplication window
        """
        self.db_pool = db_pool
        self.market_service = market_service
        self.timeout_seconds = timeout_seconds
        self.reload_interval = reload_interval
        self.dedup_window_seconds = dedup_window_seconds

        self._strategies: dict[UUID, StrategyContext] = {}
        self._executor = StrategyExecutor(timeout_seconds=timeout_seconds)
        self._last_reload = 0.0
        self._lock = asyncio.Lock()
        self._signal_history: list[TradeSignal] = []
        self._max_signal_history = 500
        self._tick_count = 0
        self._stats = {
            "signals_emitted": 0,
            "signals_executed": 0,
            "signals_rejected": 0,
            "signals_failed": 0,
            "strategy_errors": 0,
            "deduplicated": 0,
        }

    async def execute_tick(
        self,
        symbol: str,
        candle_time: datetime,
        tick_indicators: dict[str, float],
        current_price: Decimal,
    ) -> list[TradeSignal]:
        """Run all active strategies for a symbol tick.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDC')
            candle_time: Time of the candle
            tick_indicators: Dictionary of indicator values
            current_price: Current market price

        Returns:
            List of TradeSignal emitted by strategies
        """
        self._tick_count += 1

        # Hot-reload if interval elapsed
        if time.time() - self._last_reload > self.reload_interval:
            await self.hot_reload()

        # Filter strategies that trade this symbol
        eligible = [
            ctx for ctx in self._strategies.values()
            if ctx.is_active and (not ctx.symbols or symbol in ctx.symbols)
        ]

        if not eligible:
            return []

        # Execute all eligible strategies in parallel
        tasks = []
        for ctx in eligible:
            tick = EnrichedTick(
                symbol=symbol,
                price=current_price,
                volume=Decimal("0"),
                time=candle_time,
                indicators=tick_indicators,
            )
            tasks.append(self._execute_single(ctx, tick))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect signals
        signals: list[TradeSignal] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Strategy execution exception: {result}")
                self._stats["strategy_errors"] += 1
                continue
            if result.signal:
                # Deduplication check
                if self._is_duplicate(result.signal):
                    self._stats["deduplicated"] += 1
                    continue
                signals.append(result.signal)
                self._signal_history.append(result.signal)
                if len(self._signal_history) > self._max_signal_history:
                    self._signal_history = self._signal_history[-self._max_signal_history:]

                # Update strategy context
                ctx = self._strategies.get(UUID(result.signal.strategy_id))
                if ctx:
                    ctx.signals_today += 1
                    ctx.last_signal_at = result.signal.timestamp
                self._stats["signals_emitted"] += 1

                # Route to market service
                await self._route_signal(result.signal)

            # Capture stdout
            if result.stdout:
                ctx = self._strategies.get(UUID(result.strategy_id))
                if ctx:
                    ctx.stdout_buffer.extend(result.stdout)
                    # Trim buffer
                    if len(ctx.stdout_buffer) > self.MAX_STDOUT_BUFFER:
                        ctx.stdout_buffer = ctx.stdout_buffer[-self.MAX_STDOUT_BUFFER:]

        # Periodic logging every 500 ticks
        if self._tick_count % 500 == 0:
            logger.info(
                f"StrategyRunner stats (tick {self._tick_count}): "
                f"active={len(eligible)}, signals={self._stats['signals_emitted']}, "
                f"errors={self._stats['strategy_errors']}, "
                f"dedup={self._stats['deduplicated']}"
            )

        return signals

    async def _execute_single(
        self,
        ctx: StrategyContext,
        tick: EnrichedTick,
    ) -> StrategyResult:
        """Execute a single strategy with error isolation.

        Args:
            ctx: Strategy context
            tick: Enriched tick data

        Returns:
            StrategyResult with signal or error
        """
        try:
            return await self._executor.execute(ctx.strategy, tick)
        except Exception as e:
            logger.error(f"Strategy {ctx.strategy_id} execution error: {e}")
            self._stats["strategy_errors"] += 1
            return StrategyResult(
                strategy_id=str(ctx.strategy_id),
                strategy_name=ctx.strategy_name,
                symbol=tick.symbol,
                error=str(e),
            )

    async def _route_signal(self, signal: TradeSignal) -> None:
        """Route signal to MarketService for order placement.

        Args:
            signal: TradeSignal to execute
        """
        if self.market_service is None:
            logger.debug(f"No market service configured, signal {signal.signal_id} logged only")
            signal = TradeSignal(
                **{**signal.__dict__, "status": SignalStatus.REJECTED}
            )
            self._stats["signals_rejected"] += 1
            await self._persist_signal(signal, reason="No market service configured")
            return

        try:
            from src.domain.market.order import OrderRequest, OrderSide, OrderType

            order_request = OrderRequest(
                symbol=signal.symbol,
                side=OrderSide(signal.side),
                order_type=OrderType(signal.order_type),
                quantity=signal.quantity,
                limit_price=signal.price,
                client_order_id=str(signal.signal_id),
                metadata=signal.metadata,
            )

            order = await self.market_service.place_order(order_request)

            signal = TradeSignal(
                **{**signal.__dict__, "status": SignalStatus.EXECUTED}
            )
            self._stats["signals_executed"] += 1
            await self._persist_signal(signal, order_id=str(order.id))

        except Exception as e:
            logger.error(f"Failed to route signal {signal.signal_id}: {e}")
            signal = TradeSignal(
                **{**signal.__dict__, "status": SignalStatus.FAILED}
            )
            self._stats["signals_failed"] += 1
            await self._persist_signal(signal, error=str(e))

    async def hot_reload(self) -> None:
        """Re-scan DB for strategy changes without restart.

        Compares DB active strategies with in-memory list:
        - Add newly activated strategies
        - Remove deactivated strategies (graceful stop)
        - Update config for changed strategies
        """
        async with self._lock:
            try:
                db_strategies = await self._load_active_strategies()
            except Exception as e:
                logger.error(f"Hot-reload failed: {e}")
                return

            current_ids = set(self._strategies.keys())
            db_ids = set(db_strategies.keys())

            # Remove deactivated strategies
            for sid in current_ids - db_ids:
                ctx = self._strategies.pop(sid)
                try:
                    await ctx.strategy.stop()
                except Exception as e:
                    logger.error(f"Error stopping strategy {sid}: {e}")
                ctx.is_active = False
                logger.info(f"Deactivated strategy: {ctx.strategy_name} ({sid})")

            # Add newly activated strategies
            for sid in db_ids - current_ids:
                ctx = db_strategies[sid]
                try:
                    await ctx.strategy.initialize()
                    await ctx.strategy.start()
                except Exception as e:
                    logger.error(f"Error starting strategy {sid}: {e}")
                    continue
                self._strategies[sid] = ctx
                logger.info(f"Activated strategy: {ctx.strategy_name} ({sid})")

            self._last_reload = time.time()

    async def _load_active_strategies(self) -> dict[UUID, StrategyContext]:
        """Load active strategies from database.

        Returns:
            Dict of strategy_id -> StrategyContext
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.id, s.name, s.mode, s.status, s.class_path,
                       sv.config
                FROM strategies s
                JOIN strategy_versions sv ON sv.strategy_id = s.id AND sv.is_active = true
                WHERE s.status = 'active' AND s.strategy_type = 'class'
                AND s.class_path IS NOT NULL
            """)

        strategies: dict[UUID, StrategyContext] = {}
        for row in rows:
            try:
                strategy = self._instantiate_strategy(row["class_path"], str(row["id"]))
                config = row["config"] or {}
                symbols = config.get("symbols", [])
                if isinstance(symbols, str):
                    symbols = [symbols]

                ctx = StrategyContext(
                    strategy_id=row["id"],
                    strategy_name=row["name"],
                    strategy=strategy,
                    mode=row["mode"],
                    symbols=symbols,
                    config=config,
                )
                strategies[row["id"]] = ctx
            except Exception as e:
                logger.error(f"Failed to load strategy {row['id']}: {e}")

        return strategies

    @staticmethod
    def _instantiate_strategy(class_path: str, strategy_id: str) -> Strategy:
        """Dynamically import and instantiate a strategy class.

        Args:
            class_path: Fully qualified class path (e.g., 'src.strategies.user.macd_buy_strategy.MacdBuyStrategy')
            strategy_id: Strategy ID to pass to constructor

        Returns:
            Strategy instance
        """
        import importlib

        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        # Instantiate with strategy_id and a placeholder symbol list
        # Symbols are loaded from config separately
        return cls(strategy_id=strategy_id, symbols=["BTC/USDC"])

    def _is_duplicate(self, signal: TradeSignal) -> bool:
        """Check if signal is a duplicate within the dedup window.

        Args:
            signal: Signal to check

        Returns:
            True if duplicate found
        """
        cutoff = datetime.now(UTC).timestamp() - self.dedup_window_seconds
        for past in reversed(self._signal_history):
            if past.timestamp.timestamp() < cutoff:
                break
            if (
                past.strategy_id == signal.strategy_id
                and past.symbol == signal.symbol
                and past.side == signal.side
            ):
                return True
        return False

    async def _persist_signal(
        self,
        signal: TradeSignal,
        order_id: str | None = None,
        error: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Persist signal to database.

        Args:
            signal: TradeSignal to persist
            order_id: Associated order ID if executed
            error: Error message if failed
            reason: Rejection reason if rejected
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO strategy_signals (
                        id, strategy_id, symbol, side, order_type,
                        quantity, price, status, metadata,
                        created_at, executed_at, error_message
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    signal.signal_id,
                    UUID(signal.strategy_id) if isinstance(signal.strategy_id, str) else signal.strategy_id,
                    signal.symbol,
                    signal.side,
                    signal.order_type,
                    signal.quantity,
                    signal.price,
                    signal.status.value,
                    signal.metadata,
                    signal.timestamp,
                    datetime.now(UTC) if signal.status == SignalStatus.EXECUTED else None,
                    error or reason,
                )
        except Exception as e:
            logger.error(f"Failed to persist signal {signal.signal_id}: {e}")

    def get_stdout(self, strategy_id: UUID, limit: int = 100) -> list[str]:
        """Get last N lines of stdout for a strategy.

        Args:
            strategy_id: Strategy UUID
            limit: Maximum lines to return

        Returns:
            List of stdout lines
        """
        ctx = self._strategies.get(strategy_id)
        if ctx is None:
            return []
        return ctx.stdout_buffer[-limit:]

    def clear_stdout(self, strategy_id: UUID) -> None:
        """Clear stdout buffer for a strategy.

        Args:
            strategy_id: Strategy UUID
        """
        ctx = self._strategies.get(strategy_id)
        if ctx:
            ctx.stdout_buffer.clear()

    def get_recent_signals(
        self,
        strategy_id: UUID | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[TradeSignal]:
        """Get recent signals with optional filters.

        Args:
            strategy_id: Filter by strategy
            symbol: Filter by symbol
            limit: Maximum signals to return

        Returns:
            List of recent signals
        """
        signals = self._signal_history
        if strategy_id:
            signals = [s for s in signals if s.strategy_id == strategy_id]
        if symbol:
            signals = [s for s in signals if s.symbol == symbol]
        return signals[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get runner statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "active_strategies": len(self._strategies),
            "tick_count": self._tick_count,
            "signals": dict(self._stats),
            "strategies": {
                str(sid): {
                    "name": ctx.strategy_name,
                    "mode": ctx.mode,
                    "signals_today": ctx.signals_today,
                    "last_signal_at": ctx.last_signal_at.isoformat() if ctx.last_signal_at else None,
                    "stdout_lines": len(ctx.stdout_buffer),
                    "is_active": ctx.is_active,
                }
                for sid, ctx in self._strategies.items()
            },
        }
