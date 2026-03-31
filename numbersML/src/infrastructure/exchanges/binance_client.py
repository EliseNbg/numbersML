"""
Binance WebSocket client for real-time tick collection.

This module provides a client for connecting to Binance WebSocket
streams and collecting real-time trade data.
"""

import asyncio
import asyncpg
import websockets
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from src.domain.models.trade import Trade
from src.domain.models.symbol import Symbol
from src.domain.services.tick_validator import TickValidator

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """
    Binance WebSocket client for real-time tick collection.
    
    Connects to Binance WebSocket streams and collects
    real-time trade data with validation and batch storage.
    
    Attributes:
        db_pool: PostgreSQL connection pool
        symbols: List of symbols to collect
        batch_size: Number of trades to batch before storing
        batch_interval: Time interval for batch flush (seconds)
    
    Example:
        >>> client = BinanceWebSocketClient(db_pool, ['BTC/USDT'])
        >>> await client.start()
    """
    
    BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        symbols: List[str],
        batch_size: int = 500,
        batch_interval: float = 0.5,
    ) -> None:
        """
        Initialize Binance WebSocket client.
        
        Args:
            db_pool: PostgreSQL connection pool
            symbols: List of symbols to collect (e.g., ['BTC/USDT'])
            batch_size: Number of trades to batch (default: 500)
            batch_interval: Batch flush interval in seconds (default: 0.5)
        """
        self.db_pool: asyncpg.Pool = db_pool
        self.symbols: List[str] = symbols
        self.batch_size: int = batch_size
        self.batch_interval: float = batch_interval
        
        # Internal state
        self._symbol_ids: Dict[str, int] = {}
        self._buffers: Dict[int, List[Dict]] = {}
        self._validators: Dict[int, TickValidator] = {}
        self._running: bool = False
        self._stats: Dict[str, int] = {'processed': 0, 'errors': 0}
    
    async def start(self) -> None:
        """
        Start WebSocket collection.
        
        Connects to Binance WebSocket and starts collecting
        real-time trade data.
        """
        logger.info(f"Starting Binance WebSocket client for {len(self.symbols)} symbols")
        
        await self._init_symbols()
        self._running = True
        
        await self._connect_websocket()
    
    async def stop(self) -> None:
        """Stop WebSocket collection."""
        logger.info("Stopping Binance WebSocket client...")
        self._running = False
        await self._flush_all_buffers()
    
    async def _init_symbols(self) -> None:
        """Initialize symbol mappings and validators."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, symbol, tick_size, step_size, min_notional
                FROM symbols
                WHERE symbol = ANY($1) AND is_active = true AND is_allowed = true
                """,
                self.symbols
            )
            
            for row in rows:
                symbol = row['symbol']
                symbol_id = row['id']
                
                self._symbol_ids[symbol] = symbol_id
                self._buffers[symbol_id] = []
                
                # Create validator for symbol
                symbol_entity = Symbol(
                    id=symbol_id,
                    symbol=symbol,
                    tick_size=row['tick_size'],
                    step_size=row['step_size'],
                    min_notional=row['min_notional'],
                )
                self._validators[symbol_id] = TickValidator(symbol_entity)
        
        logger.info(f"Initialized {len(self._symbol_ids)} active symbols")
    
    async def _connect_websocket(self) -> None:
        """Connect to Binance WebSocket with auto-reconnect."""
        while self._running:
            try:
                # Build stream URLs
                streams = [
                    f"{s.lower().replace('/', '')}@trade"
                    for s in self._symbol_ids.keys()
                ]
                ws_url = f"{self.BINANCE_WS_URL}/{'/'.join(streams)}"
                
                logger.info(f"Connecting to {ws_url}")
                
                async with websockets.connect(ws_url) as ws:
                    logger.info("WebSocket connected")
                    
                    while self._running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=60)
                            await self._process_trade_msg(msg)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=10)
                
            except Exception as e:
                self._stats['errors'] += 1
                logger.error(f"WebSocket error: {e}")
                
                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
    
    async def _process_trade_msg(self, msg: str) -> None:
        """
        Process incoming trade message.
        
        Args:
            msg: WebSocket message (JSON string)
        """
        try:
            data = json.loads(msg)
            
            # Validate message type
            if data.get('e') != 'trade':
                return
            
            # Parse symbol (BTCUSDT -> BTC/USDT)
            raw_symbol = data.get('s', '')
            symbol = self._parse_symbol(raw_symbol)
            
            if symbol not in self._symbol_ids:
                return
            
            symbol_id = self._symbol_ids[symbol]
            
            # Create trade object
            trade = Trade(
                time=datetime.fromtimestamp(data['T'] / 1000, tz=timezone.utc),
                symbol_id=symbol_id,
                trade_id=str(data['t']),
                price=Decimal(data['p']),
                quantity=Decimal(data['q']),
                side='SELL' if data['m'] else 'BUY',
                is_buyer_maker=data['m'],
            )
            
            # Validate trade
            validator = self._validators[symbol_id]
            result = validator.validate(trade)
            
            if not result.is_valid:
                logger.warning(f"Trade validation failed: {result.errors}")
                self._stats['errors'] += 1
                return
            
            # Buffer for batch insert
            self._buffers[symbol_id].append({
                'time': trade.time,
                'symbol_id': symbol_id,
                'trade_id': trade.trade_id,
                'price': trade.price,
                'quantity': trade.quantity,
                'side': trade.side,
                'is_buyer_maker': trade.is_buyer_maker,
            })
            
            self._stats['processed'] += 1
            
            # Flush if buffer is full
            if len(self._buffers[symbol_id]) >= self.batch_size:
                await self._flush_buffer(symbol_id)
        
        except Exception as e:
            logger.error(f"Error processing trade message: {e}")
            self._stats['errors'] += 1
    
    def _parse_symbol(self, raw_symbol: str) -> str:
        """
        Parse symbol from Binance format.
        
        Args:
            raw_symbol: Raw symbol from Binance (e.g., 'BTCUSDT')
        
        Returns:
            Parsed symbol (e.g., 'BTC/USDT')
        """
        # Handle USDT pairs
        if raw_symbol.endswith('USDT'):
            return f"{raw_symbol[:-4]}/USDT"
        
        # Handle BTC pairs
        if raw_symbol.endswith('BTC'):
            return f"{raw_symbol[:-3]}/BTC"
        
        # Handle ETH pairs
        if raw_symbol.endswith('ETH'):
            return f"{raw_symbol[:-3]}/ETH"
        
        # Default: return as-is
        return raw_symbol
    
    async def _flush_buffer(self, symbol_id: int) -> None:
        """
        Flush buffer to database.
        
        Args:
            symbol_id: Symbol ID to flush
        """
        if not self._buffers[symbol_id]:
            return
        
        buffer = self._buffers[symbol_id]
        
        try:
            async with self.db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO trades (
                        time, symbol_id, trade_id, price, quantity,
                        side, is_buyer_maker
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (trade_id, symbol_id) DO NOTHING
                    """,
                    [
                        (
                            t['time'],
                            t['symbol_id'],
                            t['trade_id'],
                            t['price'],
                            t['quantity'],
                            t['side'],
                            t['is_buyer_maker'],
                        )
                        for t in buffer
                    ]
                )
            
            logger.debug(f"Flushed {len(buffer)} trades for symbol {symbol_id}")
            self._buffers[symbol_id] = []
        
        except Exception as e:
            logger.error(f"Error flushing buffer: {e}")
            self._stats['errors'] += 1
    
    async def _flush_all_buffers(self) -> None:
        """Flush all buffers to database."""
        for symbol_id in self._buffers.keys():
            await self._flush_buffer(symbol_id)
        
        logger.info(f"All buffers flushed. Stats: {self._stats}")
    
    async def start_periodic_flush(self) -> None:
        """Start periodic buffer flush."""
        while self._running:
            await asyncio.sleep(self.batch_interval)
            await self._flush_all_buffers()
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get collection statistics.
        
        Returns:
            Dictionary with processed and error counts
        """
        return self._stats.copy()
