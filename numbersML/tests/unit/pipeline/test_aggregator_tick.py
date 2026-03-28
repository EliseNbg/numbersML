"""
Comprehensive tests for tick-based 1-second candle aggregation.

Tests that every symbol produces exactly one candle per second,
regardless of trade activity. Flat candles fill gaps with previous close.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.pipeline.aggregator import TradeAggregator, TradeAggregation, MultiSymbolAggregator
from src.pipeline.websocket_manager import AggTrade


def make_trade(
    symbol: str = 'BTC/USDC',
    price: float = 100.0,
    quantity: float = 1.0,
    trade_id: int = 1,
    trade_time: datetime = None,
) -> AggTrade:
    """Create a test AggTrade."""
    t = trade_time or datetime.now(timezone.utc)
    return AggTrade(
        event_type='aggTrade',
        event_time=int(t.timestamp() * 1000),
        symbol=symbol.replace('/', ''),
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
        emitted = []

        async def on_candle(candle):
            emitted.append(candle)

        agg = TradeAggregator(symbol='BTC/USDC', on_candle=on_candle)

        # Add trade at t=0.5s
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)
        trade = make_trade(price=100.0, trade_time=t0 + timedelta(milliseconds=500))
        await agg.add_trade(trade)

        # Tick at t=1s - should emit window [0s, 1s)
        await agg.tick(t0 + timedelta(seconds=1))

        assert len(emitted) == 1
        candle = emitted[0]
        assert candle.time == t0
        assert candle.open == Decimal('100')
        assert candle.close == Decimal('100')
        assert candle.trade_count == 1

    @pytest.mark.asyncio
    async def test_tick_emits_flat_candle_when_no_trades(self) -> None:
        """Tick emits flat candle when no trades in the window."""
        emitted = []

        async def on_candle(candle):
            emitted.append(candle)

        agg = TradeAggregator(symbol='BTC/USDC', on_candle=on_candle)

        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Add trade at t=0s to establish last_close
        trade = make_trade(price=100.0, trade_time=t0)
        await agg.add_trade(trade)

        # Tick at t=1s - emits window [0s)
        await agg.tick(t0 + timedelta(seconds=1))
        assert len(emitted) == 1
        assert emitted[0].trade_count == 1

        # Tick at t=2s - NO trades in [1s, 2s) -> flat candle
        await agg.tick(t0 + timedelta(seconds=2))
        assert len(emitted) == 2
        flat = emitted[1]
        assert flat.time == t0 + timedelta(seconds=1)
        assert flat.open == Decimal('100')
        assert flat.high == Decimal('100')
        assert flat.low == Decimal('100')
        assert flat.close == Decimal('100')
        assert flat.volume == Decimal('0')
        assert flat.trade_count == 0

    @pytest.mark.asyncio
    async def test_tick_does_nothing_without_any_data(self) -> None:
        """Tick does nothing when no trades have ever occurred."""
        emitted = []

        async def on_candle(candle):
            emitted.append(candle)

        agg = TradeAggregator(symbol='BTC/USDC', on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Tick with no prior trades
        await agg.tick(t0 + timedelta(seconds=1))
        assert len(emitted) == 0

    @pytest.mark.asyncio
    async def test_consecutive_ticks_emit_every_second(self) -> None:
        """Each tick emits exactly one candle per second."""
        emitted = []

        async def on_candle(candle):
            emitted.append(candle)

        agg = TradeAggregator(symbol='BTC/USDC', on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Add trade at t=0s
        await agg.add_trade(make_trade(price=100.0, trade_time=t0))

        # Tick 5 times (t=1s through t=5s)
        for i in range(1, 6):
            await agg.tick(t0 + timedelta(seconds=i))

        # Should have 5 candles: [0s real] + [1s flat] + [2s flat] + [3s flat] + [4s flat]
        assert len(emitted) == 5
        for i, candle in enumerate(emitted):
            assert candle.time == t0 + timedelta(seconds=i)

    @pytest.mark.asyncio
    async def test_trades_across_multiple_windows(self) -> None:
        """Trades in different windows emit correct OHLCV per window."""
        emitted = []

        async def on_candle(candle):
            emitted.append(candle)

        agg = TradeAggregator(symbol='BTC/USDC', on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Window [0s): trades at 90, 110, 95
        await agg.add_trade(make_trade(price=90.0, trade_time=t0 + timedelta(milliseconds=100)))
        await agg.add_trade(make_trade(price=110.0, trade_time=t0 + timedelta(milliseconds=500)))
        await agg.add_trade(make_trade(price=95.0, trade_time=t0 + timedelta(milliseconds=900)))

        # Window [1s): trade at 200
        await agg.add_trade(make_trade(price=200.0, trade_time=t0 + timedelta(seconds=1, milliseconds=100)))

        # Tick at t=2s - should emit both windows
        await agg.tick(t0 + timedelta(seconds=1))
        await agg.tick(t0 + timedelta(seconds=2))

        assert len(emitted) == 2

        # First candle: window [0s)
        c0 = emitted[0]
        assert c0.time == t0
        assert c0.open == Decimal('90')
        assert c0.high == Decimal('110')
        assert c0.low == Decimal('90')
        assert c0.close == Decimal('95')
        assert c0.trade_count == 3

        # Second candle: window [1s)
        c1 = emitted[1]
        assert c1.time == t0 + timedelta(seconds=1)
        assert c1.open == Decimal('200')
        assert c1.close == Decimal('200')
        assert c1.trade_count == 1

    @pytest.mark.asyncio
    async def test_flat_candle_updates_after_trades(self) -> None:
        """Flat candle uses close of most recent real candle."""
        emitted = []

        async def on_candle(candle):
            emitted.append(candle)

        agg = TradeAggregator(symbol='BTC/USDC', on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Real candle at t=0s, close=150
        await agg.add_trade(make_trade(price=100.0, trade_time=t0))
        await agg.add_trade(make_trade(price=150.0, trade_time=t0 + timedelta(milliseconds=500)))

        # Real candle at t=1s, close=200
        await agg.add_trade(make_trade(price=200.0, trade_time=t0 + timedelta(seconds=1)))

        # Emit t=0s
        await agg.tick(t0 + timedelta(seconds=1))
        assert emitted[0].close == Decimal('150')

        # Emit t=1s
        await agg.tick(t0 + timedelta(seconds=2))
        assert emitted[1].close == Decimal('200')

        # Emit t=2s (flat) - should use close=200 from previous real candle
        await agg.tick(t0 + timedelta(seconds=3))
        assert emitted[2].close == Decimal('200')
        assert emitted[2].trade_count == 0

    @pytest.mark.asyncio
    async def test_duplicate_tick_is_ignored(self) -> None:
        """Ticking the same second twice emits only once."""
        emitted = []

        async def on_candle(candle):
            emitted.append(candle)

        agg = TradeAggregator(symbol='BTC/USDC', on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        await agg.add_trade(make_trade(price=100.0, trade_time=t0))

        # Tick t=1s twice
        await agg.tick(t0 + timedelta(seconds=1))
        await agg.tick(t0 + timedelta(seconds=1))

        assert len(emitted) == 1


class TestMultiSymbolAggregatorTickAll:
    """Test MultiSymbolAggregator tick_all."""

    @pytest.mark.asyncio
    async def test_tick_all_emits_for_all_symbols(self) -> None:
        """tick_all emits candle for each symbol."""
        emitted = []

        async def on_candle(symbol, candle):
            emitted.append((symbol, candle))

        agg = MultiSymbolAggregator(on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Add trades for 3 symbols
        await agg.add_trade('BTC/USDC', make_trade(symbol='BTC/USDC', price=100.0, trade_time=t0))
        await agg.add_trade('ETH/USDC', make_trade(symbol='ETH/USDC', price=50.0, trade_time=t0))
        await agg.add_trade('DOGE/USDC', make_trade(symbol='DOGE/USDC', price=1.0, trade_time=t0))

        # Tick all at t=1s
        count = await agg.tick_all(t0 + timedelta(seconds=1))

        assert count == 3
        symbols = {s for s, c in emitted}
        assert symbols == {'BTC/USDC', 'ETH/USDC', 'DOGE/USDC'}

    @pytest.mark.asyncio
    async def test_tick_all_produces_flat_candles(self) -> None:
        """tick_all produces flat candles for symbols with no trades."""
        emitted = []

        async def on_candle(symbol, candle):
            emitted.append((symbol, candle))

        agg = MultiSymbolAggregator(on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Only BTC has a trade at t=0s
        await agg.add_trade('BTC/USDC', make_trade(symbol='BTC/USDC', price=100.0, trade_time=t0))

        # Tick t=1s - BTC emits real, others don't exist yet
        count = await agg.tick_all(t0 + timedelta(seconds=1))
        assert count == 1

        # Now add ETH trade at t=1s
        await agg.add_trade('ETH/USDC', make_trade(symbol='ETH/USDC', price=50.0, trade_time=t0 + timedelta(seconds=1)))

        # Tick t=2s - BTC emits flat, ETH emits real
        emitted.clear()
        count = await agg.tick_all(t0 + timedelta(seconds=2))
        assert count == 2

        btc_candle = next(c for s, c in emitted if s == 'BTC/USDC')
        eth_candle = next(c for s, c in emitted if s == 'ETH/USDC')

        assert btc_candle.trade_count == 0  # flat
        assert btc_candle.close == Decimal('100')
        assert eth_candle.trade_count == 1  # real

    @pytest.mark.asyncio
    async def test_consecutive_tick_all(self) -> None:
        """Multiple tick_all calls emit one candle per symbol per tick."""
        emitted = []

        async def on_candle(symbol, candle):
            emitted.append((symbol, candle))

        agg = MultiSymbolAggregator(on_candle=on_candle)
        t0 = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Add trades
        await agg.add_trade('BTC/USDC', make_trade(symbol='BTC/USDC', price=100.0, trade_time=t0))
        await agg.add_trade('ETH/USDC', make_trade(symbol='ETH/USDC', price=50.0, trade_time=t0))

        # Tick 3 times
        for i in range(1, 4):
            await agg.tick_all(t0 + timedelta(seconds=i))

        # 3 seconds × 2 symbols = 6 candles
        assert len(emitted) == 6

        # Verify one candle per symbol per tick
        for i in range(3):
            tick_candles = [c for s, c in emitted if c.time == t0 + timedelta(seconds=i)]
            assert len(tick_candles) == 2
