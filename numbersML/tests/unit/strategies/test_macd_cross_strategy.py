"""
Unit tests for MACDCrossStrategy.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.strategies.base import EnrichedTick, SignalType
from src.strategies.user.macd_cross_strategy import MACDCrossStrategy


class TestMACDCrossStrategy:
    """Test cases for MACDCrossStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create a strategy instance for testing."""
        return MACDCrossStrategy(
            strategy_id="test_macd_cross",
            symbols=["BTC/USDT"],
        )

    @pytest.fixture
    def sample_tick(self):
        """Create a sample enriched tick."""
        return EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

    def test_initialization(self, strategy):
        """Test strategy initializes correctly."""
        assert strategy.id == "test_macd_cross"
        assert strategy.symbols == ["BTC/USDT"]
        assert strategy.last_macd == 0.0
        assert strategy.last_signal == 0.0
        assert strategy.in_position is False
        assert strategy.cross_count == 0
        assert strategy._tick_count == 0
        assert strategy._initialized is False

    def test_initialize_macd(self, strategy):
        """Test MACD initialization with config values."""
        strategy.set_config("macd_indicator_name", "custom_macd")
        strategy.set_config("fast_period", 10)
        strategy.set_config("slow_period", 20)
        strategy.set_config("signal_period", 8)

        strategy._initialize_macd()

        assert strategy.macd_indicator_name == "custom_macd"
        assert strategy.fast_period == 10
        assert strategy.slow_period == 20
        assert strategy.signal_period == 8

    def test_initialize_macd_defaults(self, strategy):
        """Test MACD initialization with default values."""
        strategy._initialize_macd()

        assert strategy.macd_indicator_name == "macdindicator"
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.signal_period == 9

    def test_get_macd_values_prefixed(self, strategy, sample_tick):
        """Test getting MACD values with prefixed indicator names."""
        strategy._initialize_macd()

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": 0.0015,
                "macdindicator_signal": 0.0010,
            },
        )

        macd_value, signal_value, histogram_value = strategy._get_macd_values(tick)

        assert macd_value == 0.0015
        assert signal_value == 0.0010
        assert histogram_value == 0.0005

    def test_get_macd_values_simple(self, strategy, sample_tick):
        """Test getting MACD values with simple indicator names."""
        strategy._initialize_macd()

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd": 0.0015,
                "macd_signal": 0.0010,
            },
        )

        macd_value, signal_value, histogram_value = strategy._get_macd_values(tick)

        assert macd_value == 0.0015
        assert signal_value == 0.0010
        assert histogram_value == 0.0005

    def test_get_macd_values_missing(self, strategy, sample_tick):
        """Test getting MACD values when indicators are missing."""
        strategy._initialize_macd()

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        macd_value, signal_value, histogram_value = strategy._get_macd_values(tick)

        assert macd_value is None
        assert signal_value is None
        assert histogram_value is None

    def test_detect_crossover_bullish(self, strategy, sample_tick):
        """Test bullish crossover detection."""
        strategy.last_macd = 0.0010
        strategy.last_signal = 0.0012
        strategy.in_position = False

        signal = strategy._detect_crossover(0.0015, 0.0010, sample_tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDT"
        assert strategy.in_position is True
        assert strategy.cross_count == 1
        assert signal.metadata["crossover_type"] == "bullish"
        assert signal.metadata["macd"] == 0.0015
        assert signal.metadata["signal"] == 0.0010

    def test_detect_crossover_bearish(self, strategy, sample_tick):
        """Test bearish crossover detection."""
        strategy.last_macd = 0.0015
        strategy.last_signal = 0.0010
        strategy.in_position = True

        signal = strategy._detect_crossover(0.0008, 0.0012, sample_tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.symbol == "BTC/USDT"
        assert strategy.in_position is False
        assert strategy.cross_count == 1
        assert signal.metadata["crossover_type"] == "bearish"
        assert signal.metadata["macd"] == 0.0008
        assert signal.metadata["signal"] == 0.0012

    def test_detect_crossover_no_signal_when_in_position(self, strategy, sample_tick):
        """Test no BUY signal when already in position."""
        strategy.last_macd = 0.0010
        strategy.last_signal = 0.0012
        strategy.in_position = True

        signal = strategy._detect_crossover(0.0015, 0.0010, sample_tick)

        assert signal is None
        assert strategy.cross_count == 0

    def test_detect_crossover_no_signal_when_not_in_position(self, strategy, sample_tick):
        """Test no SELL signal when not in position."""
        strategy.last_macd = 0.0015
        strategy.last_signal = 0.0010
        strategy.in_position = False

        signal = strategy._detect_crossover(0.0008, 0.0012, sample_tick)

        assert signal is None
        assert strategy.cross_count == 0

    def test_detect_crossover_no_cross(self, strategy, sample_tick):
        """Test no signal when no crossover occurs."""
        strategy.last_macd = 0.0010
        strategy.last_signal = 0.0012
        strategy.in_position = False

        signal = strategy._detect_crossover(0.0008, 0.0010, sample_tick)

        assert signal is None
        assert strategy.cross_count == 0

    def test_on_tick_initializes_on_first_tick(self, strategy, sample_tick):
        """Test that on_tick initializes strategy on first tick."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": 0.0015,
                "macdindicator_signal": 0.0010,
            },
        )

        assert strategy._initialized is False
        strategy.on_tick(tick)
        assert strategy._initialized is True
        assert strategy._tick_count == 1

    def test_on_tick_returns_none_when_indicators_missing(self, strategy, sample_tick):
        """Test that on_tick returns None when indicators are missing."""
        strategy._initialize_macd()
        strategy._initialized = True

        signal = strategy.on_tick(sample_tick)

        assert signal is None

    def test_on_tick_generates_buy_signal(self, strategy):
        """Test that on_tick generates BUY signal on bullish crossover."""
        strategy._initialize_macd()
        strategy._initialized = True
        strategy.last_macd = 0.0010
        strategy.last_signal = 0.0012
        strategy.in_position = False

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": 0.0015,
                "macdindicator_signal": 0.0010,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert strategy.in_position is True
        assert strategy.cross_count == 1

    def test_on_tick_generates_sell_signal(self, strategy):
        """Test that on_tick generates SELL signal on bearish crossover."""
        strategy._initialize_macd()
        strategy._initialized = True
        strategy.last_macd = 0.0015
        strategy.last_signal = 0.0010
        strategy.in_position = True

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": 0.0008,
                "macdindicator_signal": 0.0012,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert strategy.in_position is False
        assert strategy.cross_count == 1

    def test_on_tick_updates_state(self, strategy):
        """Test that on_tick updates MACD state variables."""
        strategy._initialize_macd()
        strategy._initialized = True

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": 0.0015,
                "macdindicator_signal": 0.0010,
            },
        )

        strategy.on_tick(tick)

        assert strategy.last_macd == 0.0015
        assert strategy.last_signal == 0.0010
        assert strategy.last_histogram == 0.0005

    def test_on_position_closed(self, strategy):
        """Test that on_position_closed resets position state."""
        strategy.in_position = True

        strategy.on_position_closed(
            symbol="BTC/USDT",
            price=Decimal("51000"),
            exit_reason="take_profit",
        )

        assert strategy.in_position is False

    def test_get_stats(self, strategy):
        """Test that get_stats returns correct information."""
        strategy._initialize_macd()
        strategy.last_macd = 0.0015
        strategy.last_signal = 0.0010
        strategy.last_histogram = 0.0005
        strategy.in_position = True
        strategy.cross_count = 3
        strategy._tick_count = 500

        stats = strategy.get_stats()

        assert stats["strategy_id"] == "test_macd_cross"
        assert stats["last_macd"] == 0.0015
        assert stats["last_signal"] == 0.0010
        assert stats["last_histogram"] == 0.0005
        assert stats["in_position"] is True
        assert stats["cross_count"] == 3
        assert stats["tick_count"] == 500
        assert stats["macd_indicator_name"] == "macdindicator"
        assert stats["fast_period"] == 12
        assert stats["slow_period"] == 26
        assert stats["signal_period"] == 9

    def test_signal_buy_confidence(self, strategy, sample_tick):
        """Test that BUY signal confidence is calculated correctly."""
        macd_value = 0.0050
        signal_value = 0.0010

        signal = strategy._signal_buy(sample_tick, macd_value, signal_value)

        expected_confidence = min(1.0, abs(macd_value - signal_value) / 10.0)
        assert signal.confidence == expected_confidence

    def test_signal_sell_confidence(self, strategy, sample_tick):
        """Test that SELL signal confidence is calculated correctly."""
        strategy.in_position = True
        macd_value = 0.0010
        signal_value = 0.0050

        signal = strategy._signal_sell(sample_tick, macd_value, signal_value)

        expected_confidence = min(1.0, abs(macd_value - signal_value) / 10.0)
        assert signal.confidence == expected_confidence
