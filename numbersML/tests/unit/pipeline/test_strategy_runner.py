"""Unit tests for StrategyRunner."""
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy, StrategyState
from src.domain.strategies.signal import TradeSignal
from src.pipeline.strategy_runner import StrategyContext, StrategyRunner


class MockStrategy(Strategy):
    """Mock strategy for testing."""

    def __init__(self, strategy_id: str = "test-1", symbols: list[str] | None = None) -> None:
        super().__init__(strategy_id=strategy_id, symbols=symbols or ["BTC/USDC"])
        self._signal_to_return: Signal | None = None

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        return self._signal_to_return

    def on_position_closed(
        self,
        symbol: str,
        price: Decimal,
        exit_reason: str,
        grid_index: int | None = None,
    ) -> None:
        pass


class TestStrategyRunner:
    """Tests for StrategyRunner."""

    def _make_runner(self, market_service=None) -> StrategyRunner:
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        return StrategyRunner(
            db_pool=mock_pool,
            market_service=market_service,
            reload_interval=1.0,
        )

    def _make_tick_time(self) -> datetime:
        return datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_execute_no_active_strategies_returns_empty(self) -> None:
        runner = self._make_runner()
        signals = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert signals == []

    @pytest.mark.asyncio
    async def test_execute_single_strategy_returns_signal(self) -> None:
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        ctx = StrategyContext(
            strategy_id=uuid4(),
            strategy_name="TestStrategy",
            strategy=strategy,
            symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        signals = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert len(signals) == 1
        assert signals[0].side == "BUY"
        assert signals[0].symbol == "BTC/USDC"

    @pytest.mark.asyncio
    async def test_execute_multiple_strategies_in_parallel(self) -> None:
        runner = self._make_runner()

        for i in range(3):
            strategy = MockStrategy(strategy_id=f"test-{i}")
            strategy._state = StrategyState.RUNNING
            strategy._signal_to_return = Signal(
                strategy_id=f"test-{i}",
                symbol="BTC/USDC",
                signal_type=SignalType.BUY,
                price=Decimal("67500"),
                metadata={"quantity": Decimal("0.001")},
            )
            ctx = StrategyContext(
                strategy_id=uuid4(),
                strategy_name=f"Strategy{i}",
                strategy=strategy,
                symbols=["BTC/USDC"],
            )
            runner._strategies[ctx.strategy_id] = ctx

        signals = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert len(signals) == 3

    @pytest.mark.asyncio
    async def test_strategy_failure_does_not_crash_others(self) -> None:
        runner = self._make_runner()

        # Strategy A raises
        strategy_a = MockStrategy(strategy_id="test-a")
        strategy_a._signal_to_return = None

        class FailingStrategy(Strategy):
            def __init__(self) -> None:
                super().__init__(strategy_id="test-fail", symbols=["BTC/USDC"])

            def on_tick(self, tick: EnrichedTick) -> Signal | None:
                raise RuntimeError("Intentional failure")

            def on_position_closed(
                self,
                symbol: str,
                price: Decimal,
                exit_reason: str,
                grid_index: int | None = None,
            ) -> None:
                pass

        # Strategy B works
        strategy_b = MockStrategy(strategy_id="test-b")
        strategy_b._state = StrategyState.RUNNING
        strategy_b._signal_to_return = Signal(
            strategy_id="test-b",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )

        ctx_a = StrategyContext(
            strategy_id=uuid4(),
            strategy_name="StrategyA",
            strategy=strategy_a,
            symbols=["BTC/USDC"],
        )
        ctx_fail = StrategyContext(
            strategy_id=uuid4(),
            strategy_name="FailingStrategy",
            strategy=FailingStrategy(),
            symbols=["BTC/USDC"],
        )
        ctx_b = StrategyContext(
            strategy_id=uuid4(),
            strategy_name="StrategyB",
            strategy=strategy_b,
            symbols=["BTC/USDC"],
        )
        runner._strategies[ctx_a.strategy_id] = ctx_a
        runner._strategies[ctx_fail.strategy_id] = ctx_fail
        runner._strategies[ctx_b.strategy_id] = ctx_b

        signals = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        # At least strategy B's signal should be present
        assert any(s.side == "BUY" for s in signals)

    @pytest.mark.asyncio
    async def test_inactive_strategy_not_executed(self) -> None:
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        ctx = StrategyContext(
            strategy_id=uuid4(),
            strategy_name="TestStrategy",
            strategy=strategy,
            symbols=["BTC/USDC"],
            is_active=False,
        )
        runner._strategies[ctx.strategy_id] = ctx

        signals = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert signals == []

    @pytest.mark.asyncio
    async def test_signal_deduplication(self) -> None:
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        # Use a valid UUID for strategy_id so dedup works
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid),
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        ctx = StrategyContext(
            strategy_id=fixed_sid,
            strategy_name="TestStrategy",
            strategy=strategy,
            symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        # First tick
        signals1 = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert len(signals1) == 1

        # Second tick immediately (within dedup window)
        signals2 = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert len(signals2) == 0  # Deduplicated

    @pytest.mark.asyncio
    async def test_market_order_signal_has_no_price(self) -> None:
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001"), "order_type": "MARKET"},
        )
        ctx = StrategyContext(
            strategy_id=uuid4(),
            strategy_name="TestStrategy",
            strategy=strategy,
            symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        signals = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert len(signals) == 1
        assert signals[0].order_type == "MARKET"

    @pytest.mark.asyncio
    async def test_limit_order_signal_has_price(self) -> None:
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={
                "quantity": Decimal("0.001"),
                "order_type": "LIMIT",
                "price": Decimal("67000"),
            },
        )
        ctx = StrategyContext(
            strategy_id=uuid4(),
            strategy_name="TestStrategy",
            strategy=strategy,
            symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        signals = await runner.execute_tick(
            symbol="BTC/USDC",
            candle_time=self._make_tick_time(),
            tick_indicators={},
            current_price=Decimal("67500"),
        )
        assert len(signals) == 1
        assert signals[0].order_type == "LIMIT"
        assert signals[0].price == Decimal("67000")

    @pytest.mark.asyncio
    async def test_signal_persisted_to_db(self) -> None:
        mock_conn = AsyncMock()
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=acm)

        runner = StrategyRunner(db_pool=mock_pool, reload_interval=1.0)

        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="TestStrategy",
            symbol="BTC/USDC",
            side="BUY",
            quantity=Decimal("0.001"),
        )
        await runner._persist_signal(signal)
        assert mock_conn.execute.called

    def test_stdout_capture_and_retrieve(self) -> None:
        runner = self._make_runner()
        sid = uuid4()
        ctx = StrategyContext(
            strategy_id=sid,
            strategy_name="TestStrategy",
            strategy=MockStrategy(),
        )
        ctx.stdout_buffer = [f"Line {i}" for i in range(50)]
        runner._strategies[sid] = ctx

        lines = runner.get_stdout(sid, limit=10)
        assert len(lines) == 10
        assert lines[0] == "Line 40"

    def test_clear_stdout(self) -> None:
        runner = self._make_runner()
        sid = uuid4()
        ctx = StrategyContext(
            strategy_id=sid,
            strategy_name="TestStrategy",
            strategy=MockStrategy(),
        )
        ctx.stdout_buffer = ["Line 1", "Line 2"]
        runner._strategies[sid] = ctx

        runner.clear_stdout(sid)
        assert runner.get_stdout(sid) == []

    def test_get_recent_signals(self) -> None:
        runner = self._make_runner()
        sid = uuid4()
        signals = [
            TradeSignal(strategy_id=sid, symbol="BTC/USDC", side="BUY"),
            TradeSignal(strategy_id=sid, symbol="ETH/USDC", side="SELL"),
            TradeSignal(strategy_id=uuid4(), symbol="BTC/USDC", side="BUY"),
        ]
        runner._signal_history = signals

        # Filter by strategy
        result = runner.get_recent_signals(strategy_id=sid)
        assert len(result) == 2

        # Filter by symbol
        result = runner.get_recent_signals(symbol="BTC/USDC")
        assert len(result) == 2

        # Limit
        result = runner.get_recent_signals(limit=1)
        assert len(result) == 1

    def test_get_stats(self) -> None:
        runner = self._make_runner()
        sid = uuid4()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        ctx = StrategyContext(
            strategy_id=sid,
            strategy_name="TestStrategy",
            strategy=strategy,
        )
        ctx.signals_today = 5
        runner._strategies[sid] = ctx
        runner._tick_count = 100

        stats = runner.get_stats()
        assert stats["active_strategies"] == 1
        assert stats["tick_count"] == 100
        assert any(
            v["name"] == "TestStrategy" for v in stats["strategies"].values()
        )

    @pytest.mark.asyncio
    async def test_no_market_service_rejects_signal(self) -> None:
        runner = self._make_runner(market_service=None)
        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="Test",
            symbol="BTC/USDC",
            side="BUY",
            quantity=Decimal("0.001"),
        )
        await runner._route_signal(signal)
        assert runner._stats["signals_rejected"] == 1

    @pytest.mark.asyncio
    async def test_market_service_executes_signal(self) -> None:
        mock_market = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_market.place_order.return_value = mock_order

        runner = self._make_runner(market_service=mock_market)
        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="Test",
            symbol="BTC/USDC",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.001"),
        )
        await runner._route_signal(signal)
        assert mock_market.place_order.called
        assert runner._stats["signals_executed"] == 1
