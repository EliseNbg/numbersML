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
| `avg_multiplicator_day` | `float` | `0.991` | Multiplier applied to day average price for comparison |
| `avg_multiplicator_week` | `float` | `0.991` | Multiplier applied to week average price for comparison |
| `rsi_99_threshold` | `float` | `32.0` | RSI filter threshold |
| `trend_lookback` | `int` | `3` | Number of ticks to confirm downtrend before reversal |
| `max_open_positions` | `int` | `5` | Maximum number of simultaneous open positions. Enforced by ``open_position()`` — returns ``None`` when the limit is reached. |

### Position Management (base class)

The base ``Strategy`` class provides automatic take-profit and stop-loss checking
via ``process_tick()``.

**``Position`` fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| ``take_profit_price`` | ``Decimal \| None`` | ``None`` | Price that triggers an auto-close for profit |
| ``stop_loss_price`` | ``Decimal \| None`` | ``None`` | Price that triggers an auto-close to limit loss |

**How it works:**

1. A strategy calls ``self.open_position(symbol, side, quantity, price, take_profit_price, stop_loss_price)``.
2. If ``len(self._positions) >= self.max_open_positions``, the open is rejected with a warning.
3. On every tick, ``process_tick()`` first runs ``_check_positions(tick)``, which:
   - Updates the position's current price
   - Tests ``is_take_profit_hit()`` / ``is_stop_loss_hit()``
   - If triggered, closes the position, calls ``on_position_closed()``, and returns a close ``Signal``
4. Only if no TP/SL is triggered does ``on_tick()`` run, so the strategy can evaluate new entries.

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
| `MACDBuyStrategy` | All except `prev_macd`, `avg_multiplicator_day`, `avg_multiplicator_week`, `rsi_99_threshold`, `trend_lookback` |
| `InfinityGridStrategy` | `grid_profit_pct`, `grid_quantity_absolute` (via config) |

Strategies that do not reference these attributes (`SMACrossStrategy`,
`BollingerBandsStrategy`, `ExampleRSIStrategy`, `GridTradingStrategy`) simply inherit
unused defaults with no behavioural impact.
