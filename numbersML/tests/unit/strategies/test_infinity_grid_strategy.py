"""
Unit tests for InfinityGridStrategy.
"""
import pytest
from decimal import Decimal

from src.domain.strategies.base import EnrichedTick, SignalType
from src.strategies.user.infinity_grid_strategy import InfinityGridStrategy


class TestInfinityGridStrategy:
    """Test cases for InfinityGridStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create a strategy instance for testing."""
        return InfinityGridStrategy(
            strategy_id="test_infinity_grid",
            symbols=["BTC/USDT"],
        )

    @pytest.fixture
    def sample_tick(self):
        """Create a sample enriched tick."""
        return EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=Decimal("1640995200"),  # 2022-01-01 00:00:00 UTC
            indicators={},
        )

    def test_initialization(self, strategy):
        """Test strategy initializes correctly."""
        assert strategy.id == "test_infinity_grid"
        assert strategy.symbols == ["BTC/USDT"]
        assert strategy.reference_price is None
        assert len(strategy.grid_levels) == 0

    def test_initialize_grid(self, strategy, sample_tick):
        """Test grid initialization."""
        # Set config values
        strategy.set_config("grid_size", 8)
        strategy.set_config("grid_spacing_pct", 0.65)
        strategy.set_config("grid_profit_pct", 0.85)
        strategy.set_config("grid_quantity_absolute", 100.0)

        # Initialize grid with first price
        strategy._initialize_grid(50000.0)

        assert strategy.reference_price == 50000.0
        assert strategy.grid_size == 8
        assert strategy.grid_spacing_pct == 0.65
        assert strategy.grid_profit_pct == 0.85
        assert len(strategy.grid_levels) == 8

        # Check grid levels are below reference price
        for level in strategy.grid_levels:
            assert level < 50000.0

        # Check spacing is consistent
        expected_spacing = 50000.0 * (0.65 / 100.0)  # 325.0
        for i in range(len(strategy.grid_levels) - 1):
            diff = strategy.grid_levels[i] - strategy.grid_levels[i + 1]
            assert abs(diff - expected_spacing) < 0.01

    def test_signal_buy_generates_correct_signal(self, strategy, sample_tick):
        """Test that _signal_buy generates correct signal with expected profit price."""
        # Initialize grid
        strategy._initialize_grid(50000.0)
        strategy.grid_spacing_pct = 0.65
        strategy.grid_profit_pct = 0.85

        # Generate a buy signal at level 0
        level = strategy.grid_levels[0]  # Should be 50000 - 1*spacing
        expected_profit_price = level * (1 + 0.85 / 100.0)

        signal = strategy._signal_buy(sample_tick, level, 0, "BTC/USDT")

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDT"
        assert signal.price == sample_tick.price
        assert signal.confidence == 0.8
        assert signal.metadata["grid_level"] == level
        assert signal.metadata["grid_index"] == 0
        assert abs(signal.metadata["expected_profit_price"] - expected_profit_price) < 0.01
        assert signal.metadata["reference_price"] == 50000.0

    def test_detect_crossing_buy_signal(self, strategy):
        """Test that buy signals are generated when price crosses below a level."""
        # Initialize grid
        strategy._initialize_grid(50000.0)
        strategy.grid_spacing_pct = 0.65  # 325 spacing
        strategy.grid_profit_pct = 0.85

        # Set up price crossing scenario: last price above level, current price at/below level
        last_price = strategy.grid_levels[0] + 10  # Above the level
        current_price = strategy.grid_levels[0] - 10  # Below the level

        # Create ticks
        tick_before = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal(str(last_price)),
            volume=Decimal("1.5"),
            time=Decimal("1640995200"),
            indicators={},
        )
        tick_at = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal(str(current_price)),
            volume=Decimal("1.5"),
            time=Decimal("1640995201"),
            indicators={},
        )

        # Process the tick before (should not generate signal)
        strategy.last_price = float(last_price)
        signal_before = strategy.on_tick(tick_before)
        assert signal_before is None

        # Process the tick at/below level (should generate signal)
        strategy.last_price = float(last_price)  # This is what _detect_crossing uses as 'last'
        signal_at = strategy.on_tick(tick_at)
        
        assert signal_at is not None
        assert signal_at.signal_type == SignalType.BUY
        assert signal_at.metadata["grid_index"] == 0

    def test_on_position_closed_cleans_up_state(self, strategy):
        """Test that on_position_closed properly cleans up state."""
        # Initialize grid
        strategy._initialize_grid(50000.0)

        # Simulate opening a position by using the internal state as set by _signal_buy
        strategy._symbol_used_buy_levels["BTC/USDT"].add(0)
        strategy._symbol_open_positions["BTC/USDT"] = 0

        # Close the position
        strategy.on_position_closed(
            symbol="BTC/USDT",
            price=Decimal("51000"),
            exit_reason="take_profit",
            grid_index=0
        )

        # Check that state is cleaned up
        assert 0 not in strategy._symbol_used_buy_levels["BTC/USDT"]
        assert strategy._symbol_open_positions["BTC/USDT"] is None

    def test_on_position_closed_without_grid_index(self, strategy):
        """Test on_position_closed works when grid_index is not provided."""
        # Initialize grid
        strategy._initialize_grid(50000.0)

        # Simulate opening a position
        strategy._symbol_used_buy_levels["BTC/USDT"].add(1)
        strategy._symbol_open_positions["BTC/USDT"] = 1

        # Close the position without providing grid_index
        strategy.on_position_closed(
            symbol="BTC/USDT",
            price=Decimal("51000"),
            exit_reason="take_profit",
            grid_index=None  # Should be looked up from _symbol_open_positions
        )

        # Check that state is cleaned up
        assert 1 not in strategy._symbol_used_buy_levels["BTC/USDT"]
        assert strategy._symbol_open_positions["BTC/USDT"] is None

    def test_multiple_symbols_tracking(self, strategy):
        """Test that multiple symbols are tracked independently."""
        # Add another symbol
        strategy._symbols = ["BTC/USDT", "ETH/USDT"]
        strategy._symbol_used_buy_levels = {
            "BTC/USDT": set(),
            "ETH/USDT": set()
        }
        strategy._symbol_open_positions = {
            "BTC/USDT": None,
            "ETH/USDT": None
        }

        # Initialize grid
        strategy._initialize_grid(50000.0)

        # Open positions for both symbols at different levels
        strategy._symbol_used_buy_levels["BTC/USDT"].add(0)
        strategy._symbol_open_positions["BTC/USDT"] = 0
        
        strategy._symbol_used_buy_levels["ETH/USDT"].add(2)
        strategy._symbol_open_positions["ETH/USDT"] = 2

        # Close BTC position
        strategy.on_position_closed(
            symbol="BTC/USDT",
            price=Decimal("51000"),
            exit_reason="take_profit",
            grid_index=0
        )

        # Check that only BTC state is cleaned up
        assert 0 not in strategy._symbol_used_buy_levels["BTC/USDT"]
        assert strategy._symbol_open_positions["BTC/USDT"] is None
        
        # ETH position should remain open
        assert 2 in strategy._symbol_used_buy_levels["ETH/USDT"]
        assert strategy._symbol_open_positions["ETH/USDT"] == 2

    def test_get_stats(self, strategy):
        """Test that get_stats returns correct information."""
        # Initialize grid
        strategy._initialize_grid(50000.0)
        strategy.set_config("grid_size", 8)

        # Simulate some activity
        strategy._symbol_used_buy_levels["BTC/USDT"].add(0)
        strategy._symbol_open_positions["BTC/USDT"] = 0
        strategy._tick_count = 100

        stats = strategy.get_stats()

        assert stats["strategy_id"] == "test_infinity_grid"
        assert stats["reference_price"] == 50000.0
        assert len(stats["grid_levels"]) == 8
        assert stats["open_positions_count"] == 1
        assert stats["used_buy_levels"]["BTC/USDT"] == [0]
        assert stats["tick_count"] == 100