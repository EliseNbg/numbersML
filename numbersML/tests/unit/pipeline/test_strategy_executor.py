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

    @pytest.mark.asyncio
    async def test_market_buy_signal_has_price_from_signal_price(self) -> None:
        """MARKET BUY: TradeSignal.price comes from Signal.price (not metadata)."""
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
        assert result.signal.price == Decimal("67500")
        assert result.signal.order_type == "MARKET"

    @pytest.mark.asyncio
    async def test_market_sell_signal_has_price_from_signal_price(self) -> None:
        """MARKET SELL: TradeSignal.price comes from Signal.price (not metadata)."""
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
        assert result.signal.price == Decimal("67500")
        assert result.signal.order_type == "MARKET"

    @pytest.mark.asyncio
    async def test_market_signal_price_from_metadata_takes_precedence(self) -> None:
        """When metadata has 'price', it overrides Signal.price."""
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67500"),
            metadata={"price": Decimal("68000"), "quantity": Decimal("0.001")},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is not None
        assert result.signal.price == Decimal("68000")

    @pytest.mark.asyncio
    async def test_market_buy_signal_has_market_price_in_metadata_after_routing(self) -> None:
        """Simulate the routing path: MARKET buy must have market_price in metadata."""
        from src.domain.market.order import OrderRequest, OrderSide, OrderType

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

        # Replicate _route_signal logic
        signal = result.signal
        metadata = dict(signal.metadata)
        if signal.order_type.upper() == "MARKET" and signal.price is not None:
            metadata.setdefault("market_price", float(signal.price))

        order_request = OrderRequest(
            symbol=signal.symbol,
            side=OrderSide(signal.side),
            order_type=OrderType(signal.order_type),
            quantity=signal.quantity,
            limit_price=signal.price,
            client_order_id=str(signal.signal_id),
            metadata=metadata,
        )

        assert "market_price" in order_request.metadata
        assert order_request.metadata["market_price"] == 67500.0

    @pytest.mark.asyncio
    async def test_market_sell_signal_has_market_price_in_metadata_after_routing(self) -> None:
        """Simulate the routing path: MARKET sell must have market_price in metadata."""
        from src.domain.market.order import OrderRequest, OrderSide, OrderType

        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.SELL,
            price=Decimal("68000"),
            metadata={"quantity": Decimal("0.001")},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is not None

        # Replicate _route_signal logic
        signal = result.signal
        metadata = dict(signal.metadata)
        if signal.order_type.upper() == "MARKET" and signal.price is not None:
            metadata.setdefault("market_price", float(signal.price))

        order_request = OrderRequest(
            symbol=signal.symbol,
            side=OrderSide(signal.side),
            order_type=OrderType(signal.order_type),
            quantity=signal.quantity,
            limit_price=signal.price,
            client_order_id=str(signal.signal_id),
            metadata=metadata,
        )

        assert "market_price" in order_request.metadata
        assert order_request.metadata["market_price"] == 68000.0

    @pytest.mark.asyncio
    async def test_limit_buy_signal_has_price(self) -> None:
        """LIMIT BUY: TradeSignal.price comes from Signal.price."""
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("67000"),
            metadata={"quantity": Decimal("0.001"), "order_type": "LIMIT"},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is not None
        assert result.signal.price == Decimal("67000")
        assert result.signal.order_type == "LIMIT"

    @pytest.mark.asyncio
    async def test_limit_sell_signal_has_price(self) -> None:
        """LIMIT SELL: TradeSignal.price comes from Signal.price."""
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.SELL,
            price=Decimal("68000"),
            metadata={"quantity": Decimal("0.001"), "order_type": "LIMIT"},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick())
        assert result.signal is not None
        assert result.signal.price == Decimal("68000")
        assert result.signal.order_type == "LIMIT"
        assert result.signal.side == "SELL"

    @pytest.mark.asyncio
    async def test_quantity_computed_from_quantity_usdc(self) -> None:
        """quantity_usdc in metadata is divided by price to get token quantity."""
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("50000"),
            metadata={"quantity_usdc": 100, "expected_profit_price": 52000},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick(price=50000))
        assert result.signal is not None
        assert result.signal.quantity == Decimal("0.002")  # 100 / 50000

    @pytest.mark.asyncio
    async def test_quantity_key_takes_precedence_over_quantity_usdc(self) -> None:
        """When both quantity and quantity_usdc are in metadata, quantity wins."""
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("50000"),
            metadata={"quantity": Decimal("0.005"), "quantity_usdc": 100},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick(price=50000))
        assert result.signal is not None
        assert result.signal.quantity == Decimal("0.005")  # explicit quantity wins

    @pytest.mark.asyncio
    async def test_quantity_defaults_to_zero(self) -> None:
        """Without quantity or quantity_usdc, quantity is 0."""
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("50000"),
            metadata={},
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick(price=50000))
        assert result.signal is not None
        assert result.signal.quantity == Decimal("0")

    @pytest.mark.asyncio
    async def test_quantity_from_metadata_used_when_present(self) -> None:
        """quantity in metadata is used as the TradeSignal quantity."""
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = Signal(
            strategy_id="test-1",
            symbol="BTC/USDC",
            signal_type=SignalType.SELL,
            price=Decimal("55000"),
            metadata={
                "quantity": Decimal("0.5"),
                "reason": "take_profit",
                "entry_price": 50000.0,
                "pnl": 2500.0,
                "pnl_percent": 10.0,
            },
        )
        executor = StrategyExecutor(timeout_seconds=1.0)
        result = await executor.execute(strategy, self._make_tick(price=55000))
        assert result.signal is not None
        assert result.signal.quantity == Decimal("0.5")
        assert result.signal.side == "SELL"
        assert result.signal.price == Decimal("55000")
