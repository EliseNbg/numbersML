#!/usr/bin/env python3
"""
Historical Data Backfill from Binance.

Fetches 1-second klines for active symbols and populates:
- ticker_24hr_stats (1-sec kline data)
- tick_indicators (calculated inline)

Usage:
    # Backfill last 3 days (default) for all active symbols
    python -m src.cli.backfill.py

    # Backfill last 7 days
    python -m src.cli.backfill.py --days 7

    # Backfill specific symbol
    python -m src.cli.backfill.py --days 3 --symbol BTC/USDT

    # Dry run (no inserts)
    python -m src.cli.backfill.py --days 3 --dry-run
"""

import asyncio
import asyncpg
import argparse
import logging
import sys
import json
import aiohttp
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Optional, Any

import numpy as np

from src.indicators.registry import IndicatorRegistry
from src.indicators.base import Indicator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Binance REST API endpoints
BINANCE_API_BASE = "https://api.binance.com/api/v3"


class HistoricalBackfill:
    """
    Backfill historical data from Binance.

    Features:
    - Collects active symbols (1-min sampling)
    - Fetches 1-sec klines via REST API
    - Calculates indicators inline
    - Checkpoint in system_config table for resume
    """

    def __init__(
        self,
        db_url: str,
        days: int = 3,
        symbol_filter: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize backfill.

        Args:
            db_url: Database connection string
            days: Days to backfill (default: 3)
            symbol_filter: Optional symbol to backfill (e.g., 'BTC/USDT')
            dry_run: If True, don't insert data
        """
        self.db_url = db_url
        self.days = days
        self.symbol_filter = symbol_filter
        self.dry_run = dry_run

        self._stats: Dict[str, int] = {
            'symbols_processed': 0,
            'records_inserted': 0,
            'indicators_calculated': 0,
            'errors': 0,
        }

    async def run(self) -> Dict:
        """
        Run backfill process.

        Returns:
            Statistics dictionary
        """
        print(f"🚀 Starting historical backfill ({self.days} days)")
        print(f"Database: {self.db_url.split('@')[-1]}")
        if self.dry_run:
            print("⚠️  DRY RUN MODE - No data will be inserted")
        print()

        db_pool: Optional[asyncpg.Pool] = None

        try:
            # Create database pool
            db_pool = await asyncpg.create_pool(
                dsn=self.db_url,
                min_size=2,
                max_size=10,
                timeout=60,
            )

            # Step 1: Collect active symbols
            if self.symbol_filter:
                symbols = [self.symbol_filter]
                print(f"Using symbol filter: {symbols}")
            else:
                symbols = await self._collect_active_symbols(db_pool)
                print(f"Collected {len(symbols)} active symbols")

            if not symbols:
                print("❌ No symbols to backfill")
                return self._stats

            print()

            # Step 2: Backfill each symbol (sequential)
            for i, symbol in enumerate(symbols, 1):
                print(f"[{i}/{len(symbols)}] Backfilling {symbol}...")
                try:
                    inserted = await self._backfill_symbol(db_pool, symbol)
                    self._stats['records_inserted'] += inserted
                    self._stats['symbols_processed'] += 1
                    print(f"  ✅ Inserted {inserted:,} records")
                except Exception as e:
                    print(f"  ❌ Error backfilling {symbol}: {e}")
                    logger.error(f"Error backfilling {symbol}: {e}", exc_info=True)
                    self._stats['errors'] += 1
                    continue

            # Print summary
            print()
            self._print_summary()

        except Exception as e:
            logger.error(f"Backfill failed: {e}", exc_info=True)
            raise

        finally:
            # Close database pool
            if db_pool:
                await db_pool.close()

        return self._stats

    async def _collect_active_symbols(
        self,
        pool: asyncpg.Pool,
        duration_sec: int = 60
    ) -> List[str]:
        """
        Collect active symbols by sampling 24hr ticker.

        Args:
            pool: Database pool
            duration_sec: Sampling duration (default: 60 sec)

        Returns:
            List of EU-compliant symbols
        """
        print(f"Collecting active symbols for {duration_sec} seconds...")

        symbols_seen: set[str] = set()
        end_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=duration_sec)

        async with aiohttp.ClientSession() as session:
            while datetime.now(timezone.utc).replace(tzinfo=None) < end_time:
                # Fetch 24hr tickers from Binance REST API
                async with session.get(
                    f"{BINANCE_API_BASE}/ticker/24hr",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        tickers = await response.json()
                        for t in tickers:
                            if self._is_eu_compliant(t):
                                symbols_seen.add(t['symbol'])
                
                await asyncio.sleep(1)

                # Progress
                remaining = int((end_time - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
                if remaining % 10 == 0:
                    print(f"  Collecting... {remaining}s remaining, {len(symbols_seen)} symbols found", end='\r')

        print()  # New line after progress

        # Filter by minimum volume (1M USDT)
        # Note: We already filter in _is_eu_compliant, but double-check
        filtered = sorted(symbols_seen)

        print(f"Found {len(filtered)} EU-compliant symbols with sufficient volume")
        return filtered

    def _is_eu_compliant(self, ticker: Dict) -> bool:
        """
        Check if symbol is EU-compliant.

        Per MiFID II regulations:
        - Allowed: USDC, BTC, ETH quote assets
        - Excluded: USDT, BUSD, TUSD (not EU approved stablecoins)
        - Excluded: Leveraged tokens (UP/DOWN)

        Args:
            ticker: Ticker data from Binance

        Returns:
            True if EU-compliant
        """
        symbol = ticker.get('symbol', '')

        # Exclude leveraged tokens
        if 'UP' in symbol or 'DOWN' in symbol:
            return False

        # Parse quote asset (e.g., BTCUSDT -> USDT, BTC/USDT -> USDT)
        # Binance format: BASEQUOTE (e.g., BTCUSDT, ETHUSDC)
        quote_asset = None
        for allowed_quote in ['USDC', 'BTC', 'ETH']:
            if symbol.endswith(allowed_quote):
                quote_asset = allowed_quote
                break
        
        # Must end with allowed quote asset
        if quote_asset is None:
            return False

        # Exclude low volume (< 1M in quote currency)
        quote_volume = float(ticker.get('quoteVolume', 0))
        if quote_volume < 1_000_000:
            return False

        return True

    async def _backfill_symbol(
        self,
        pool: asyncpg.Pool,
        symbol: str
    ) -> int:
        """
        Backfill single symbol.

        Args:
            pool: Database pool
            symbol: Symbol to backfill

        Returns:
            Number of records inserted
        """
        # Get symbol ID
        async with pool.acquire() as conn:
            # Convert BTC/USDT → BTCUSDT for Binance API
            binance_symbol = symbol.replace('/', '')

            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1",
                symbol
            )

            if not symbol_id:
                # Insert symbol if not exists
                symbol_id = await self._insert_symbol(conn, symbol, binance_symbol)

            # Check checkpoint (for resume)
            checkpoint = await conn.fetchrow(
                "SELECT value FROM system_config WHERE key = $1",
                f"backfill_checkpoint_{binance_symbol}"
            )

            if checkpoint and not self.symbol_filter:
                checkpoint_data = checkpoint['value']
                days_backfilled = checkpoint_data.get('days', 0)
                if days_backfilled >= self.days:
                    print(f"  ⏭️  Skipping (already backfilled {days_backfilled} days)")
                    return 0
                print(f"  Resuming from checkpoint ({days_backfilled} days already done)")

        # Fetch historical klines
        end_time = datetime.now(timezone.utc).replace(tzinfo=None)
        start_time = end_time - timedelta(days=self.days)

        print(f"  Fetching klines from {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%H:%M')}...")
        klines = await self._fetch_klines(binance_symbol, start_time, end_time)
        print(f"  Fetched {len(klines):,} klines")

        if not klines:
            print("  ⚠️  No klines fetched")
            return 0

        if self.dry_run:
            print(f"  [DRY RUN] Would insert {len(klines):,} records")
            return 0

        # Insert and enrich
        async with pool.acquire() as conn:
            inserted = await self._insert_and_enrich(conn, symbol_id, symbol, klines)

            # Save checkpoint
            await self._save_checkpoint(
                conn,
                binance_symbol,
                datetime.now(timezone.utc).replace(tzinfo=None),
                self.days,
                inserted
            )

        return inserted

    async def _insert_symbol(
        self,
        conn: asyncpg.Connection,
        symbol: str,
        binance_symbol: str
    ) -> int:
        """
        Insert symbol if not exists.

        Args:
            conn: Database connection
            symbol: Symbol (e.g., 'BTC/USDT')
            binance_symbol: Binance format (e.g., 'BTCUSDT')

        Returns:
            Symbol ID
        """
        # Parse base and quote assets
        parts = symbol.split('/')
        base_asset = parts[0] if len(parts) > 0 else ''
        quote_asset = parts[1] if len(parts) > 1 else ''

        symbol_id = await conn.fetchval(
            """
            INSERT INTO symbols (symbol, base_asset, quote_asset, is_active, is_allowed)
            VALUES ($1, $2, $3, true, true)
            ON CONFLICT (symbol) DO UPDATE SET is_active = true
            RETURNING id
            """,
            symbol, base_asset, quote_asset
        )

        logger.info(f"Inserted symbol: {symbol} (ID: {symbol_id})")
        return symbol_id

    async def _fetch_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """
        Fetch 1-sec klines from Binance.

        Args:
            symbol: Symbol (e.g., 'BTCUSDT')
            start_time: Start time
            end_time: End time

        Returns:
            List of kline dictionaries
        """
        all_klines: List[Dict] = []
        current_time = start_time

        async with aiohttp.ClientSession() as session:
            while current_time < end_time:
                try:
                    # Fetch klines from Binance REST API
                    params = {
                        'symbol': symbol,
                        'interval': '1s',
                        'startTime': int(current_time.timestamp() * 1000),
                        'limit': 1000,
                    }
                    
                    async with session.get(
                        f"{BINANCE_API_BASE}/klines",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status != 200:
                            logger.error(f"Binance API error: {response.status}")
                            await asyncio.sleep(1)
                            continue
                        
                        klines = await response.json()
                        
                        if not klines:
                            break

                        all_klines.extend(klines)

                        # Advance time (last kline time + 1 sec)
                        current_time = datetime.fromtimestamp(
                            klines[-1][0] / 1000 + 1
                        )

                        # Rate limiting (100ms)
                        await asyncio.sleep(0.1)

                        # Progress logging
                        if len(all_klines) % 10000 == 0:
                            print(f"    Fetched {len(all_klines):,} klines...", end='\r')

                except Exception as e:
                    logger.error(f"Error fetching klines: {e}")
                    await asyncio.sleep(1)  # Retry delay

        print()  # New line after progress
        return all_klines

    async def _insert_and_enrich(
        self,
        conn: asyncpg.Connection,
        symbol_id: int,
        symbol: str,
        klines: List[Dict]
    ) -> int:
        """
        Insert klines and calculate indicators inline.

        Args:
            conn: Database connection
            symbol_id: Symbol ID
            symbol: Symbol name
            klines: Kline data

        Returns:
            Number of records inserted
        """
        # Initialize indicator registry
        import sys
        sys.path.insert(0, '/home/andy/projects/numbers/numbersML')
        
        IndicatorRegistry.discover()
        indicators = {
            name: IndicatorRegistry.get(name)
            for name in IndicatorRegistry.list_indicators()
        }
        print(f"  Loaded {len(indicators)} indicators for inline calculation")

        # Tick window arrays (circular buffer style)
        window_size = 200
        prices: List[float] = []
        volumes: List[float] = []
        highs: List[float] = []
        lows: List[float] = []

        inserted = 0
        batch: List[tuple] = []
        indicator_batch: List[tuple] = []
        batch_size = 1000

        for kline in klines:
            # Parse kline [time, open, high, low, close, volume, ...]
            tick_time = datetime.fromtimestamp(kline[0] / 1000)
            open_price = Decimal(kline[1])
            high_price = Decimal(kline[2])
            low_price = Decimal(kline[3])
            close_price = Decimal(kline[4])
            volume = Decimal(kline[5])
            quote_volume = Decimal(kline[7])

            # Calculate price change
            price_change = close_price - open_price
            price_change_pct = (price_change / open_price * 100) if open_price > 0 else Decimal(0)

            # Update tick window
            prices.append(float(close_price))
            volumes.append(float(volume))
            highs.append(float(high_price))
            lows.append(float(low_price))

            # Maintain window size
            if len(prices) > window_size:
                prices.pop(0)
                volumes.pop(0)
                highs.pop(0)
                lows.pop(0)

            # Calculate indicators (if enough data)
            indicator_values: Dict[str, float] = {}
            if len(prices) >= 50:  # Minimum data for indicators
                np_prices = np.array(prices, dtype=np.float64)
                np_volumes = np.array(volumes, dtype=np.float64)
                np_highs = np.array(highs, dtype=np.float64)
                np_lows = np.array(lows, dtype=np.float64)

                for name, indicator in indicators.items():
                    if indicator is None:
                        continue
                    try:
                        result = indicator.calculate(
                            prices=np_prices,
                            volumes=np_volumes,
                            highs=np_highs,
                            lows=np_lows,
                        )

                        # Get latest value for each indicator output
                        for key, values in result.values.items():
                            if len(values) > 0:
                                latest_value = values[-1]
                                if not np.isnan(latest_value):
                                    indicator_values[f"{name}_{key}"] = float(latest_value)

                    except Exception as e:
                        logger.debug(f"Error calculating {name}: {e}")
                        continue

            # Add to batch
            batch.append((
                tick_time,
                symbol_id,
                symbol,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                quote_volume,
                price_change,
                price_change_pct,
            ))

            # Add indicator batch if we have indicators
            if indicator_values:
                indicator_batch.append((
                    tick_time,
                    symbol_id,
                    close_price,
                    volume,
                    json.dumps(indicator_values),
                    list(indicator_values.keys()),
                ))
                self._stats['indicators_calculated'] += len(indicator_values)

            # Insert batch
            if len(batch) >= batch_size:
                await self._insert_batch(conn, batch, indicator_batch)
                inserted += len(batch)
                batch = []
                indicator_batch = []

                if inserted % 10000 == 0:
                    print(f"    Inserted {inserted:,}/{len(klines):,} records...", end='\r')

        # Insert remaining
        if batch:
            await self._insert_batch(conn, batch, indicator_batch)
            inserted += len(batch)

        print()  # New line after progress
        return inserted

    async def _insert_batch(
        self,
        conn: asyncpg.Connection,
        batch: List[tuple],
        indicator_batch: List[tuple]
    ) -> None:
        """
        Insert batch of records.

        Args:
            conn: Database connection
            batch: Kline records
            indicator_batch: Indicator records
        """
        if batch:
            await conn.executemany(
                """
                INSERT INTO ticker_24hr_stats (
                    time, symbol_id, symbol,
                    open_price, high_price, low_price, last_price,
                    total_volume, total_quote_volume,
                    price_change, price_change_pct
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (time, symbol_id) DO NOTHING
                """,
                batch
            )

        if indicator_batch:
            await conn.executemany(
                """
                INSERT INTO tick_indicators (
                    time, symbol_id, price, volume,
                    values, indicator_keys
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (time, symbol_id) DO UPDATE SET
                    values = EXCLUDED.values,
                    indicator_keys = EXCLUDED.indicator_keys,
                    updated_at = NOW()
                """,
                indicator_batch
            )

    async def _save_checkpoint(
        self,
        conn: asyncpg.Connection,
        symbol: str,
        last_time: datetime,
        days: int,
        records_count: int
    ) -> None:
        """
        Save checkpoint to system_config table.

        Args:
            conn: Database connection
            symbol: Symbol name
            last_time: Last backfilled time
            days: Days backfilled
            records_count: Number of records inserted
        """
        await conn.execute(
            """
            INSERT INTO system_config (key, value, description)
            VALUES ($1, $2, $3)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW(),
                version = system_config.version + 1
            """,
            f"backfill_checkpoint_{symbol}",
            json.dumps({
                'last_time': last_time.isoformat(timespec='seconds'),
                'days': days,
                'records': records_count,
            }),
            f"Backfill checkpoint for {symbol}",
        )

        logger.debug(f"Saved checkpoint for {symbol}: {records_count} records, {days} days")

    def _print_summary(self) -> None:
        """Print backfill summary."""
        print("=" * 60)
        print("BACKFILL SUMMARY")
        print("=" * 60)
        print(f"Symbols processed:     {self._stats['symbols_processed']}")
        print(f"Records inserted:      {self._stats['records_inserted']:,}")
        print(f"Indicators calculated: {self._stats['indicators_calculated']:,}")
        print(f"Errors:                {self._stats['errors']}")
        print("=" * 60)

        if self._stats['errors'] > 0:
            print(f"\n⚠️  Backfill completed with {self._stats['errors']} errors")
        else:
            print("\n✅ Backfill completed successfully!")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Backfill historical data from Binance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backfill last 3 days (default)
  python -m src.cli.backfill

  # Backfill last 7 days
  python -m src.cli.backfill --days 7

  # Backfill specific symbol
  python -m src.cli.backfill --days 3 --symbol BTC/USDT

  # Dry run (test without inserting)
  python -m src.cli.backfill --days 3 --dry-run
        """
    )

    parser.add_argument(
        '--days',
        type=int,
        default=3,
        help='Days to backfill (default: 3)'
    )

    parser.add_argument(
        '--symbol',
        type=str,
        help='Specific symbol to backfill (e.g., BTC/USDT)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Don't insert data, just log what would be done"
    )

    parser.add_argument(
        '--db-url',
        type=str,
        default='postgresql://crypto:crypto_secret@localhost:5432/crypto_trading',
        help='Database URL (default: postgresql://crypto:crypto_secret@localhost:5432/crypto_trading)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting Historical Backfill CLI")

    if args.dry_run:
        logger.info("DRY RUN MODE - No data will be inserted")

    # Run backfill
    backfill = HistoricalBackfill(
        db_url=args.db_url,
        days=args.days,
        symbol_filter=args.symbol,
        dry_run=args.dry_run,
    )

    try:
        asyncio.run(backfill.run())
    except KeyboardInterrupt:
        print("\n⚠️  Backfill interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
