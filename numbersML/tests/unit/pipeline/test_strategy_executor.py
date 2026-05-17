"""Unit tests for StrategyExecutor."""
from decimal import Decimal

import pytest

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy, StrategyState
from src.pipeline.strategy_executor import StrategyExecutor, StrategyResult


class MockStrategy(Strategy):
    """Mock strategy for testing."""

    def __init__(self, strategy_id: str = "test-1", symbols: list[str] | None = None) -> None:
        super().__init__(strategy_id=strategy_id, symbols=symbols or ["BTC/USDC"])
        self._raise: Exception | None = None
        self._signal_to_return: Signal | None = None
        self._sleep_seconds: float = 0

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        if self._raise:
            raise self._raise
        if self._sleep_seconds > 0:
            import time
            time.sleep(self._sleep_seconds)
        return self._signal_to_return

    def on_position_closed(
        self,
        symbol: str,
        price: Decimal,
        exit_reason: str,
        grid_index: int | None = None,
    ) -> None:
        pass


class TestStrategyExecutor:
    """Tests for StrategyExecutor."""

    def _make_tick(self, symbol: str = "BTC/USDC", price: float = 67500.0) -> EnrichedTick:
        from datetime import UTC, datetime
        return EnrichedTick(
            symbol=symbol,
            price=Decimal(str(price)),
            volume=Decimal("100"),
            time=datetime.now(UTC),
            indicators={"rsi": 45.0},
        )

    @pytest.mark.asyncio
    async def test_execute_returns_result_with_no_signal(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert isinstance(result, StrategyResult)
        assert result.signal is None
        assert result.error is None
        assert result.strategy_id == "test-1"

    @pytest.mark.asyncio
    async def test_execute_returns_signal(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is not None
        assert result.signal.side == "BUY"
        assert result.signal.symbol == "BTC/USDC"

    @pytest.mark.asyncio
    async def test_execute_captures_error(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._raise = ValueError("Test error")
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.error is not None
        assert "Test error" in result.error
        assert result.signal is None

    @pytest.mark.asyncio
    async def test_execute_timeout(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._sleep_seconds = 2.0
        executor = StrategyExecutor(timeout_seconds=0.1)
        result = await executor.execute(strategy, self._make_tick())
        assert result.error is not None
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_execute_captures_stdout(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING

        def on_tick_with_print(tick: EnrichedTick) -> Signal | None:
            print("Hello from strategy")
            return None

        strategy.on_tick = on_tick_with_print
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert "Hello from strategy" in result.stdout

    @pytest.mark.asyncio
    async def test_execution_time_measured(self) -> None:
        strategy = MockStrategy()
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_strategy_not_running_returns_none(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.STOPPED
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is None
        assert result.error is None

    @pytest.mark.asyncio
    async def test_symbol_not_in_strategy_symbols(self) -> None:
        strategy = MockStrategy(symbols=["ETH/USDC"])
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick(symbol="BTC/USDC"))
        assert result.signal is None

    @pytest.mark.asyncio
    async def test_sell_signal_conversion(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.SELL,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is not None
        assert result.signal.side == "SELL"

    @pytest.mark.asyncio
    async def test_close_short_converted_to_buy(self) -> None:
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.CLOSE_SHORT,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is not None
        assert result.signal.side == "BUY"
