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
from datetime import datetime, timezone
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
    
    async def add_trade(self, trade: AggTrade) -> Optional[TradeAggregation]:
        """
        Add trade to aggregation.
        
        Emits completed candle when window changes.
        
        Args:
            trade: Trade to add
        
        Returns:
            Completed candle if window changed, None otherwise
        """
        async with self._lock:
            trade_time = trade.timestamp
            window_time = self._get_window_time(trade_time)
            
            completed_candle = None
            
            # Check if we need to emit current candle
            if self._current is not None:
                if window_time > self._current.time:
                    # Window changed - emit current candle
                    completed_candle = self._current
                    self._current = None
                    self._stats['candles_emitted'] += 1
                    self._stats['last_candle_time'] = completed_candle.time
                    
                    # Emit candle
                    await self.on_candle(completed_candle)
            
            # Create or update current aggregation
            if self._current is None:
                # New window
                self._current = TradeAggregation(
                    time=window_time,
                    symbol=self.symbol,
                )
            
            # Add trade to current aggregation
            self._current.update(trade)
            self._stats['trades_aggregated'] += 1
            
            return completed_candle
    
    async def flush(self) -> Optional[TradeAggregation]:
        """
        Flush current aggregation (emit incomplete candle).
        
        Call this before shutdown to emit final candle.
        
        Returns:
            Final candle if exists, None otherwise
        """
        async with self._lock:
            if self._current is not None:
                candle = self._current
                self._current = None
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
