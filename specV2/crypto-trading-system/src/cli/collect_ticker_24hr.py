#!/usr/bin/env python3
"""
Collect 24hr ticker statistics from Binance using !miniTicker@arr stream.

This collects aggregated 24hr stats for ALL symbols efficiently:
- Only transmits changed tickers (bandwidth efficient)
- 1-second update interval
- Replaces deprecated !ticker@arr stream (after 2026-03-26)

Filters:
- Only USDT, USDC, EUR, GBP quote assets (EU compliance)
- Excludes: BUSD, TUSD (not EU allowed)
- Only active trading pairs
- Excludes stablecoin-to-stablecoin pairs

Frequency: Every 1 second (when data changes)
Storage: ticker_24hr_stats table
"""

import asyncio
import asyncpg
import websockets
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any, Set

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# EU Compliance Configuration
# Per MiFID II regulations, only certain stablecoins are approved for EU traders
# BTC and ETH are NOT stablecoins - they are crypto assets and ARE allowed
# Note: GBP removed (user doesn't have GBP access)
EU_ALLOWED_QUOTES: Set[str] = {'USDC', 'EUR', 'BTC', 'ETH'}  # EU-compliant + crypto assets
EU_EXCLUDED_QUOTES: Set[str] = {'USDT', 'BUSD', 'TUSD', 'GBP'}  # NOT EU allowed or no access
STABLECOINS: Set[str] = {'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'FDUSD'}  # Only actual stablecoins


class Ticker24hrCollector:
    """
    Collect 24hr ticker statistics from Binance !miniTicker@arr stream.

    Uses the efficient all-symbols stream instead of individual subscriptions.
    Filters for EU-compliant symbols only.
    """

    # Binance !miniTicker@arr WebSocket endpoint (ALL symbols)
    BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/!miniTicker@arr"

    def __init__(
        self,
        db_url: str,
        snapshot_interval_sec: int = 1,
    ) -> None:
        """
        Initialize ticker collector.

        Args:
            db_url: PostgreSQL connection URL
            snapshot_interval_sec: Snapshot interval in seconds
        """
        self.db_url = db_url
        self.snapshot_interval_sec = snapshot_interval_sec
        self.db_pool = None
        self.running = False
        self.stats = {'ticks': 0, 'errors': 0, 'filtered': 0}
        self._symbol_ids: Dict[str, int] = {}
        self._allowed_symbols: Set[str] = set()
        self._allowed_quotes: Set[str] = EU_ALLOWED_QUOTES - EU_EXCLUDED_QUOTES

    def is_symbol_allowed(self, symbol: str) -> bool:
        """
        Check if symbol is EU-compliant.

        Args:
            symbol: Symbol string (e.g., 'BTC/USDT')

        Returns:
            True if symbol is allowed
        """
        # Parse quote asset
        parts = symbol.split('/')
        if len(parts) != 2:
            return False
        
        quote = parts[1]
        
        # Check if quote is allowed
        if quote not in self._allowed_quotes:
            return False
        
        # Exclude stablecoin-to-stablecoin pairs
        base = parts[0]
        if base in STABLECOINS and quote in STABLECOINS:
            return False
        
        return True

    async def start(self) -> None:
        """Start ticker collection."""
        logger.info("Starting 24hr ticker collection (!miniTicker@arr stream)")
        logger.info(f"EU Compliance: Allowed quotes = {self._allowed_quotes}")

        # Setup database
        self.db_pool = await asyncpg.create_pool(
            self.db_url,
            min_size=5,
            max_size=20,
        )
        await self._init_symbols()

        self.running = True

        logger.info(f"Connecting to {self.BINANCE_WS_URL}")
        logger.info(f"Filtering for EU-compliant symbols only")

        async with websockets.connect(self.BINANCE_WS_URL) as ws:
            logger.info("WebSocket connected - collecting 24hr ticker stats...")

            while self.running:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    await self._process_ticker_array(msg)

                except asyncio.TimeoutError:
                    await ws.ping()

                except Exception as e:
                    self.stats['errors'] += 1
                    logger.error(f"Error: {e}")

        logger.info(f"Collection stopped. Stats: {self.stats}")

    async def stop(self) -> None:
        """Stop ticker collection."""
        logger.info("Stopping ticker collection...")
        self.running = False
        if self.db_pool:
            await self.db_pool.close()

    async def _init_symbols(self) -> None:
        """Initialize symbol mappings from database."""
        async with self.db_pool.acquire() as conn:
            # Get all active and allowed symbols
            rows = await conn.fetch(
                """
                SELECT id, symbol, base_asset, quote_asset
                FROM symbols
                WHERE is_active = true AND is_allowed = true
                ORDER BY symbol
                """
            )
            
            for row in rows:
                symbol = row['symbol']
                self._symbol_ids[symbol] = row['id']
                self._allowed_symbols.add(symbol)
            
            logger.info(f"Loaded {len(self._symbol_ids)} allowed symbols from database")

    async def _process_ticker_array(self, msg: str) -> None:
        """
        Process ticker array message from WebSocket.

        Args:
            msg: WebSocket message (JSON array of tickers)
        """
        try:
            data = json.loads(msg)
            
            if not isinstance(data, list):
                return

            # Process each ticker in the array
            for ticker_data in data:
                await self._process_single_ticker(ticker_data)

        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Error processing ticker array: {e}")

    async def _process_single_ticker(self, data: Dict[str, Any]) -> None:
        """
        Process single ticker from array.

        Args:
            data: Ticker data dictionary
        """
        try:
            # Parse symbol
            raw_symbol = data.get('s', '')
            symbol = self._parse_symbol(raw_symbol)

            # Filter: Only allowed symbols (EU compliance)
            if not self.is_symbol_allowed(symbol):
                self.stats['filtered'] += 1
                return

            # Filter: Only symbols we're tracking
            if symbol not in self._symbol_ids:
                # Auto-register new symbol if it's allowed
                await self._register_symbol(symbol)
                if symbol not in self._symbol_ids:
                    return

            symbol_id = self._symbol_ids[symbol]

            # Parse ticker data
            ticker = {
                'time': datetime.utcnow(),
                'symbol_id': symbol_id,
                'symbol': symbol,

                # Price data
                'last_price': Decimal(data.get('c', '0')),
                'open_price': Decimal(data.get('o', '0')),
                'high_price': Decimal(data.get('h', '0')),
                'low_price': Decimal(data.get('l', '0')),

                # Volume data
                'volume': Decimal(data.get('v', '0')),
                'quote_volume': Decimal(data.get('q', '0')),

                # Price change (calculate from open)
                'price_change': Decimal(data.get('c', '0')) - Decimal(data.get('o', '0')),
                'price_change_pct': Decimal('0'),  # Calculate below

                # Trade count (not in miniTicker)
                'trade_count': 0,
            }

            # Calculate price change percent
            if ticker['open_price'] > 0:
                ticker['price_change_pct'] = (
                    ticker['price_change'] / ticker['open_price'] * 100
                )

            # Store in database
            await self._store_ticker(ticker)

            self.stats['ticks'] += 1

            # Log progress every 100 ticks
            if self.stats['ticks'] % 100 == 0:
                logger.info(f"Collected {self.stats['ticks']} ticker updates "
                          f"(filtered: {self.stats['filtered']})")

        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Error processing ticker: {e}")

    async def _register_symbol(self, symbol: str) -> None:
        """
        Register new symbol in database.

        Args:
            symbol: Symbol string to register
        """
        try:
            base, quote = symbol.split('/')
            
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO symbols (symbol, base_asset, quote_asset,
                                        tick_size, step_size, min_notional,
                                        is_allowed, is_active)
                    VALUES ($1, $2, $3, 0.00000001, 0.00000001, 10, true, true)
                    ON CONFLICT (symbol) DO UPDATE SET is_active = true
                    RETURNING id
                    """,
                    symbol, base, quote
                )
                self._symbol_ids[symbol] = row['id']
                self._allowed_symbols.add(symbol)
                logger.info(f"Auto-registered symbol: {symbol} (ID: {row['id']})")

        except Exception as e:
            logger.error(f"Failed to register symbol {symbol}: {e}")

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

        # Handle USDC pairs
        if raw_symbol.endswith('USDC'):
            return f"{raw_symbol[:-4]}/USDC"

        # Handle EUR pairs
        if raw_symbol.endswith('EUR'):
            return f"{raw_symbol[:-3]}/EUR"

        # Handle GBP pairs
        if raw_symbol.endswith('GBP'):
            return f"{raw_symbol[:-3]}/GBP"

        # Handle BUSD pairs (will be filtered out)
        if raw_symbol.endswith('BUSD'):
            return f"{raw_symbol[:-4]}/BUSD"

        return raw_symbol

    async def _store_ticker(self, ticker: Dict[str, Any]) -> None:
        """
        Store ticker in database.

        Args:
            ticker: Ticker data dictionary
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ticker_24hr_stats (
                    time, symbol_id, symbol,
                    last_price, open_price, high_price, low_price,
                    total_volume, total_quote_volume,
                    price_change, price_change_pct,
                    total_trades
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (time, symbol_id) DO UPDATE SET
                    last_price = EXCLUDED.last_price,
                    total_volume = EXCLUDED.total_volume,
                    total_quote_volume = EXCLUDED.total_quote_volume,
                    total_trades = EXCLUDED.total_trades
                """,
                ticker['time'],
                ticker['symbol_id'],
                ticker['symbol'],
                ticker['last_price'],
                ticker['open_price'],
                ticker['high_price'],
                ticker['low_price'],
                ticker['volume'],
                ticker['quote_volume'],
                ticker['price_change'],
                ticker['price_change_pct'],
                ticker['trade_count'],
            )


async def main() -> None:
    """Main entry point."""
    db_url = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

    print("=" * 70)
    print("Crypto Trading System - 24hr Ticker Collection")
    print("Using !miniTicker@arr stream (EU compliant)")
    print("=" * 70)
    print()

    # Create collector
    collector = Ticker24hrCollector(
        db_url=db_url,
        snapshot_interval_sec=1,
    )

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
