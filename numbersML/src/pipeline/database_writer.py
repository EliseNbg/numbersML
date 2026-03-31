"""
Database Writer for batch inserting candles and trades.

Features:
- Batch insert for performance
- Transaction management
- Error handling with retry
- Connection pooling

Usage:
    writer = DatabaseWriter(db_pool=pool)
    await writer.write_candle(candle)
    await writer.flush()
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

import asyncpg

from src.pipeline.aggregator import TradeAggregation

logger = logging.getLogger(__name__)


class DatabaseWriter:
    """
    Writer for persisting candles and trades to database.
    
    Features:
        - Batch insert for performance
        - Automatic flush on size/time threshold
        - Error handling with retry
        - Statistics tracking
    
    Example:
        >>> writer = DatabaseWriter(db_pool=pool, symbol_id=1)
        >>> await writer.write_candle(candle)
        >>> await writer.flush()
    """
    
    # Batch settings
    BATCH_SIZE = 100  # Flush after N candles
    FLUSH_INTERVAL = 5.0  # Flush every N seconds
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        symbol_id: int,
    ) -> None:
        """
        Initialize database writer.
        
        Args:
            db_pool: Database connection pool
            symbol_id: Symbol ID for filtering
        """
        self.db_pool = db_pool
        self.symbol_id = symbol_id
        
        # Batch buffer
        self._buffer: List[TradeAggregation] = []
        self._lock = asyncio.Lock()
        
        # Flush task
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Statistics
        self._stats = {
            'candles_written': 0,
            'batches_written': 0,
            'errors': 0,
            'last_flush_time': None,
        }
    
    async def start(self) -> None:
        """Start background flush task."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("Database writer started")
    
    async def stop(self) -> None:
        """Stop writer and flush remaining data."""
        self._running = False
        
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining data
        await self.flush()
        logger.info("Database writer stopped")
    
    async def _flush_loop(self) -> None:
        """Background flush loop."""
        while self._running:
            await asyncio.sleep(self.FLUSH_INTERVAL)
            
            async with self._lock:
                if len(self._buffer) > 0:
                    await self._flush_batch()
    
    async def write_candle(self, candle: TradeAggregation) -> None:
        """
        Add candle to write buffer.
        
        Args:
            candle: Candle to write
        """
        async with self._lock:
            self._buffer.append(candle)
            
            # Auto-flush if buffer is full
            if len(self._buffer) >= self.BATCH_SIZE:
                await self._flush_batch()
    
    async def _flush_batch(self) -> None:
        """Flush current batch to database."""
        if not self._buffer:
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                # Prepare batch data
                records = [
                    (
                        candle.time,
                        self.symbol_id,
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                        candle.quote_volume,
                        candle.trade_count,
                        candle.first_trade_id,
                        candle.last_trade_id,
                    )
                    for candle in self._buffer
                ]
                
                # Batch insert
                await conn.executemany(
                    """
                    INSERT INTO "candles_1s" (
                        time, symbol_id, open, high, low, close,
                        volume, quote_volume, trade_count,
                        first_trade_id, last_trade_id
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (time, symbol_id) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        quote_volume = EXCLUDED.quote_volume,
                        trade_count = EXCLUDED.trade_count,
                        first_trade_id = EXCLUDED.first_trade_id,
                        last_trade_id = EXCLUDED.last_trade_id,
                        updated_at = NOW()
                    """,
                    records,
                )
            
            # Update stats
            self._stats['candles_written'] += len(self._buffer)
            self._stats['batches_written'] += 1
            self._stats['last_flush_time'] = datetime.now(timezone.utc)
            
            logger.debug(f"Flushed {len(self._buffer)} candles to database")
            
            # Only clear on success
            self._buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to write batch ({len(self._buffer)} candles): {e}")
            self._stats['errors'] += 1
            # Buffer NOT cleared - will retry on next flush
    
    async def flush(self) -> None:
        """Flush all pending data."""
        async with self._lock:
            await self._flush_batch()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get writer statistics.
        
        Returns:
            Dictionary with statistics
        """
        stats = self._stats.copy()
        
        if stats['last_flush_time']:
            stats['last_flush_time'] = stats['last_flush_time'].isoformat()
        
        stats['buffer_size'] = len(self._buffer)
        
        return stats


class MultiSymbolDatabaseWriter:
    """
    Database writer for multiple symbols.
    
    Manages individual DatabaseWriter instances per symbol.
    
    Example:
        >>> writer = MultiSymbolDatabaseWriter(db_pool=pool)
        >>> await writer.write_candle(symbol='BTC/USDT', candle=candle)
        >>> await writer.flush_all()
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize multi-symbol writer.
        
        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self._writers: Dict[int, DatabaseWriter] = {}
        self._symbol_id_cache: Dict[str, int] = {}
        self._running = False
    
    async def _get_symbol_id(self, symbol: str) -> Optional[int]:
        """
        Get symbol ID from cache or database.
        
        Args:
            symbol: Symbol name
        
        Returns:
            Symbol ID or None if not found
        """
        if symbol in self._symbol_id_cache:
            return self._symbol_id_cache[symbol]
        
        async with self.db_pool.acquire() as conn:
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1",
                symbol,
            )
            
            if symbol_id:
                self._symbol_id_cache[symbol] = symbol_id
            
            return symbol_id
    
    def _get_writer(self, symbol_id: int) -> DatabaseWriter:
        """
        Get or create writer for symbol.
        
        Args:
            symbol_id: Symbol ID
        
        Returns:
            DatabaseWriter instance
        """
        if symbol_id not in self._writers:
            writer = DatabaseWriter(
                db_pool=self.db_pool,
                symbol_id=symbol_id,
            )
            self._writers[symbol_id] = writer
            # Start flush loop for new writer
            if self._running:
                writer._running = True
                writer._flush_task = asyncio.create_task(writer._flush_loop())
        
        return self._writers[symbol_id]
    
    async def start(self) -> None:
        """Start all writers."""
        self._running = True
        for writer in self._writers.values():
            await writer.start()
        logger.info("Multi-symbol database writer started")
    
    async def stop(self) -> None:
        """Stop all writers."""
        self._running = False
        for writer in self._writers.values():
            await writer.stop()
        logger.info("Multi-symbol database writer stopped")
    
    async def write_candle(
        self,
        symbol: str,
        candle: TradeAggregation,
    ) -> None:
        """
        Write candle for symbol.
        
        Args:
            symbol: Symbol name
            candle: Candle to write
        """
        symbol_id = await self._get_symbol_id(symbol)
        
        if symbol_id:
            writer = self._get_writer(symbol_id)
            await writer.write_candle(candle)
    
    async def flush_all(self) -> None:
        """Flush all writers."""
        for writer in self._writers.values():
            await writer.flush()

    async def flush_symbol(self, symbol: str) -> None:
        """Flush writer for specific symbol."""
        symbol_id = self._symbol_id_cache.get(symbol)
        if symbol_id and symbol_id in self._writers:
            await self._writers[symbol_id].flush()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all writers.
        
        Returns:
            Dictionary with per-symbol statistics
        """
        stats = {
            'symbols': len(self._writers),
            'writers': {},
        }
        
        for symbol_id, writer in self._writers.items():
            symbol = next(
                (s for s, sid in self._symbol_id_cache.items() if sid == symbol_id),
                str(symbol_id),
            )
            stats['writers'][symbol] = writer.get_stats()
        
        return stats
