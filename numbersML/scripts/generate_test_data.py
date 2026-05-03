"""
Generate synthetic test data for Grid Algorithm.

Creates noised sin wave price data for TEST/USDT.
The oscillation allows Grid Algorithm to generate positive PnL.

Usage:
    .venv/bin/python scripts/generate_test_data.py
"""

import asyncio
import json
import logging
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import pi, sin

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
SYMBOL = "TEST/USDT"
BASE_PRICE = 100.0  # Base price
AMPLITUDE = 2.0  # Sin wave amplitude ($2 → 4% range)
NUM_CANDLES = 5000  # Number of 1-second candles
NOISE_LEVEL = 0.3  # Price noise (±$0.30)

# Grid Algorithm works best with 1-2% oscillations
# At $100 base, amplitude=2 means $98-$102 range


async def generate_data():
    """Generate and insert test data."""
    # Get DB connection
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="crypto",
        password="crypto_secret",
        database="crypto_trading",
    )

    try:
        # 1. Ensure TEST/USDT symbol exists (is_test=True)
        await conn.execute(
            """
            INSERT INTO symbols (symbol, base_asset, quote_asset, status, is_active, is_allowed, is_test)
            VALUES ($1, $2, $3, 'TRADING', true, true, true)
            ON CONFLICT (symbol) DO UPDATE SET is_test = true
            """,
            SYMBOL,
            SYMBOL.split("/")[0],  # BASE/QUOTE
            SYMBOL.split("/")[1],
        )

        symbol_id = await conn.fetchval(
            "SELECT id FROM symbols WHERE symbol = $1",
            SYMBOL,
        )
        logger.info(f"Symbol {SYMBOL} has ID {symbol_id}")

        # 2. Ensure ConfigurationSet exists for Grid Algorithm
        config_dict = {
            "symbols": [SYMBOL],
            "grid_levels": 5,
            "grid_spacing_pct": 1.0,
            "quantity": 0.01,
            "initial_balance": 10000.0,
            "risk": {
                "max_position_size_pct": 10,
                "max_daily_loss_pct": 5,
                "stop_loss_pct": 2.0,
                "take_profit_pct": 0.5,
            },
            "execution": {
                "order_type": "market",
                "slippage_bps": 10,
                "fee_bps": 10,
            },
        }
        config_set_id = await conn.fetchval(
            """
            INSERT INTO configuration_sets (name, description, config, is_active)
            VALUES ($1, $2, $3, true)
            ON CONFLICT (name) DO UPDATE SET config = EXCLUDED.config
            RETURNING id
            """,
            "Grid TEST/USDT Default",
            "Default grid configuration for TEST/USDT with noised sin wave",
            json.dumps(config_dict),
        )
        logger.info(f"ConfigurationSet created with ID {config_set_id}")

        # 3. Generate candles with noised sin wave
        logger.info(f"Generating {NUM_CANDLES} candles...")

        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Clear existing candles for this symbol
        await conn.execute(
            "DELETE FROM candles_1s WHERE symbol_id = $1",
            symbol_id,
        )
        await conn.execute(
            "DELETE FROM candle_indicators WHERE symbol_id = $1",
            symbol_id,
        )

        candles = []
        for i in range(NUM_CANDLES):
            # Sin wave: period = 1000 seconds (16.67 minutes)
            t = i / 1000.0 * 2 * pi
            pure_price = BASE_PRICE + AMPLITUDE * sin(t)

            # Add noise
            noise = random.uniform(-NOISE_LEVEL, NOISE_LEVEL)
            price = pure_price + noise

            # Create candle (open/close near price, high/low spread)
            spread = random.uniform(0.01, 0.05)
            candle_time = base_time + timedelta(seconds=i)
            candle = {
                "time": candle_time,
                "symbol_id": symbol_id,
                "open": Decimal(str(price - spread / 2)),
                "high": Decimal(str(price + spread)),
                "low": Decimal(str(price - spread)),
                "close": Decimal(str(price + spread / 2)),
                "volume": Decimal(str(random.uniform(1.0, 10.0))),
                "quote_volume": Decimal(str(price * random.uniform(1.0, 10.0))),
                "trade_count": random.randint(1, 100),
            }
            candles.append(candle)

        # Batch insert candles
        await conn.copy_records_to_table(
            "candles_1s",
            records=[
                (
                    c["time"],
                    c["symbol_id"],
                    c["open"],
                    c["high"],
                    c["low"],
                    c["close"],
                    c["volume"],
                    c["quote_volume"],
                    c["trade_count"],
                )
                for c in candles
            ],
            columns=[
                "time",
                "symbol_id",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trade_count",
            ],
        )
        logger.info(f"Inserted {len(candles)} candles")

        # 4. Generate indicators (simplified - just RSI-like value)
        # In production, these would be calculated by the pipeline
        logger.info("Generating indicators...")

        indicator_records = []
        for candle in candles:
            # Simulate RSI (lower when price < 100, higher when price > 100)
            price = float(candle["close"])
            if price < 99:
                rsi = random.uniform(25, 35)  # Oversold
            elif price > 101:
                rsi = random.uniform(65, 75)  # Overbought
            else:
                rsi = random.uniform(45, 55)  # Neutral

            indicator_records.append(
                (
                    candle["time"],
                    candle["symbol_id"],
                    candle["close"],
                    candle["volume"],
                    json.dumps(
                        {
                            "rsiindicator_period14_rsi": {"value": rsi},
                            "smaindicator_period20_sma": {"value": price},
                        }
                    ),
                )
            )

        await conn.copy_records_to_table(
            "candle_indicators",
            records=indicator_records,
            columns=["time", "symbol_id", "price", "volume", "values"],
        )
        logger.info(f"Inserted {len(indicator_records)} indicator records")

        # 5. Verify the data
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1",
            symbol_id,
        )
        logger.info(f"Total candles for {SYMBOL}: {count}")

        # Show price range
        row = await conn.fetchrow(
            """
            SELECT MIN(close) as min_price, MAX(close) as max_price
            FROM candles_1s
            WHERE symbol_id = $1
            """,
            symbol_id,
        )
        logger.info(f"Price range: ${row['min_price']:.2f} - ${row['max_price']:.2f}")

        logger.info("Test data generation complete!")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(generate_data())
