#!/usr/bin/env python3
"""
Start data collection for the 5 most volatile symbols.

This script:
1. Fetches current volatile symbols from Binance
2. Creates/updates database
3. Starts the data collector
"""

import asyncio
import asyncpg
import websockets
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_volatile_symbols(limit: int = 5) -> List[str]:
    """Get most volatile symbols from Binance."""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
    
    symbols = []
    for ticker in data:
        quote = ticker['symbol'][-4:]
        if quote not in ['USDT', 'USDC']:
            continue
        base = ticker['symbol'][:-4]
        if base in ['USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'FDUSD']:
            continue
        try:
            high = Decimal(ticker['highPrice'])
            low = Decimal(ticker['lowPrice'])
            open_p = Decimal(ticker['openPrice'])
            if open_p > 0:
                vol = ((high - low) / open_p) * 100
                symbols.append({
                    'symbol': f"{base}/{quote}",
                    'binance_symbol': ticker['symbol'],
                    'volatility': float(vol),
                })
        except:
            continue
    
    symbols.sort(key=lambda x: x['volatility'], reverse=True)
    return [s['symbol'] for s in symbols[:limit]]


async def setup_database(db_url: str, symbols: List[str]) -> Dict[str, int]:
    """Setup database and register symbols."""
    pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    
    symbol_ids = {}
    
    async with pool.acquire() as conn:
        for symbol in symbols:
            base, quote = symbol.split('/')
            
            # Insert or update symbol
            row = await conn.fetchrow(
                """
                INSERT INTO symbols (symbol, base_asset, quote_asset, exchange, 
                                    tick_size, step_size, min_notional, is_allowed, is_active)
                VALUES ($1, $2, $3, 'binance', 0.00000001, 0.00000001, 10, true, true)
                ON CONFLICT (symbol) DO UPDATE SET 
                    is_active = true, 
                    is_allowed = true,
                    updated_at = NOW()
                RETURNING id
                """,
                symbol, base, quote
            )
            symbol_ids[symbol] = row['id']
            logger.info(f"Registered symbol: {symbol} (ID: {row['id']})")
    
    await pool.close()
    return symbol_ids


class DataCollector:
    """Simple data collector for volatile symbols."""
    
    def __init__(
        self,
        db_url: str,
        symbols: List[str],
        batch_size: int = 100,
    ) -> None:
        self.db_url = db_url
        self.symbols = symbols
        self.batch_size = batch_size
        self.db_pool = None
        self.running = False
        self.stats = {'trades': 0, 'errors': 0}
        
    async def start(self) -> None:
        """Start collection."""
        logger.info(f"Starting collection for {len(self.symbols)} symbols: {self.symbols}")
        
        # Setup database
        self.db_pool = await asyncpg.create_pool(self.db_url, min_size=5, max_size=20)
        await setup_database(self.db_url, self.symbols)
        
        # Build WebSocket URL
        streams = '/'.join([
            f"{s.lower().replace('/', '')}@trade"
            for s in self.symbols
        ])
        ws_url = f"wss://stream.binance.com:9443/ws/{streams}"
        
        self.running = True
        buffer = []
        
        logger.info(f"Connecting to {ws_url}")
        
        async with websockets.connect(ws_url) as ws:
            logger.info("WebSocket connected - collecting data...")
            
            while self.running:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(msg)
                    
                    if data.get('e') != 'trade':
                        continue
                    
                    # Parse trade
                    symbol = data['s']
                    # Convert BTCUSDT -> BTC/USDT
                    for s in self.symbols:
                        if s.replace('/', '') == symbol:
                            symbol = s
                            break
                    
                    trade = {
                        'time': datetime.fromtimestamp(data['T'] / 1000),
                        'symbol': symbol,
                        'trade_id': str(data['t']),
                        'price': Decimal(data['p']),
                        'quantity': Decimal(data['q']),
                        'side': 'SELL' if data['m'] else 'BUY',
                        'is_buyer_maker': data['m'],
                    }
                    buffer.append(trade)
                    self.stats['trades'] += 1
                    
                    # Batch insert
                    if len(buffer) >= self.batch_size:
                        await self._store_trades(buffer)
                        buffer = []
                        
                except asyncio.TimeoutError:
                    await ws.ping()
                except Exception as e:
                    self.stats['errors'] += 1
                    logger.error(f"Error: {e}")
                    
                    if buffer:
                        await self._store_trades(buffer)
                        buffer = []
        
        # Final flush
        if buffer:
            await self._store_trades(buffer)
    
    async def _store_trades(self, trades: List[Dict]) -> None:
        """Store trades in database."""
        if not trades:
            return
        
        async with self.db_pool.acquire() as conn:
            for trade in trades:
                try:
                    # Get symbol ID
                    row = await conn.fetchrow(
                        "SELECT id FROM symbols WHERE symbol = $1",
                        trade['symbol']
                    )
                    if not row:
                        continue
                    
                    await conn.execute(
                        """
                        INSERT INTO trades (time, symbol_id, trade_id, price, quantity, side, is_buyer_maker)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (trade_id, symbol_id) DO NOTHING
                        """,
                        trade['time'],
                        row['id'],
                        trade['trade_id'],
                        trade['price'],
                        trade['quantity'],
                        trade['side'],
                        trade['is_buyer_maker'],
                    )
                except Exception as e:
                    logger.debug(f"Error storing trade: {e}")
        
        logger.info(f"Stored {len(trades)} trades (total: {self.stats['trades']})")
    
    async def stop(self) -> None:
        """Stop collection."""
        self.running = False
        if self.db_pool:
            await self.db_pool.close()


async def main() -> None:
    """Main entry point."""
    db_url = "postgresql://crypto:crypto@localhost:5432/crypto_trading"
    
    print("=" * 70)
    print("Crypto Trading System - Data Collection")
    print("=" * 70)
    print()
    
    # Get volatile symbols
    print("Fetching most volatile symbols from Binance...")
    symbols = await get_volatile_symbols(5)
    print(f"Top 5 volatile symbols: {symbols}")
    print()
    
    # Start collector
    collector = DataCollector(db_url, symbols)
    
    try:
        await collector.start()
    except KeyboardInterrupt:
        print("\nStopping...")
        await collector.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await collector.stop()
        raise
    
    print(f"\nCollection stopped. Stats: {collector.stats}")


if __name__ == '__main__':
    asyncio.run(main())
