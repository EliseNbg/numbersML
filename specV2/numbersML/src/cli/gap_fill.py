#!/usr/bin/env python3
"""
Gap Filler CLI - Detect and fill gaps in historical data.

Usage:
    # Detect gaps (dry run)
    python -m src.cli.gap_fill --detect --dry-run

    # Fill all gaps
    python -m src.cli.gap-fill

    # Fill gaps for specific symbol
    python -m src.cli.gap-fill --symbol BTC/USDT

    # Fill only critical gaps (>1 minute)
    python -m src.cli.gap-fill --critical-only
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import asyncpg
import click

from src.domain.services.gap_detector import GapDetector, GapFiller, DataGap

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    '--db-url',
    envvar='DATABASE_URL',
    default='postgresql://crypto:crypto@localhost:5432/crypto_trading',
    help='Database URL'
)
@click.option(
    '--binance-api-key',
    envvar='BINANCE_API_KEY',
    help='Binance API key (optional, increases rate limits)'
)
@click.option(
    '--detect',
    is_flag=True,
    help='Only detect gaps, don\'t fill'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be done without making changes'
)
@click.option(
    '--symbol',
    help='Filter by symbol (e.g., BTC/USDT)'
)
@click.option(
    '--critical-only',
    is_flag=True,
    help='Only fill critical gaps (>1 minute)'
)
@click.option(
    '--max-concurrent',
    default=3,
    help='Maximum concurrent gap fills (default: 3)'
)
@click.option(
    '--hours',
    default=24,
    help='Look for gaps in last N hours (default: 24)'
)
@click.option(
    '--verbose',
    '-v',
    is_flag=True,
    help='Enable verbose logging'
)
def main(
    db_url: str,
    binance_api_key: Optional[str],
    detect: bool,
    dry_run: bool,
    symbol: Optional[str],
    critical_only: bool,
    max_concurrent: int,
    hours: int,
    verbose: bool,
) -> None:
    """
    Detect and fill gaps in historical tick data.

    Scans the database for gaps in tick data and fills them
    by fetching historical data from Binance API.

    Examples:

    \b
    # Detect gaps (last 24 hours)
    python -m src.cli.gap_fill --detect

    # Fill all gaps
    python -m src.cli.gap-fill

    # Fill only critical gaps for BTC/USDT
    python -m src.cli.gap-fill --symbol BTC/USDT --critical-only

    # Dry run (preview)
    python -m src.cli.gap-fill --dry-run
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting Gap Filler CLI")

    exit_code = asyncio.run(
        run_gap_fill(
            db_url=db_url,
            binance_api_key=binance_api_key,
            detect=detect,
            dry_run=dry_run,
            symbol=symbol,
            critical_only=critical_only,
            max_concurrent=max_concurrent,
            hours=hours,
        )
    )

    sys.exit(exit_code)


async def run_gap_fill(
    db_url: str,
    binance_api_key: Optional[str],
    detect: bool,
    dry_run: bool,
    symbol: Optional[str],
    critical_only: bool,
    max_concurrent: int,
    hours: int,
) -> int:
    """
    Run gap detection and filling.

    Args:
        db_url: Database URL
        binance_api_key: Binance API key
        detect: Only detect gaps
        dry_run: Don't make changes
        symbol: Filter by symbol
        critical_only: Only critical gaps
        max_concurrent: Max concurrent fills
        hours: Look back hours

    Returns:
        Exit code (0 = success)
    """
    db_pool: Optional[asyncpg.Pool] = None

    try:
        # Connect to database
        logger.info(f"Connecting to database...")
        db_pool = await asyncpg.create_pool(
            dsn=db_url,
            min_size=2,
            max_size=10,
            timeout=30,
        )

        # Detect gaps
        logger.info(f"Detecting gaps in last {hours} hours...")
        gaps = await detect_gaps(
            db_pool=db_pool,
            symbol=symbol,
            hours=hours,
        )

        if not gaps:
            logger.info("No gaps found!")
            return 0

        logger.info(f"Found {len(gaps)} gaps")

        # Filter critical gaps if requested
        if critical_only:
            gaps = [g for g in gaps if g.is_critical]
            logger.info(f"After filtering: {len(gaps)} critical gaps")

        # Print gap summary
        print("\n" + "=" * 60)
        print("GAP SUMMARY")
        print("=" * 60)

        for i, gap in enumerate(gaps[:20], 1):  # Show first 20
            critical_marker = " [CRITICAL]" if gap.is_critical else ""
            print(f"{i:2}. {gap.symbol} - {gap.gap_seconds:.0f}s{critical_marker}")

        if len(gaps) > 20:
            print(f"... and {len(gaps) - 20} more")

        total_gap_seconds = sum(g.gap_seconds for g in gaps)
        critical_count = sum(1 for g in gaps if g.is_critical)
        print(f"\nTotal gap time: {total_gap_seconds:.0f}s ({total_gap_seconds/3600:.2f}h)")
        print(f"Critical gaps: {critical_count}/{len(gaps)}")
        print("=" * 60)

        if detect or dry_run:
            logger.info("Dry run - no gaps filled")
            return 0

        # Fill gaps
        logger.info(f"Filling {len(gaps)} gaps...")

        async with GapFiller(db_pool=db_pool, binance_api_key=binance_api_key) as filler:
            results = await filler.fill_gaps_batch(gaps, max_concurrent=max_concurrent)

        # Print results
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_ticks = sum(r.ticks_filled for r in results if r.success)

        print("\n" + "=" * 60)
        print("GAP FILL RESULTS")
        print("=" * 60)
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Total ticks fetched: {total_ticks}")

        if failed > 0:
            print("\nFailed gaps:")
            for r in results:
                if not r.success:
                    print(f"  - {r.gap.symbol}: {r.error}")

        print("=" * 60)

        # Get stats
        stats = filler.get_stats()
        logger.info(f"Stats: {stats}")

        if failed > 0:
            logger.warning(f"Gap fill completed with {failed} failures")
            return 1

        logger.info("Gap fill complete!")
        return 0

    except Exception as e:
        logger.error(f"Gap fill failed: {e}", exc_info=True)
        return 1

    finally:
        if db_pool:
            await db_pool.close()


async def detect_gaps(
    db_pool: asyncpg.Pool,
    symbol: Optional[str],
    hours: int = 24,
) -> list[DataGap]:
    """
    Detect gaps in database.

    Args:
        db_pool: Database pool
        symbol: Filter by symbol
        hours: Look back hours

    Returns:
        List of detected gaps
    """
    async with db_pool.acquire() as conn:
        # Get all trades in time range
        if symbol:
            # Get symbol ID
            symbol_row = await conn.fetchrow(
                "SELECT id, symbol FROM symbols WHERE symbol = $1",
                symbol
            )
            if not symbol_row:
                logger.warning(f"Symbol not found: {symbol}")
                return []

            symbol_id = symbol_row['id']
            symbol_str = symbol_row['symbol']

            rows = await conn.fetch(
                """
                SELECT time
                FROM trades
                WHERE symbol_id = $1
                AND time > NOW() - INTERVAL '%s hours'
                ORDER BY time
                """ % hours,
                symbol_id,
            )

            times = [row['time'] for row in rows]
            gaps = []

            for i in range(1, len(times)):
                gap_seconds = (times[i] - times[i-1]).total_seconds()
                if gap_seconds > 5:  # Gap threshold
                    gaps.append(DataGap(
                        symbol_id=symbol_id,
                        symbol=symbol_str,
                        gap_start=times[i-1],
                        gap_end=times[i],
                        gap_seconds=gap_seconds,
                    ))

            return gaps

        else:
            # All symbols
            rows = await conn.fetch(
                """
                SELECT
                    t.symbol_id,
                    s.symbol,
                    t.time,
                    LAG(t.time) OVER (PARTITION BY t.symbol_id ORDER BY t.time) as prev_time
                FROM trades t
                JOIN symbols s ON s.id = t.symbol_id
                WHERE t.time > NOW() - INTERVAL '%s hours'
                ORDER BY t.symbol_id, t.time
                """ % hours,
            )

            gaps = []
            for row in rows:
                if row['prev_time'] is None:
                    continue

                gap_seconds = (row['time'] - row['prev_time']).total_seconds()
                if gap_seconds > 5:  # Gap threshold
                    gaps.append(DataGap(
                        symbol_id=row['symbol_id'],
                        symbol=row['symbol'],
                        gap_start=row['prev_time'],
                        gap_end=row['time'],
                        gap_seconds=gap_seconds,
                    ))

            return gaps


if __name__ == '__main__':
    main()
