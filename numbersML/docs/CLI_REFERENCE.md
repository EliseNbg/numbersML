# CLI Reference

Command-line tools for data management, backfilling, gap filling, and recalculation.

## Quick Start

```bash
# 1. Sync symbols from Binance
python3 -m src.cli.asset_sync

# 2. Start live pipeline (candles + indicators + wide vectors)
# Use dashboard: http://localhost:8000

# 3. Backfill historical data
python3 -m src.cli.backfill --days 3

# 4. Recalculate indicators + wide vectors for backfilled data
python3 -m src.cli.recalculate --all --from "2026-03-25 00:00:00"
```

## Pipeline

Start/stop via dashboard at `http://localhost:8000/dashboard/index.html`

Or via API:

```bash
curl -X POST http://localhost:8000/api/pipeline/start
curl -X POST http://localhost:8000/api/pipeline/stop
curl http://localhost:8000/api/pipeline/status
```

## Backfill

Fetches 1-second klines from Binance REST API and writes to `candles_1s`.
Sets `processed=false` so indicators can be recalculated.

```bash
# Backfill last 3 days (default)
python3 -m src.cli.backfill

# Backfill last 7 days
python3 -m src.cli.backfill --days 7

# Backfill specific symbol
python3 -m src.cli.backfill --days 3 --symbol BTC/USDC

# Dry run
python3 -m src.cli.backfill --days 3 --dry-run

# Custom database URL
python3 -m src.cli.backfill --db-url "postgresql://user:pass@host:5432/db"
```

### After Backfill

Backfilled candles have `processed=false`. To compute indicators and wide vectors:

```bash
python3 -m src.cli.recalculate --all --from "YYYY-MM-DD HH:MM:SS"
```

## Gap Fill

Detects missing seconds in `candles_1s` and fills them from Binance.

```bash
# Detect gaps (last 24 hours)
python3 -m src.cli.gap_fill --detect

# Fill all gaps
python3 -m src.cli.gap_fill

# Fill gaps for specific symbol
python3 -m src.cli.gap_fill --symbol BTC/USDC

# Only critical gaps (> 60 seconds)
python3 -m src.cli.gap_fill --critical-only

# Dry run
python3 -m src.cli.gap_fill --dry-run

# Look back 48 hours
python3 -m src.cli.gap_fill --hours 48
```

### After Gap Fill

Filled candles have `processed=false`. Recalculate:

```bash
python3 -m src.cli.recalculate --all --from "YYYY-MM-DD HH:MM:SS"
```

## Recalculate

Resets `processed` flag and recalculates indicators + wide vectors.

```bash
# Full recalculation (reset + indicators + wide vectors)
python3 -m src.cli.recalculate --all --from "2026-03-29 00:00:00" --to "2026-03-29 01:00:00"

# Reset processed flag only
python3 -m src.cli.recalculate --reset --from "2026-03-29 00:00:00"

# Recalculate indicators only
python3 -m src.cli.recalculate --indicators --from "2026-03-29 00:00:00"

# Recalculate wide vectors only (requires indicators to exist)
python3 -m src.cli.recalculate --vectors --from "2026-03-29 00:00:00"

# Specific symbols only
python3 -m src.cli.recalculate --all --symbols "BTC/USDC,ETH/USDC" --from "2026-03-29 00:00:00"
```

## Data Flow

```
Binance REST API (klines)
    -> backfill.py -> candles_1s (processed=false)
    -> recalculate.py -> candle_indicators + wide_vectors

Binance WebSocket (trades)
    -> pipeline -> candles_1s -> candle_indicators -> wide_vectors (processed=true)

Gaps detected
    -> gap_fill.py -> candles_1s (processed=false)
    -> recalculate.py -> candle_indicators + wide_vectors
```

## Performance

Tested on 2026-03-29 with 4 symbols (ADA, BTC, DOGE, ETH), 24h of data:

| Operation | Records | Time | Rate |
|-----------|---------|------|------|
| Backfill | 332,000 candles | ~2 min | 166k/min |
| Indicators | 336,000 values | ~25 min | 13k/min |
| Wide vectors | 91,000 vectors | ~20 sec | 273k/min |

## Tables

| Table | Description |
|-------|-------------|
| `symbols` | Active trading pairs |
| `candles_1s` | 1-second OHLCV candles (`processed` flag) |
| `candle_indicators` | Calculated indicator values per candle |
| `wide_vectors` | Flat feature vectors for ML training |
| `indicator_definitions` | Registered indicator configurations |
| `pipeline_state` | Per-symbol pipeline recovery state |
