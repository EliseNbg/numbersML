# MACD Cross Strategy

## Overview

The MACD Cross Strategy is a trend-following momentum strategy that generates trading signals based on the Moving Average Convergence Divergence (MACD) indicator crossing its signal line.

## How It Works

### MACD Indicator

The MACD indicator consists of three components:
- **MACD Line**: The difference between two exponential moving averages (fast and slow periods)
- **Signal Line**: An exponential moving average of the MACD line
- **Histogram**: The difference between the MACD line and signal line

### Signal Generation

The strategy detects crossovers between the MACD line and the signal line:

- **BUY Signal**: Generated when the MACD line crosses **above** the signal line (bullish crossover)
  - Only generated when not already in a position
  - Confidence is calculated based on the crossover magnitude

- **SELL Signal**: Generated when the MACD line crosses **below** the signal line (bearish crossover)
  - Only generated when currently in a position
  - Confidence is calculated based on the crossover magnitude

### State Management

The strategy maintains the following state:
- `last_macd`: Previous MACD line value
- `last_signal`: Previous signal line value
- `last_histogram`: Previous histogram value
- `in_position`: Boolean flag tracking whether a position is open
- `cross_count`: Total number of crossovers detected
- `_tick_count`: Number of ticks processed

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `macd_indicator_name` | str | `"macdindicator"` | Base name of the pre-calculated MACD indicator to use |
| `fast_period` | int | `12` | Fast EMA period for MACD calculation |
| `slow_period` | int | `26` | Slow EMA period for MACD calculation |
| `signal_period` | int | `9` | Signal line EMA period |
| `min_relative_threshold` | float | `0.001` | Minimum histogram/price ratio to trigger a signal (noise filter) |

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

To use the long-term MACD (280/590/29):

```json
{
  "macd_indicator_name": "macd_280_590_29",
  "fast_period": 280,
  "slow_period": 590,
  "signal_period": 29,
  "min_relative_threshold": 0.001
}
```

To use the very long-term MACD (450/960/100):

```json
{
  "macd_indicator_name": "macd_450_960_100",
  "fast_period": 450,
  "slow_period": 960,
  "signal_period": 100,
  "min_relative_threshold": 0.001
}
```

### Example Configuration (Python)

```python
strategy = MACDCrossStrategy(
    strategy_id="macd_cross_btc",
    symbols=["BTC/USDT"],
)

# Use long-term MACD
strategy.set_config("macd_indicator_name", "macd_280_590_29")
strategy.set_config("fast_period", 280)
strategy.set_config("slow_period", 590)
strategy.set_config("signal_period", 29)
strategy.set_config("min_relative_threshold", 0.001)
```

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
  │   ├── _signal_buy()         # Create BUY signal
  │   └── _signal_sell()        # Create SELL signal
  └── Update state variables
```

### Key Methods

- **`on_tick(tick)`**: Main entry point called for each incoming tick
- **`_initialize_macd()`**: Loads configuration parameters and logs them
- **`_get_macd_values(tick)`**: Extracts MACD and signal values from tick indicators
- **`_detect_crossover(macd, signal, tick)`**: Detects crossovers and delegates to signal methods
- **`_signal_buy(tick, macd, signal)`**: Creates and logs BUY signals
- **`_signal_sell(tick, macd, signal)`**: Creates and logs SELL signals
- **`on_position_closed(symbol, price, exit_reason)`**: Handles external position closure
- **`get_stats()`**: Returns comprehensive strategy statistics

## Logging

### Initialization

On first tick, the strategy logs its configuration:

```
[strategy_id] MACD: name=macd_280_590_29, fast=280, slow=590, signal=29, min_relative_threshold=0.001
[strategy_id] Config: {'macd_indicator_name': 'macd_280_590_29', 'min_relative_threshold': 0.001, ...}
[strategy_id] Indicators: {'macd_280_590_29_macd': 0.0012, 'macd_280_590_29_signal': 0.0010, ...}
```

### Periodic Status

Every 500 ticks, the strategy logs current state:

```
{timestamp} Tick 500: macd=0.0012, signal=0.0010, histogram=0.0002, in_position=True, cross_count=3
```

### Signal Generation

When a signal is generated:

```
[strategy_id] BUY signal: MACD=0.0015 > Signal=0.0010, histogram=0.0005
[strategy_id] SELL signal: MACD=0.0008 < Signal=0.0012, histogram=-0.0004
```

### Position Closure

When a position is closed externally:

```
[strategy_id] Position closed for BTC/USDT: reason=take_profit, price=50000.00000000
```

## Statistics

The `get_stats()` method returns:

```python
{
    "strategy_id": "macd_cross_btc",
    "state": "RUNNING",
    "symbols": ["BTC/USDT"],
    "ticks_processed": 1000,
    "signals_generated": 5,
    "active_positions": 0,
    "total_unrealized_pnl": 0.0,
    "errors": 0,
    "last_macd": 0.0012,
    "last_signal": 0.0010,
    "last_histogram": 0.0002,
    "in_position": False,
    "cross_count": 5,
    "tick_count": 1000,
    "macd_indicator_name": "macd_280_590_29",
    "fast_period": 280,
    "slow_period": 590,
    "signal_period": 29,
    "min_relative_threshold": 0.001,
}
```

## Indicator Data Format

The strategy expects tick data to include MACD indicators. It tries to find them in this order:

### 1. Configured indicator name (recommended)

Set `macd_indicator_name` in config to match your pre-calculated indicators:

```python
tick.indicators = {
    "macd_280_590_29_macd": 0.0012,
    "macd_280_590_29_signal": 0.0010,
    "macd_280_590_29_histogram": 0.0002,
}
```

### 2. Simple names (fallback)

```python
tick.indicators = {
    "macd": 0.0012,
    "macd_signal": 0.0010,
    "macd_histogram": 0.0002,
}
```

### 3. Auto-detection (last resort)

If neither of the above matches, the strategy scans all indicator keys for any
containing "macd" with `_macd`, `_signal`, or `_histogram` suffixes.

## Usage Example

```python
from decimal import Decimal
from datetime import UTC, datetime
from src.domain.strategies.base import EnrichedTick
from src.strategies.user.macd_cross_strategy import MACDCrossStrategy

# Create strategy
strategy = MACDCrossStrategy(
    strategy_id="macd_cross_eth",
    symbols=["ETH/USDT"],
)

# Configure - select which pre-calculated MACD indicator to use
strategy.set_config("macd_indicator_name", "macd_280_590_29")
strategy.set_config("fast_period", 280)
strategy.set_config("slow_period", 590)
strategy.set_config("signal_period", 29)

# Process ticks
tick = EnrichedTick(
    symbol="ETH/USDT",
    price=Decimal("3000.0"),
    volume=Decimal("10.5"),
    time=datetime.now(UTC),
    indicators={
        "macd_280_590_29_macd": 0.0015,
        "macd_280_590_29_signal": 0.0010,
        "macd_280_590_29_histogram": 0.0005,
    },
)

signal = strategy.on_tick(tick)
if signal:
    print(f"Signal: {signal.signal_type} @ {signal.price}")
```

## Risk Considerations

- The strategy does not implement stop-loss or take-profit logic internally
- Position management is handled externally by the trading engine
- The strategy assumes MACD indicators are pre-calculated and provided in tick data
- Confidence scores are based on crossover magnitude and may not reflect actual trade quality
