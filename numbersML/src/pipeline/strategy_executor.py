"""Per-strategy async executor with isolation and stdout capture.

Wraps strategy.on_tick() in a sandboxed execution context:
- Captures stdout/stderr via context managers
- Enforces per-strategy timeout
- Returns StrategyResult with signal or error
"""
from __future__ import annotations

import asyncio
import io
import logging
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from src.domain.strategies.base import EnrichedTick, Signal, Strategy
from src.domain.strategies.signal import SignalStatus, TradeSignal

logger = logging.getLogger(__name__)


@dataclass
class StrategyResult:
    """Result of a single strategy execution."""

    strategy_id: str
    strategy_name: str
    symbol: str
    signal: TradeSignal | None = None
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    error: str | None = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class StrategyExecutor:
    """Executes a single strategy with full isolation.

    Attributes:
        timeout_seconds: Maximum execution time per tick (default 0.5s)
    """

    def __init__(self, timeout_seconds: float = 0.5) -> None:
        """Initialize executor.

        Args:
            timeout_seconds: Per-tick timeout for strategy execution
        """
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        strategy: Strategy,
        tick: EnrichedTick,
    ) -> StrategyResult:
        """Execute strategy.on_tick() with isolation and stdout capture.

        Args:
            strategy: Strategy instance to execute
            tick: Enriched tick data

        Returns:
            StrategyResult with signal, stdout, or error
        """
        start_time = datetime.now(UTC)
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        try:
            # Run on_tick with stdout capture and timeout
            result_container: list[Any] = []
            error_container: list[Exception] = []

            def _run() -> None:
                try:
                    sig = self._run_with_capture(
                        strategy, tick, stdout_buffer, stderr_buffer,
                    )
                    result_container.append(sig)
                except Exception as e:
                    error_container.append(e)

            await asyncio.wait_for(
                asyncio.to_thread(_run),
                timeout=self.timeout_seconds,
            )

            if error_container:
                raise error_container[0]

            signal = result_container[0] if result_container else None
            execution_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            trade_signal = self._to_trade_signal(strategy, signal, tick) if signal else None

            return StrategyResult(
                strategy_id=strategy.id,
                strategy_name=strategy.__class__.__name__,
                symbol=tick.symbol,
                signal=trade_signal,
                stdout=stdout_buffer.getvalue().splitlines(),
                stderr=stderr_buffer.getvalue().splitlines(),
                execution_time_ms=execution_time_ms,
            )

        except TimeoutError:
            execution_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            logger.warning(
                f"Strategy {strategy.id} timed out after {self.timeout_seconds}s "
                f"on {tick.symbol}"
            )
            return StrategyResult(
                strategy_id=strategy.id,
                strategy_name=strategy.__class__.__name__,
                symbol=tick.symbol,
                error=f"Timeout after {self.timeout_seconds}s",
                stdout=stdout_buffer.getvalue().splitlines(),
                stderr=stderr_buffer.getvalue().splitlines(),
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            logger.error(
                f"Strategy {strategy.id} error on {tick.symbol}: {e}",
                exc_info=True,
            )
            return StrategyResult(
                strategy_id=strategy.id,
                strategy_name=strategy.__class__.__name__,
                symbol=tick.symbol,
                error=str(e),
                stdout=stdout_buffer.getvalue().splitlines(),
                stderr=stderr_buffer.getvalue().splitlines(),
                execution_time_ms=execution_time_ms,
            )

    @staticmethod
    def _run_with_capture(
        strategy: Strategy,
        tick: EnrichedTick,
        stdout_buf: io.StringIO,
        stderr_buf: io.StringIO,
    ) -> Signal | None:
        """Run strategy.on_tick() directly with stdout/stderr redirected.

        We call on_tick() directly (not process_tick) so that exceptions
        propagate to the executor for proper error handling.

        Args:
            strategy: Strategy instance
            tick: Enriched tick data
            stdout_buf: Buffer for stdout capture
            stderr_buf: Buffer for stderr capture

        Returns:
            Signal if generated, None otherwise
        """
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            return strategy.on_tick(tick)

    @staticmethod
    def _to_trade_signal(
        strategy: Strategy,
        signal: Signal,
        tick: EnrichedTick,
    ) -> TradeSignal:
        """Convert domain Signal to TradeSignal.

        Args:
            strategy: Originating strategy
            signal: Domain signal
            tick: Tick that produced the signal

        Returns:
            TradeSignal ready for order routing
        """
        side = "BUY" if signal.signal_type.value in {"BUY", "CLOSE_SHORT"} else "SELL"

        quantity = signal.metadata.get("quantity", Decimal("0"))
        if isinstance(quantity, (int, float)):
            quantity = Decimal(str(quantity))

        price = signal.metadata.get("price")
        if price is not None and not isinstance(price, Decimal):
            price = Decimal(str(price))

        order_type = signal.metadata.get("order_type", "MARKET")
        if hasattr(order_type, "value"):
            order_type = order_type.value

        # Handle strategy_id that may not be a valid UUID
        raw_sid = signal.strategy_id
        if isinstance(raw_sid, UUID):
            strategy_id = str(raw_sid)
        else:
            try:
                UUID(str(raw_sid))
                strategy_id = str(raw_sid)
            except (ValueError, AttributeError):
                strategy_id = str(uuid4())

        return TradeSignal(
            strategy_id=strategy_id,
            strategy_name=strategy.__class__.__name__,
            symbol=signal.symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            timestamp=signal.timestamp,
            metadata=signal.metadata,
            status=SignalStatus.PENDING,
        )
