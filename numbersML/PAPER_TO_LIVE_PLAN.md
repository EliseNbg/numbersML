# Paper Trading → Live Production Plan

## Status: Paper trading is working (MACD_Peak_ATOM on ATOM/USDC)

## Steps Required

### 1. Add Binance API Keys

Binance mainnet API key + secret must be stored for live order execution.

**Option A — Via Dashboard API** (recommended):
```bash
# Start the dashboard
.venv/bin/python -m src.cli.start_dashboard

# POST API key (replace with your actual key/secret)
curl -X POST 'http://localhost:8000/api/v1/api-keys?name=BinanceMainnet&environment=mainnet&api_key=YOUR_API_KEY&api_secret=YOUR_API_SECRET'
```

**Option B — Direct DB insert** (encrypted storage; not recommended manually).

**Option C — Environment variables** (used by backtest engine):
```bash
export BINANCE_LIVE_API_KEY="your_key"
export BINANCE_LIVE_API_SECRET="your_secret"
```

### 2. Change Strategy Mode from `paper` → `live`

**Via the Dashboard UI**: Open the strategy detail modal → click the new toggle button near "Resume"
**Via API**: `POST /api/strategies/{id}/mode` with `{"mode": "live"}`
**Via direct SQL**:
```sql
UPDATE strategies SET mode = 'live' WHERE name = 'MACD_Peak_ATOM';
```

This updates both the `strategies.mode` column and the active version config's `mode` field.

### 3. Configure the Pipeline for Live Execution

The current `TradePipeline` in `src/pipeline/service.py:75` hardcodes `PaperMarketService()`.
It must be swapped for a `LiveMarketService` backed by Binance exchange client.

Changes needed in `src/cli/start_trade_pipeline.py`:
- Accept `--mode live` flag
- Load API keys from `api_keys` table or env vars
- Instantiate `LiveMarketService` with `BinanceExchangeClient`
- Pass to `TradePipeline` instead of `PaperMarketService`

### 4. Verify & Monitor

- Start the pipeline with `--mode live`
- Monitor orders via Binance account or dashboard
- Keep the dashboard open for runtime status
- Use `/api/strategies/{id}/runtime` to check state

### 5. Safety Precautions

- Always test in paper mode first (done ✓)
- Risk guardrails: `stop_loss_pct`, `max_position_size_pct`, `max_daily_loss_pct` in config
- Start with small `quantity` (25 USDC in current config)
- Have the dashboard running to deactivate if needed

---

## Implementation Checklist

- [x] Paper trading verified working
- [ ] Binance API keys configured
- [ ] Strategy mode toggled to `live`
- [ ] Pipeline updated for live execution
- [ ] Dashboard toggle button implemented
- [ ] API endpoint for mode toggle implemented
- [ ] Tests for mode toggle endpoint

## Rollback

To return to paper mode:
```sql
UPDATE strategies SET mode = 'paper' WHERE name = 'MACD_Peak_ATOM';
```
Then restart the pipeline with paper mode.
