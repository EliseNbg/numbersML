# Wide Vector Generator

## Overview

The Wide Vector Generator creates a flat feature vector from all active symbols'
candle data and technical indicators. One vector is generated per second after
all candles for that round are processed. Stored in DB for backtesting and
ML model training.

## Data Flow

```
_ticker_loop (every 1s)
  -> tick_all() -> _on_candle(BTC) -> write candle + indicators
                  -> _on_candle(ETH) -> write candle + indicators
                  -> _on_candle(DOGE) -> write candle + indicators
                  -> _on_candle(ADA) -> write candle + indicators
                  -> (all done)
  -> WideVectorService.generate(candle_time)
     -> reads candles_1s + candle_indicators from DB
     -> builds flat vector
     -> INSERT INTO wide_vectors
     -> UPDATE candles_1s SET processed = true
```

## Vector Format

Per symbol (sorted alphabetically by symbol name):

```
[close, volume, atr, ema, histogram, lower, macd, middle, rsi, signal, sma, std, upper]
```

Full vector (all symbols concatenated):

```
[BTC/USDC_close, BTC/USDC_volume, BTC/USDC_atr, ..., ETH/USDC_close, ETH/USDC_volume, ...]
```

Example with 2 symbols, 2 indicators (rsi, sma):

```
[67000, 1.5, 65.0, 66900, 3500, 10.0, 45.0, 3480]
 [sym1_close, sym1_vol, sym1_rsi, sym1_sma, sym2_close, sym2_vol, sym2_rsi, sym2_sma]
```

## Database Schema

### `candles_1s` - new column

```sql
processed BOOLEAN NOT NULL DEFAULT false
```

Set to `true` after indicators and wide vector are calculated for that
(symbol_id, time) pair. Allows recalculation of unprocessed rows.

### `wide_vectors` table

| Column            | Type         | Description                    |
|-------------------|-------------|--------------------------------|
| time              | TIMESTAMPTZ | Candle timestamp (PK)          |
| vector            | JSONB       | Flat float array               |
| column_names      | TEXT[]      | Column names matching vector   |
| symbols           | TEXT[]      | Symbol names in order          |
| vector_size       | INTEGER     | Number of floats in vector     |
| symbol_count      | INTEGER     | Number of symbols              |
| indicator_count   | INTEGER     | Indicators per symbol          |
| created_at        | TIMESTAMP   | Row creation time              |

## CLI Commands

### Full recalculation (reset + indicators + vectors)

```bash
python3 -m src.cli.recalculate --all \
    --from "2026-03-29 00:00:00" \
    --to "2026-03-29 01:00:00"
```

### Reset processed flag only

```bash
python3 -m src.cli.recalculate --reset \
    --from "2026-03-29 00:00:00" \
    --to "2026-03-29 01:00:00"
```

### Recalculate indicators only

```bash
python3 -m src.cli.recalculate --indicators \
    --from "2026-03-29 00:00:00"
```

### Recalculate wide vectors only (requires indicators to exist)

```bash
python3 -m src.cli.recalculate --vectors \
    --from "2026-03-29 00:00:00"
```

### Recalculate specific symbols

```bash
python3 -m src.cli.recalculate --all \
    --symbols "BTC/USDC,ETH/USDC" \
    --from "2026-03-29 00:00:00"
```

## Recalculation Workflow

When new indicators are added:

1. Add new indicator to `indicator_definitions` table
2. Run recalculation:

```bash
# Reset processed flag
python3 -m src.cli.recalculate --reset --from "2026-03-20 00:00:00"

# Recalculate indicators (reads 200 candles of history per symbol)
python3 -m src.cli.recalculate --indicators --from "2026-03-20 00:00:00"

# Regenerate wide vectors with new indicator columns
python3 -m src.cli.recalculate --vectors --from "2026-03-20 00:00:00"
```

## Python API

```python
from src.pipeline.wide_vector_service import WideVectorService

service = WideVectorService(db_pool)
await service.load_symbols()

# Generate vector for specific time
result = await service.generate(candle_time)
# result = {
#     'time': datetime(...),
#     'vector': [67000.0, 1.5, 65.0, ...],
#     'column_names': ['BTC/USDC_close', 'BTC/USDC_volume', ...],
#     'symbol_count': 4,
#     'indicator_count': 8,
#     'vector_size': 52,
# }

# Read stored vector
stored = await service.get_vector(candle_time)
```

## Querying for ML Training

```sql
-- Get all vectors in a time range
SELECT time, vector, column_names
FROM wide_vectors
WHERE time >= '2026-03-29 00:00:00' AND time < '2026-03-29 01:00:00'
ORDER BY time;

-- Get vectors for unprocessed candles
SELECT c.time, s.symbol
FROM candles_1s c
JOIN symbols s ON s.id = c.symbol_id
WHERE c.processed = false
ORDER BY c.time;

-- Get wide vector with related candle data
SELECT w.time, w.vector, w.column_names,
       c.close as btc_close
FROM wide_vectors w
JOIN candles_1s c ON c.time = w.time
JOIN symbols s ON s.id = c.symbol_id AND s.symbol = 'BTC/USDC'
WHERE w.time >= '2026-03-29 00:00:00'
ORDER BY w.time;
```

## Using in ML Model

```python
import json
import numpy as np
import asyncpg

async def load_training_data(db_url, from_time, to_time):
    conn = await asyncpg.connect(db_url)
    rows = await conn.fetch(
        "SELECT vector, column_names FROM wide_vectors "
        "WHERE time >= $1 AND time < $2 ORDER BY time",
        from_time, to_time
    )
    await conn.close()

    # Build matrix: (N_timesteps, N_features)
    vectors = [json.loads(r['vector']) for r in rows]
    column_names = list(rows[0]['column_names']) if rows else []
    return np.array(vectors, dtype=np.float32), column_names
```
