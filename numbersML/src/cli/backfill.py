#!/usr/bin/env python3
"""
Historical Data Backfill from Binance.

Fetches 1-second klines for active symbols and populates:
- candles_1s (1-sec OHLCV data)

Usage:
    # Backfill last 3 days (default) for all active symbols
    python -m src.cli.backfill

    # Backfill last 7 days
    python -m src.cli.backfill --days 7

    # Backfill specific symbol
    python -m src.cli.backfill --days 3 --symbol BTC/USDC

    # Dry run (no inserts)
    python -m src.cli.backfill --days 3 --dry-run
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Optional

import aiohttp
import asyncpg

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Binance REST API endpoints
BINANCE_API_BASE = "https://api.binance.com/api/v3"


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


class HistoricalBackfill:
    """
    Backfill historical data from Binance into candles_1s table.
    """

    def __init__(
        self,
        db_url: str,
        days: int = 3,
        symbol_filter: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        self.db_url = db_url
        self.days = days
        self.symbol_filter = symbol_filter
        self.dry_run = dry_run

        self._stats: dict[str, int] = {
            "symbols_processed": 0,
            "records_inserted": 0,
            "errors": 0,
        }

    async def run(self) -> dict:
        """Run backfill process."""
        print(f"Starting historical backfill ({self.days} days)")
        print(f"Database: {self.db_url.split('@')[-1]}")
        if self.dry_run:
            print("DRY RUN MODE - No data will be inserted")
        print()

        db_pool: Optional[asyncpg.Pool] = None

        try:
            db_pool = await asyncpg.create_pool(
                dsn=self.db_url,
                min_size=2,
                max_size=10,
                timeout=60,
                init=_init_utc,
            )

            # Get active symbols from DB
            async with db_pool.acquire() as conn:
                if self.symbol_filter:
                    symbols = await conn.fetch(
                        "SELECT id, symbol FROM symbols WHERE symbol = $1 AND is_active = true",
                        self.symbol_filter,
                    )
                else:
                    symbols = await conn.fetch(
                        "SELECT id, symbol FROM symbols WHERE is_active = true AND is_allowed = true ORDER BY symbol",
                    )

            if not symbols:
                print("No symbols to backfill")
                return self._stats

            print(f"Backfilling {len(symbols)} symbols")
            print()

            # Backfill each symbol
            for i, sym_row in enumerate(symbols, 1):
                symbol_id = sym_row["id"]
                symbol = sym_row["symbol"]
                binance_symbol = symbol.replace("/", "")

                print(f"[{i}/{len(symbols)}] Backfilling {symbol}...")
                try:
                    inserted = await self._backfill_symbol(
                        db_pool, symbol_id, binance_symbol, symbol
                    )
                    self._stats["records_inserted"] += inserted
                    self._stats["symbols_processed"] += 1
                    print(f"  Inserted {inserted:,} records")
                except Exception as e:
                    print(f"  Error backfilling {symbol}: {e}")
                    logger.error(f"Error backfilling {symbol}: {e}", exc_info=True)
                    self._stats["errors"] += 1
                    continue

            self._print_summary()

        except Exception as e:
            logger.error(f"Backfill failed: {e}", exc_info=True)
            raise

        finally:
            if db_pool:
                await db_pool.close()

        return self._stats

    async def _backfill_symbol(
        self,
        pool: asyncpg.Pool,
        symbol_id: int,
        binance_symbol: str,
        symbol: str,
    ) -> int:
        """Backfill single symbol. Returns number of records inserted."""
        async with pool.acquire() as conn:
            # Check existing records
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(days=self.days)

            existing_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM candles_1s
                WHERE symbol_id = $1 AND time BETWEEN $2 AND $3
                """,
                symbol_id,
                start_time,
                end_time,
            )
            if existing_count > 0:
                print(f"  Found {existing_count:,} existing records in time range")

            # Check checkpoint (skip if already backfilled)
            checkpoint = await conn.fetchrow(
                "SELECT value FROM system_config WHERE key = $1",
                f"backfill_checkpoint_{binance_symbol}",
            )
            if checkpoint and not self.symbol_filter:
                checkpoint_data = checkpoint["value"]
                if isinstance(checkpoint_data, str):
                    import json as _json

                    checkpoint_data = _json.loads(checkpoint_data)
                days_backfilled = checkpoint_data.get("days", 0)
                if days_backfilled >= self.days:
                    print(f"  ⏭️  Skipping (already backfilled {days_backfilled} days)")
                    return 0

        # Fetch klines from Binance
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=self.days)

        print(
            f"  Fetching klines from {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%H:%M')}..."
        )
        klines = await self._fetch_klines(binance_symbol, start_time, end_time)
        print(f"  Fetched {len(klines):,} klines")

        if not klines:
            print("  No klines fetched")
            return 0

        if self.dry_run:
            print(f"  [DRY RUN] Would insert {len(klines):,} records")
            return 0

        # Insert into candles_1s
        inserted = await self._insert_klines(pool, symbol_id, klines)
        return inserted

    async def _fetch_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[list]:
        """Fetch 1-second klines from Binance REST API."""
        all_klines: list[list] = []
        current_time = start_time

        async with aiohttp.ClientSession() as session:
            consecutive_errors = 0
            max_consecutive_errors = 10
            while current_time < end_time:
                try:
                    params = {
                        "symbol": symbol,
                        "interval": "1s",
                        "startTime": int(current_time.timestamp() * 1000),
                        "limit": 1000,
                    }

                    async with session.get(
                        f"{BINANCE_API_BASE}/klines",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status != 200:
                            logger.error(f"Binance API error: {response.status}")
                            consecutive_errors += 1
                            if consecutive_errors >= max_consecutive_errors:
                                logger.error(
                                    f"Too many consecutive errors ({consecutive_errors}), stopping"
                                )
                                break
                            await asyncio.sleep(1)
                            continue

                        consecutive_errors = 0

                        klines = await response.json()

                        if not klines:
                            break

                        all_klines.extend(klines)

                        # Advance time
                        current_time = datetime.fromtimestamp(
                            klines[-1][0] / 1000 + 1,
                            tz=UTC,
                        )

                        # Rate limiting
                        await asyncio.sleep(0.1)

                        if len(all_klines) % 10000 == 0:
                            print(f"    Fetched {len(all_klines):,} klines...", end="\r")

                except Exception as e:
                    logger.error(f"Error fetching klines: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            f"Too many consecutive errors ({consecutive_errors}), stopping"
                        )
                        break
                    await asyncio.sleep(1)

        print()
        return all_klines

    async def _insert_klines(
        self,
        pool: asyncpg.Pool,
        symbol_id: int,
        klines: list[list],
    ) -> int:
        """
        Insert klines into candles_1s table.
        """
        batch_size = 1000
        total_inserted = 0

        async with pool.acquire() as conn:
            for i in range(0, len(klines), batch_size):
                batch = []
                for kline in klines[i : i + batch_size]:
                    # Parse kline: [time, open, high, low, close, volume,
                    #               quote_volume, ...]
                    batch.append(
                        (
                            datetime.fromtimestamp(kline[0] / 1000, tz=UTC),
                            symbol_id,
                            Decimal(kline[1]),  # open
                            Decimal(kline[2]),  # high
                            Decimal(kline[3]),  # low
                            Decimal(kline[4]),  # close
                            Decimal(kline[5]),  # volume
                            Decimal(kline[7]),  # quote_volume
                        )
                    )

                await conn.executemany(
                    """
                    INSERT INTO candles_1s (
                        time, symbol_id, open, high, low, close,
                        volume, quote_volume
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (time, symbol_id) DO NOTHING
                    """,
                    batch,
                )

                total_inserted += len(batch)
                if total_inserted % 10000 == 0:
                    print(f"    Inserted {total_inserted:,}/{len(klines):,}...", end="\r")

        print()
        return total_inserted

    def _is_eu_compliant(self, ticker: dict) -> bool:
        """
        Check if symbol is EU-compliant.

        Args:
            ticker: Ticker data from Binance

        Returns:
            True if EU-compliant
        """
        symbol = ticker.get("symbol", "")

        # Exclude leveraged tokens
        if "UP" in symbol or "DOWN" in symbol:
            return False

        # Exclude non-USDT/major-stablecoin pairs (for EU compliance)
        # Accept USDT, USDC, EUR - reject BUSD, GBP, etc.
        if not any(symbol.endswith(x) for x in ("USDT", "USDC", "EUR")):
            return False

        # Exclude low volume (< 1M USDT)
        quote_volume = float(ticker.get("quoteVolume", 0))
        if quote_volume < 1_000_000:
            return False

        return True

    def _print_summary(self) -> None:
        """Print backfill summary."""
        print("=" * 60)
        print("BACKFILL SUMMARY")
        print("=" * 60)
        print(f"Symbols processed: {self._stats['symbols_processed']}")
        print(f"Records inserted:  {self._stats['records_inserted']:,}")
        print(f"Errors:            {self._stats['errors']}")
        print("=" * 60)
        print()
        print("Next step: recalculate indicators and wide vectors:")
        print("  python3 -m src.cli.recalculate --all --from 'YYYY-MM-DD HH:MM:SS'")
        print()

        if self._stats["errors"] > 0:
            print(f"Backfill completed with {self._stats['errors']} errors")
        else:
            print("Backfill completed successfully!")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Backfill historical data from Binance into candles_1s",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backfill last 3 days (default)
  python -m src.cli.backfill

  # Backfill last 7 days
  python -m src.cli.backfill --days 7

  # Backfill specific symbol
  python -m src.cli.backfill --days 3 --symbol BTC/USDC

  # Dry run (test without inserting)
  python -m src.cli.backfill --days 3 --dry-run

After backfill, recalculate indicators:
  python3 -m src.cli.recalculate --all --from 'YYYY-MM-DD HH:MM:SS'
        """,
    )

    parser.add_argument("--days", type=int, default=3, help="Days to backfill (default: 3)")
    parser.add_argument("--symbol", type=str, help="Specific symbol (e.g., BTC/USDC)")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert data")
    parser.add_argument(
        "--db-url",
        type=str,
        default="postgresql://crypto:crypto_secret@localhost:5432/crypto_trading",
        help="Database URL",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    backfill = HistoricalBackfill(
        db_url=args.db_url,
        days=args.days,
        symbol_filter=args.symbol,
        dry_run=args.dry_run,
    )

    try:
        asyncio.run(backfill.run())
    except KeyboardInterrupt:
        print("\nBackfill interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
