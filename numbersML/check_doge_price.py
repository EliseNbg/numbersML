import asyncio
import os
from datetime import datetime
import logging
from decimal import Decimal

from src.infrastructure.database.connection import DatabaseConnection

logging.basicConfig(level=logging.INFO)

async def check_price():
    dsn = os.getenv("DATABASE_URL", "postgresql://crypto:crypto_secret@localhost/crypto_trading")
    db = DatabaseConnection(dsn=dsn)
    await db.connect()
    
    symbol = "DOGE/USDC"
    
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MIN(c.time) as min_t, MAX(c.time) as max_t, COUNT(*) as cnt
            FROM candles_1s c
            JOIN symbols s ON s.id = c.symbol_id
            WHERE s.symbol = $1
            """,
            symbol,
        )
        if row and row['cnt'] > 0:
            print(f"DOGE/USDC data: {row['cnt']} candles from {row['min_t']} to {row['max_t']}")
            
            # Get first and last price
            first_p = await conn.fetchval("SELECT close FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id WHERE s.symbol = $1 ORDER BY time ASC LIMIT 1", symbol)
            last_p = await conn.fetchval("SELECT close FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id WHERE s.symbol = $1 ORDER BY time DESC LIMIT 1", symbol)
            print(f"First price: {first_p}, Last price: {last_p}")
        else:
            print("No DOGE/USDC data found.")
            
            # Check what symbols ARE available
            symbols = await conn.fetch("SELECT symbol FROM symbols")
            print(f"Available symbols: {[s['symbol'] for s in symbols]}")
            
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_price())
