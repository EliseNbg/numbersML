# Backtest Strategy CLI Integration

## Overview

This document describes the integration of a CLI command for running strategy backtests from the terminal, along with UI enhancements to the backtest strategy page to show and copy the equivalent CLI command.

## Changes Made

### 1. New CLI Command: `src/cli/run_backtest.py`

Created a new command-line interface for running strategy backtests with the following features:

- **Required Parameters**:
  - `--strategy-id UUID`: Strategy ID to backtest (required)

- **Optional Parameters**:
  - `--version INT`: Specific strategy version (defaults to active)
  - `--symbol SYMBOL`: Symbol to backtest (e.g., BTC/USDC)
  - `--start-time TIMESTAMP`: Start time (ISO format, defaults to 7 days ago)
  - `--end-time TIMESTAMP`: End time (ISO format, defaults to now)
  - `--initial-balance FLOAT`: Initial capital (default: 10000)
  - `--include-equity-curve`: Include equity curve in output (default: true)
  - `--no-equity-curve`: Exclude equity curve from output
  - `--include-trades`: Include individual trades in output (default: true)
  - `--no-trades`: Exclude individual trades from output
  - `--output FILE`: Output file for results (JSON format)
  - `--wait`: Wait for completion and show results
  - `--timeout SECONDS`: Timeout for waiting in seconds (default: 300)

- **Features**:
  - Runs backtests using the same backend services as the web interface
  - Outputs detailed statistics including:
    - Overall performance metrics (return, drawdown, Sharpe ratio, win rate, profit factor)
    - Detailed trade list with entry/exit times, symbols, prices, PnL, and reasons
    - Equity curve points for comparison
  - Can wait for completion and display results in terminal
  - Can save results to JSON file for later analysis
  - Progress reporting during execution
  - Proper error handling and logging

### 2. Enhanced Backtest Strategy Page

Modified `dashboard/backtest_strategy.html` and `dashboard/js/backtest_strategy.js` to add:

- **"Show CLI Command" Button**:
  - Located next to the "Run Backtest" button
  - Toggles visibility of a panel containing the equivalent CLI command
  
- **Dynamic CLI Command Generation**:
  - Command is automatically generated based on current form values
  - Updates when form values change (when panel is visible)
  - Includes all relevant parameters: strategy ID, version, symbol, dates, balance, options

- **Copy to Clipboard Functionality**:
  - "Copy Command" button copies the CLI command to clipboard
  - Shows toast notification confirming copy success
  
- **Improved Strategy Dropdown**:
  - Fixed to show `strategy.strategy_type` instead of undefined `strategy.type`
  - Now displays strategy name with its type (e.g., "My Strategy (config)")

## Usage Examples

### From the Web Interface:
1. Configure your backtest parameters on the Strategy Backtest page
2. Click "Show CLI Command" button
3. Click "Copy Command" to copy the equivalent CLI command
4. Paste and run in your terminal

### Direct CLI Usage:
```bash
# Run backtest with defaults (last 7 days)
python -m src.cli.run_backtest --strategy-id 123e4567-e89b-12d3-a456-426614174000

# Run backtest with specific parameters
python -m src.cli.run_backtest \
  --strategy-id 123e4567-e89b-12d3-a456-426614174000 \
  --symbol BTC/USDC \
  --start-time "2026-05-01T00:00:00" \
  --end-time "2026-05-08T00:00:00" \
  --initial-balance 10000 \
  --wait

# Run backtest and save results to file
python -m src.cli.run_backtest \
  --strategy-id 123e4567-e89b-12d3-a456-426614174000 \
  --output backtest_results.json
```

## Sample Output

When running with `--wait`, the CLI outputs detailed statistics:

```
============================================================
BACKTEST RESULTS
============================================================
Strategy ID: dcb32c52-cc78-4e2f-91e6-76287cc345ee
Version: active
Period: 2026-05-03T00:00:00 to 2026-05-10T00:00:00
Symbol: BTC/USDC
Initial Balance: $10000.00
Final Balance: $12456.78
Total Return: +24.57%
Max Drawdown: 8.32%
Sharpe Ratio: 1.85
Win Rate: 65.0%
Total Trades: 20
Profit Factor: 2.24

------------------------------------------------------------
TRADES
------------------------------------------------------------
  1. 2026-05-03T09:30:00 -> 2026-05-03T15:45:00 BTC/USDC BUY @65000.0000 -> 65500.0000 PnL: $ 500.00 (+0.77%) [signal]
  2. 2026-05-04T10:15:00 -> 2026-05-04T16:30:00 BTC/USDC SELL @66000.0000 -> 65800.0000 PnL: $ 200.00 (+0.30%) [signal]
  ...
 20. 2026-05-09T14:20:00 -> 2026-05-09T15:55:00 BTC/USDC BUY @67200.0000 -> 67800.0000 PnL: $ 600.00 (+0.89%) [signal]

------------------------------------------------------------
EQUITY CURVE (last 5 points)
------------------------------------------------------------
2026-05-06T00:00:00: Equity $11200.50 (DD: 2.10%)
2026-05-07T00:00:00: Equity $11550.75 (DD: 1.25%)
2026-05-08T00:00:00: Equity $11800.25 (DD: 0.80%)
2026-05-09T00:00:00: Equity $12100.00 (DD: 0.40%)
2026-05-10T00:00:00: Equity $12456.78 (DD: 0.00%)
============================================================
```

## Technical Implementation

### CLI Command (`src/cli/run_backtest.py`):
- Uses the same `StrategyBacktestService` as the web API
- Properly initializes database connections
- Handles async execution with progress reporting
- Serializes results using the same functions as the API
- Formats output for readability in terminal

### Frontend Changes:
- Added event listeners for the new buttons
- Implemented `toggleCliCommand()` to show/hide the command panel
- Implemented `generateCliCommand()` to build command from form values
- Implemented `copyCliCommand()` to copy to clipboard
- Enhanced `loadStrategies()` to use `strategy.strategy_type`

## Testing

All existing tests continue to pass:
- Strategy API tests
- Strategy lifecycle persistence tests
- Backtest dashboard API tests
- Unit tests for strategy-related functionality

The CLI command has been tested for:
- Help display
- Argument parsing
- Error handling (invalid strategy ID, date ranges, etc.)
- Basic structure (though full execution requires running services)

## Benefits

1. **Consistency**: CLI and web interface use the same backend services
2. **Reproducibility**: Easy to reproduce exact backtest runs from terminal
3. **Automation**: Can be scripted for batch processing or CI/CD
4. **Debugging**: Terminal output provides detailed logs for troubleshooting
5. **Comparison**: Structured output makes it easy to compare different runs
6. **Integration**: Fits seamlessly into existing workflows

## Future Enhancements

- Add support for running multiple backtests in batch
- Implement result comparison functionality
- Add ability to schedule backtests via cron-like syntax
- Integrate with notebook environments for interactive analysis
- Add ML model backtesting capabilities