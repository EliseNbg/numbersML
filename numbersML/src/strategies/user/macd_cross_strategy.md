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
| `macd_indicator_name` | str | `"macdindicator"` | Name of the MACD indicator in the tick data |
| `fast_period` | int | `12` | Fast EMA period for MACD calculation |
| `slow_period` | int | `26` | Slow EMA period for MACD calculation |
| `signal_period` | int | `9` | Signal line EMA period |

### Example Configuration

```python
strategy = MACDCrossStrategy(
    strategy_id="macd_cross_btc",
    symbols=["BTC/USDT"],
)

# Set custom configuration
strategy.set_config("macd_indicator_name", "macdindicator")
strategy.set_config("fast_period", 12)
strategy.set_config("slow_period", 26)
strategy.set_config("signal_period", 9)
```

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
[strategy_id] MACD: name=macdindicator, fast=12, slow=26, signal=9
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
    "macd_indicator_name": "macdindicator",
    "fast_period": 12,
    "slow_period": 26,
    "signal_period": 9,
}
```

## Indicator Data Format

The strategy expects tick data to include MACD indicators in one of two formats:

### Format 1: Prefixed with indicator name
```python
tick.indicators = {
    "macdindicator_macd": 0.0012,
    "macdindicator_signal": 0.0010,
}
```

### Format 2: Simple names
```python
tick.indicators = {
    "macd": 0.0012,
    "macd_signal": 0.0010,
}
```

The strategy tries Format 1 first, then falls back to Format 2.

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

# Configure
strategy.set_config("fast_period", 12)
strategy.set_config("slow_period", 26)
strategy.set_config("signal_period", 9)

# Process ticks
tick = EnrichedTick(
    symbol="ETH/USDT",
    price=Decimal("3000.0"),
    volume=Decimal("10.5"),
    time=datetime.now(UTC),
    indicators={
        "macdindicator_macd": 0.0015,
        "macdindicator_signal": 0.0010,
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
