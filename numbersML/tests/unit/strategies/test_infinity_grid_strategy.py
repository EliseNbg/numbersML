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
        assert strategy._symbol_locked_level == {}

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

        # Check grid levels (with even grid_size=8, reference is between levels)
        # half_size = 4
        # Levels 0-3: below reference (indices 0,1,2,3)
        # Levels 4-7: above reference (indices 4,5,6,7)
        expected_spacing = 50000.0 * (0.65 / 100.0)  # 325.0
        expected_levels = [
            50000.0 - 4 * expected_spacing,  # 48700.0
            50000.0 - 3 * expected_spacing,  # 49025.0
            50000.0 - 2 * expected_spacing,  # 49350.0
            50000.0 - 1 * expected_spacing,  # 49675.0
            50000.0 + 1 * expected_spacing,  # 50325.0
            50000.0 + 2 * expected_spacing,  # 50650.0
            50000.0 + 3 * expected_spacing,  # 50975.0
            50000.0 + 4 * expected_spacing,  # 51300.0
        ]
        
        for i, expected in enumerate(expected_levels):
            assert abs(strategy.grid_levels[i] - expected) < 0.01

        # Check that only levels below reference are used for BUY signals
        for i in range(4):  # First 4 levels (indices 0-3) are below reference
            assert strategy.grid_levels[i] < 50000.0
        for i in range(4, 8):  # Last 4 levels (indices 4-7) are above reference
            assert strategy.grid_levels[i] > 50000.0

        # Check spacing is consistent
        for i in range(len(strategy.grid_levels) - 1):
            diff = strategy.grid_levels[i + 1] - strategy.grid_levels[i]
            # The middle gap (between last below-ref and first above-ref level) is 2*spacing
            if i == 3:  # Between index 3 and 4 (last below-ref and first above-ref)
                assert abs(diff - 2 * expected_spacing) < 0.01
            else:
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
        
        # Disable reference price reset for this test by using levels close to reference
        # that won't trigger the 2% threshold when we move around them
        strategy.set_config("grid_size", 8)

        # With grid_size=8 (even), half_size=4
        # Levels 0-3: below reference (indices 0,1,2,3)
        # Levels 4-7: above reference (indices 4,5,6,7)
        # Test with a level below reference (index 1) and a level above reference (index 4)
        # These levels are within 2% of reference price to avoid triggering reset
        
        # Test level below reference (index 1)
        level_1 = strategy.grid_levels[1]  # Should be 50000 - 3*spacing = 49025
        last_price = level_1 + 1  # Above the level (small move to avoid 2% reset)
        current_price = level_1 - 1  # Below the level

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
        signal_before = strategy.on_tick(tick_before)
        assert signal_before is None

        # Process the tick at/below level (should generate signal)
        signal_at = strategy.on_tick(tick_at)
        
        assert signal_at is not None
        assert signal_at.signal_type == SignalType.BUY
        assert signal_at.metadata["grid_index"] == 1
        
        # Test level above reference (index 4) - should also generate BUY signal when crossed from above
        level_4 = strategy.grid_levels[4]  # Should be 50000 + 1*spacing = 50325
        last_price = level_4 + 1  # Above the level (small move)
        current_price = level_4 - 1  # Below the level
        
        # Process ticks for level 4
        tick_before_4 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal(str(last_price)),
            volume=Decimal("1.5"),
            time=Decimal("1640995202"),
            indicators={},
        )
        tick_at_4 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal(str(current_price)),
            volume=Decimal("1.5"),
            time=Decimal("1640995203"),
            indicators={},
        )
        
        # Process the tick before (should not generate signal)
        # last_price was already set by Strategy.on_tick to last processed price
        signal_before_4 = strategy.on_tick(tick_before_4)
        assert signal_before_4 is None

        # Process the tick at/below level (should generate signal)
        signal_at_4 = strategy.on_tick(tick_at_4)
        
        assert signal_at_4 is not None
        assert signal_at_4.signal_type == SignalType.BUY
        assert signal_at_4.metadata["grid_index"] == 4

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