"""
Trade Aggregator for 1-second candle creation.

Aggregates individual trades into 1-second OHLCV candles:
- Open: First trade price
- High: Maximum price in 1s window
- Low: Minimum price in 1s window
- Close: Last trade price
- Volume: Sum of trade quantities
- Quote Volume: Sum of price * quantity

Usage:
    aggregator = TradeAggregator(symbol='BTC/USDT', on_candle=callback)
    await aggregator.add_trade(trade)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field

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
        high: Highest price in window
        low: Lowest price in window
        close: Closing price (last trade)
        volume: Total base asset volume
        quote_volume: Total quote asset volume
        trade_count: Number of trades in window
        first_trade_id: First aggregate trade ID
        last_trade_id: Last aggregate trade ID
    """
    time: datetime
    symbol: str
    open: Decimal = Decimal('0')
    high: Decimal = Decimal('0')
    low: Decimal = Decimal('0')
    close: Decimal = Decimal('0')
    volume: Decimal = Decimal('0')
    quote_volume: Decimal = Decimal('0')
    trade_count: int = 0
    first_trade_id: int = 0
    last_trade_id: int = 0
    
    def update(self, trade: AggTrade) -> None:
        """
        Update aggregation with new trade.
        
        Args:
            trade: Trade to add
        """
        if self.trade_count == 0:
            # First trade in window
            self.open = trade.price
            self.high = trade.price
            self.low = trade.price
            self.first_trade_id = trade.agg_trade_id
        else:
            # Update OHLC
            if trade.price > self.high:
                self.high = trade.price
            if trade.price < self.low:
                self.low = trade.price
        
        # Always update close and last trade ID
        self.close = trade.price
        self.last_trade_id = trade.agg_trade_id
        
        # Update volume
        self.volume += trade.quantity
        self.quote_volume += trade.quote_quantity
        self.trade_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            'time': self.time,
            'symbol': self.symbol,
            'open': str(self.open),
            'high': str(self.high),
            'low': str(self.low),
            'close': str(self.close),
            'volume': str(self.volume),
            'quote_volume': str(self.quote_volume),
            'trade_count': self.trade_count,
            'first_trade_id': self.first_trade_id,
            'last_trade_id': self.last_trade_id,
        }


class TradeAggregator:
    """
    Aggregator for converting trades to 1-second candles.
    
    Features:
        - Time-window aggregation (1 second)
        - Automatic candle emission on window change
        - Thread-safe operation
        - Statistics tracking
    
    Example:
        >>> async def on_candle(candle: TradeAggregation):
        ...     print(f"Candle: {candle.symbol} O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close}")
        >>> 
        >>> aggregator = TradeAggregator(symbol='BTC/USDT', on_candle=on_candle)
        >>> await aggregator.add_trade(trade)
    """
    
    def __init__(
        self,
        symbol: str,
        on_candle: Callable[[TradeAggregation], None],
    ) -> None:
        """
        Initialize aggregator.
        
        Args:
            symbol: Symbol to aggregate (e.g., 'BTC/USDT')
            on_candle: Callback function for completed candles
        """
        self.symbol = symbol
        self.on_candle = on_candle
        
        # Current aggregation window
        self._current: Optional[TradeAggregation] = None
        self._lock = asyncio.Lock()
        
        # Track last emitted state for flat candle generation
        self._last_close: Optional[Decimal] = None
        self._last_emitted_time: Optional[datetime] = None
        
        # Statistics
        self._stats = {
            'trades_aggregated': 0,
            'candles_emitted': 0,
            'last_candle_time': None,
        }
    
    def _get_window_time(self, trade_time: datetime) -> datetime:
        """
        Get start time of 1-second window for given trade time.
        
        Args:
            trade_time: Trade timestamp
        
        Returns:
            Window start time (truncated to second)
        """
        return trade_time.replace(microsecond=0)
    
    async def add_trade(self, trade: AggTrade) -> None:
        """
        Add trade to aggregation.
        
        Emits completed candle when trade arrives in a new window.
        Flat candles are emitted by tick().
        
        Args:
            trade: Trade to add
        """
        async with self._lock:
            trade_time = trade.timestamp
            window_time = self._get_window_time(trade_time)
            
            # If trade is in a new window, emit old window first
            if self._current is not None and window_time > self._current.time:
                candle = self._current
                self._last_close = candle.close
                self._current = None
                self._last_emitted_time = candle.time
                self._stats['candles_emitted'] += 1
                self._stats['last_candle_time'] = candle.time
                await self.on_candle(candle)
            
            # Create new window if needed
            if self._current is None:
                self._current = TradeAggregation(
                    time=window_time,
                    symbol=self.symbol,
                )
            elif window_time != self._current.time:
                # Trade jumped to a later window - emit flat candles for gaps
                while self._current.time < window_time:
                    gap_time = self._current.time + timedelta(seconds=1)
                    if self._last_close is not None:
                        flat = TradeAggregation(
                            time=self._current.time,
                            symbol=self.symbol,
                            open=self._last_close,
                            high=self._last_close,
                            low=self._last_close,
                            close=self._last_close,
                            volume=Decimal('0'),
                            quote_volume=Decimal('0'),
                            trade_count=0,
                        )
                        self._last_emitted_time = flat.time
                        self._stats['candles_emitted'] += 1
                        self._stats['last_candle_time'] = flat.time
                        await self.on_candle(flat)
                    if gap_time >= window_time:
                        break
                    self._current = TradeAggregation(
                        time=gap_time,
                        symbol=self.symbol,
                    )
                
                self._current = TradeAggregation(
                    time=window_time,
                    symbol=self.symbol,
                )
            
            # Add trade to current window
            self._current.update(trade)
            self._stats['trades_aggregated'] += 1

    async def tick(self, now: datetime) -> Optional[TradeAggregation]:
        """
        Tick at second boundary - emit candle for completed window.
        
        This is the ONLY way candles get emitted. Called once per second
        by the pipeline ticker loop.
        
        - If current window has trades: emit real candle
        - If no trades in window: emit flat candle (previous close)
        - If never had any trades: emit nothing
        
        Args:
            now: Current time (truncated to second)
        
        Returns:
            Emitted candle, or None if no data yet
        """
        async with self._lock:
            # Determine which window to emit
            # We emit the previous completed second
            emit_time = now - timedelta(seconds=1)
            
            if self._last_emitted_time is not None and emit_time <= self._last_emitted_time:
                # Already emitted this window
                return None
            
            candle = None
            
            if self._current is not None and self._current.time == emit_time:
                # Current window matches emit time - emit real candle
                candle = self._current
                self._last_close = candle.close
                self._current = None
            elif self._current is not None and self._current.time < emit_time:
                # Current window is behind - emit it first
                candle = self._current
                self._last_close = candle.close
                self._current = None
            elif self._last_close is not None:
                # No trades in this window - emit flat candle
                candle = TradeAggregation(
                    time=emit_time,
                    symbol=self.symbol,
                    open=self._last_close,
                    high=self._last_close,
                    low=self._last_close,
                    close=self._last_close,
                    volume=Decimal('0'),
                    quote_volume=Decimal('0'),
                    trade_count=0,
                )
            
            if candle is not None:
                self._last_emitted_time = candle.time
                self._stats['candles_emitted'] += 1
                self._stats['last_candle_time'] = candle.time
                
                await self.on_candle(candle)
            
            return candle
    
    async def flush(self) -> Optional[TradeAggregation]:
        """
        Flush current aggregation (emit any remaining candle).
        
        Call this before shutdown to emit final candle.
        
        Returns:
            Final candle if exists, None otherwise
        """
        async with self._lock:
            if self._current is not None:
                candle = self._current
                self._last_close = candle.close
                self._current = None
                self._last_emitted_time = candle.time
                self._stats['candles_emitted'] += 1
                self._stats['last_candle_time'] = candle.time
                
                await self.on_candle(candle)
                return candle
            
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get aggregator statistics.
        
        Returns:
            Dictionary with statistics
        """
        return self._stats.copy()


class MultiSymbolAggregator:
    """
    Aggregator for multiple symbols.
    
    Manages individual TradeAggregator instances per symbol.
    
    Example:
        >>> async def on_candle(symbol: str, candle: TradeAggregation):
        ...     print(f"{symbol}: {candle.to_dict()}")
        >>> 
        >>> aggregator = MultiSymbolAggregator(on_candle=on_candle)
        >>> await aggregator.add_trade(symbol='BTC/USDT', trade=trade)
    """
    
    def __init__(
        self,
        on_candle: Callable[[str, TradeAggregation], None],
    ) -> None:
        """
        Initialize multi-symbol aggregator.
        
        Args:
            on_candle: Callback function (symbol, candle)
        """
        self.on_candle = on_candle
        self._aggregators: Dict[str, TradeAggregator] = {}
        self._lock = asyncio.Lock()
    
    def _get_aggregator(self, symbol: str) -> TradeAggregator:
        """
        Get or create aggregator for symbol.
        
        Args:
            symbol: Symbol name
        
        Returns:
            TradeAggregator instance
        """
        if symbol not in self._aggregators:
            # Create wrapper callback that includes symbol
            async def on_candle_wrapper(candle: TradeAggregation) -> None:
                await self.on_candle(symbol, candle)
            
            self._aggregators[symbol] = TradeAggregator(
                symbol=symbol,
                on_candle=on_candle_wrapper,
            )
        
        return self._aggregators[symbol]
    
    async def add_trade(
        self,
        symbol: str,
        trade: AggTrade,
    ) -> None:
        """
        Add trade to symbol aggregator.
        
        Args:
            symbol: Symbol name
            trade: Trade to add
        """
        aggregator = self._get_aggregator(symbol)
        await aggregator.add_trade(trade)

    async def tick_all(self, now: datetime) -> int:
        """
        Tick all aggregators at second boundary.
        
        Each aggregator emits its completed candle (or flat candle if no trades).
        
        Args:
            now: Current time (truncated to second)
        
        Returns:
            Number of candles emitted
        """
        count = 0
        for aggregator in self._aggregators.values():
            candle = await aggregator.tick(now)
            if candle:
                count += 1
        return count
    
    async def flush_all(self) -> List[TradeAggregation]:
        """
        Flush all aggregators.
        
        Returns:
            List of emitted candles
        """
        candles = []
        
        for symbol, aggregator in self._aggregators.items():
            candle = await aggregator.flush()
            if candle:
                candles.append(candle)
        
        return candles
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all symbols.
        
        Returns:
            Dictionary with per-symbol statistics
        """
        stats = {
            'symbols': len(self._aggregators),
            'aggregators': {},
        }
        
        for symbol, aggregator in self._aggregators.items():
            stats['aggregators'][symbol] = aggregator.get_stats()
        
        return stats
