import asyncio
import os
from datetime import datetime
import logging
from decimal import Decimal

from src.infrastructure.database.connection import DatabaseConnection

logging.basicConfig(level=logging.INFO)

async def check_volatility():
    dsn = os.getenv("DATABASE_URL", "postgresql://crypto:crypto_secret@localhost/crypto_trading")
    db = DatabaseConnection(dsn=dsn)
    await db.connect()
    
    symbol = "DOGE/USDC"
    
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.close
            FROM candles_1s c
            JOIN symbols s ON s.id = c.symbol_id
            WHERE s.symbol = $1
            ORDER BY time ASC
            """,
            symbol,
        )
        
        prices = [float(r['close']) for r in rows]
        if not prices:
            print("No data.")
            return
            
        min_p = min(prices)
        max_p = max(prices)
        avg_p = sum(prices) / len(prices)
        
        print(f"DOGE/USDC: Min={min_p}, Max={max_p}, Avg={avg_p}")
        print(f"Range %: {(max_p - min_p) / avg_p * 100:.2f}%")
        
        # Calculate standard deviation of returns
        import math
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        avg_return = sum(returns) / len(returns)
        var_return = sum((r - avg_return)**2 for r in returns) / len(returns)
        std_return = math.sqrt(var_return)
        print(f"1s volatility (std dev of returns): {std_return * 100:.6f}%")
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_volatility())
