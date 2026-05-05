"""
Unit tests for AlgorithmInstance domain entity.

Follows TDD approach: tests first, then implementation.
"""

from uuid import UUID, uuid4

import pytest

from src.domain.algorithms.base import Algorithm, EnrichedTick, Signal, SignalType
from src.domain.algorithms.algorithm_instance import (
    RuntimeStats,
    AlgorithmInstance,
    AlgorithmInstanceState,
)


class SimpleTestAlgorithm(Algorithm):
    """Simple test algorithm for testing."""

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Generate HOLD signal for testing."""
        return Signal(
            algorithm_id=self.id,
            symbol=tick.symbol,
            signal_type=SignalType.HOLD,
            price=tick.price,
        )


class TestRuntimeStats:
    """Tests for RuntimeStats value object."""

    def test_create_default(self) -> None:
        """Test creating default RuntimeStats."""
        stats = RuntimeStats()

        assert stats.pnl == 0.0
        assert stats.total_trades == 0
        assert stats.winning_trades == 0
        assert stats.losing_trades == 0
        assert stats.win_rate == 0.0

    def test_create_with_values(self) -> None:
        """Test creating RuntimeStats with values."""
        stats = RuntimeStats(
            pnl=100.50,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
        )

        assert stats.pnl == 100.50
        assert stats.total_trades == 10
        assert stats.winning_trades == 6
        assert stats.losing_trades == 4
        assert stats.win_rate == 60.0  # 6/10 * 100

    def test_win_rate_zero_trades(self) -> None:
        """Test win rate with zero trades."""
        stats = RuntimeStats(total_trades=0)
        assert stats.win_rate == 0.0

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        stats = RuntimeStats(pnl=50.0, total_trades=5)
        result = stats.to_dict()

        assert result["pnl"] == 50.0
        assert result["total_trades"] == 5
        assert "win_rate" in result


class TestAlgorithmInstanceCreation:
    """Tests for AlgorithmInstance creation."""

    def test_create_valid(self) -> None:
        """Test creating a valid AlgorithmInstance."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        config_set_id = uuid4()

        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=config_set_id,
        )

        assert isinstance(instance.id, UUID)
        assert instance.algorithm_id == algorithm.id
        assert instance.config_set_id == config_set_id
        assert instance.status == AlgorithmInstanceState.STOPPED
        assert instance.can_start() is True

    def test_create_with_custom_id(self) -> None:
        """Test creating with custom UUID."""
        custom_id = uuid4()
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
            id=custom_id,
        )

        assert instance.id == custom_id

    def test_create_with_status(self) -> None:
        """Test creating with specific status."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
            status=AlgorithmInstanceState.PAUSED,
        )

        assert instance.status == AlgorithmInstanceState.PAUSED
        assert instance.can_start() is False  # Can't start from PAUSED

    def test_create_missing_algorithm(self) -> None:
        """Test that missing algorithm raises ValueError."""
        with pytest.raises(ValueError, match="algorithm_id cannot be None"):
            AlgorithmInstance(
                algorithm_id=None,  # type: ignore
                config_set_id=uuid4(),
            )

    def test_create_missing_config_set_id(self) -> None:
        """Test that missing config_set_id raises ValueError."""
        with pytest.raises(ValueError, match="config_set_id cannot be None"):
            AlgorithmInstance(
                algorithm_id=uuid4(),
                config_set_id=None,  # type: ignore
            )


class TestAlgorithmInstanceLifecycle:
    """Tests for state transitions."""

    def test_start_from_stopped(self) -> None:
        """Test starting from STOPPED state."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )

        assert instance.status == AlgorithmInstanceState.STOPPED
        assert instance.can_start() is True

        instance.start()

        assert instance.status == AlgorithmInstanceState.RUNNING
        assert instance.started_at is not None

    def test_stop_from_running(self) -> None:
        """Test stopping from RUNNING state."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.start()

        instance.stop()

        assert instance.status == AlgorithmInstanceState.STOPPED
        assert instance.stopped_at is not None

    def test_pause_from_running(self) -> None:
        """Test pausing from RUNNING state."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.start()

        instance.pause()

        assert instance.status == AlgorithmInstanceState.PAUSED

    def test_resume_from_paused(self) -> None:
        """Test resuming from PAUSED state."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.start()
        instance.pause()

        instance.resume()

        assert instance.status == AlgorithmInstanceState.RUNNING

    def test_start_from_running_raises_error(self) -> None:
        """Test that starting from RUNNING raises ValueError."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.start()

        with pytest.raises(ValueError, match="Cannot start from state"):
            instance.start()

    def test_stop_from_stopped_raises_error(self) -> None:
        """Test that stopping from STOPPED raises ValueError."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )

        with pytest.raises(ValueError, match="Cannot stop from state"):
            instance.stop()

    def test_resume_from_running_raises_error(self) -> None:
        """Test that resuming from RUNNING raises ValueError."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.start()

        with pytest.raises(ValueError, match="Cannot resume from state"):
            instance.resume()


class TestAlgorithmInstanceStats:
    """Tests for runtime statistics."""

    def test_update_stats(self) -> None:
        """Test updating runtime statistics."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )

        instance.update_stats(pnl=100.0, total_trades=5, winning_trades=3)

        assert instance.runtime_stats.pnl == 100.0
        assert instance.runtime_stats.total_trades == 5
        assert instance.runtime_stats.winning_trades == 3

    def test_record_error(self) -> None:
        """Test recording an error."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.start()

        instance.record_error("Connection failed")

        assert instance.status == AlgorithmInstanceState.ERROR
        assert instance.runtime_stats.last_error == "Connection failed"

    def test_stats_preserved_on_error(self) -> None:
        """Test that stats are preserved when error recorded."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.update_stats(pnl=50.0, total_trades=2)
        instance.start()

        instance.record_error("Test error")

        assert instance.runtime_stats.pnl == 50.0
        assert instance.runtime_stats.total_trades == 2


class TestAlgorithmInstanceSerialization:
    """Tests for to_dict serialization."""

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )

        result = instance.to_dict()

        assert "id" in result
        assert "algorithm_id" in result
        assert "config_set_id" in result
        assert "status" in result
        assert "runtime_stats" in result
        assert result["status"] == "stopped"

    def test_to_dict_running(self) -> None:
        """Test to_dict when instance is running."""
        algorithm = SimpleTestAlgorithm(uuid4(), ["BTC/USDT"])
        instance = AlgorithmInstance(
            algorithm_id=algorithm.id,
            config_set_id=uuid4(),
        )
        instance.start()

        result = instance.to_dict()

        assert result["status"] == "running"
        assert result["started_at"] is not None
