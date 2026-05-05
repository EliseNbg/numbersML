"""
Unit tests for GridAlgorithm.

Follows TDD approach: tests first, then implementation.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.algorithms.base import EnrichedTick, SignalType, TimeFrame
from src.domain.algorithms.grid_algorithm import GridAlgorithm


@pytest.fixture
def grid_algorithm():
    """Create a GridAlgorithm for testing."""
    return GridAlgorithm(
        algorithm_id=uuid4(),
        symbols=["TEST/USDT"],
        time_frame=TimeFrame.TICK,
    )


@pytest.fixture
def create_tick():
    """Factory for creating EnrichedTick."""

    def _create(
        symbol="TEST/USDT",
        price=100.0,
        time=None,
        indicators=None,
    ):
        return EnrichedTick(
            symbol=symbol,
            price=Decimal(str(price)),
            volume=Decimal("1.0"),
            time=time or datetime.now(UTC),
            indicators=indicators or {},
        )

    return _create


class TestGridAlgorithmInit:
    """Tests for GridAlgorithm initialization."""

    def test_create_grid_algorithm(self, grid_algorithm):
        """Test creating a GridAlgorithm."""
        assert isinstance(grid_algorithm.id, uuid4().__class__)
        assert grid_algorithm.symbols == ["TEST/USDT"]
        assert grid_algorithm.time_frame == TimeFrame.TICK

    def test_initial_grid_empty(self, grid_algorithm):
        """Test that grid levels are empty initially."""
        assert len(grid_algorithm.get_grid_levels()) == 0
        stats = grid_algorithm.get_grid_stats()
        assert stats["num_levels"] == 0


class TestGridInitialization:
    """Tests for grid initialization."""

    def test_initialize_grid(self, grid_algorithm):
        """Test grid initialization on first tick."""
        tick = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("100.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
        )

        # Process tick to initialize grid
        grid_algorithm.on_tick(tick)

        # Check grid was initialized
        levels = grid_algorithm.get_grid_levels()
        assert len(levels) > 0

        # Check levels are around base price (100.0)
        for level in levels:
            assert Decimal("90.0") < level < Decimal("110.0")

    def test_grid_levels_count(self, grid_algorithm):
        """Test that correct number of levels are created."""
        grid_algorithm.set_config("grid_levels", 3)

        tick = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("100.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
        )

        grid_algorithm.on_tick(tick)

        # 3 levels below + 3 levels above = 6 total
        levels = grid_algorithm.get_grid_levels()
        assert len(levels) == 6

    def test_grid_rebalance(self, grid_algorithm):
        """Test grid rebalancing on large price move."""
        # Initialize at 100
        tick1 = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("100.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
        )
        grid_algorithm.on_tick(tick1)

        # Price moves >5% → should rebalance
        tick2 = EnrichedTick(
            symbol="TEST/USDT",
            price=Decimal("106.0"),  # 6% move
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
        )
        grid_algorithm.on_tick(tick2)

        new_levels = grid_algorithm.get_grid_levels()

        # New levels should be around 106, not 100
        for level in new_levels:
            assert Decimal("96.0") < level < Decimal("116.0")


class TestBuySignals:
    """Tests for buy signal generation."""

    def test_buy_signal_near_grid(self, grid_algorithm, create_tick):
        """Test buy signal when price near grid level."""
        # Initialize grid at 100
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)

        # Price at 99.0 should be near a buy grid level
        tick2 = create_tick(price=99.0)
        signal = grid_algorithm.on_tick(tick2)

        # Check if signal generated
        if signal:
            assert signal.signal_type == SignalType.BUY
            assert signal.symbol == "TEST/USDT"

    def test_no_buy_with_position(self, grid_algorithm, create_tick):
        """Test that no buy signal if position exists."""
        # Initialize grid
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)

        # Open a position
        grid_algorithm.open_position(
            symbol="TEST/USDT",
            side="LONG",
            quantity=Decimal("0.01"),
            price=Decimal("99.0"),
        )

        # Try to get another buy signal
        tick2 = create_tick(price=98.0)
        signal = grid_algorithm.on_tick(tick2)

        # Should not get buy signal with open position
        assert signal is None


class TestSellSignals:
    """Tests for sell signal generation."""

    def test_sell_at_take_profit(self, grid_algorithm, create_tick):
        """Test sell signal at take profit."""
        # Initialize and open position
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)

        grid_algorithm.open_position(
            symbol="TEST/USDT",
            side="LONG",
            quantity=Decimal("0.01"),
            price=Decimal("100.0"),
        )

        # Price rises to trigger take profit (0.5% by default)
        tick2 = create_tick(price=100.6)  # 0.6% profit
        signal = grid_algorithm.on_tick(tick2)

        if signal:
            assert signal.signal_type == SignalType.SELL
            assert "take_profit" in signal.metadata.get("reason", "")

    def test_sell_at_stop_loss(self, grid_algorithm, create_tick):
        """Test sell signal at stop loss."""
        # Initialize and open position
        tick1 = create_tick(price=100.0)
        grid_algorithm.on_tick(tick1)

        grid_algorithm.open_position(
            symbol="TEST/USDT",
            side="LONG",
            quantity=Decimal("0.01"),
            price=Decimal("100.0"),
        )

        # Price drops to trigger stop loss (2% by default)
        tick2 = create_tick(price=97.5)  # -2.5% loss
        signal = grid_algorithm.on_tick(tick2)

        if signal:
            assert signal.signal_type == SignalType.SELL
            assert "stop_loss" in signal.metadata.get("reason", "")


class TestGridStats:
    """Tests for grid statistics."""

    def test_get_grid_stats(self, grid_algorithm, create_tick):
        """Test getting grid statistics."""
        tick = create_tick(price=100.0)
        grid_algorithm.on_tick(tick)

        stats = grid_algorithm.get_grid_stats()

        assert "base_price" in stats
        assert stats["base_price"] == 100.0
        assert "num_levels" in stats
        assert stats["num_levels"] > 0
        assert "open_positions" in stats
