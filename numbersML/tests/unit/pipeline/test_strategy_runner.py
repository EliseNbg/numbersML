"""Unit tests for StrategyRunner."""
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domain.strategies.base import (
    EnrichedTick,
    Signal,
    SignalType,
    Strategy,
    StrategyState,
    get_price_statistics,
    reset_price_statistics,
)
from src.domain.strategies.signal import TradeSignal
from src.infrastructure.market.paper_market_service import PaperMarketService
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

    def _make_context(
        self,
        strategy_id,
        strategy,
        symbols=None,
        is_active=True,
    ) -> StrategyContext:
        return StrategyContext(
            strategy_id=strategy_id,
            strategy_name="TestStrategy",
            strategy=strategy,
            symbols=symbols or ["BTC/USDC"],
            is_active=is_active,
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

    @pytest.mark.asyncio
    async def test_signal_persisted_with_json_serialized_metadata(self) -> None:
        """Metadata dict must be JSON-serialized before passing to asyncpg."""
        import json

        mock_conn = AsyncMock()
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=acm)

        runner = StrategyRunner(db_pool=mock_pool, reload_interval=1.0)

        metadata = {
            "macd": -0.004310119062817641,
            "signal": -0.0043,
            "histogram": -0.0001,
            "reversal_type": "decline_to_uptrend",
            "signal_count": 1,
        }
        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="TestStrategy",
            symbol="ATOM/USDC",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("1.982"),
            metadata=metadata,
        )
        await runner._persist_signal(signal)

        # Verify conn.execute was called with JSON-string metadata (not raw dict)
        call_args = mock_conn.execute.call_args
        assert call_args is not None
        sql, *params = call_args[0]
        # $9 is the metadata parameter (0-indexed: params[8])
        metadata_param = params[8]
        assert isinstance(metadata_param, str), (
            f"Expected metadata as JSON string, got {type(metadata_param).__name__}"
        )
        assert json.loads(metadata_param) == metadata

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

    @pytest.mark.asyncio
    async def test_route_signal_rejects_zero_quantity(self) -> None:
        """Signal with quantity 0 is rejected without calling market_service."""
        mock_market = AsyncMock()
        runner = self._make_runner(market_service=mock_market)
        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="Test",
            symbol="BTC/USDC",
            side="SELL",
            order_type="MARKET",
            quantity=Decimal("0"),
            price=Decimal("50000"),
        )
        await runner._route_signal(signal)
        assert runner._stats["signals_rejected"] == 1
        assert mock_market.place_order.call_count == 0

    async def test_route_signal_rejects_negative_quantity(self) -> None:
        """Signal with negative quantity is rejected."""
        mock_market = AsyncMock()
        runner = self._make_runner(market_service=mock_market)
        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="Test",
            symbol="BTC/USDC",
            side="SELL",
            order_type="MARKET",
            quantity=Decimal("-1"),
            price=Decimal("50000"),
        )
        await runner._route_signal(signal)
        assert runner._stats["signals_rejected"] == 1
        assert mock_market.place_order.call_count == 0

    async def test_route_signal_adds_market_price_for_market_orders(self) -> None:
        """market_price is injected into metadata for MARKET order signals."""
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
            price=Decimal("50000"),
        )
        await runner._route_signal(signal)
        call_kwargs = mock_market.place_order.call_args[0][0]
        assert call_kwargs.metadata.get("market_price") == 50000.0

    @pytest.mark.asyncio
    async def test_paper_market_service_executes_market_signal(self) -> None:
        """Signal is filled by PaperMarketService and persisted as EXECUTED."""
        paper = PaperMarketService(initial_balance=Decimal("10000"))
        runner = self._make_runner(market_service=paper)
        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="Test",
            symbol="BTC/USDC",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("1"),
            price=Decimal("100"),
        )
        await runner._route_signal(signal)
        assert runner._stats["signals_executed"] == 1
        # Balance should reflect the paper fill
        balance = await paper.get_balance("USDC")
        assert balance.free < Decimal("10000")

    @pytest.mark.asyncio
    async def test_paper_market_service_rejects_signal_on_insufficient_balance(self) -> None:
        """Signal is failed when paper balance is insufficient."""
        paper = PaperMarketService(initial_balance=Decimal("1"))
        runner = self._make_runner(market_service=paper)
        signal = TradeSignal(
            strategy_id=uuid4(),
            strategy_name="Test",
            symbol="BTC/USDC",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("1"),
            price=Decimal("100"),
        )
        await runner._route_signal(signal)
        assert runner._stats["signals_failed"] == 1
        assert runner._stats["signals_executed"] == 0

    def _make_fetch_mock(self, rows: list[dict]) -> tuple[AsyncMock, MagicMock]:
        """Create a mocked DB pool that returns given rows on fetch."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=rows)
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=acm)
        return mock_conn, pool

    @pytest.mark.asyncio
    async def test_load_strategy_with_json_string_config_parses(self) -> None:
        """String config is parsed as JSON before accessing config.get()."""
        import json

        runner = self._make_runner()
        sid = uuid4()

        _, pool = self._make_fetch_mock([
            {
                "id": sid,
                "name": "TestStrategy",
                "mode": "paper",
                "status": "active",
                "class_path": "tests.unit.pipeline.test_strategy_runner.MockStrategy",
                "config": json.dumps({"universe": {"symbols": ["BTC/USDC"]}}),
            },
        ])
        runner.db_pool = pool

        strategies = await runner._load_active_strategies()
        assert len(strategies) == 1
        ctx = strategies[sid]
        assert ctx.symbols == ["BTC/USDC"]

    @pytest.mark.asyncio
    async def test_load_strategy_with_string_config_skips_on_invalid_json(self) -> None:
        """Invalid JSON string config is rejected and skipped."""
        runner = self._make_runner()
        sid = uuid4()

        _, pool = self._make_fetch_mock([
            {
                "id": sid,
                "name": "TestStrategy",
                "mode": "paper",
                "status": "active",
                "class_path": "tests.unit.pipeline.test_strategy_runner.MockStrategy",
                "config": "{invalid json}",
            },
        ])
        runner.db_pool = pool

        strategies = await runner._load_active_strategies()
        assert len(strategies) == 0

    @pytest.mark.asyncio
    async def test_hot_reload_debounces_after_failure(self) -> None:
        """hot_reload skips reload if a failure happened less than 30s ago."""
        runner = self._make_runner()
        runner._last_failed_reload = time.time() - 5.0  # 5 seconds ago

        # Should skip because _last_failed_reload is within 30s
        await runner.hot_reload()
        # _last_reload should NOT have been updated
        assert runner._last_reload == 0.0

    @pytest.mark.asyncio
    async def test_hot_plug_adds_new_strategy(self) -> None:
        """A strategy newly appearing in the DB is hot-loaded and started."""
        runner = self._make_runner()
        sid = uuid4()

        _, pool = self._make_fetch_mock([
            {
                "id": sid,
                "name": "HotPlugStrategy",
                "mode": "paper",
                "status": "active",
                "class_path": "tests.unit.pipeline.test_strategy_runner.MockStrategy",
                "config": {"symbols": ["BTC/USDC"]},
            },
        ])
        runner.db_pool = pool

        await runner.hot_reload()

        assert sid in runner._strategies
        ctx = runner._strategies[sid]
        assert ctx.is_active is True
        assert ctx.strategy_name == "HotPlugStrategy"
        assert ctx.mode == "paper"

    @pytest.mark.asyncio
    async def test_hot_unplug_removes_and_stops_strategy(self) -> None:
        """A strategy removed from the DB is stopped and deactivated."""
        runner = self._make_runner()
        sid = uuid4()
        strategy = MockStrategy()
        strategy.stop = AsyncMock()  # spy on stop()

        # Setup: strategy is currently active
        ctx = self._make_context(sid, strategy)
        runner._strategies[sid] = ctx

        # DB returns empty
        _, pool = self._make_fetch_mock([])
        runner.db_pool = pool

        await runner.hot_reload()

        assert sid not in runner._strategies
        strategy.stop.assert_awaited_once()
        assert ctx.is_active is False

    @pytest.mark.asyncio
    async def test_hot_reload_no_change_leaves_strategies(self) -> None:
        """hot_reload does nothing when DB matches current strategies."""
        runner = self._make_runner()
        sid = uuid4()
        strategy = MockStrategy()
        strategy.stop = AsyncMock()

        ctx = self._make_context(sid, strategy)
        runner._strategies[sid] = ctx

        # DB returns the same strategy
        _, pool = self._make_fetch_mock([
            {
                "id": sid,
                "name": "TestStrategy",
                "mode": "paper",
                "status": "active",
                "class_path": "tests.unit.pipeline.test_strategy_runner.MockStrategy",
                "config": {"symbols": ["BTC/USDC"]},
            },
        ])
        runner.db_pool = pool

        await runner.hot_reload()

        assert sid in runner._strategies
        strategy.stop.assert_not_called()  # was NOT stopped
        assert ctx.is_active is True

    @pytest.mark.asyncio
    async def test_preload_price_statistics_fetches_from_binance_when_db_empty(self) -> None:
        """When the DB has < 3600 candles, Binance fallback loads price stats."""
        reset_price_statistics()

        now = datetime.now(UTC)
        # 7 days of 1-minute mock klines in ascending time order (oldest first),
        # matching _fetch_binance_klines_to_prices output — recent prices lower
        # than older ones so day average ≠ week average
        mock_prices: list[tuple[datetime, Decimal]] = []
        for i in range(10080):
            t = now - timedelta(minutes=10079 - i)  # oldest first
            if i < 10080 - 1440:
                p = Decimal("2.08")  # older prices
            else:
                p = Decimal("2.03")  # last 24h
            mock_prices.append((t, p))

        runner = self._make_runner()

        # Pre-populate a strategy so all_symbols is non-empty
        strategy = MockStrategy(strategy_id="test-atom", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = None
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        # Bypass hot_reload (already populated strategies) and reset prices
        runner._last_reload = time.time()
        runner._prices_preloaded = False

        # Mock DB query to return 0 rows from candles_1s
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        runner.db_pool.acquire = MagicMock(return_value=acm)

        with patch.object(
            runner, "_fetch_binance_klines_to_prices",
            new=AsyncMock(return_value=mock_prices),
        ) as mock_fetch:
            _ = await runner.execute_tick(
                symbol="ATOM/USDC",
                candle_time=now,
                tick_indicators={"sma_800": 2.055},
                current_price=Decimal("2.05"),
            )

        # Binance was called with the right symbol (2nd positional arg)
        mock_fetch.assert_called_once()
        args, _ = mock_fetch.call_args
        assert args[1] == "ATOMUSDC"

        # Price statistics have data loaded
        stats = get_price_statistics()
        avg_day = stats.get_avg_price("ATOM/USDC", "day")
        avg_week = stats.get_avg_price("ATOM/USDC", "week")
        assert avg_day > 0
        assert avg_week > 0
        # With 7 days of data, day and week should differ
        assert avg_day != avg_week

        # Preload flag is set so second tick doesn't re-trigger
        assert runner._prices_preloaded is True

        reset_price_statistics()

    @pytest.mark.asyncio
    async def test_preload_price_statistics_uses_db_when_enough_data(self) -> None:
        """When the DB has >= 3600 candles, Binance fallback is skipped."""
        reset_price_statistics()

        now = datetime.now(UTC)
        # 4000 rows (above 3600 threshold)
        db_rows = [
            {
                "symbol": "ATOM/USDC",
                "time": now - timedelta(seconds=i),
                "close": "2.05",
            }
            for i in range(4000)
        ]

        runner = self._make_runner()

        # Pre-populate strategy
        strategy = MockStrategy(strategy_id="test-atom", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        strategy._signal_to_return = None
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        runner._last_reload = time.time()
        runner._prices_preloaded = False

        # Mock DB query to return 4000 rows
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=db_rows)
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        runner.db_pool.acquire = MagicMock(return_value=acm)

        with patch.object(
            runner, "_fetch_binance_klines_to_prices",
            new=AsyncMock(return_value=[]),
        ) as mock_fetch:
            _ = await runner.execute_tick(
                symbol="ATOM/USDC",
                candle_time=now,
                tick_indicators={"sma_800": 2.055},
                current_price=Decimal("2.05"),
            )

        # Binance was NOT called — DB had enough data
        mock_fetch.assert_not_called()

        # Price statistics loaded from DB data
        stats = get_price_statistics()
        avg = stats.get_avg_price("ATOM/USDC", "day")
        assert avg == Decimal("2.05")

        reset_price_statistics()

    @pytest.mark.asyncio
    async def test_route_buy_signal_opens_position_with_take_profit(self) -> None:
        """Filled BUY opens a strategy position with take_profit from metadata."""
        paper = PaperMarketService(initial_balance=Decimal("10000"))
        runner = self._make_runner(market_service=paper)

        strategy = MockStrategy(strategy_id="tp-test", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid),
            strategy_name="MockStrategy",
            symbol="ATOM/USDC",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("10"),
            price=Decimal("2.03"),
            metadata={"expected_profit_price": 2.08},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is not None
        assert pos.side == "LONG"
        assert pos.entry_price == Decimal("2.03")
        assert pos.take_profit_price == Decimal("2.08")

    @pytest.mark.asyncio
    async def test_route_buy_signal_opens_position_without_take_profit(self) -> None:
        """Filled BUY without take_profit opens position with TP=None."""
        paper = PaperMarketService(initial_balance=Decimal("10000"))
        runner = self._make_runner(market_service=paper)

        strategy = MockStrategy(strategy_id="no-tp-test", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid),
            strategy_name="MockStrategy",
            symbol="ATOM/USDC",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("10"),
            price=Decimal("2.03"),
            metadata={},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is not None
        assert pos.side == "LONG"
        assert pos.take_profit_price is None

    @pytest.mark.asyncio
    async def test_route_sell_signal_does_not_open_position(self) -> None:
        """Filled SELL does not open a new position."""
        paper = PaperMarketService(initial_balance=Decimal("10000"))
        runner = self._make_runner(market_service=paper)

        strategy = MockStrategy(strategy_id="sell-test", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid),
            strategy_name="MockStrategy",
            symbol="ATOM/USDC",
            side="SELL",
            order_type="MARKET",
            quantity=Decimal("10"),
            price=Decimal("2.03"),
            metadata={},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is None

    @pytest.mark.asyncio
    async def test_route_signal_does_not_open_position_on_rejected(self) -> None:
        """When the market service rejects, no position is opened."""
        paper = PaperMarketService(initial_balance=Decimal("1"))  # very low balance
        runner = self._make_runner(market_service=paper)

        strategy = MockStrategy(strategy_id="reject-test", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid),
            strategy_name="MockStrategy",
            symbol="ATOM/USDC",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("10"),
            price=Decimal("2.03"),
            metadata={"expected_profit_price": 2.08},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is None
        assert runner._stats["signals_failed"] == 1

    @pytest.mark.asyncio
    async def test_route_limit_buy_signal_opens_position_with_take_profit(self) -> None:
        """Filled LIMIT BUY opens a strategy position with take_profit."""
        paper = PaperMarketService(initial_balance=Decimal("10000"))
        runner = self._make_runner(market_service=paper)

        strategy = MockStrategy(strategy_id="limit-tp-test", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid),
            strategy_name="MockStrategy",
            symbol="ATOM/USDC",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("10"),
            price=Decimal("2.01"),
            metadata={"expected_profit_price": 2.06},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is not None
        assert pos.side == "LONG"
        assert pos.entry_price == Decimal("2.01")
        assert pos.take_profit_price == Decimal("2.06")

    @pytest.mark.asyncio
    async def test_route_limit_sell_signal_does_not_open_position(self) -> None:
        """Filled LIMIT SELL does not open a new position."""
        paper = PaperMarketService(initial_balance=Decimal("10000"))
        runner = self._make_runner(market_service=paper)

        strategy = MockStrategy(strategy_id="limit-sell-test", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = self._make_context(sid, strategy, symbols=["ATOM/USDC"])
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid),
            strategy_name="MockStrategy",
            symbol="ATOM/USDC",
            side="SELL",
            order_type="LIMIT",
            quantity=Decimal("10"),
            price=Decimal("2.05"),
            metadata={},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is None

    # ── Comprehensive dedup tests ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_dedup_same_signal_on_three_consecutive_ticks(self) -> None:
        """Only the first of three identical signals within the window passes dedup."""
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
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

        s1 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(s1) == 1
        s2 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(s2) == 0, "2nd consecutive duplicate should be deduped"
        s3 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(s3) == 0, "3rd consecutive duplicate should be deduped"

    @pytest.mark.asyncio
    async def test_dedup_different_symbol_not_duplicate(self) -> None:
        """Same strategy, same side, different symbols → both pass dedup."""
        runner = self._make_runner()
        strategy = MockStrategy(strategy_id="multi-sym", symbols=["BTC/USDC", "ETH/USDC"])
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        ctx = StrategyContext(
            strategy_id=fixed_sid,
            strategy_name="MultiSymbol",
            strategy=strategy,
            symbols=["BTC/USDC", "ETH/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.BUY, price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        s1 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(s1) == 1

        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="ETH/USDC",
            signal_type=SignalType.BUY, price=Decimal("3200"),
            metadata={"quantity": Decimal("0.1")},
        )
        s2 = await runner.execute_tick(
            symbol="ETH/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("3200"),
        )
        assert len(s2) == 1, "Different symbol should NOT be deduped"

    @pytest.mark.asyncio
    async def test_dedup_different_side_not_duplicate(self) -> None:
        """Same strategy, same symbol, different sides → both pass dedup."""
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        ctx = StrategyContext(
            strategy_id=fixed_sid,
            strategy_name="TestStrategy",
            strategy=strategy,
            symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.BUY, price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        s1 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(s1) == 1

        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.SELL, price=Decimal("68000"),
            metadata={"quantity": Decimal("0.001")},
        )
        s2 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("68000"),
        )
        assert len(s2) == 1, "Different side (SELL vs BUY) should NOT be deduped"

    @pytest.mark.asyncio
    async def test_dedup_different_strategy_not_duplicate(self) -> None:
        """Different strategies, same symbol, same side → both pass dedup."""
        runner = self._make_runner()
        for i in range(2):
            strategy = MockStrategy(strategy_id=f"strat-{i}")
            strategy._state = StrategyState.RUNNING
            sid = uuid4()
            strategy._strategy_id = str(sid)
            strategy._signal_to_return = Signal(
                strategy_id=str(sid), symbol="BTC/USDC",
                signal_type=SignalType.BUY, price=Decimal("67500"),
                metadata={"quantity": Decimal("0.001")},
            )
            ctx = StrategyContext(
                strategy_id=sid, strategy_name=f"Strategy{i}",
                strategy=strategy, symbols=["BTC/USDC"],
            )
            runner._strategies[sid] = ctx

        signals = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(signals) == 2, "Two different strategies should both emit"

    @pytest.mark.asyncio
    async def test_dedup_outside_window_allows_signal(self) -> None:
        """Same signal past the dedup window passes."""
        runner = self._make_runner()
        runner.dedup_window_seconds = 60
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.BUY, price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        ctx = StrategyContext(
            strategy_id=fixed_sid, strategy_name="TestStrategy",
            strategy=strategy, symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        s1 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(s1) == 1

        # Manually age the signal history out of the window
        runner._signal_history[0] = TradeSignal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC", side="BUY",
            timestamp=datetime.now(UTC) - timedelta(seconds=120),
        )

        s2 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(s2) == 1, "Signal outside dedup window should NOT be deduped"

    @pytest.mark.asyncio
    async def test_dedup_stats_tracked_correctly(self) -> None:
        """Dedup count and signals_emitted count are tracked correctly."""
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.BUY, price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        ctx = StrategyContext(
            strategy_id=fixed_sid, strategy_name="TestStrategy",
            strategy=strategy, symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        assert runner._stats["deduplicated"] == 0
        assert runner._stats["signals_emitted"] == 0

        await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert runner._stats["signals_emitted"] == 1
        assert runner._stats["deduplicated"] == 0

        await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert runner._stats["signals_emitted"] == 1
        assert runner._stats["deduplicated"] == 1

        await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert runner._stats["signals_emitted"] == 1
        assert runner._stats["deduplicated"] == 2

    @pytest.mark.asyncio
    async def test_dedup_strategy_context_updated_only_on_emit(self) -> None:
        """signals_today and last_signal_at update only on emit, not on dedup."""
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        signal = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.BUY, price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        strategy._signal_to_return = signal
        ctx = StrategyContext(
            strategy_id=fixed_sid, strategy_name="TestStrategy",
            strategy=strategy, symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx
        assert ctx.signals_today == 0

        await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert ctx.signals_today == 1

        await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert ctx.signals_today == 1, "signals_today should NOT increment on dedup"

    @pytest.mark.asyncio
    async def test_dedup_signal_history_pruned_at_max(self) -> None:
        """Signal history pruned to max_signal_history, keeping most recent."""
        runner = self._make_runner()
        runner._max_signal_history = 3

        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        ctx = StrategyContext(
            strategy_id=fixed_sid, strategy_name="TestStrategy",
            strategy=strategy, symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        prices = [Decimal("100"), Decimal("200"), Decimal("300"), Decimal("400")]
        for p in prices:
            strategy._signal_to_return = Signal(
                strategy_id=str(fixed_sid), symbol="BTC/USDC",
                signal_type=SignalType.BUY, price=p,
                metadata={"quantity": Decimal("0.001")},
            )
            await runner.execute_tick(
                symbol="BTC/USDC", candle_time=self._make_tick_time(),
                tick_indicators={}, current_price=p,
            )

        assert len(runner._signal_history) == 3, "History should be pruned to max=3"
        assert runner._signal_history[-1].price == Decimal("400"), "Most recent should be last"

    @pytest.mark.asyncio
    async def test_dedup_signal_with_no_history_passes(self) -> None:
        """When signal_history is empty, any signal passes dedup."""
        runner = self._make_runner()
        assert runner._signal_history == []

        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.BUY, price=Decimal("67500"),
            metadata={"quantity": Decimal("0.001")},
        )
        ctx = StrategyContext(
            strategy_id=fixed_sid, strategy_name="TestStrategy",
            strategy=strategy, symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        signals = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("67500"),
        )
        assert len(signals) == 1, "First signal should always pass"

    @pytest.mark.asyncio
    async def test_dedup_buy_and_sell_from_same_strategy_both_emitted(self) -> None:
        """BUY and SELL signals from same strategy on same symbol both emit (different side)."""
        runner = self._make_runner()
        strategy = MockStrategy()
        strategy._state = StrategyState.RUNNING
        fixed_sid = uuid4()
        strategy._strategy_id = str(fixed_sid)
        # Same strategy returns BUY first, SELL next (different on_tick logic)
        ctx = StrategyContext(
            strategy_id=fixed_sid, strategy_name="TestStrategy",
            strategy=strategy, symbols=["BTC/USDC"],
        )
        runner._strategies[ctx.strategy_id] = ctx

        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.BUY, price=Decimal("100"),
            metadata={"quantity": Decimal("0.001")},
        )
        s1 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("100"),
        )
        assert len(s1) == 1 and s1[0].side == "BUY"

        strategy._signal_to_return = Signal(
            strategy_id=str(fixed_sid), symbol="BTC/USDC",
            signal_type=SignalType.SELL, price=Decimal("110"),
            metadata={"quantity": Decimal("0.001")},
        )
        s2 = await runner.execute_tick(
            symbol="BTC/USDC", candle_time=self._make_tick_time(),
            tick_indicators={}, current_price=Decimal("110"),
        )
        assert len(s2) == 1 and s2[0].side == "SELL", "SELL after BUY should emit"

    # ── Persist failure / position opening edge cases ─────────────────────────

    @pytest.mark.asyncio
    async def test_persist_failure_still_opens_position(self) -> None:
        """When _persist_signal throws (e.g. table missing), position still opens."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            side_effect=Exception("relation \"strategy_signals\" does not exist"),
        )
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=acm)

        paper = PaperMarketService(initial_balance=Decimal("10000"))
        runner = StrategyRunner(db_pool=mock_pool, market_service=paper, reload_interval=1.0)

        strategy = MockStrategy(strategy_id="persist-fail-test", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = StrategyContext(
            strategy_id=sid, strategy_name="MockStrategy",
            strategy=strategy, symbols=["ATOM/USDC"],
        )
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid), strategy_name="MockStrategy",
            symbol="ATOM/USDC", side="BUY", order_type="MARKET",
            quantity=Decimal("10"), price=Decimal("2.03"),
            metadata={"expected_profit_price": 2.08},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is not None, "Position should open even when persist fails"
        assert pos.side == "LONG"
        assert pos.take_profit_price == Decimal("2.08")

    @pytest.mark.asyncio
    async def test_persist_and_order_failure_leaves_no_position(self) -> None:
        """When order is rejected (insufficient balance) AND persist also fails, no position."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("DB error"))
        acm = AsyncMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=acm)

        paper = PaperMarketService(initial_balance=Decimal("1"))
        runner = StrategyRunner(db_pool=mock_pool, market_service=paper, reload_interval=1.0)

        strategy = MockStrategy(strategy_id="reject-persist-fail", symbols=["ATOM/USDC"])
        strategy._state = StrategyState.RUNNING
        sid = uuid4()
        ctx = StrategyContext(
            strategy_id=sid, strategy_name="MockStrategy",
            strategy=strategy, symbols=["ATOM/USDC"],
        )
        runner._strategies[sid] = ctx

        signal = TradeSignal(
            strategy_id=str(sid), strategy_name="MockStrategy",
            symbol="ATOM/USDC", side="BUY", order_type="MARKET",
            quantity=Decimal("10"), price=Decimal("2.03"),
            metadata={"expected_profit_price": 2.08},
        )
        await runner._route_signal(signal)

        pos = ctx.strategy.get_position("ATOM/USDC")
        assert pos is None, "Position should NOT open when order rejected"
        assert runner._stats["signals_failed"] == 1
