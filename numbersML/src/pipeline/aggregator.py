"""
Trade Aggregator for 1-second candle creation.

Aggregates individual trades into 1-second OHLCV candles:
- Open: First trade price
- High: Maximum price in 1s window
- Low: Minimum price in 1s window
- Close: Last trade price
- Volume: Sum of trade quantities
- Quote Volume: Sum of price * quantity

Pull model: tick() and drain_pending() return candles. No callbacks.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from src.pipeline.websocket_manager import AggTrade

logger = logging.getLogger(__name__)


@dataclass
class TradeAggregation:
    """
    1-second trade aggregation (candle).

    Attributes:
        time: Start time of 1-second window
        symbol: Symbol (e.g., 'BTC/USDT')
        open: Opening price (first trade)
        high: Highest price in 1s window
        low: Lowest price in 1s window
        close: Closing price (last trade)
        volume: Total base asset volume
        quote_volume: Total quote asset volume
        trade_count: Number of trades in window
        first_trade_id: First aggregate trade ID
        last_trade_id: Last aggregate trade ID
    """

    time: datetime
    symbol: str
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    quote_volume: Decimal = Decimal("0")
    trade_count: int = 0
    first_trade_id: int = 0
    last_trade_id: int = 0

    def update(self, trade: AggTrade) -> None:
        """Update aggregation with new trade."""
        if self.trade_count == 0:
            self.open = trade.price
            self.high = trade.price
            self.low = trade.price
            self.first_trade_id = trade.agg_trade_id
        else:
            if trade.price > self.high:
                self.high = trade.price
            if trade.price < self.low:
                self.low = trade.price

        self.close = trade.price
        self.last_trade_id = trade.agg_trade_id
        self.volume += trade.quantity
        self.quote_volume += trade.quote_quantity
        self.trade_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "time": self.time,
            "symbol": self.symbol,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "quote_volume": str(self.quote_volume),
            "trade_count": self.trade_count,
            "first_trade_id": self.first_trade_id,
            "last_trade_id": self.last_trade_id,
        }


class TradeAggregator:
    """
    Aggregator for converting trades to 1-second candles.

    Pull model: tick() returns the emitted candle. Inter-window transitions
    during add_trade() queue candles in _pending for later retrieval.

    Example:
        >>> aggregator = TradeAggregator(symbol='BTC/USDT')
        >>> await aggregator.add_trade(trade)  # may queue candle internally
        >>> candle = await aggregator.tick(now)  # returns candle or None
        >>> pending = aggregator.drain_pending()  # candles from add_trade transitions
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

        # Current aggregation window
        self._current: Optional[TradeAggregation] = None
        self._lock = asyncio.Lock()

        # Track last emitted state for flat candle generation
        self._last_close: Optional[Decimal] = None
        self._last_emitted_time: Optional[datetime] = None

        # Candles pending emission (from window transitions during add_trade)
        self._pending: deque[TradeAggregation] = deque()

        # Statistics
        self._stats = {
            "trades_aggregated": 0,
            "candles_emitted": 0,
            "last_candle_time": None,
        }

    def _emit(self, candle: TradeAggregation) -> None:
        """Mark candle as emitted and update state."""
        self._last_close = candle.close
        self._last_emitted_time = candle.time
        self._stats["candles_emitted"] += 1
        self._stats["last_candle_time"] = candle.time

    async def add_trade(self, trade: AggTrade) -> None:
        """
        Add trade to aggregation.

        When a trade arrives in a new window, the old window is queued
        in _pending for tick() to emit.
        """
        async with self._lock:
            trade_time = trade.timestamp
            window_time = trade_time.replace(microsecond=0)

            # If trade is in a new window, queue old window for emission
            if self._current is not None and window_time != self._current.time:
                self._last_close = self._current.close
                self._pending.append(self._current)
                self._current = None

            # Create new window if needed
            if self._current is None:
                self._current = TradeAggregation(time=window_time, symbol=self.symbol)

            # Add trade to current window
            self._current.update(trade)
            self._stats["trades_aggregated"] += 1

    async def tick(self, now: datetime) -> Optional[TradeAggregation]:
        """
        Tick at second boundary - emit candle for completed window.

        Drains _pending queue first (candles from add_trade window transitions),
        then handles current window / flat candle logic.
        """
        async with self._lock:
            # First: drain pending candles from add_trade transitions
            if self._pending:
                candle = self._pending.popleft()
                self._emit(candle)
                return candle

            emit_time = now - timedelta(seconds=1)

            if self._last_emitted_time is not None and emit_time <= self._last_emitted_time:
                return None

            candle = None

            if self._current is not None and self._current.time == emit_time:
                candle = self._current
                self._current = None
            elif self._current is not None and self._current.time < emit_time:
                candle = self._current
                self._current = None
            elif self._last_close is not None:
                candle = TradeAggregation(
                    time=emit_time,
                    symbol=self.symbol,
                    open=self._last_close,
                    high=self._last_close,
                    low=self._last_close,
                    close=self._last_close,
                    volume=Decimal("0"),
                    quote_volume=Decimal("0"),
                    trade_count=0,
                )

            if candle is not None:
                self._emit(candle)

            return candle

    async def flush(self) -> Optional[TradeAggregation]:
        """Flush current aggregation (emit any remaining candle)."""
        async with self._lock:
            if self._current is not None:
                candle = self._current
                self._emit(candle)
                self._current = None
                return candle
            return None

    def get_stats(self) -> dict[str, Any]:
        return self._stats.copy()


class MultiSymbolAggregator:
    """
    Aggregator for multiple symbols.

    Pull model: tick_all() returns emitted candles as a dict.
    """

    def __init__(self) -> None:
        self._aggregators: dict[str, TradeAggregator] = {}
        self._lock = asyncio.Lock()

    def _get_aggregator(self, symbol: str) -> TradeAggregator:
        if symbol in self._aggregators:
            return self._aggregators[symbol]
        self._aggregators[symbol] = TradeAggregator(symbol=symbol)
        return self._aggregators[symbol]

    async def add_trade(self, symbol: str, trade: AggTrade) -> None:
        """Add trade to symbol aggregator."""
        async with self._lock:
            aggregator = self._get_aggregator(symbol)
        await aggregator.add_trade(trade)

    async def tick_all(self, now: datetime) -> dict[str, TradeAggregation]:
        """
        Tick all aggregators. Returns emitted candles as {symbol: candle}.
        """
        emitted: dict[str, TradeAggregation] = {}

        for symbol, aggregator in self._aggregators.items():
            candle = await aggregator.tick(now)
            if candle:
                emitted[symbol] = candle

        return emitted

    async def flush_all(self) -> list[TradeAggregation]:
        """Flush all aggregators. Returns emitted candles."""
        candles = []
        for aggregator in self._aggregators.values():
            candle = await aggregator.flush()
            if candle:
                candles.append(candle)
        return candles

    def get_stats(self) -> dict[str, Any]:
        return {
            "symbols": len(self._aggregators),
            "aggregators": {s: a.get_stats() for s, a in self._aggregators.items()},
        }
