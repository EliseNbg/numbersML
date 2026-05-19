# Run Backtest CLI

Run a strategy backtest from the command line against historical candle data stored in PostgreSQL.

## Usage

```bash
.venv/bin/python -m src.cli.run_backtest --strategy-id UUID [options]
```

## Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--strategy-id` | UUID | **required** | Strategy ID to backtest |
| `--version` | int | active | Specific strategy version number |
| `--symbol` | string | All | Symbol to backtest (e.g. `DOGE/USDC`) |
| `--start-time` | timestamp | 7 days ago | Start time (ISO format, e.g. `"2026-05-11 17:41:00"`) |
| `--end-time` | timestamp | now | End time (ISO format) |
| `--initial-balance` | float | 10000 | Starting capital in quote asset |
| `--include-equity-curve` | flag | true | Include equity curve in JSON output |
| `--no-equity-curve` | flag | — | Exclude equity curve |
| `--include-trades` | flag | true | Include individual trades in output |
| `--no-trades` | flag | — | Exclude individual trades |
| `--output` | file path | — | Save results to JSON file |
| `--wait` | flag | — | Wait for completion and print results |
| `--timeout` | int | 300 | Timeout in seconds when waiting |
| `--validate-with-binance` | flag | false | Validate every order against Binance testnet |

## Examples

### Basic backtest (last 7 days)

```bash
.venv/bin/python -m src.cli.run_backtest \
  --strategy-id f92aca3f-0d7b-4325-a7d0-6a5529b106cd
```

### Backtest with specific time range and symbol

```bash
.venv/bin/python -m src.cli.run_backtest \
  --strategy-id f92aca3f-0d7b-4325-a7d0-6a5529b106cd \
  --version 5 \
  --symbol "DOGE/USDC" \
  --start-time "2026-05-11 17:41:00" \
  --end-time "2026-05-12 10:41:00"
```

### Backtest with Binance testnet validation

Every buy/sell signal generated during the backtest is sent to the Binance testnet
`/api/v3/order/test` endpoint. This endpoint **validates the order parameters without
executing** the trade — perfect for verifying that your strategy produces orders that
Binance would actually accept.

```bash
export BINANCE_TESTNET_API_KEY="your-testnet-api-key"
export BINANCE_TESTNET_API_SECRET="your-testnet-api-secret"

.venv/bin/python -m src.cli.run_backtest \
  --strategy-id f92aca3f-0d7b-4325-a7d0-6a5529b106cd \
  --version 5 \
  --symbol "DOGE/USDC" \
  --start-time "2026-05-11 17:41:00" \
  --end-time "2026-05-12 10:41:00" \
  --validate-with-binance
```

### Save results to file

```bash
.venv/bin/python -m src.cli.run_backtest \
  --strategy-id f92aca3f-0d7b-4325-a7d0-6a5529b106cd \
  --symbol "BTC/USDC" \
  --output backtest_results.json
```

## Binance Testnet Validation — Console Output

When `--validate-with-binance` is enabled you will see these log lines in the console:

```
[BINANCE-TEST] Sending test order: BUY 1500.00000000 DOGE/USDC type=MARKET price=None time=2026-05-11 18:23:01+00:00 clientOrderId=bt-a1b2c3d4e5f6
[BINANCE-TEST] Response: {'symbol': 'DOGEUSDC', 'orderId': 0, 'orderListId': -1, 'clientOrderId': 'bt-a1b2c3d4e5f6', 'transactTime': 1715451781000}
```

Raw HTTP request/response details are also logged at DEBUG level by `aiohttp`:

```
DEBUG:aiohttp.client:Request: POST https://testnet.binance.vision/api/v3/order/test?symbol=DOGEUSDC&side=BUY&type=MARKET&quantity=1500.0&...
DEBUG:aiohttp.client:Response status: 200
```

If validation fails:

```
[BINANCE-TEST] Validation failed for SELL DOGE/USDC: Binance API error (400): {'code': -2010, 'msg': 'Account has insufficient balance.'}
```

### Getting Binance Testnet Credentials

1. Go to https://testnet.binance.vision/
2. Register or log in with your GitHub account
3. Generate an API key and secret
4. Export them as environment variables before running the backtest

## How It Works

The backtest engine replays historical candles chronologically. On each candle:

1. Strategy `process_tick()` is called with the enriched tick data
2. If a BUY/SELL signal is emitted, the `PaperExecutionSimulator` calculates the fill
   price with configurable fees and slippage
3. When `--validate-with-binance` is set, the same order parameters are simultaneously
   sent to Binance testnet's `/api/v3/order/test` endpoint
4. The testnet validates the order against live symbol filters (min quantity, price
   precision, lot size, etc.) and returns a success or error response
5. The backtest continues with its own paper simulation — the Binance call is
   **read-only validation only**, it does not affect backtest results

## Architecture

```
CLI (run_backtest.py)
  └── StrategyBacktestService
        └── BacktestEngine
              ├── PaperExecutionSimulator  (local fill simulation)
              └── BinanceExchangeClient    (optional testnet validation)
                    └── POST /api/v3/order/test  (validate only, no execution)
```
