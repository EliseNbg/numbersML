#!/usr/bin/env python3
"""
Gap Filler CLI - Detect and fill gaps in candles_1s.

Scans candles_1s for missing seconds and fills them by fetching
1-second klines from Binance REST API.

Usage:
    # Detect gaps (last 24 hours)
    python -m src.cli.gap_fill --detect

    # Fill all gaps
    python -m src.cli.gap_fill

    # Fill gaps for specific symbol
    python -m src.cli.gap_fill --symbol BTC/USDC

    # Dry run (preview)
    python -m src.cli.gap_fill --dry-run
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List

import asyncpg
import click
import aiohttp

BINANCE_API_BASE = "https://api.binance.com/api/v3"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


class CandleGap:
    """Represents a gap in candles_1s data."""

    def __init__(
        self,
        symbol_id: int,
        symbol: str,
        gap_start: datetime,
        gap_end: datetime,
        gap_seconds: int,
    ):
        self.symbol_id = symbol_id
        self.symbol = symbol
        self.gap_start = gap_start
        self.gap_end = gap_end
        self.gap_seconds = gap_seconds

    @property
    def is_critical(self) -> bool:
        """Gaps > 60 seconds are critical."""
        return self.gap_seconds > 60

    def __repr__(self):
        return f"CandleGap({self.symbol}, {self.gap_seconds}s)"


async def detect_gaps(
    db_pool: asyncpg.Pool,
    symbol_filter: Optional[str] = None,
    hours: int = 24,
) -> List[CandleGap]:
    """
    Detect gaps in candles_1s table.

    Looks for missing seconds between consecutive candle timestamps.
    """
    async with db_pool.acquire() as conn:
        if symbol_filter:
            rows = await conn.fetch(
                """
                SELECT c.symbol_id, s.symbol, c.time,
                       LAG(c.time) OVER (PARTITION BY c.symbol_id ORDER BY c.time) AS prev_time
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE s.symbol = $1
                  AND c.time > NOW() - INTERVAL '1 hour' * $2
                ORDER BY c.symbol_id, c.time
                """,
                symbol_filter, hours,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT c.symbol_id, s.symbol, c.time,
                       LAG(c.time) OVER (PARTITION BY c.symbol_id ORDER BY c.time) AS prev_time
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE s.is_active = true
                  AND c.time > NOW() - INTERVAL '1 hour' * $1
                ORDER BY c.symbol_id, c.time
                """,
                hours,
            )

    gaps: List[CandleGap] = []
    for row in rows:
        if row['prev_time'] is None:
            continue
        gap_sec = (row['time'] - row['prev_time']).total_seconds()
        if gap_sec > 2:  # More than 1 missing second
            gaps.append(CandleGap(
                symbol_id=row['symbol_id'],
                symbol=row['symbol'],
                gap_start=row['prev_time'],
                gap_end=row['time'],
                gap_seconds=int(gap_sec) - 1,
            ))

    return gaps


async def fill_gap(
    db_pool: asyncpg.Pool,
    gap: CandleGap,
) -> int:
    """
    Fill a single gap by fetching klines from Binance.

    Returns number of candles inserted.
    """
    binance_symbol = gap.symbol.replace('/', '')
    start_time = gap.gap_start + timedelta(seconds=1)
    end_time = gap.gap_end - timedelta(seconds=1)

    if start_time >= end_time:
        return 0

    all_klines = []
    current = start_time

    async with aiohttp.ClientSession() as session:
        while current < end_time:
            try:
                params = {
                    'symbol': binance_symbol,
                    'interval': '1s',
                    'startTime': int(current.timestamp() * 1000),
                    'endTime': int(end_time.timestamp() * 1000),
                    'limit': 1000,
                }

                async with session.get(
                    f"{BINANCE_API_BASE}/klines",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        logger.error(f"Binance API error {response.status} for {gap.symbol}")
                        break

                    klines = await response.json()
                    if not klines:
                        break

                    all_klines.extend(klines)
                    current = datetime.fromtimestamp(klines[-1][0] / 1000 + 1)

                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error fetching klines for {gap.symbol}: {e}")
                break

    if not all_klines:
        return 0

    # Insert into candles_1s
    records = [
        (
            datetime.fromtimestamp(k[0] / 1000).replace(tzinfo=None),
            gap.symbol_id,
            Decimal(k[1]),   # open
            Decimal(k[2]),   # high
            Decimal(k[3]),   # low
            Decimal(k[4]),   # close
            Decimal(k[5]),   # volume
            Decimal(k[7]),   # quote_volume
        )
        for k in all_klines
    ]

    async with db_pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO candles_1s (
                time, symbol_id, open, high, low, close,
                volume, quote_volume, processed
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, false)
            ON CONFLICT (time, symbol_id) DO NOTHING
            """,
            records,
        )

    return len(records)


@click.command()
@click.option('--db-url', envvar='DATABASE_URL',
              default='postgresql://crypto:crypto_secret@localhost:5432/crypto_trading')
@click.option('--detect', is_flag=True, help='Only detect gaps, do not fill')
@click.option('--dry-run', is_flag=True, help='Show what would be done')
@click.option('--symbol', help='Filter by symbol (e.g., BTC/USDC)')
@click.option('--critical-only', is_flag=True, help='Only fill gaps > 60 seconds')
@click.option('--hours', default=24, help='Look back N hours (default: 24)')
@click.option('--verbose', '-v', is_flag=True)
def main(
    db_url: str,
    detect: bool,
    dry_run: bool,
    symbol: Optional[str],
    critical_only: bool,
    hours: int,
    verbose: bool,
) -> None:
    """Detect and fill gaps in candles_1s."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    exit_code = asyncio.run(
        _run(db_url, detect, dry_run, symbol, critical_only, hours)
    )
    sys.exit(exit_code)


async def _run(
    db_url: str,
    detect: bool,
    dry_run: bool,
    symbol: Optional[str],
    critical_only: bool,
    hours: int,
) -> int:
    """Run gap detection and filling."""
    db_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=5)

    try:
        logger.info(f"Detecting gaps in candles_1s (last {hours} hours)...")
        gaps = await detect_gaps(db_pool, symbol, hours)

        if not gaps:
            logger.info("No gaps found")
            return 0

        if critical_only:
            gaps = [g for g in gaps if g.is_critical]

        # Summary
        print(f"\nFound {len(gaps)} gaps:")
        for g in gaps[:20]:
            marker = " [CRITICAL]" if g.is_critical else ""
            print(f"  {g.symbol}: {g.gap_seconds}s{marker}")
        if len(gaps) > 20:
            print(f"  ... and {len(gaps) - 20} more")

        total_sec = sum(g.gap_seconds for g in gaps)
        print(f"Total gap time: {total_sec}s ({total_sec / 3600:.2f}h)")

        if detect or dry_run:
            return 0

        # Fill gaps
        filled = 0
        failed = 0
        total_candles = 0

        for i, gap in enumerate(gaps, 1):
            try:
                count = await fill_gap(db_pool, gap)
                if count > 0:
                    filled += 1
                    total_candles += count
                    logger.info(f"[{i}/{len(gaps)}] {gap.symbol}: {count} candles inserted")
                else:
                    filled += 1
                    logger.info(f"[{i}/{len(gaps)}] {gap.symbol}: no data from Binance")
            except Exception as e:
                failed += 1
                logger.error(f"[{i}/{len(gaps)}] {gap.symbol} failed: {e}")

        print(f"\nResults: {filled} filled, {failed} failed, {total_candles} candles inserted")
        print("Next step: recalculate indicators for filled candles:")
        print("  python3 -m src.cli.recalculate --all --from 'YYYY-MM-DD HH:MM:SS'")

        return 1 if failed > 0 else 0

    finally:
        await db_pool.close()


if __name__ == '__main__':
    main()
