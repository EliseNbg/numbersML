"""User-written strategy classes.

Place your custom strategy classes in this directory.
Each strategy must inherit from src.domain.strategies.base.Strategy
and implement the on_tick method.

Available reference implementations:
- example_rsi_strategy.ExampleRSIStrategy - RSI-based strategy
- grid_strategy.GridTradingStrategy - Grid trading strategy
- macd_cross_strategy.MACDCrossStrategy - MACD crossover strategy
- bollinger_strategy.BollingerBandsStrategy - Bollinger Bands mean reversion
- sma_cross_strategy.SMACrossStrategy - SMA Golden/Death Cross

Example:
    from src.domain.strategies.base import Strategy, Signal, SignalType

    class MyStrategy(Strategy):
        def on_tick(self, tick):
            # Access indicators
            rsi = tick.get_indicator('rsiindicator_period14_rsi')
            # Access config
            threshold = self.get_config('threshold', 30)
            # Generate signal
            if rsi < threshold:
                return Signal(self.id, tick.symbol, SignalType.BUY, tick.price)
            return None
"""
