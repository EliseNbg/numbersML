#!/usr/bin/env python3
"""
Start Real-Time Trade Pipeline CLI.

Usage:
    python -m src.cli.start_trade_pipeline
    python -m src.cli.start_trade_pipeline --symbols BTC/USDT ETH/USDT
"""

import argparse
import asyncio
import logging
import sys
from typing import List

import asyncpg

from src.pipeline.service import TradePipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Start real-time trade pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with default symbols (from active symbols in DB)
  python -m src.cli.start_trade_pipeline
  
  # Start with specific symbols
  python -m src.cli.start_trade_pipeline --symbols BTC/USDT ETH/USDT
  
  # Start with custom database
  python -m src.cli.start_trade_pipeline --db-url postgresql://user:pass@host/db
        """,
    )
    
    parser.add_argument(
        '--symbols',
        nargs='+',
        default=None,
        help='Symbols to process (default: all active symbols from DB)'
    )
    
    parser.add_argument(
        '--db-url',
        type=str,
        default=DATABASE_URL,
        help=f'Database URL (default: {DATABASE_URL})'
    )
    
    return parser.parse_args()


async def run_pipeline(symbols: List[str], db_url: str) -> None:
    """
    Run trade pipeline.
    
    Args:
        symbols: List of symbols to process
        db_url: Database URL
    """
    # Create database pool
    logger.info(f"Connecting to database: {db_url.split('@')[-1]}")
    db_pool = await asyncpg.create_pool(
        db_url,
        min_size=2,
        max_size=10,
        timeout=30,
    )
    
    try:
        # Get active symbols if not specified
        if not symbols:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT symbol FROM symbols
                    WHERE is_active = true
                    AND is_allowed = true
                    ORDER BY symbol
                    """
                )
                symbols = [row['symbol'] for row in rows]
            
            logger.info(f"Using {len(symbols)} active symbols from database")
        
        # Create and start pipeline
        pipeline = TradePipeline(
            db_pool=db_pool,
            symbols=symbols,
        )
        
        logger.info(f"Starting pipeline with symbols: {symbols}")
        await pipeline.start()
        
    except KeyboardInterrupt:
        logger.info("Pipeline stopped by user")
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
    finally:
        await db_pool.close()
        logger.info("Database connection closed")


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    logger.info("=" * 60)
    logger.info("Starting Real-Time Trade Pipeline")
    logger.info("=" * 60)
    logger.info(f"Database: {args.db_url.split('@')[-1]}")
    logger.info(f"Symbols: {args.symbols or 'All active symbols'}")
    logger.info("=" * 60)
    
    try:
        asyncio.run(run_pipeline(args.symbols or [], args.db_url))
        return 0
    except Exception as e:
        logger.error(f"Failed to start pipeline: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
