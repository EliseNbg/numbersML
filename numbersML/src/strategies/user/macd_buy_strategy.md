# MACD Buy Strategy

## Overview

BUY-only strategy that generates signals when the MACD line crosses above the signal line,
with an additional constraint that the MACD value must be below a configured bottom border.
This ensures buying only occurs during dips or oversold conditions.

No SELL signals are generated. Each BUY signal includes an `expected_profit_price` in its
metadata, which is handled externally by the market or take-profit mechanism.

## Buy Conditions

A BUY signal is generated when **all** of the following are true:

1. **Bullish crossover**: MACD crosses above signal line (previous: MACD <= signal, current: MACD > signal)
2. **Below bottom border**: Current MACD value < `bottom_border_macd_to_buy`
3. **Noise filter**: `abs(MACD - signal) / price >= min_relative_threshold`

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `macd_indicator_name` | str | `"macdindicator"` | Base name of the pre-calculated MACD indicator to use |
| `fast_period` | int | `12` | Fast EMA period for MACD calculation |
| `slow_period` | int | `26` | Slow EMA period for MACD calculation |
| `signal_period` | int | `9` | Signal line EMA period |
| `min_relative_threshold` | float | `0.001` | Minimum histogram/price ratio to trigger a signal (noise filter) |
| `bottom_border_macd_to_buy` | float | `0.0` | Maximum MACD value to allow BUY signals |
| `grid_quantity_absolute` | float | `100.0` | USDC amount to buy per signal |
| `grid_profit_pct` | float | `0.85` | Profit target percentage for take-profit calculation |

### Selecting a Pre-calculated MACD Indicator

The database may contain multiple pre-calculated MACD indicators with different parameters.
Use the `macd_indicator_name` config key to select which one the strategy should use.

Available indicators in the database:

| Indicator Name | Fast | Slow | Signal | Description |
|---------------|------|------|--------|-------------|
| `macd_280_590_29` | 280 | 590 | 29 | Long-term MACD for slower trends |
| `macd_450_960_100` | 450 | 960 | 100 | Very long-term MACD for macro trends |

The strategy looks for indicator keys in the format:
- `{macd_indicator_name}_macd`
- `{macd_indicator_name}_signal`
- `{macd_indicator_name}_histogram`

If no matching indicator is found, the strategy falls back to auto-detection
(scans all available indicator keys for any containing "macd").

### Example Configuration (JSON)

To use the long-term MACD (280/590/29) with a bottom border of -0.5:

```json
{
  "macd_indicator_name": "macd_280_590_29",
  "fast_period": 280,
  "slow_period": 590,
  "signal_period": 29,
  "bottom_border_macd_to_buy": -0.5,
  "grid_quantity_absolute": 100.0,
  "grid_profit_pct": 0.85
}
```

To use the very long-term MACD (450/960/100) with a larger position size:

```json
{
  "macd_indicator_name": "macd_450_960_100",
  "fast_period": 450,
  "slow_period": 960,
  "signal_period": 100,
  "bottom_border_macd_to_buy": -1.0,
  "grid_quantity_absolute": 200.0,
  "grid_profit_pct": 1.0
}
```

### Example Configuration (Python)

```python
strategy = MACDBuyStrategy(
    strategy_id="macd_buy_doge",
    symbols=["DOGE/USDC"],
)

# Use long-term MACD with dip-buying constraint
strategy.set_config("macd_indicator_name", "macd_280_590_29")
strategy.set_config("fast_period", 280)
strategy.set_config("slow_period", 590)
strategy.set_config("signal_period", 29)
strategy.set_config("bottom_border_macd_to_buy", -0.0001)
strategy.set_config("grid_quantity_absolute", 100.0)
strategy.set_config("grid_profit_pct", 0.85)
```

### Bottom Border Tuning

The `bottom_border_macd_to_buy` parameter controls when the strategy is allowed to buy:

| Bottom Border | Effect |
|---------------|--------|
| `0.0` (default) | Buy on any bullish crossover when MACD is negative |
| `-0.5` | Only buy when MACD is deeply negative (strong dip) |
| `-1.0` | Very selective, only buy during extreme oversold conditions |

### Noise Filter

The `min_relative_threshold` parameter prevents floating-point noise near zero
from triggering false crossovers. Signals are only generated when
`abs(macd - signal) / price >= min_relative_threshold`.

This relative approach works across all price ranges:

| Asset | Price | Histogram (0.1% of price) | Threshold |
|-------|-------|---------------------------|-----------|
| SHIB/USDC | 0.00001 | 1e-8 | `0.001` |
| DOGE/USDC | 0.11 | 1.1e-4 | `0.001` |
| BTC/USDC | 100,000 | 100 | `0.001` |

| Threshold | Effect |
|-----------|--------|
| `0.001` (default) | Requires 0.1% of price, filters noise on all assets |
| `0.0005` | Requires 0.05%, moderate filtering |
| `0.005` | Requires 0.5%, aggressive filtering, only strong crossovers |

## Architecture

### Method Structure

The strategy follows a modular design with clear separation of concerns:

```
on_tick()
  ├── _initialize_macd()        # Initialize configuration on first tick
  ├── _get_macd_values()        # Extract MACD values from tick data
  ├── _detect_crossover()       # Detect crossover and generate signal
  │   └── _signal_buy()         # Create BUY signal with take-profit price
  └── Update state variables
```

### Key Methods

- **`on_tick(tick)`**: Main entry point called for each incoming tick
- **`_initialize_macd()`**: Loads configuration parameters and logs them
- **`_get_macd_values(tick)`**: Extracts MACD and signal values from tick indicators
- **`_detect_crossover(macd, signal, tick)`**: Detects bullish crossovers below bottom border
- **`_signal_buy(tick, macd, signal)`**: Creates and logs BUY signals with expected profit price
- **`on_position_closed(symbol, price, exit_reason)`**: Handles external position closure
- **`get_stats()`**: Returns comprehensive strategy statistics

## Logging

### Initialization

On first tick, the strategy logs its configuration:

```
[strategy_id] MACD: name=macd_280_590_29, fast=280, slow=590, signal=29, min_relative_threshold=0.001, bottom_border=-0.5
[strategy_id] Trade: quantity=100.0 USDC, profit_target=0.85%
[strategy_id] Config: {'macd_indicator_name': 'macd_280_590_29', 'bottom_border_macd_to_buy': -0.5, ...}
[strategy_id] Indicators: {'macd_280_590_29_macd': -0.0012, 'macd_280_590_29_signal': -0.0015, ...}
```

### Periodic Status

Every 500 ticks, the strategy logs current state:

```
{timestamp} Tick 500: macd=-0.0012, signal=-0.0015, histogram=0.0003, cross_count=3
```

### Signal Generation

When a signal is generated:

```
[strategy_id] BUY signal: MACD=-0.0010 > Signal=-0.0015, histogram=0.0005, price=0.11033, expected_profit=0.11127
```

### Position Closure

When a position is closed externally:

```
[strategy_id] Position closed for DOGE/USDC: reason=take_profit, price=0.11127
```

## Statistics

The `get_stats()` method returns:

```python
{
    "strategy_id": "macd_buy_doge",
    "state": "RUNNING",
    "symbols": ["DOGE/USDC"],
    "ticks_processed": 1000,
    "signals_generated": 5,
    "active_positions": 0,
    "total_unrealized_pnl": 0.0,
    "errors": 0,
    "last_macd": -0.0012,
    "last_signal": -0.0015,
    "last_histogram": 0.0003,
    "cross_count": 5,
    "tick_count": 1000,
    "macd_indicator_name": "macd_280_590_29",
    "fast_period": 280,
    "slow_period": 590,
    "signal_period": 29,
    "min_relative_threshold": 0.001,
    "bottom_border_macd_to_buy": -0.5,
    "grid_quantity_absolute": 100.0,
    "grid_profit_pct": 0.85,
}
```

## Indicator Data Format

The strategy expects tick indicators in the following format:

```python
tick.indicators = {
    "macdindicator_macd": -0.0012,
    "macdindicator_signal": -0.0015,
    "macdindicator_histogram": 0.0003,  # Optional, calculated if missing
}
```

Or with custom indicator names:

```python
tick.indicators = {
    "macd_280_590_29_macd": -0.0012,
    "macd_280_590_29_signal": -0.0015,
    "macd_280_590_29_histogram": 0.0003,
}
```

## Signal Metadata

Each BUY signal includes the following metadata:

```python
{
    "macd": -0.0010,
    "signal": -0.0015,
    "histogram": 0.0005,
    "crossover_type": "bullish",
    "cross_count": 3,
    "expected_profit_price": 0.11127,  # price * (1 + grid_profit_pct / 100)
    "quantity_usdc": 100.0,
}
```
