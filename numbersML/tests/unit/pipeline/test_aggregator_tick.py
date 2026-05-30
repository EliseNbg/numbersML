"""
Comprehensive tests for tick-based 1-second candle aggregation.

Tests that every symbol produces exactly one candle per second,
regardless of trade activity. Flat candles fill gaps with previous close.

Uses pull model: tick() returns candles, no callbacks.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.pipeline.aggregator import MultiSymbolAggregator, TradeAggregator
from src.pipeline.websocket_manager import AggTrade


def make_trade(
    symbol: str = "BTC/USDC",
    price: float = 100.0,
    quantity: float = 1.0,
    trade_id: int = 1,
    trade_time: datetime = None,
) -> AggTrade:
    """Create a test AggTrade."""
    t = trade_time or datetime.now(UTC)
    return AggTrade(
        event_type="aggTrade",
        event_time=int(t.timestamp() * 1000),
        symbol=symbol.replace("/", ""),
        agg_trade_id=trade_id,
        price=Decimal(str(price)),
        quantity=Decimal(str(quantity)),
        first_trade_id=trade_id,
        last_trade_id=trade_id,
        trade_time=int(t.timestamp() * 1000),
        is_buyer_maker=True,
    )


class TestTradeAggregatorTick:
    """Test TradeAggregator tick-based emission."""

    @pytest.mark.asyncio
    async def test_tick_emits_candle_from_trades(self) -> None:
        """Tick emits candle when trades exist in the window."""
        agg = TradeAggregator(symbol="BTC/USDC")

        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)
        trade = make_trade(price=100.0, trade_time=t0 + timedelta(milliseconds=500))
        await agg.add_trade(trade)

        # Tick at t=1s - should emit window [0s, 1s)
        candle = await agg.tick(t0 + timedelta(seconds=1))

        assert candle is not None
        assert candle.time == t0
        assert candle.open == Decimal("100")
        assert candle.close == Decimal("100")
        assert candle.trade_count == 1

    @pytest.mark.asyncio
    async def test_tick_emits_flat_candle_when_no_trades(self) -> None:
        """Tick emits flat candle when no trades in the window."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        # Add trade at t=0s to establish last_close
        await agg.add_trade(make_trade(price=100.0, trade_time=t0))

        # Tick at t=1s - emits window [0s)
        candle0 = await agg.tick(t0 + timedelta(seconds=1))
        assert candle0 is not None
        assert candle0.trade_count == 1

        # Tick at t=2s - NO trades in [1s, 2s) -> flat candle
        flat = await agg.tick(t0 + timedelta(seconds=2))
        assert flat is not None
        assert flat.time == t0 + timedelta(seconds=1)
        assert flat.open == Decimal("100")
        assert flat.high == Decimal("100")
        assert flat.low == Decimal("100")
        assert flat.close == Decimal("100")
        assert flat.volume == Decimal("0")
        assert flat.trade_count == 0

    @pytest.mark.asyncio
    async def test_tick_returns_none_without_any_data(self) -> None:
        """Tick returns None when no trades have ever occurred."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        candle = await agg.tick(t0 + timedelta(seconds=1))
        assert candle is None

    @pytest.mark.asyncio
    async def test_consecutive_ticks_emit_every_second(self) -> None:
        """Each tick emits exactly one candle per second."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        await agg.add_trade(make_trade(price=100.0, trade_time=t0))

        # Collect candles from 5 ticks
        candles = []
        for i in range(1, 6):
            c = await agg.tick(t0 + timedelta(seconds=i))
            candles.append(c)

        assert len(candles) == 5
        for i, candle in enumerate(candles):
            assert candle.time == t0 + timedelta(seconds=i)

    @pytest.mark.asyncio
    async def test_trades_across_multiple_windows(self) -> None:
        """Trades in different windows emit correct OHLCV per window."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        # Window [0s): trades at 90, 110, 95
        await agg.add_trade(make_trade(price=90.0, trade_time=t0 + timedelta(milliseconds=100)))
        await agg.add_trade(make_trade(price=110.0, trade_time=t0 + timedelta(milliseconds=500)))
        await agg.add_trade(make_trade(price=95.0, trade_time=t0 + timedelta(milliseconds=900)))

        # Window [1s): trade at 200
        await agg.add_trade(
            make_trade(price=200.0, trade_time=t0 + timedelta(seconds=1, milliseconds=100))
        )

        c0 = await agg.tick(t0 + timedelta(seconds=1))
        c1 = await agg.tick(t0 + timedelta(seconds=2))

        assert c0 is not None
        assert c0.time == t0
        assert c0.open == Decimal("90")
        assert c0.high == Decimal("110")
        assert c0.low == Decimal("90")
        assert c0.close == Decimal("95")
        assert c0.trade_count == 3

        assert c1 is not None
        assert c1.time == t0 + timedelta(seconds=1)
        assert c1.open == Decimal("200")
        assert c1.close == Decimal("200")
        assert c1.trade_count == 1

    @pytest.mark.asyncio
    async def test_flat_candle_updates_after_trades(self) -> None:
        """Flat candle uses close of most recent real candle."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        await agg.add_trade(make_trade(price=100.0, trade_time=t0))
        await agg.add_trade(make_trade(price=150.0, trade_time=t0 + timedelta(milliseconds=500)))
        await agg.add_trade(make_trade(price=200.0, trade_time=t0 + timedelta(seconds=1)))

        c0 = await agg.tick(t0 + timedelta(seconds=1))
        c1 = await agg.tick(t0 + timedelta(seconds=2))
        c2 = await agg.tick(t0 + timedelta(seconds=3))

        assert c0.close == Decimal("150")
        assert c1.close == Decimal("200")
        assert c2.trade_count == 0  # flat
        assert c2.close == Decimal("200")

    @pytest.mark.asyncio
    async def test_duplicate_tick_is_ignored(self) -> None:
        """Ticking the same second twice emits only once."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        await agg.add_trade(make_trade(price=100.0, trade_time=t0))

        c1 = await agg.tick(t0 + timedelta(seconds=1))
        c2 = await agg.tick(t0 + timedelta(seconds=1))

        assert c1 is not None
        assert c2 is None  # duplicate ignored

    @pytest.mark.asyncio
    async def test_add_trade_only_buffers_no_emission(self) -> None:
        """add_trade only updates state, no candles emitted until tick()."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        await agg.add_trade(make_trade(price=100.0, trade_time=t0))
        await agg.add_trade(make_trade(price=200.0, trade_time=t0 + timedelta(seconds=1)))

        # No candles emitted yet
        assert agg._stats["candles_emitted"] == 0
        assert agg._stats["trades_aggregated"] == 2

    @pytest.mark.asyncio
    async def test_flat_candle_with_initial_last_close(self) -> None:
        """Aggregator created with last_close emits flat candles immediately."""
        agg = TradeAggregator(symbol="BTC/USDC", last_close=Decimal("123.45"))
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        # First tick emits flat candle without any trades
        flat = await agg.tick(t0 + timedelta(seconds=1))
        assert flat is not None
        assert flat.time == t0
        assert flat.open == Decimal("123.45")
        assert flat.close == Decimal("123.45")
        assert flat.high == Decimal("123.45")
        assert flat.low == Decimal("123.45")
        assert flat.volume == Decimal("0")
        assert flat.trade_count == 0

    @pytest.mark.asyncio
    async def test_consecutive_flat_candles_with_initial_last_close(self) -> None:
        """Aggregator with last_close emits consecutive flat candles."""
        agg = TradeAggregator(symbol="BTC/USDC", last_close=Decimal("500.00"))
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        candles = []
        for i in range(1, 4):
            c = await agg.tick(t0 + timedelta(seconds=i))
            candles.append(c)

        assert len(candles) == 3
        for i, candle in enumerate(candles):
            assert candle.time == t0 + timedelta(seconds=i)
            assert candle.close == Decimal("500.00")
            assert candle.trade_count == 0

    @pytest.mark.asyncio
    async def test_flat_candle_from_last_close_then_updates_after_trade(self) -> None:
        """After initial last_close, real trades update flat candle prices."""
        agg = TradeAggregator(symbol="BTC/USDC", last_close=Decimal("100.00"))
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        # Flat candle at t=0
        flat = await agg.tick(t0 + timedelta(seconds=1))
        assert flat.close == Decimal("100.00")

        # Real trade at t=1s
        await agg.add_trade(make_trade(price=200.0, trade_time=t0 + timedelta(seconds=1)))

        # Tick at t=2s - emits real candle for [1s, 2s)
        real = await agg.tick(t0 + timedelta(seconds=2))
        assert real.trade_count == 1
        assert real.close == Decimal("200.00")

        # Tick at t=3s - flat candle uses new close
        flat2 = await agg.tick(t0 + timedelta(seconds=3))
        assert flat2.close == Decimal("200.00")


class TestTradeAggregatorInit:
    """Test TradeAggregator initialization variations."""

    @pytest.mark.asyncio
    async def test_init_without_last_close(self) -> None:
        """Aggregator without last_close returns None on first tick."""
        agg = TradeAggregator(symbol="BTC/USDC")
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)
        candle = await agg.tick(t0 + timedelta(seconds=1))
        assert candle is None

    @pytest.mark.asyncio
    async def test_init_with_last_close_emits_immediately(self) -> None:
        """Aggregator with last_close emits flat candle on first tick."""
        agg = TradeAggregator(symbol="BTC/USDC", last_close=Decimal("42.00"))
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)
        candle = await agg.tick(t0 + timedelta(seconds=1))
        assert candle is not None
        assert candle.close == Decimal("42.00")

    @pytest.mark.asyncio
    async def test_init_last_close_none_returns_none(self) -> None:
        """Explicit last_close=None behaves same as no argument."""
        agg = TradeAggregator(symbol="BTC/USDC", last_close=None)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)
        candle = await agg.tick(t0 + timedelta(seconds=1))
        assert candle is None


class TestMultiSymbolAggregatorTickAll:
    """Test MultiSymbolAggregator tick_all."""

    @pytest.mark.asyncio
    async def test_tick_all_empty_when_no_symbols(self) -> None:
        """tick_all returns empty dict when no symbols registered."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)
        emitted = await agg.tick_all(t0 + timedelta(seconds=1))
        assert emitted == {}

    @pytest.mark.asyncio
    async def test_ensure_symbol_creates_aggregator(self) -> None:
        """ensure_symbol creates aggregator without requiring a trade."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        agg.ensure_symbol("BTC/USDC")
        stats = agg.get_stats()
        assert stats["symbols"] == 1

    @pytest.mark.asyncio
    async def test_ensure_symbol_with_last_close_emits_flat_candles(self) -> None:
        """ensure_symbol with last_close produces flat candles immediately."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        agg.ensure_symbol("BTC/USDC", last_close=Decimal("999.99"))

        emitted = await agg.tick_all(t0 + timedelta(seconds=1))
        assert len(emitted) == 1
        assert emitted["BTC/USDC"].close == Decimal("999.99")
        assert emitted["BTC/USDC"].trade_count == 0

    @pytest.mark.asyncio
    async def test_ensure_symbol_without_last_close_returns_none(self) -> None:
        """ensure_symbol without last_close: aggregator exists but tick returns None."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        agg.ensure_symbol("BTC/USDC")
        emitted = await agg.tick_all(t0 + timedelta(seconds=1))
        assert emitted == {}

    @pytest.mark.asyncio
    async def test_ensure_symbol_is_idempotent(self) -> None:
        """Calling ensure_symbol multiple times does not duplicate."""
        agg = MultiSymbolAggregator()
        agg.ensure_symbol("BTC/USDC", last_close=Decimal("10.00"))
        agg.ensure_symbol("BTC/USDC", last_close=Decimal("20.00"))  # second call ignored
        assert agg.get_stats()["symbols"] == 1

        # Don't need to verify the close value - ensure_symbol is a no-op if exists

    @pytest.mark.asyncio
    async def test_mixed_ensure_and_add_trade(self) -> None:
        """ensure_symbol + real trades work together correctly."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        # Pre-create BTC, add trade for ETH
        agg.ensure_symbol("BTC/USDC", last_close=Decimal("100.00"))
        await agg.add_trade(
            "ETH/USDC",
            make_trade(symbol="ETH/USDC", price=50.0, trade_time=t0),
        )

        emitted = await agg.tick_all(t0 + timedelta(seconds=1))
        assert len(emitted) == 2
        assert emitted["BTC/USDC"].trade_count == 0  # flat
        assert emitted["BTC/USDC"].close == Decimal("100.00")
        assert emitted["ETH/USDC"].trade_count == 1  # real

    @pytest.mark.asyncio
    async def test_tick_all_returns_dict(self) -> None:
        """tick_all returns {symbol: candle} dict."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        await agg.add_trade("BTC/USDC", make_trade(symbol="BTC/USDC", price=100.0, trade_time=t0))
        await agg.add_trade("ETH/USDC", make_trade(symbol="ETH/USDC", price=50.0, trade_time=t0))
        await agg.add_trade("DOGE/USDC", make_trade(symbol="DOGE/USDC", price=1.0, trade_time=t0))

        emitted = await agg.tick_all(t0 + timedelta(seconds=1))

        assert len(emitted) == 3
        assert "BTC/USDC" in emitted
        assert "ETH/USDC" in emitted
        assert "DOGE/USDC" in emitted

    @pytest.mark.asyncio
    async def test_tick_all_produces_flat_candles(self) -> None:
        """tick_all produces flat candles for symbols with no new trades."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        await agg.add_trade("BTC/USDC", make_trade(symbol="BTC/USDC", price=100.0, trade_time=t0))

        # Tick t=1s - BTC emits real
        emitted1 = await agg.tick_all(t0 + timedelta(seconds=1))
        assert len(emitted1) == 1

        # Add ETH trade at t=1s
        await agg.add_trade(
            "ETH/USDC",
            make_trade(symbol="ETH/USDC", price=50.0, trade_time=t0 + timedelta(seconds=1)),
        )

        # Tick t=2s - BTC emits flat, ETH emits real
        emitted2 = await agg.tick_all(t0 + timedelta(seconds=2))
        assert len(emitted2) == 2

        assert emitted2["BTC/USDC"].trade_count == 0  # flat
        assert emitted2["BTC/USDC"].close == Decimal("100")
        assert emitted2["ETH/USDC"].trade_count == 1  # real

    @pytest.mark.asyncio
    async def test_consecutive_tick_all(self) -> None:
        """Multiple tick_all calls emit one candle per symbol per tick."""
        agg = MultiSymbolAggregator()
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        await agg.add_trade("BTC/USDC", make_trade(symbol="BTC/USDC", price=100.0, trade_time=t0))
        await agg.add_trade("ETH/USDC", make_trade(symbol="ETH/USDC", price=50.0, trade_time=t0))

        # Tick 3 times
        all_candles = []
        for i in range(1, 4):
            emitted = await agg.tick_all(t0 + timedelta(seconds=i))
            all_candles.extend(emitted.values())

        # 3 seconds × 2 symbols = 6 candles
        assert len(all_candles) == 6
