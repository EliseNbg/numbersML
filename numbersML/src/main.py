#!/usr/bin/env python3
"""
Data Collection Service - Main entry point.

Collects real-time tick data from Binance WebSocket.
"""

import asyncio
import logging

from src.infrastructure.database.connection import DatabaseConnection
from src.infrastructure.exchanges.binance_client import BinanceWebSocketClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point."""
    logger.info("Starting Data Collection Service...")

    # Initialize database
    db = DatabaseConnection(
        dsn="postgresql://crypto:crypto@localhost:5432/crypto_trading",
        min_size=5,
        max_size=20,
    )
    await db.connect()

    # Symbols to collect
    symbols = ["BTC/USDT", "ETH/USDT"]

    # Create client
    client = BinanceWebSocketClient(
        db_pool=db.pool,
        symbols=symbols,
        batch_size=500,
        batch_interval=0.5,
    )

    try:
        # Start collection
        await client.start()

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await client.stop()
        await db.disconnect()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await db.disconnect()
        raise


if __name__ == "__main__":
    asyncio.run(main())
