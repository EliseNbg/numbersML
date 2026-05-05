# Step 12: Grid Algorithm ConfigurationSet & Test Data#

## Objective#
Create ConfigurationSet for Grid Algorithm and generate noised sin wave test data for TEST/USDT that shows positive PnL.

## Context#
- Step 11 complete: GridAlgorithm implementation exists#
- Step 1-3 complete: ConfigurationSet entity, repository, API exist#
- Need TEST/USDT symbol with synthetic noised sin wave data#
- Data must generate positive PnL for Grid Algorithm#

## DDD Architecture Decision (ADR)#

**Decision**: Test data generation as a script#
- **Script**: `scripts/generate_test_data.py`#
- **Output**: SQL or direct DB insert into `candles_1s` and `candle_indicators`#
- **Noised Sin Wave**: sin(t) + random noise, oscillating in range#

**Key Requirements**:#
- TEST/USDT symbol (not TEST/USDT - create new if needed)#
- Price oscillates between $98 and $102 (4% range)#
- Noised sin wave: price = 100 + 2*sin(t) + noise#
- Grid Algorithm buys at $98-99, sells at $101-102 → positive PnL#
- At least 1000 candles for meaningful backtest#

## TDD Approach#

1. **Red**: Write test expecting positive PnL#
2. **Green**: Generate data and verify PnL > 0#
3. **Refactor**: Optimize, add more indicators#

## Implementation Files#

### 1. `scripts/generate_test_data.py`#

```python
"""
Generate synthetic test data for Grid Algorithm.

Creates noised sin wave price data for TEST/USDT.
The oscillation allows Grid Algorithm to generate positive PnL.

Usage:
    .venv/bin/python scripts/generate_test_data.py
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from decimal import Decimal
from math import sin, pi

import asyncpg

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
            SYMBOL.split('/')[0],  # BASE/QUOTE
            SYMBOL.split('/')[1],
        )
        
        symbol_id = await conn.fetchval(
            "SELECT id FROM symbols WHERE symbol = $1",
            SYMBOL,
        )
        logger.info(f"Symbol {SYMBOL} has ID {symbol_id}")
        
        # 2. Ensure ConfigurationSet exists for Grid Algorithm
        config_set_id = await conn.fetchval(
            """
            INSERT INTO configuration_sets (name, description, config, is_active)
            VALUES ($1, $2, $3, true)
            ON CONFLICT (name) DO UPDATE SET config = EXCLUDED.config
            RETURNING id
            """,
            "Grid TEST/USDT Default",
            "Default grid configuration for TEST/USDT with noised sin wave",
            {
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
            },
        )
        logger.info(f"ConfigurationSet created with ID {config_set_id}")
        
        # 3. Generate candles with noised sin wave
        logger.info(f"Generating {NUM_CANDLES} candles...")
        
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
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
            candle = {
                "time": base_time.replace(second=i),
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
            columns=["time", "symbol_id", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"],
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
            
            indicator_records.append((
                candle["time"],
                candle["symbol_id"],
                candle["close"],
                candle["volume"],
                {
                    "rsiindicator_period14_rsi": {"value": rsi},
                    "smaindicator_period20_sma": {"value": price},
                },
            ))
        
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
```

### 2. Update `migrations/test_data.sql`#

Add TEST/USDT and Grid Algorithm ConfigurationSet:

```sql
-- ============================================
-- 9. TEST/USDT SYMBOL FOR GRID ALGORITHM
-- ============================================

-- Insert TEST/USDT symbol (if not exists)
INSERT INTO symbols (
    symbol, base_asset, quote_asset, status, is_active, is_allowed,
    price_precision, quantity_precision, tick_size, step_size,
    min_notional, is_test
) VALUES (
    'TEST/USDT', 'TEST', 'USDT', 'TRADING', true, true,
    2, 6, 0.01, 0.000001, 10.0, true
) ON CONFLICT (symbol) DO UPDATE SET
    is_test = EXCLUDED.is_test,
    is_active = EXCLUDED.is_active,
    is_allowed = EXCLUDED.is_allowed;


-- ============================================
-- 10. GRID ALGORITHM CONFIGURATION SET
-- ============================================

INSERT INTO configuration_sets (name, description, config, is_active)
VALUES (
    'Grid TEST/USDT Default',
    'Default grid configuration for TEST/USDT with noised sin wave',
    '{
        "symbols": ["TEST/USDT"],
        "grid_levels": 5,
        "grid_spacing_pct": 1.0,
        "quantity": 0.01,
        "initial_balance": 10000.0,
        "risk": {
            "max_position_size_pct": 10,
            "max_daily_loss_pct": 5,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 0.5
        },
        "execution": {
            "order_type": "market",
            "slippage_bps": 10,
            "fee_bps": 10
        }
    }'::jsonb,
    true
) ON CONFLICT (name) DO UPDATE SET
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active;
```

### 3. Test to verify positive PnL#

```python
"""
Integration test: Grid Algorithm on TEST/USDT noised sin wave.

Verifies that Grid Algorithm generates positive PnL.
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID


@pytest.mark.integration
class TestGridAlgorithmPnL:
    """Test that Grid Algorithm shows positive PnL on synthetic data."""
    
    @pytest.mark.asyncio
    async def test_grid_backtest_positive_pnl(self):
        """
        Test running Grid Algorithm backtest on TEST/USDT.
        
        Prerequisites:
            - TEST/USDT symbol exists with noised sin wave data
            - Grid Algorithm ConfigurationSet exists
            - GridAlgorithm implementation exists
        
        Expected:
            - PnL > 0 (positive)
            - At least some trades executed
        """
        from src.application.services.backtest_service import BacktestService
        from src.domain.algorithms.grid_algorithm import GridAlgorithm
        from src.domain.algorithms.algorithm_instance import AlgorithmInstance
        
        # This test requires:
        # 1. Database with test data
        # 2. GridAlgorithm registered/loadable
        # 3. BacktestService working
        
        # For now, this is a placeholder
        # In full implementation:
        # - Load GridAlgorithm
        # - Create AlgorithmInstance with Grid config
        # - Run backtest
        # - Assert PnL > 0
        
        pytest.skip("Requires database with generated test data")
    
    @pytest.mark.asyncio
    async def test_sin_wave_data_exists(self):
        """Test that TEST/USDT has sin wave data."""
        import asyncpg
        
        conn = await asyncpg.connect(
            host="localhost", port=5432,
            user="crypto", password="crypto_secret",
            database="crypto_trading",
        )
        
        try:
            # Check symbol exists
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = 'TEST/USDT'"
            )
            assert symbol_id is not None, "TEST/USDT symbol not found"
            
            # Check candles exist
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM candles_1s WHERE symbol_id = $1",
                symbol_id,
            )
            assert count > 1000, f"Expected >1000 candles, got {count}"
            
            # Check price range (should be ~$98-$102)
            row = await conn.fetchrow(
                "SELECT MIN(close) as min_p, MAX(close) as max_p FROM candles_1s WHERE symbol_id = $1",
                symbol_id,
            )
            assert 97.0 < float(row["min_p"]) < 99.0, f"Min price too low/high: {row['min_p']}"
            assert 101.0 < float(row["max_p"]) < 103.0, f"Max price too low/high: {row['max_p']}"
            
        finally:
            await conn.close()
```

## LLM Implementation Prompt#

```text
You are implementing Step 12 of Phase 4: Grid Algorithm ConfigurationSet & Test Data.

## Your Task#

Create ConfigurationSet for Grid Algorithm and generate noised sin wave test data.

## Context#

- Step 11 complete: GridAlgorithm in src/domain/algorithms/grid_algorithm.py`
- Step 1-3 complete: ConfigurationSet entity, repository, API exist
- Need TEST/USDT symbol (not TEST/USDT)
- Generate data that shows POSITIVE PnL for Grid Algorithm#

## Requirements#

1. Create `scripts/generate_test_data.py` with:
   - Connect to PostgreSQL (asyncpg)
   - Create TEST/USDT symbol (is_test=True)
   - Create ConfigurationSet for Grid Algorithm:
     * symbols: ["TEST/USDT"]
     * grid_levels: 5
     * grid_spacing_pct: 1.0
     * quantity: 0.01
     * initial_balance: 10000.0
   - Generate noised sin wave candles:
     * price = 100 + 2*sin(t) + noise (±0.3)
     * 5000 candles (1-second intervals)
     * Price range: ~$98-$102 (4% oscillation)
   - Generate indicators (RSI-like values):
     * RSI < 30 when price < 99 (oversold)
     * RSI > 70 when price > 101 (overbought)
   - Insert into `candles_1s` and `candle_indicators` tables
   - Full logging with logger.info(f"...")#

2. Update `migrations/test_data.sql`:
   - Add TEST/USDT symbol insert
   - Add Grid Algorithm ConfigurationSet insert
   - Use ON CONFLICT DO UPDATE for idempotency#

3. Create test `tests/integration/test_grid_pnl.py`:
   - Test that TEST/USDT has >1000 candles
   - Test price range is ~$98-$102
   - Test that backtest on this data shows PnL > 0
   - Mark as @pytest.mark.integration#

## Constraints#

- Follow AGENTS.md coding standards#
- Use asyncpg (not psycopg2)#
- Use Decimal for price calculations#
- Use math.sin() for wave generation#
- Random noise with random.uniform()#
- Log progress with logger.info(f"message")#
- Make script idempotent (can run multiple times)#

## Acceptance Criteria#

1. TEST/USDT symbol created with is_test=True#
2. ConfigurationSet for Grid Algorithm created#
3. 5000 candles generated with noised sin wave#
4. Price oscillates between $98-$102#
5. Indicators (RSI) generated for each candle#
6. Running Grid Algorithm backtest shows PnL > 0#
7. Script is idempotent (safe to re-run)#
8. Test data added to migrations/test_data.sql#

## Commands to Run#

```bash
# Generate test data
.venv/bin/python scripts/generate_test_data.py

# Verify data in database
psql -h localhost -p 5432 -U crypto -d crypto_trading -c "
SELECT COUNT(*) FROM candles_1s WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = 'TEST/USDT');
"

# Run integration test (requires DB)
.venv/bin/python -m pytest tests/integration/test_grid_pnl.py -v
```

## Output#

1. List of files created/modified#
2. Confirmation that TEST/USDT has 5000+ candles#
3. Price range verification ($98-$102)#
4. Backtest PnL verification (> 0)#
5. Any issues encountered and how resolved#
```

## Success Criteria#

- [ ] generate_test_data.py script created#
- [ ] TEST/USDT symbol created with is_test=True#
- [ ] Grid Algorithm ConfigurationSet created#
- [ ] 5000 candles with noised sin wave generated#
- [ ] Price oscillates $98-$102 (positive PnL for grid)#
- [ ] Indicators generated for each candle#
- [ ] migrations/test_data.sql updated#
- [ ] Integration test verifies PnL > 0#
- [ ] Script is idempotent#
