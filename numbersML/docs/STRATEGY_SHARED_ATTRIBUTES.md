# Shared Strategy Configuration Attributes

## Overview

The base `Strategy` class (defined in `src/domain/strategies/base.py`) declares a set of common
configuration and state attributes with sensible defaults. All derived class-based strategies
inherit these automatically, avoiding duplicate declarations across `MACDPeakStrategy`,
`MACDCrossStrategy`, `MACDBuyStrategy`, etc.

Subclasses may override any attribute in their `__init__` (if they need a different default)
or via `self.get_config("key", default)` at initialization time (e.g., `_initialize_macd()`),
which reads from the strategy's persistent configuration dictionary.

## Declared Attributes

Default values are set in `Strategy.__init__()`:

### MACD State (tracking)

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `last_macd` | `float` | `0.0` | Previous tick's MACD line value |
| `last_signal` | `float` | `0.0` | Previous tick's signal line value |
| `last_histogram` | `float` | `0.0` | Previous tick's histogram (`macd - signal`) |
| `prev_macd` | `float` | `0.0` | MACD value before `last_macd` (used for trend detection) |
| `signal_count` | `int` | `0` | Total number of signals generated |

### MACD Indicator Configuration

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `macd_indicator_name` | `str` | `"macdindicator"` | Prefix name of MACD indicators in tick data |
| `fast_period` | `int` | `12` | MACD fast EMA period |
| `slow_period` | `int` | `26` | MACD slow EMA period |
| `signal_period` | `int` | `9` | Signal line EMA period |
| `min_relative_threshold` | `float` | `0.001` | Minimum relative change to avoid noise |

### Trade / Grid Parameters

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `bottom_border_macd_to_buy` | `float` | `0.0` | Maximum MACD value for BUY signals |
| `grid_quantity_absolute` | `float` | `100.0` | USDC amount per grid position |
| `grid_profit_pct` | `float` | `0.85` | Target profit percentage per trade |

### Price Filters

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `sma_fast` | `str \| None` | `None` | Name of fast SMA indicator (e.g. `"sma_800"`) |
| `sma_slow` | `str \| None` | `None` | Name of slow SMA indicator (e.g. `"sma_2000"`) |
| `sma_multiplicator` | `float` | `0.997` | Multiplier applied to SMA values for comparison |
| `avg_multiplicator` | `float` | `0.991` | Multiplier applied to average price filter |
| `rsi_99_threshold` | `float` | `32.0` | RSI filter threshold |
| `trend_lookback` | `int` | `3` | Number of ticks to confirm downtrend before reversal |

## Usage From Subclasses

Subclasses access these as normal `self.` attributes. Override with config values at
initialization time:

```python
def _initialize_macd(self, tick: EnrichedTick) -> None:
    self.fast_period = self.get_config("fast_period", 12)
    self.slow_period = self.get_config("slow_period", 26)
    # ...
```

The base class provides the defaults; `_initialize_macd()` (or equivalent) is called on the
first tick and overrides them from the strategy's persistent config.

## Strategies Using These Attributes

| Strategy | Uses |
|----------|------|
| `MACDPeakStrategy` | All attributes |
| `MACDCrossStrategy` | `last_macd`, `last_signal`, `last_histogram`, `macd_indicator_name`, `fast_period`, `slow_period`, `signal_period`, `min_relative_threshold` |
| `MACDBuyStrategy` | All except `prev_macd`, `avg_multiplicator`, `rsi_99_threshold`, `trend_lookback` |
| `InfinityGridStrategy` | `grid_profit_pct`, `grid_quantity_absolute` (via config) |

Strategies that do not reference these attributes (`SMACrossStrategy`,
`BollingerBandsStrategy`, `ExampleRSIStrategy`, `GridTradingStrategy`) simply inherit
unused defaults with no behavioural impact.
