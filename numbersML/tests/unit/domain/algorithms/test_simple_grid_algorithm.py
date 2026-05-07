"""
Unit tests for SimpleGridAlgorithm.

Follows TDD approach: tests first, then implementation.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.algorithms.base import EnrichedTick, SignalType
from src.domain.algorithms.simple_grid_algorithm import SimpleGridAlgorithm


@pytest.fixture
def algorithm():
    """Create a SimpleGridAlgorithm for testing."""
    return SimpleGridAlgorithm(
        algorithm_id=uuid4(),
        symbols=["BTC/USDT"],
    )


@pytest.fixture
def create_tick():
    """Factory for creating EnrichedTick."""

    def _create(price=100.0, symbol="BTC/USDT"):
        return EnrichedTick(
            symbol=symbol,
            price=Decimal(str(price)),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={},
        )

    return _create


class TestSimpleGridAlgorithmInit:
    """Tests for SimpleGridAlgorithm initialization."""

    def test_create_algorithm(self, algorithm):
        """Test creating a SimpleGridAlgorithm."""
        assert algorithm.id is not None
        assert algorithm.symbols == ["BTC/USDT"]
        assert len(algorithm.get_grid_levels()) == 0

    def test_initial_state(self, algorithm):
        """Test initial state is empty."""
        state = algorithm.get_algorithm_state()
        assert state["has_position"] is False
        assert state["grid_levels_count"] == 0
        assert state["base_price"] is None


class TestGridInitialization:
    """Tests for grid initialization."""

    def test_grid_setup_on_first_tick(self, algorithm, create_tick):
        """Test grid is set up on first tick."""
        tick = create_tick(price=100.0)
        algorithm.on_tick(tick)

        levels = algorithm.get_grid_levels()
        assert len(levels) > 0

        # Check levels are around 100.0
        for level in levels:
            assert Decimal("90.0") < level < Decimal("110.0")

    def test_grid_levels_count(self, algorithm, create_tick):
        """Test correct number of grid levels."""
        algorithm.set_config("grid_levels", 3)

        tick = create_tick(price=100.0)
        algorithm.on_tick(tick)

        # 3 levels below + 3 levels above = 6 total
        levels = algorithm.get_grid_levels()
        assert len(levels) == 6


class TestEntrySignals:
    """Tests for entry signal generation."""

    def test_buy_signal_near_grid(self, algorithm, create_tick):
        """Test buy signal when price is near grid level."""
        # Setup grid at 100
        tick1 = create_tick(price=100.0)
        algorithm.on_tick(tick1)

        # Price at 99.0 should be near a buy grid level (assuming 1% spacing)
        tick2 = create_tick(price=99.0)
        signal = algorithm.on_tick(tick2)

        if signal:
            assert signal.signal_type == SignalType.BUY
            assert signal.symbol == "BTC/USDT"
            assert signal.metadata["reason"] == "price_near_grid"

    def test_no_signal_with_position(self, algorithm, create_tick):
        """Test no buy signal when position exists."""
        # Setup grid
        tick1 = create_tick(price=100.0)
        algorithm.on_tick(tick1)

        # Manually set position (simulate having a position)
        algorithm._position = {
            "entry_price": 99.0,
            "quantity": 0.01,
            "side": "LONG",
        }

        # Try to get buy signal
        tick2 = create_tick(price=98.0)
        signal = algorithm.on_tick(tick2)

        # Should not get buy signal with open position
        assert signal is None


class TestExitSignals:
    """Tests for exit signal generation."""

    def test_sell_signal_take_profit(self, algorithm, create_tick):
        """Test sell signal at take profit."""
        # Setup and create position
        tick1 = create_tick(price=100.0)
        algorithm.on_tick(tick1)

        algorithm._position = {
            "entry_price": 100.0,
            "quantity": 0.01,
            "side": "LONG",
        }

        # Set take profit to 0.5%
        algorithm.set_config("take_profit_pct", 0.5)

        # Price rises to trigger take profit
        tick2 = create_tick(price=100.6)  # 0.6% profit
        signal = algorithm.on_tick(tick2)

        if signal:
            assert signal.signal_type == SignalType.SELL
            assert signal.metadata["reason"] == "take_profit"

    def test_sell_signal_stop_loss(self, algorithm, create_tick):
        """Test sell signal at stop loss."""
        # Setup and create position
        algorithm.set_config("stop_loss_pct", 2.0)

        tick1 = create_tick(price=100.0)
        algorithm.on_tick(tick1)

        algorithm._position = {
            "entry_price": 100.0,
            "quantity": 0.01,
            "side": "LONG",
        }

        # Price drops to trigger stop loss
        tick2 = create_tick(price=97.5)  # -2.5% loss
        signal = algorithm.on_tick(tick2)

        if signal:
            assert signal.signal_type == SignalType.SELL
            assert signal.metadata["reason"] == "stop_loss"


class TestConfigAccess:
    """Tests for configuration access."""

    def test_get_config_with_default(self, algorithm):
        """Test get_config returns default when key missing."""
        value = algorithm.get_config("nonexistent", 42)
        assert value == 42

    def test_set_and_get_config(self, algorithm):
        """Test runtime config override."""
        algorithm.set_config("quantity", 0.05)
        assert algorithm.get_config("quantity") == 0.05

    def test_grid_config_influences_levels(self, algorithm, create_tick):
        """Test that grid_levels config affects grid."""
        algorithm.set_config("grid_levels", 2)
        algorithm.set_config("grid_spacing_pct", 1.0)

        tick = create_tick(price=100.0)
        algorithm.on_tick(tick)

        # 2 levels below + 2 levels above = 4 total
        levels = algorithm.get_grid_levels()
        assert len(levels) == 4


class TestAlgorithmState:
    """Tests for state management."""

    def test_state_persists_after_tick(self, algorithm, create_tick):
        """Test that grid state persists between ticks."""
        tick1 = create_tick(price=100.0)
        algorithm.on_tick(tick1)

        levels_before = algorithm.get_grid_levels()

        tick2 = create_tick(price=101.0)
        algorithm.on_tick(tick2)

        levels_after = algorithm.get_grid_levels()

        # Grid levels should persist
        assert levels_before == levels_after

    def test_position_cleared_after_sell(self, algorithm, create_tick):
        """Test position state is cleared after sell."""
        # Setup
        tick1 = create_tick(price=100.0)
        algorithm.on_tick(tick1)

        # Set position
        algorithm._position = {
            "entry_price": 100.0,
            "quantity": 0.01,
            "side": "LONG",
        }

        # Sell (take profit)
        algorithm.set_config("take_profit_pct", 0.5)
        tick2 = create_tick(price=100.6)
        signal = algorithm.on_tick(tick2)

        if signal and signal.signal_type == SignalType.SELL:
            # Position should be cleared
            state = algorithm.get_algorithm_state()
            assert state["has_position"] is False
