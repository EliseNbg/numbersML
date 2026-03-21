#!/usr/bin/env python3
"""
Asset Sync CLI - Manual and scheduled asset synchronization.

Synchronizes symbol metadata from Binance API.

Usage:
    # Dry run (see what would change)
    python -m src.cli.sync_assets --dry-run

    # Actual sync
    python -m src.cli.sync_assets

    # With custom database URL
    python -m src.cli.sync_assets --db-url postgresql://user:pass@localhost/db
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import asyncpg
import click

from src.application.services.asset_sync_service import AssetSyncService, AssetSyncError

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
    help='Database URL (default: postgresql://crypto:crypto@localhost:5432/crypto_trading)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be synced without making changes'
)
@click.option(
    '--no-auto-activate',
    is_flag=True,
    help='Do not auto-activate new symbols'
)
@click.option(
    '--auto-deactivate',
    is_flag=True,
    help='Auto-deactivate delisted symbols'
)
@click.option(
    '--no-eu-compliance',
    is_flag=True,
    help='Disable EU compliance filtering'
)
@click.option(
    '--verbose',
    '-v',
    is_flag=True,
    help='Enable verbose logging'
)
def main(
    db_url: str,
    dry_run: bool,
    no_auto_activate: bool,
    auto_deactivate: bool,
    no_eu_compliance: bool,
    verbose: bool,
) -> None:
    """
    Synchronize symbol metadata from Binance API.

    Fetches exchange info from Binance and updates the database
    with latest symbol metadata including:

    \b
    - Trading pairs (BTC/USDT, ETH/USDC, etc.)
    - Tick size (price precision)
    - Step size (quantity precision)
    - Minimum notional value
    - EU compliance status
    - Active/inactive status

    Examples:

    \b
    # Dry run (preview changes)
    python -m src.cli.sync_assets --dry-run

    # Actual sync
    python -m src.cli.sync_assets

    # Auto-deactivate delisted symbols
    python -m src.cli.sync_assets --auto-deactivate

    # Disable EU filtering (for non-EU users)
    python -m src.cli.sync_assets --no-eu-compliance
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting Asset Sync CLI")

    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")

    # Run sync
    exit_code = asyncio.run(
        run_sync(
            db_url=db_url,
            dry_run=dry_run,
            auto_activate=not no_auto_activate,
            auto_deactivate=auto_deactivate,
            eu_compliance=not no_eu_compliance,
        )
    )

    sys.exit(exit_code)


async def run_sync(
    db_url: str,
    dry_run: bool,
    auto_activate: bool,
    auto_deactivate: bool,
    eu_compliance: bool,
) -> int:
    """
    Run asset synchronization.

    Args:
        db_url: Database URL
        dry_run: If True, don't make changes
        auto_activate: Auto-activate new symbols
        auto_deactivate: Auto-deactivate delisted symbols
        eu_compliance: Apply EU compliance filtering

    Returns:
        Exit code (0 for success, 1 for error)
    """
    db_pool: Optional[asyncpg.Pool] = None

    try:
        # Create database pool
        logger.info(f"Connecting to database: {db_url.split('@')[-1]}")
        db_pool = await asyncpg.create_pool(
            dsn=db_url,
            min_size=2,
            max_size=5,
            timeout=30,
        )

        # Create service
        service = AssetSyncService(
            db_pool=db_pool,
            auto_activate=auto_activate,
            auto_deactivate_delisted=auto_deactivate,
            eu_compliance=eu_compliance,
        )

        if dry_run:
            # Dry run - just fetch and display
            logger.info("Fetching exchange info from Binance...")
            symbols_data = await service._fetch_exchange_info()
            logger.info(f"Found {len(symbols_data)} trading pairs on Binance")

            # Count by quote asset
            quote_assets: dict[str, int] = {}
            for s in symbols_data:
                quote = s.get('quoteAsset', 'UNKNOWN')
                quote_assets[quote] = quote_assets.get(quote, 0) + 1

            logger.info("Quote asset distribution:")
            for quote, count in sorted(quote_assets.items()):
                logger.info(f"  {quote}: {count}")

            # Check EU compliance
            if eu_compliance:
                allowed = sum(
                    1 for s in symbols_data
                    if service._check_eu_compliance(s.get('quoteAsset', ''))
                )
                logger.info(f"EU compliant symbols: {allowed}/{len(symbols_data)}")

            logger.info("DRY RUN complete - no changes made")

        else:
            # Actual sync
            stats = await service.sync()

            logger.info("Sync Statistics:")
            logger.info(f"  Fetched: {stats['fetched']}")
            logger.info(f"  Added: {stats['added']}")
            logger.info(f"  Updated: {stats['updated']}")
            logger.info(f"  Deactivated: {stats['deactivated']}")
            logger.info(f"  Errors: {stats['errors']}")

            if stats['errors'] > 0:
                logger.warning(f"Sync completed with {stats['errors']} errors")
                return 1

        logger.info("Asset sync complete")
        return 0

    except AssetSyncError as e:
        logger.error(f"Asset sync failed: {e.message}")
        return 1

    except asyncpg.PostgresError as e:
        logger.error(f"Database error: {e}")
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1

    finally:
        # Close database pool
        if db_pool is not None:
            await db_pool.close()
            logger.debug("Database pool closed")


if __name__ == '__main__':
    main()
