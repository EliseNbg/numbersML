# Infinity Grid Trading Strategy

## Overview

The Infinity Grid Trading Strategy is a simple grid-based trading approach that places buy orders at predefined grid levels when price crosses from above to below a level. After a buy signal, buying is locked until price crosses an adjacent level (either above or below). The strategy does not track which levels have been used - levels can be reused multiple times as long as the locking mechanism allows it.

## Key Features

- **Simple Grid Usage**: The strategy generates buy signals at ANY grid level when price crosses from above to below.
- **Expected Profit Price**: Each buy signal includes an `expected_profit_price` in its metadata, calculated as `buy_price × (1 + grid_profit_pct/100)`.
- **No Built-in Take-Profit Levels**: The strategy does not generate sell signals. Users must place sell orders (e.g., limit orders) at the expected profit price or manage exits externally.
- **Adjacent-Level Locking**: After generating a buy signal at level N, buying is locked until price crosses either level N-1 or N+1 (in either direction).
- **Multi-Symbol Support**: Tracks lock state independently for each symbol in the universe.
- **Configuration-Driven**: All grid parameters are configurable via strategy configuration.

## Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `grid_size` | integer | 8 | Number of grid levels |
| `grid_spacing_pct` | float | 0.65 | Spacing between grid levels as a percentage of the reference price |
| `grid_profit_pct` | float | 0.85 | Profit target percentage for each buy level (used to calculate expected profit price) |
| `grid_quantity_absolute` | float | 100.0 | Dollar amount to allocate per grid position |

## Grid Calculation

The strategy calculates grid levels both above and below the reference price with uniform spacing. The reference price itself is not included in the levels array.

1. **Reference Price**: Set to the first received tick price when the strategy starts.
2. **Price Spacing**: `spacing = reference_price × (grid_spacing_pct / 100)`
3. **Grid Levels Calculation**:
   - The strategy creates `grid_size` price levels distributed evenly around (but not including) the reference price
   - Half of the levels are below the reference price, half are above (for even grid_size)
   - Levels are calculated as: `reference_price ± n × spacing` where n = 1, 2, 3, ... up to grid_size/2
   - The reference price itself is not included in the grid levels array

With the default configuration (`grid_size=8`, `grid_spacing_pct=0.65`, reference price=50000):
- Spacing = 50000 × 0.65/100 = 325
- Grid levels: [48700, 49025, 49350, 49675, 50325, 50650, 50975, 51300]
  - Note: Reference price (50000) is not in the array
  - Levels below reference: [48700, 49025, 49350, 49675] (indices 0-3)
  - Levels above reference: [50325, 50650, 50975, 51300] (indices 4-7)

## Signal Generation

When the market price crosses below an available grid level (from above to at/below the level) AND buying is not currently locked for that symbol, the strategy generates a BUY signal with:

- **Signal Type**: `BUY`
- **Price**: Current tick price
- **Metadata**:
  - `grid_level`: The price level that was triggered
  - `grid_index`: Index of the level in the grid array
  - `expected_profit_price`: `grid_level × (1 + grid_profit_pct/100)`
  - `reference_price`: The reference price used for grid calculation

## Adjacent-Level Locking Mechanism

To prevent multiple signals at the same level during volatile markets:
1. After a BUY signal is generated at level N, buying becomes "locked" for that symbol
2. Buying remains locked until the price crosses either level N-1 or N+1 (in either direction - above to below or below to above)
3. Once an adjacent level is crossed, the lock is released and buying is enabled again for all levels

This mechanism ensures that after a buy signal, we wait for the price to move to an adjacent level before allowing another buy signal, preventing whipsaw trades at the same level.

## Position Management

- **Opening**: When a BUY signal is generated, buying becomes locked for that symbol until an adjacent level is crossed.
- **Closing**: The strategy does not close positions directly. Instead, it relies on external position closure notifications (via the `on_position_closed` callback) for tracking purposes, but does not use this for locking/unlocking.
- **Reuse**: Levels can be reused multiple times as long as the locking mechanism allows it (i.e., after buying is unlocked by crossing an adjacent level).

## Usage Example

```python
# Strategy initialization
strategy = InfinityGridStrategy(
    strategy_id="infinity_grid_btc",
    symbols=["BTC/USDT"]
)

# Configure grid parameters
strategy.set_config("grid_size", 8)
strategy.set_config("grid_spacing_pct", 0.65)
strategy.set_config("grid_profit_pct", 0.85)
strategy.set_config("grid_quantity_absolute", 100.0)

# Process incoming ticks
signal = strategy.process_tick(enriched_tick)
if signal and signal.signal_type == SignalType.BUY:
    # Place a buy order at signal.price
    # Place a corresponding sell limit order at signal.metadata["expected_profit_price"]
    # (or manage the exit via your preferred method)
    pass
```

## Integration with Market Services

The strategy is designed to work with the existing market service abstraction:

1. **Buy Orders**: Place market or limit orders at the signal price.
2. **Sell Orders**: Place limit orders at the `expected_profit_price` from the signal metadata, or use other exit strategies (trailing stop, manual exit, etc.).
3. **Position Closure Notification**: When a position is closed (by whichever method), notify the strategy by calling `on_position_closed` with:
   - `symbol`: The traded symbol
   - `price`: The exit price
   - `exit_reason`: Reason for closure (e.g., "take_profit", "stop_loss")
   - `grid_index`: Optional grid index (if known; the strategy stores it for statistics but doesn't use it for logic)

## Testing

Unit tests for this strategy are located in:
`tests/unit/strategies/test_infinity_grid_strategy.py`

Tests cover:
- Grid initialization and level calculation
- Signal generation with correct expected profit prices
- Adjacent-level locking mechanism
- Multiple symbol handling
- Statistics reporting

## Notes

- The strategy does not implement stop-loss functionality. Users should implement their own risk management.
- The `grid_quantity_absolute` parameter is informational; actual order sizing should be handled by the trading execution layer based on account balance and risk parameters.
- For best results, ensure that the market service used provides timely and accurate tick data.
