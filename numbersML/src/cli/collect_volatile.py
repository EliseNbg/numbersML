#!/usr/bin/env python3
"""
Start data collection for the 5 most volatile symbols.

This script:
1. Fetches current volatile symbols from Binance
2. Creates/updates database
3. Starts the data collector
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import aiohttp
import asyncpg
import websockets

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def get_volatile_symbols(limit: int = 5) -> list[str]:
    """Get most volatile symbols from Binance with minimum volume."""
    url = "https://api.binance.com/api/v3/ticker/24hr"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    symbols = []
    for ticker in data:
        quote = ticker["symbol"][-4:]
        if quote not in ["USDT", "USDC"]:
            continue
        base = ticker["symbol"][:-4]
        if base in ["USDT", "USDC", "BUSD", "TUSD", "DAI", "FDUSD"]:
            continue
        try:
            high = Decimal(ticker["highPrice"])
            low = Decimal(ticker["lowPrice"])
            open_p = Decimal(ticker["openPrice"])
            volume = Decimal(ticker["quoteVolume"])
            # Require minimum $500k volume for liquid symbols
            if open_p > 0 and volume > 500000:
                vol = ((high - low) / open_p) * 100
                symbols.append(
                    {
                        "symbol": f"{base}/{quote}",
                        "binance_symbol": ticker["symbol"],
                        "volatility": float(vol),
                    }
                )
        except:
            continue

    symbols.sort(key=lambda x: x["volatility"], reverse=True)
    return [s["symbol"] for s in symbols[:limit]]


async def _init_utc(conn):
    await conn.execute("SET timezone = 'UTC'")


async def setup_database(db_url: str, symbols: list[str]) -> dict[str, int]:
    """Setup database and register symbols."""
    pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10, init=_init_utc)

    symbol_ids = {}

    async with pool.acquire() as conn:
        for symbol in symbols:
            base, quote = symbol.split("/")

            # Insert or update symbol (matching actual schema)
            row = await conn.fetchrow(
                """
                INSERT INTO symbols (symbol, base_asset, quote_asset,
                                    tick_size, step_size, min_notional, is_allowed, is_active)
                VALUES ($1, $2, $3, 0.00000001, 0.00000001, 10, true, true)
                ON CONFLICT (symbol) DO UPDATE SET
                    is_active = true,
                    is_allowed = true,
                    updated_at = NOW()
                RETURNING id
                """,
                symbol,
                base,
                quote,
            )
            symbol_ids[symbol] = row["id"]
            logger.info(f"Registered symbol: {symbol} (ID: {row['id']})")

    await pool.close()
    return symbol_ids


class DataCollector:
    """Simple data collector for volatile symbols."""

    def __init__(
        self,
        db_url: str,
        symbols: list[str],
        batch_size: int = 5,  # Very small for immediate storage
        batch_interval: float = 5.0,  # Flush every 5 seconds
    ) -> None:
        self.db_url = db_url
        self.symbols = symbols
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.db_pool = None
        self.running = False
        self.stats = {"trades": 0, "errors": 0}

    async def start(self) -> None:
        """Start collection."""
        logger.info(f"Starting collection for {len(self.symbols)} symbols: {self.symbols}")

        # Setup database
        self.db_pool = await asyncpg.create_pool(
            self.db_url, min_size=5, max_size=20, init=_init_utc
        )
        await setup_database(self.db_url, self.symbols)

        # Build WebSocket URL
        streams = "/".join([f"{s.lower().replace('/', '')}@trade" for s in self.symbols])
        ws_url = f"wss://stream.binance.com:9443/ws/{streams}"

        self.running = True
        buffer = []
        last_flush = datetime.now()

        logger.info(f"Connecting to {ws_url}")

        async with websockets.connect(ws_url) as ws:
            logger.info("WebSocket connected - collecting data...")

            while self.running:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1)
                    data = json.loads(msg)

                    if data.get("e") != "trade":
                        continue

                    # Parse trade
                    symbol = data["s"]
                    # Convert BTCUSDT -> BTC/USDT
                    for s in self.symbols:
                        if s.replace("/", "") == symbol:
                            symbol = s
                            break

                    trade = {
                        "time": datetime.fromtimestamp(data["T"] / 1000, tz=UTC),
                        "symbol": symbol,
                        "trade_id": str(data["t"]),
                        "price": Decimal(data["p"]),
                        "quantity": Decimal(data["q"]),
                        "side": "SELL" if data["m"] else "BUY",
                        "is_buyer_maker": data["m"],
                    }
                    buffer.append(trade)
                    self.stats["trades"] += 1

                    # Batch insert
                    if len(buffer) >= self.batch_size:
                        await self._store_trades(buffer)
                        logger.info(f"Stored {len(buffer)} trades (total: {self.stats['trades']})")
                        buffer = []

                    # Timed flush
                    elif (datetime.now() - last_flush).total_seconds() >= self.batch_interval:
                        if buffer:
                            await self._store_trades(buffer)
                            logger.info(
                                f"Timed flush: {len(buffer)} trades (total: {self.stats['trades']})"
                            )
                            buffer = []
                        last_flush = datetime.now()

                except asyncio.TimeoutError:
                    await ws.ping()
                    # Timed flush on timeout too
                    if (
                        buffer
                        and (datetime.now() - last_flush).total_seconds() >= self.batch_interval
                    ):
                        await self._store_trades(buffer)
                        logger.info(
                            f"Timeout flush: {len(buffer)} trades (total: {self.stats['trades']})"
                        )
                        buffer = []
                        last_flush = datetime.now()
                except Exception as e:
                    self.stats["errors"] += 1
                    logger.error(f"Error: {e}")

                    if buffer:
                        await self._store_trades(buffer)
                        buffer = []

        # Final flush
        if buffer:
            await self._store_trades(buffer)

    async def _store_trades(self, trades: list[dict]) -> None:
        """Store trades in database."""
        if not trades:
            return

        stored = 0
        errors = 0

        async with self.db_pool.acquire() as conn:
            for trade in trades:
                try:
                    # Get symbol ID
                    row = await conn.fetchrow(
                        "SELECT id, is_active FROM symbols WHERE symbol = $1", trade["symbol"]
                    )
                    if not row:
                        logger.warning(f"Symbol not found: {trade['symbol']}")
                        errors += 1
                        continue

                    if not row["is_active"]:
                        logger.warning(f"Symbol not active: {trade['symbol']}")
                        continue

                    await conn.execute(
                        """
                        INSERT INTO trades (time, symbol_id, trade_id, price, quantity, is_buyer_maker)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (trade_id, symbol_id) DO NOTHING
                        """,
                        trade["time"],
                        row["id"],
                        int(trade["trade_id"]),  # Convert to int for bigint column
                        trade["price"],
                        trade["quantity"],
                        trade["is_buyer_maker"],
                    )
                    stored += 1
                except Exception as e:
                    logger.error(f"Error storing trade: {e} - {trade}")
                    errors += 1

        if stored > 0:
            logger.info(f"Database stored: {stored} trades, errors: {errors}")

        logger.info(f"Stored {len(trades)} trades (total: {self.stats['trades']})")

    async def stop(self) -> None:
        """Stop collection."""
        self.running = False
        if self.db_pool:
            await self.db_pool.close()


async def main() -> None:
    """Main entry point."""
    # Use same password as docker-compose-infra.yml (POSTGRES_PASSWORD=crypto_secret)
    db_url = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

    print("=" * 70)
    print("Crypto Trading System - Data Collection")
    print("=" * 70)
    print()

    # Get volatile symbols
    print("Fetching most volatile symbols from Binance...")
    symbols = await get_volatile_symbols(5)
    print(f"Top 5 volatile symbols: {symbols}")
    print()

    # Start collector
    collector = DataCollector(db_url, symbols)

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


if __name__ == "__main__":
    asyncio.run(main())
