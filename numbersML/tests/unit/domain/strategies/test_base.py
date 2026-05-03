"""
Tests for Algorithm Interface.

Tests strategy base classes, signals, positions, and strategy manager.
"""

from decimal import Decimal

from src.domain.strategies.base import (
    Position,
    Signal,
    SignalType,
    TimeFrame,
)
from src.domain.strategies.strategy_instance import StrategyInstanceState


class TestSignalType:
    """Test SignalType enum."""

    def test_signal_type_values(self) -> None:
        """Test signal type enum values."""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"
        assert SignalType.CLOSE_LONG.value == "CLOSE_LONG"
        assert SignalType.CLOSE_SHORT.value == "CLOSE_SHORT"


class TestTimeFrame:
    """Test TimeFrame enum."""

    def test_timeframe_values(self) -> None:
        """Test time frame enum values."""
        assert TimeFrame.TICK.value == "TICK"
        assert TimeFrame.MINUTE.value == "1M"
        assert TimeFrame.HOUR.value == "1H"
        assert TimeFrame.DAY.value == "1D"


class TestStrategyInstanceState:
    """Test StrategyInstanceState enum."""

    def test_strategy_state_values(self) -> None:
        """Test strategy state enum values."""
        assert StrategyInstanceState.STOPPED.value == "stopped"
        assert StrategyInstanceState.RUNNING.value == "running"
        assert StrategyInstanceState.PAUSED.value == "paused"
        assert StrategyInstanceState.ERROR.value == "error"


class TestSignal:
    """Test Signal dataclass."""

    def test_signal_creation(self) -> None:
        """Test creating a signal."""
        signal = Signal(
            strategy_id="test_strategy",
            symbol="BTC/USDT",
            signal_type=SignalType.BUY,
            price=Decimal("50000.00"),
            confidence=0.85,
        )

        assert signal.strategy_id == "test_strategy"
        assert signal.symbol == "BTC/USDT"
        assert signal.signal_type == SignalType.BUY
        assert signal.price == Decimal("50000.00")
        assert signal.confidence == 0.85
        assert signal.timestamp is not None

    def test_signal_to_dict(self) -> None:
        """Test converting signal to dictionary."""
        signal = Signal(
            strategy_id="test_strategy",
            symbol="BTC/USDT",
            signal_type=SignalType.BUY,
            price=Decimal("50000.00"),
            confidence=0.75,
            metadata={"rsi": 25.0},
        )

        data = signal.to_dict()

        assert data["strategy_id"] == "test_strategy"
        assert data["symbol"] == "BTC/USDT"
        assert data["signal_type"] == "BUY"
        assert data["price"] == 50000.0
        assert data["confidence"] == 0.75
        assert data["metadata"]["rsi"] == 25.0
        assert "timestamp" in data


class TestPosition:
    """Test Position dataclass."""

    def test_position_creation(self) -> None:
        """Test creating a position."""
        position = Position(
            symbol="BTC/USDT",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
        )

        assert position.symbol == "BTC/USDT"
        assert position.side == "LONG"
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000.00")
        assert position.unrealized_pnl == Decimal("0")

    def test_position_update_price_long(self) -> None:
        """Test updating position price for LONG."""
        position = Position(
            symbol="BTC/USDT",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
        )

        position.update_price(Decimal("51000.00"))

        assert position.current_price == Decimal("51000.00")
        assert position.unrealized_pnl == Decimal("100.00")  # (51000 - 50000) * 0.1
        assert position.pnl_percent == 0.2  # 0.2%

    def test_position_update_price_short(self) -> None:
        """Test updating position price for SHORT."""
        position = Position(
            symbol="BTC/USDT",
            side="SHORT",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
        )

        position.update_price(Decimal("49000.00"))

        assert position.current_price == Decimal("49000.00")
        assert position.unrealized_pnl == Decimal("100.00")  # (50000 - 49000) * 0.1
        assert position.pnl_percent == 0.2

    def test_position_to_dict(self) -> None:
        """Test converting position to dictionary."""
        position = Position(
            symbol="BTC/USDT",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.00"),
        )
        position.update_price(Decimal("51000.00"))

        data = position.to_dict()

        assert data["symbol"] == "BTC/USDT"
        assert data["side"] == "LONG"
        assert data["quantity"] == 0.1
        assert data["entry_price"] == 50000.0
        assert data["current_price"] == 51000.0
        assert data["unrealized_pnl"] == 100.0
        assert abs(data["pnl_percent"] - 0.2) < 0.01


class TestEnrichedTick:
    """Test EnrichedTick dataclass."""
