# MACD Momentum Strategy

## Overview

The classic MACD Momentum Strategy generates both **BUY** and **SELL** signals by detecting local extrema (peaks and troughs) in the MACD line. Instead of waiting for MACD/signal line crossovers, it identifies when the MACD line itself reverses momentum, providing earlier entry and exit signals.

- **BUY** when MACD reverses from a decline to an uptrend (local minimum / trough)
- **SELL** when MACD reverses from an uptrend to a decline (local maximum / peak)

This is the classic momentum variant — buy the dips in MACD momentum, sell the peaks.

## How It Works

### Trough Detection (BUY)

A BUY signal is generated when **all** of the following are true:

1. **Trend reversal**: MACD was declining for `trend_lookback` consecutive ticks, then starts rising (current MACD > previous MACD)
2. **Below bottom border**: Current MACD value < `bottom_border_macd_to_buy`
3. **Noise filter**: `abs(current MACD - previous MACD) / signal_magnitude >= min_relative_threshold`
4. **Not in a position**: `in_position` is `False`
5. **SMA price filter** (optional): Current close price < `sma_fast * sma_multiplicator` AND current close price < `sma_slow * sma_multiplicator`
6. **Day/week average price filter** (optional): Current close price < `avg_price_day * avg_multiplicator_day` AND current close price < `avg_price_week * avg_multiplicator_week`

### Peak Detection (SELL)

A SELL signal is generated when **all** of the following are true:

1. **Trend reversal**: MACD was rising for `trend_lookback` consecutive ticks, then starts falling (current MACD < previous MACD)
2. **Noise filter**: `abs(current MACD - previous MACD) / signal_magnitude >= min_relative_threshold`
3. **In a position**: `in_position` is `True`
4. **No cooldown**: `_signal_cooldown` counter is 0

### State Management

The strategy tracks:
- `in_position`: Whether a position is currently open (controls whether BUY or SELL signals are considered)
- `_macd_history`: Sliding window of MACD values for trend detection
- `_signal_cooldown`: Cooldown counter after a signal to prevent re-triggering on the same extremum

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `macd_indicator_name` | str | `"macd_980_1960_100"` | Base name of the pre-calculated MACD indicator to use |
| `fast_period` | int | `980` | Fast EMA period for MACD calculation |
| `slow_period` | int | `1960` | Slow EMA period for MACD calculation |
| `signal_period` | int | `100` | Signal line EMA period |
| `min_relative_threshold` | float | `0.001` | Minimum MACD change ratio to trigger a signal (noise filter) |
| `bottom_border_macd_to_buy` | float | `0.0` | Maximum MACD value to allow BUY signals (buy only when MACD is negative) |
| `grid_quantity_absolute` | float | `100.0` | USDC amount to trade per signal |
| `grid_profit_pct` | float | `0.85` | Profit target percentage for take-profit calculation |
| `sma_fast` | str | `None` | Name of fast SMA indicator for price filter (e.g., `"sma_800"`) |
| `sma_slow` | str | `None` | Name of slow SMA indicator for price filter (e.g., `"sma_2000"`) |
| `sma_multiplicator` | float | `0.997` | Multiplier applied to SMA values for price comparison |
| `trend_lookback` | int | `3` | Number of consecutive ticks required to confirm a trend before reversal |
| `avg_multiplicator_day` | float | `0.991` | Multiplier applied to daily average price for price filter |
| `avg_multiplicator_week` | float | `0.991` | Multiplier applied to weekly average price for price filter |

### Peak / Trough Detection

The strategy tracks MACD values in a sliding window of size `trend_lookback + 1`:

**Trough (BUY):**
1. All values in the window (except the last two) show a consistent decline: `MACD[i] > MACD[i+1]`
2. The most recent value shows an uptick: `MACD[current] > MACD[previous]`

**Peak (SELL):**
1. All values in the window (except the last two) show a consistent rise: `MACD[i] < MACD[i+1]`
2. The most recent value shows a downtick: `MACD[current] < MACD[previous]`

**Effect of `trend_lookback`:**

| trend_lookback | Effect |
|----------------|--------|
| `1` | Very sensitive, detects any single-tick reversal (more false signals) |
| `3` (default) | Moderate, requires 3 consecutive ticks before reversal |
| `5+` | Conservative, requires longer confirmed trend (fewer but stronger signals) |

### Example Configuration (JSON)

```json
{
  "macd_indicator_name": "macd_980_1960_100",
  "fast_period": 980,
  "slow_period": 1960,
  "signal_period": 100,
  "bottom_border_macd_to_buy": 0.0,
  "trend_lookback": 3,
  "grid_quantity_absolute": 100.0,
  "grid_profit_pct": 0.85
}
```

With SMA price filter:

```json
{
  "macd_indicator_name": "macd_980_1960_100",
  "fast_period": 980,
  "slow_period": 1960,
  "signal_period": 100,
  "bottom_border_macd_to_buy": 0.0,
  "sma_fast": "sma_800",
  "sma_slow": "sma_2000",
  "sma_multiplicator": 0.997,
  "trend_lookback": 5,
  "grid_quantity_absolute": 100.0,
  "grid_profit_pct": 0.85
}
```

### Example Configuration (Python)

```python
from src.strategies.user.macd_momentum_strategy import MACDMomentumStrategy

strategy = MACDMomentumStrategy(
    strategy_id="macd_momentum_doge",
    symbols=["DOGE/USDC"],
)

# Use the MACD 980/1960/100 indicator
strategy.set_config("macd_indicator_name", "macd_980_1960_100")
strategy.set_config("fast_period", 980)
strategy.set_config("slow_period", 1960)
strategy.set_config("signal_period", 100)
strategy.set_config("bottom_border_macd_to_buy", 0.0)
strategy.set_config("trend_lookback", 3)
strategy.set_config("grid_quantity_absolute", 100.0)
strategy.set_config("grid_profit_pct", 0.85)
```

### Bottom Border Tuning

The `bottom_border_macd_to_buy` parameter controls when the strategy is allowed to buy:

| Bottom Border | Effect |
|---------------|--------|
| `0.0` (default) | Buy on any trough when MACD is negative |
| `-0.5` | Only buy when MACD is deeply negative (strong dip) |
| `-1.0` | Very selective, only buy during extreme conditions |

### Noise Filter

The `min_relative_threshold` parameter prevents floating-point noise near zero from triggering false reversals. Signals are only generated when `abs(current MACD - previous MACD) / signal_magnitude >= min_relative_threshold`.

| Threshold | Effect |
|-----------|--------|
| `0.001` (default) | Requires 0.1% change, filters noise on all assets |
| `0.0005` | Requires 0.05%, moderate filtering |
| `0.005` | Requires 0.5%, aggressive filtering, only strong reversals |

## Architecture

### Method Structure

```
on_tick()
  ├── _initialize_macd()              # Initialize configuration on first tick
  ├── _get_macd_values()              # Extract MACD values from tick data
  ├── _detect_momentum()              # Detect peak/trough and generate signal
  │   ├── _check_sma_filter()         # Optional SMA price filter
  │   ├── _signal_buy()               # Create BUY signal (trough detected)
  │   └── _signal_sell()              # Create SELL signal (peak detected)
  └── Update state variables
```

### Key Methods

- **`on_tick(tick)`**: Main entry point called for each incoming tick
- **`_initialize_macd()`**: Loads configuration parameters and logs them
- **`_get_macd_values(tick)`**: Extracts MACD and signal values from tick indicators
- **`_detect_momentum(macd, signal, tick)`**: Detects peaks (sell) and troughs (buy) in MACD line
- **`_check_sma_filter(tick)`**: Validates price is below configured SMA thresholds
- **`_signal_buy(tick, macd, signal)`**: Creates and logs BUY signals with expected profit price
- **`_signal_sell(tick, macd, signal)`**: Creates and logs SELL signals
- **`on_position_closed(symbol, price, exit_reason)`**: Resets `in_position` on external close
- **`get_stats()`**: Returns comprehensive strategy statistics

## Logging

### Initialization

On first tick, the strategy logs its configuration:

```
[strategy_id] MACD: name=macd_980_1960_100, fast=980, slow=1960, signal=100, min_relative_threshold=0.001, bottom_border=0.0
[strategy_id] Trade: quantity=100.0 USDC, profit_target=0.85%
[strategy_id] Config: {'macd_indicator_name': 'macd_980_1960_100', ...}
[strategy_id] Indicators: {'macd_980_1960_100_macd': -0.0012, ...}
```

### Periodic Status

Every 500 ticks, the strategy logs current state:

```
{timestamp} Tick 500: macd=-0.0012, signal=-0.0015, in_position=False, sig_cnt=3
```

### Signal Generation

```
[strategy_id] BUY signal: MACD=-0.0018, Signal=-0.0019, histogram=0.0001, price=0.11033, qty=906.22, expected_profit=0.11127
[strategy_id] SELL signal: MACD=0.0021, Signal=0.0018, histogram=0.0003, price=0.11250
```

### Position Closure

```
[strategy_id] Position closed for DOGE/USDC: reason=take_profit, price=0.11127
```

## Statistics

The `get_stats()` method returns:

```python
{
    "strategy_id": "macd_momentum_doge",
    "state": "RUNNING",
    "symbols": ["DOGE/USDC"],
    "ticks_processed": 1000,
    "signals_generated": 8,
    "active_positions": 0,
    "total_unrealized_pnl": 0.0,
    "errors": 0,
    "last_macd": -0.0012,
    "last_signal": -0.0015,
    "last_histogram": 0.0003,
    "prev_macd": -0.0014,
    "in_position": False,
    "signal_count": 8,
    "tick_count": 1000,
    "macd_indicator_name": "macd_980_1960_100",
    "fast_period": 980,
    "slow_period": 1960,
    "signal_period": 100,
    "min_relative_threshold": 0.001,
    "bottom_border_macd_to_buy": 0.0,
    "grid_quantity_absolute": 100.0,
    "grid_profit_pct": 0.85,
    "sma_fast": "sma_800",
    "sma_slow": "sma_2000",
    "sma_multiplicator": 0.997,
    "trend_lookback": 3,
}
```

## Indicator Data Format

The strategy expects tick indicators with the `macd_980_1960_100` prefix:

```python
tick.indicators = {
    "macd_980_1960_100_macd": -0.0012,
    "macd_980_1960_100_signal": -0.0015,
    "macd_980_1960_100_histogram": 0.0003,
}
```

If the configured indicator name is not found, it falls back to simple names (`macd`, `macd_signal`, `macd_histogram`) and finally auto-detection.

## Signal Metadata

### BUY Signal

```python
{
    "macd": -0.0018,
    "signal": -0.0019,
    "histogram": 0.0001,
    "momentum_type": "trough_buy",
    "signal_count": 3,
    "expected_profit_price": 0.11127,
    "quantity_usdc": 100.0,
}
```

### SELL Signal

```python
{
    "macd": 0.0021,
    "signal": 0.0018,
    "histogram": 0.0003,
    "momentum_type": "peak_sell",
    "signal_count": 4,
}
```

## Usage Example

```python
from decimal import Decimal
from datetime import UTC, datetime
from src.domain.strategies.base import EnrichedTick
from src.strategies.user.macd_momentum_strategy import MACDMomentumStrategy

# Create strategy
strategy = MACDMomentumStrategy(
    strategy_id="macd_momentum_btc",
    symbols=["BTC/USDC"],
)

# Configure
strategy.set_config("macd_indicator_name", "macd_980_1960_100")
strategy.set_config("fast_period", 980)
strategy.set_config("slow_period", 1960)
strategy.set_config("signal_period", 100)
strategy.set_config("bottom_border_macd_to_buy", 0.0)
strategy.set_config("trend_lookback", 3)

# Process ticks
tick = EnrichedTick(
    symbol="BTC/USDC",
    price=Decimal("50000.0"),
    volume=Decimal("10.5"),
    time=datetime.now(UTC),
    indicators={
        "macd_980_1960_100_macd": -0.0015,
        "macd_980_1960_100_signal": -0.0018,
        "macd_980_1960_100_histogram": 0.0003,
    },
)

signal = strategy.on_tick(tick)
if signal:
    print(f"Signal: {signal.signal_type} @ {signal.price}")
```

## Risk Considerations

- The strategy opens long positions only — it does not short
- Take-profit is handled externally via `expected_profit_price` in BUY metadata
- The `in_position` flag prevents multiple simultaneous positions per strategy instance
- SELL signals are only generated when `in_position` is `True`, ensuring matched pairs
- The cooldown mechanism prevents re-triggering on the same extremum
