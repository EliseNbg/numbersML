"""
Tests for RSIMovingAverageAlgorithm.

Comprehensive test suite covering:
- State persistence between ticks
- Signal generation (BUY/SELL)
- Configuration access
- Entry/exit conditions
- Edge cases and error handling
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.algorithms.base import EnrichedTick, SignalType
from src.domain.algorithms.rsi_moving_average_algorithm import (
    RSIMovingAverageAlgorithm,
)


@pytest.fixture
def algorithm() -> RSIMovingAverageAlgorithm:
    """Create a fresh algorithm instance for testing."""
    return RSIMovingAverageAlgorithm(
        algorithm_id=uuid4(),
        symbols=["BTC/USDT"],
    )


@pytest.fixture
def create_tick():
    """Factory fixture to create enriched ticks with custom values."""

    def _create(
        symbol: str = "BTC/USDT",
        price: float = 100.0,
        rsi: float = 50.0,
        sma: float = 100.0,
        volume: float = 1.0,
    ) -> EnrichedTick:
        return EnrichedTick(
            symbol=symbol,
            price=Decimal(str(price)),
            volume=Decimal(str(volume)),
            time=datetime.now(UTC),
            indicators={
                "rsiindicator_period14_rsi": rsi,
                "smaindicator_period20_sma": sma,
            },
        )

    return _create


class TestInitialization:
    """Test algorithm initialization and setup."""

    def test_initialization(self, algorithm):
        """Test algorithm initializes with correct state."""
        assert algorithm._tick_count == 0
        assert algorithm._position is None
        assert len(algorithm._price_history) == 0
        assert len(algorithm._rsi_history) == 0
        assert algorithm._last_signal_time is None
        assert algorithm.get_config("rsi_oversold", 30) == 30

    def test_initialization_with_time_frame(self):
        """Test algorithm respects time frame parameter."""
        from src.domain.algorithms.base import TimeFrame

        algo = RSIMovingAverageAlgorithm(
            algorithm_id=uuid4(),
            symbols=["ETH/USDT"],
            time_frame=TimeFrame.HOUR,
        )
        assert algo.time_frame == TimeFrame.HOUR
        assert "ETH/USDT" in algo.symbols


class TestStatePersistence:
    """Test that state persists between ticks."""

    def test_tick_counter_increments(self, algorithm, create_tick):
        """Test tick counter increments on each tick."""
        assert algorithm._tick_count == 0

        tick1 = create_tick()
        algorithm.on_tick(tick1)
        assert algorithm._tick_count == 1

        tick2 = create_tick()
        algorithm.on_tick(tick2)
        assert algorithm._tick_count == 2

    def test_price_history_updates(self, algorithm, create_tick):
        """Test price history is maintained."""
        prices = [100.0, 101.0, 99.0, 102.0]

        for price in prices:
            tick = create_tick(price=price)
            algorithm.on_tick(tick)

        assert len(algorithm._price_history) == 4
        assert algorithm._price_history[-1] == Decimal("102.0")

    def test_price_history_limits_size(self, algorithm, create_tick):
        """Test price history is limited to max_price_history."""
        algorithm._max_price_history = 3

        for i in range(5):
            tick = create_tick(price=100.0 + i)
            algorithm.on_tick(tick)

        assert len(algorithm._price_history) == 3
        assert algorithm._price_history[0] == Decimal("102.0")

    def test_rsi_history_updates(self, algorithm, create_tick):
        """Test RSI history is tracked."""
        rsi_values = [45.0, 42.0, 38.0, 35.0]

        for rsi in rsi_values:
            tick = create_tick(rsi=rsi)
            algorithm.on_tick(tick)

        assert len(algorithm._rsi_history) == 4
        assert algorithm._rsi_history[-1] == 35.0

    def test_position_persists_between_ticks(self, algorithm, create_tick):
        """Test position state persists after entry."""
        algorithm.set_config("rsi_oversold", 40)
        algorithm.set_config("min_rsi", 25)
        # Setup: RSI history with rising pattern
        algorithm._rsi_history = [18.0, 20.0, 21.0, 22.0]

        tick = create_tick(price=101.0, rsi=22.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is not None
        assert algorithm._position is not None
        assert algorithm._position["side"] == "LONG"

        # Next tick should still have position
        tick2 = create_tick(price=102.0, rsi=35.0, sma=100.0)
        algorithm.on_tick(tick2)

        assert algorithm._position is not None


class TestSignalGeneration:
    """Test BUY and SELL signal generation."""

    def test_buy_signal_oversold_with_momentum(self, algorithm, create_tick):
        """Test buy signal when RSI oversold and rising."""
        algorithm.set_config("rsi_oversold", 30)
        algorithm.set_config("min_rsi", 25)

        # Setup: RSI rising pattern (last 3 before current tick)
        # Current tick will have rsi=22.0 (appended to history)
        # History before current: [18.0, 20.0, 21.0] - all rising
        algorithm._rsi_history = [18.0, 20.0, 21.0, 22.0]

        # Price above SMA for trend confirmation
        tick = create_tick(price=101.0, rsi=22.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["reason"] == "rsi_oversold_with_momentum"
        assert signal.metadata["rsi"] == 22.0

    def test_no_buy_when_rsi_not_oversold(self, algorithm, create_tick):
        """Test no buy signal when RSI is not oversold."""
        algorithm.set_config("rsi_oversold", 30)

        tick = create_tick(price=101.0, rsi=45.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is None

    def test_no_buy_when_price_below_sma(self, algorithm, create_tick):
        """Test no buy signal when price is below SMA."""
        algorithm.set_config("rsi_oversold", 30)
        algorithm._rsi_history = [22.0, 24.0, 26.0]

        # Price below SMA
        tick = create_tick(price=98.0, rsi=25.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is None

    def test_no_buy_when_rsi_not_rising(self, algorithm, create_tick):
        """Test no buy signal when RSI is not rising."""
        algorithm.set_config("rsi_oversold", 30)

        # RSI not rising (flat/declining)
        algorithm._rsi_history = [28.0, 27.0, 26.0]

        tick = create_tick(price=101.0, rsi=25.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is None

    def test_sell_signal_stop_loss(self, algorithm, create_tick):
        """Test sell signal on stop loss."""
        # Enter position
        algorithm.set_config("rsi_oversold", 40)
        algorithm.set_config("min_rsi", 10)
        algorithm.set_config("stop_loss_pct", 2.0)
        # Setup RSI history for entry - use lower values
        algorithm._rsi_history = [6.0, 7.0, 8.0, 9.0]

        tick = create_tick(price=100.0, rsi=9.0, sma=99.0)
        buy_signal = algorithm.on_tick(tick)
        assert buy_signal is not None

        # Price drops 3% (triggers stop loss)
        tick2 = create_tick(price=97.0, rsi=25.0, sma=99.0)
        sell_signal = algorithm.on_tick(tick2)

        assert sell_signal is not None
        assert sell_signal.signal_type == SignalType.SELL
        assert sell_signal.metadata["reason"] == "stop_loss"
        assert sell_signal.metadata["pnl_pct"] <= -2.0

    def test_sell_signal_take_profit(self, algorithm, create_tick):
        """Test sell signal on take profit."""
        # Enter position
        algorithm.set_config("rsi_oversold", 40)
        algorithm.set_config("min_rsi", 10)
        algorithm.set_config("take_profit_pct", 3.0)
        # Setup RSI history for entry - use lower values
        algorithm._rsi_history = [6.0, 7.0, 8.0, 9.0]

        tick = create_tick(price=100.0, rsi=9.0, sma=99.0)
        buy_signal = algorithm.on_tick(tick)
        assert buy_signal is not None

        # Price rises 4% (triggers take profit)
        tick2 = create_tick(price=104.0, rsi=60.0, sma=100.0)
        sell_signal = algorithm.on_tick(tick2)

        assert sell_signal is not None
        assert sell_signal.signal_type == SignalType.SELL
        assert sell_signal.metadata["reason"] == "take_profit"
        assert sell_signal.metadata["pnl_pct"] >= 3.0

    def test_sell_signal_rsi_overbought(self, algorithm, create_tick):
        """Test sell signal when RSI overbought."""
        # Enter position
        algorithm.set_config("rsi_oversold", 40)
        algorithm.set_config("min_rsi", 10)
        algorithm.set_config("rsi_overbought", 70)
        # Setup RSI history for entry - use lower values
        algorithm._rsi_history = [6.0, 7.0, 8.0, 9.0]

        tick = create_tick(price=100.0, rsi=9.0, sma=99.0)
        buy_signal = algorithm.on_tick(tick)
        assert buy_signal is not None

        # RSI goes overbought
        tick2 = create_tick(price=102.0, rsi=75.0, sma=101.0)
        sell_signal = algorithm.on_tick(tick2)

        assert sell_signal is not None
        assert sell_signal.signal_type == SignalType.SELL
        assert sell_signal.metadata["reason"] == "rsi_overbought"

    def test_position_cleared_after_sell(self, algorithm, create_tick):
        """Test position state is cleared after SELL signal."""
        algorithm.set_config("rsi_oversold", 40)
        algorithm.set_config("min_rsi", 10)
        algorithm.set_config("take_profit_pct", 3.0)
        # Setup RSI history for entry - use lower values
        algorithm._rsi_history = [6.0, 7.0, 8.0, 9.0]

        tick = create_tick(price=100.0, rsi=9.0, sma=99.0)
        algorithm.on_tick(tick)
        assert algorithm._position is not None

        # Sell
        tick2 = create_tick(price=104.0, rsi=60.0, sma=100.0)
        algorithm.on_tick(tick2)
        assert algorithm._position is None


class TestConfigAccess:
    """Test configuration access and runtime overrides."""

    def test_get_config_with_default(self, algorithm):
        """Test get_config returns default when key missing."""
        value = algorithm.get_config("nonexistent", 42)
        assert value == 42

    def test_get_config_without_default(self, algorithm):
        """Test get_config returns None when key missing and no default."""
        value = algorithm.get_config("nonexistent")
        assert value is None

    def test_set_and_get_config(self, algorithm):
        """Test runtime config override."""
        algorithm.set_config("quantity", 0.05)
        assert algorithm.get_config("quantity") == 0.05

    def test_config_in_signal_generation(self, algorithm, create_tick):
        """Test config values affect signal generation."""
        algorithm.set_config("rsi_oversold", 30)
        algorithm.set_config("min_rsi", 10)
        algorithm.set_config("quantity", 0.1)
        # Setup RSI history for entry - use lower values
        algorithm._rsi_history = [6.0, 7.0, 8.0, 9.0]

        tick = create_tick(price=101.0, rsi=9.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is not None
        assert signal.metadata["quantity"] == 0.1


class TestAlgorithmState:
    """Test state getter for monitoring."""

    def test_get_state_no_position(self, algorithm, create_tick):
        """Test state when no position."""
        tick = create_tick()
        algorithm.on_tick(tick)

        state = algorithm.get_algorithm_state()
        assert state["has_position"] is False
        assert state["tick_count"] == 1
        assert state["position"] is None

    def test_get_state_with_position(self, algorithm, create_tick):
        """Test state when position exists."""
        algorithm.set_config("rsi_oversold", 40)
        algorithm.set_config("min_rsi", 10)
        # Setup RSI history for entry - use lower values
        algorithm._rsi_history = [6.0, 7.0, 8.0, 9.0]

        tick = create_tick(price=100.0, rsi=9.0, sma=99.0)
        algorithm.on_tick(tick)

        state = algorithm.get_algorithm_state()
        assert state["has_position"] is True
        assert state["position"] is not None
        assert state["position"]["side"] == "LONG"

    def test_get_state_rsi_history_count(self, algorithm, create_tick):
        """Test RSI history count in state."""
        for i in range(5):
            tick = create_tick(rsi=30.0 + i)
            algorithm.on_tick(tick)

        state = algorithm.get_algorithm_state()
        assert state["rsi_history_count"] == 5


class TestSymbolFiltering:
    """Test algorithm only processes configured symbols."""

    def test_ignore_wrong_symbol(self, algorithm, create_tick):
        """Test algorithm ignores ticks for non-configured symbols."""
        # Algorithm is configured for BTC/USDT only
        tick = create_tick(symbol="ETH/USDT", price=100.0, rsi=25.0, sma=99.0)

        signal = algorithm.on_tick(tick)
        assert signal is None
        assert algorithm._tick_count == 0  # Tick was ignored

    def test_process_correct_symbol(self, algorithm, create_tick):
        """Test algorithm processes ticks for configured symbols."""
        tick = create_tick(symbol="BTC/USDT", price=100.0, rsi=25.0, sma=99.0)

        algorithm.on_tick(tick)
        assert algorithm._tick_count == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_insufficient_rsi_history_for_entry(self, algorithm, create_tick):
        """Test no buy signal when RSI history insufficient."""
        algorithm.set_config("rsi_oversold", 30)

        # Only 2 RSI values (need 3+ for momentum check)
        algorithm._rsi_history = [22.0, 24.0]

        tick = create_tick(price=101.0, rsi=25.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is None

    def test_sell_without_position(self, algorithm, create_tick):
        """Test no sell signal when no position exists."""
        tick = create_tick(price=100.0, rsi=75.0, sma=101.0)

        # RSI overbought but no position
        signal = algorithm.on_tick(tick)

        assert signal is None

    def test_min_rsi_filter(self, algorithm, create_tick):
        """Test min_rsi config filters weak oversold signals."""
        algorithm.set_config("rsi_oversold", 30)
        algorithm.set_config("min_rsi", 28)

        algorithm._rsi_history = [22.0, 24.0, 26.0]

        # RSI 29 is oversold but above min_rsi (28)
        tick = create_tick(price=101.0, rsi=29.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        # Should not buy because RSI 29 > min_rsi 28
        assert signal is None

    def test_last_signal_time_updated(self, algorithm, create_tick):
        """Test last_signal_time is updated on signals."""
        algorithm.set_config("rsi_oversold", 30)
        algorithm.set_config("min_rsi", 10)
        # Setup RSI history for entry - use lower values
        algorithm._rsi_history = [6.0, 7.0, 8.0, 9.0]

        assert algorithm._last_signal_time is None

        tick = create_tick(price=101.0, rsi=9.0, sma=100.0)
        signal = algorithm.on_tick(tick)

        assert signal is not None
        assert algorithm._last_signal_time is not None

    def test_multiple_symbols(self):
        """Test algorithm with multiple symbols."""
        algo = RSIMovingAverageAlgorithm(
            algorithm_id=uuid4(),
            symbols=["BTC/USDT", "ETH/USDT"],
        )

        assert "BTC/USDT" in algo.symbols
        assert "ETH/USDT" in algo.symbols

        # Test each symbol gets processed
        tick1 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("100.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsiindicator_period14_rsi": 50.0},
        )
        tick2 = EnrichedTick(
            symbol="ETH/USDT",
            price=Decimal("200.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsiindicator_period14_rsi": 50.0},
        )

        algo.on_tick(tick1)
        algo.on_tick(tick2)

        assert algo._tick_count == 2
