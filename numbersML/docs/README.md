# numbersML

**Real-time crypto trading data infrastructure for ML/LLM models**

## Quick Start

```bash
# 1. Setup
git clone https://github.com/EliseNbg/numbersML.git
cd numbersML
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2. Start infrastructure
docker compose -f docker/docker-compose-infra.yml up -d

# 3. Initialize database
psql -h localhost -U crypto -d crypto_trading -f migrations/CLEAN_SCHEMA.sql

# 4. Start real-time pipeline
.venv/bin/python -m src.cli.start_trade_pipeline

# 5. Train ML models (after collecting data)
.venv/bin/python -m ml.train --model transformer --epochs 50 --symbol BTC/USDC
```

## UTC Time Standard

**All timestamps use UTC.** All `time` columns are `timestamp with time zone`. All `asyncpg.create_pool()` calls enforce `SET timezone = 'UTC'`. Use `datetime.now(timezone.utc)` — never `datetime.utcnow()` or naive datetimes.

## Architecture

```
Binance WebSocket → Recovery Manager → Aggregator (1s candles)
                         ↓                    ↓
                   REST API fill        Indicator Calculator
                                              ↓
                                        Wide Vector Service → ML Models
```

**Pipeline components:**
- **WebSocket Manager** — Real-time trade stream from Binance
- **Recovery Manager** — Detects gaps, recovers via REST API (synchronous, no storms)
- **Aggregator** — Builds 1-second candles from trade stream
- **Indicator Calculator** — Computes 15+ technical indicators per candle
- **Wide Vector Service** — Flattens all symbols' data into a single ML-ready vector
- **Database Writer** — Batched writes to PostgreSQL

**Recovery flow:** On startup, `_initial_recovery()` fills gaps from last run BEFORE connecting WebSocket. During operation, gaps are recovered synchronously (blocking only the affected symbol).

## Project Structure

```
src/
├── pipeline/              # Core real-time pipeline
│   ├── service.py         # TradePipeline orchestrator
│   ├── recovery.py        # Gap detection + REST recovery
│   ├── aggregator.py      # 1-second candle aggregation
│   ├── indicator_calculator.py  # Technical indicators
│   ├── wide_vector_service.py   # ML vector generation
│   └── database_writer.py # Batched DB writes
├── cli/                   # CLI tools
│   ├── start_trade_pipeline.py  # Main pipeline launcher
│   ├── recalculate.py     # Recalculate indicators/vectors
│   ├── backfill.py        # Historical data backfill
│   └── gap_fill.py        # Gap detection and filling
├── infrastructure/        # DB, API, exchanges
│   ├── database/          # Connection management (UTC enforced)
│   ├── api/               # FastAPI endpoints
│   └── exchanges/         # Binance REST/WebSocket clients
└── indicators/            # Technical indicator implementations

ml/
├── model.py               # 3 architectures: SimpleMLP, CNN+Attention, Transformer
├── dataset.py             # WideVectorDataset (PostgreSQL → PyTorch)
├── train.py               # Training loop with early stopping
├── compare.py             # Multi-model comparison
├── predict.py             # Inference engine
└── config.py              # PipelineConfig, ModelConfig, TrainingConfig

migrations/
└── CLEAN_SCHEMA.sql       # Complete database schema (pg_dump)

tests/
├── unit/                  # 457 unit tests
│   ├── ml/                # ML model tests (40)
│   └── pipeline/          # Pipeline + recovery tests (23)
└── integration/           # End-to-end tests
    └── test_dangerous_pipeline.py  # Full pipeline integration test
```

## ML Models

Five architectures available:

| Model | Architecture | Params | Use case | Status |
|-------|-------------|--------|----------|--------|
| `simple` | MLP + avg pooling | ~10K | Baseline | ✅ Stable |
| `full` | CNN + Attention + MLP | ~116K | Local + temporal patterns | ⚠️ Sometimes overfits |
| `transformer` | RoPE + SwiGLU + 4 layers | ~349K | Long-range dependencies | ⚠️ Slow, unstable |
| `temporal_cnn` | Dilated causal CNN | ~45K | General time series | ✅ Stable |
| `trading_tcn` | Gated TCN + risk head + PnL loss | ~100K | **PnL‑optimized trading** | 🆕 **New** |

**Transformer innovations:** Rotary Positional Embeddings (RoPE), SwiGLU activation, pre‑norm, multi‑scale CNN.

**TemporalCNN:** Pure dilated causal convs with exponential dilation (1,2,4,8,16). Trains reliably, MAE ~0.058–0.065 on BTC/USDC. No RNN/attention issues. See [TemporalCNN Model](TEMPORAL_CNN_MODEL.md).

**TradingTCN (NEW):** State‑of‑the‑art for profit maximization. WaveNet‑style gated residual blocks, multi‑scale dilations, channel mixing, dual heads (expected return + predicted risk). Trained with differentiable PnL / Sharpe losses. See [TradingTCN Model](TRADING_TCN_MODEL.md).

```bash
# Train standard regression models (sigmoid-scaled target)
.venv/bin/python -m ml.train --model simple          --epochs 30 --symbol BTC/USDC
.venv/bin/python -m ml.train --model full            --epochs 30 --symbol BTC/USDC
.venv/bin/python -m ml.train --model transformer     --epochs 30 --symbol BTC/USDC
.venv/bin/python -m ml.train --model temporal_cnn    --epochs 60 --symbol BTC/USDC --seq-length 120

# Train PnL-optimized TradingTCN (raw returns + risk-adjusted loss)
.venv/bin/python train_trading_tcn.py \
  --symbol BTC/USDC \
  --hours 360 \
  --seq-length 120 \
  --horizon 900 \
  --stride 60 \
  --loss risk_adjusted
```

**Entry‑point classifier** (LightGBM binary) is separate — see [Entry Point Model](ENTRY_POINT_MODEL.md).

## Testing

```bash
# All unit tests (~40s)
.venv/bin/python -m pytest tests/unit/ -v

# ML tests only
.venv/bin/python -m pytest tests/unit/ml/ -v

# Recovery tests only
.venv/bin/python -m pytest tests/unit/pipeline/test_recovery.py -v

# Dangerous integration test (deletes all data, 10 min)
echo "DELETE ALL DATA" | .venv/bin/python tests/integration/test_dangerous_pipeline.py
```

**457 tests passing.** Covers: ML models, recovery mechanism, pipeline components, target value calculation, wide vector generation.

## Phase 4: Algorithm Management & Backtesting ✅

### New Features
- **ConfigurationSets**: Reusable parameter sets for algorithms
- **AlgorithmInstances**: Link algorithms with configuration for deployment
- **Hot-Plug**: Start/stop algorithms without pipeline restart
- **Real Backtesting**: Historical data replay with NO indicator recalculation
- **Dashboard Pages**:
  - ConfigurationSet management with dynamic parameters
  - AlgorithmInstance management with hot-plug controls
  - Enhanced backtest page with Chart.js visualizations
- **Grid Algorithm**: Simple grid trading algorithm for TEST/USDT

### API Endpoints
- `POST /api/config-sets` - Create ConfigurationSet
- `GET /api/config-sets` - List ConfigurationSets
- `POST /api/algorithm-instances` - Create AlgorithmInstance
- `POST /api/algorithm-instances/{id}/start` - Hot-plug
- `POST /api/algorithm-backtests/jobs` - Submit backtest
- `GET /api/algorithm-backtests/jobs/{id}` - Get results

### Database Migrations
- `migrations/003_configuration_sets.sql`
- `migrations/004_algorithm_instances.sql`

### Test Coverage
- >80% for all new code
- Unit, integration, and E2E tests passing

## Database Schema

All tables use `timestamp with time zone` for time columns. Key tables:

| Table | Purpose |
|-------|---------|
| `candles_1s` | 1-second OHLCV candles + target_value |
| `candle_indicators` | Technical indicator values per candle |
| `wide_vectors` | ML-ready flat vectors (JSONB) |
| `pipeline_state` | Recovery state (last_trade_id, timestamps) |
| `symbols` | Active trading pairs |
| `trades` | Individual trade records |

## License

MIT
