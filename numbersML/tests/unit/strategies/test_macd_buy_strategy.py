"""
Unit tests for MACDBuyStrategy.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.strategies.base import EnrichedTick, SignalType
from src.strategies.user.macd_buy_strategy import MACDBuyStrategy


class TestMACDBuyStrategy:
    """Test cases for MACDBuyStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create a strategy instance for testing."""
        return MACDBuyStrategy(
            strategy_id="test_macd_buy",
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
        assert strategy.id == "test_macd_buy"
        assert strategy.symbols == ["BTC/USDT"]
        assert strategy.last_macd == 0.0
        assert strategy.last_signal == 0.0
        assert strategy.cross_count == 0
        assert strategy._tick_count == 0
        assert strategy._initialized is False
        assert strategy.bottom_border_macd_to_buy == 0.0
        assert strategy.grid_quantity_absolute == 100.0
        assert strategy.grid_profit_pct == 0.85

    def test_initialize_macd(self, strategy, sample_tick):
        """Test MACD initialization with config values."""
        strategy.set_config("macd_indicator_name", "custom_macd")
        strategy.set_config("fast_period", 10)
        strategy.set_config("slow_period", 20)
        strategy.set_config("signal_period", 8)
        strategy.set_config("bottom_border_macd_to_buy", -0.5)
        strategy.set_config("grid_quantity_absolute", 200.0)
        strategy.set_config("grid_profit_pct", 1.5)

        strategy._initialize_macd(sample_tick)

        assert strategy.macd_indicator_name == "custom_macd"
        assert strategy.fast_period == 10
        assert strategy.slow_period == 20
        assert strategy.signal_period == 8
        assert strategy.bottom_border_macd_to_buy == -0.5
        assert strategy.grid_quantity_absolute == 200.0
        assert strategy.grid_profit_pct == 1.5

    def test_initialize_macd_defaults(self, strategy, sample_tick):
        """Test MACD initialization with default values."""
        strategy._initialize_macd(sample_tick)

        assert strategy.macd_indicator_name == "macdindicator"
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.signal_period == 9
        assert strategy.bottom_border_macd_to_buy == 0.0
        assert strategy.grid_quantity_absolute == 100.0
        assert strategy.grid_profit_pct == 0.85

    def test_get_macd_values_prefixed(self, strategy, sample_tick):
        """Test getting MACD values with prefixed indicator names."""
        strategy._initialize_macd(sample_tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0015,
                "macdindicator_signal": -0.0020,
            },
        )

        macd_value, signal_value, histogram_value = strategy._get_macd_values(tick)

        assert macd_value == -0.0015
        assert signal_value == -0.0020
        assert histogram_value == 0.0005

    def test_get_macd_values_simple(self, strategy, sample_tick):
        """Test getting MACD values with simple indicator names."""
        strategy._initialize_macd(sample_tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd": -0.0015,
                "macd_signal": -0.0020,
            },
        )

        macd_value, signal_value, histogram_value = strategy._get_macd_values(tick)

        assert macd_value == -0.0015
        assert signal_value == -0.0020
        assert histogram_value == 0.0005

    def test_get_macd_values_missing(self, strategy, sample_tick):
        """Test getting MACD values when indicators are missing."""
        strategy._initialize_macd(sample_tick)

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

    def test_detect_crossover_bullish_below_border(self, strategy, sample_tick):
        """Test bullish crossover detection when MACD is below bottom border."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9

        signal = strategy._detect_crossover(-0.0010, -0.0015, sample_tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDT"
        assert strategy.cross_count == 1
        assert signal.metadata["crossover_type"] == "bullish"
        assert signal.metadata["macd"] == -0.0010
        assert signal.metadata["signal"] == -0.0015
        assert signal.metadata["quantity_usdc"] == 100.0

    def test_detect_crossover_blocked_above_border(self, strategy, sample_tick):
        """Test no signal when MACD is above bottom border."""
        strategy.last_macd = 0.0010
        strategy.last_signal = 0.0005
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9

        signal = strategy._detect_crossover(0.0015, 0.0010, sample_tick)

        assert signal is None
        assert strategy.cross_count == 0

    def test_detect_crossover_no_cross(self, strategy, sample_tick):
        """Test no signal when no crossover occurs."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9

        signal = strategy._detect_crossover(-0.0025, -0.0020, sample_tick)

        assert signal is None
        assert strategy.cross_count == 0

    def test_detect_crossover_noise_filter(self, strategy, sample_tick):
        """Test that small histogram relative to price is filtered as noise."""
        strategy.last_macd = -0.0000001
        strategy.last_signal = -0.0000002
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 0.001

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy._detect_crossover(-0.00000015, -0.0000001, tick)

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
                "macdindicator_macd": -0.0015,
                "macdindicator_signal": -0.0020,
            },
        )

        assert strategy._initialized is False
        strategy.on_tick(tick)
        assert strategy._initialized is True
        assert strategy._tick_count == 1

    def test_on_tick_returns_none_when_indicators_missing(self, strategy, sample_tick):
        """Test that on_tick returns None when indicators are missing."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True

        signal = strategy.on_tick(sample_tick)

        assert signal is None

    def test_on_tick_generates_buy_signal(self, strategy, sample_tick):
        """Test that on_tick generates BUY signal on bullish crossover below border."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert strategy.cross_count == 1

    def test_on_tick_updates_state(self, strategy, sample_tick):
        """Test that on_tick updates MACD state variables."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0015,
                "macdindicator_signal": -0.0020,
            },
        )

        strategy.on_tick(tick)

        assert strategy.last_macd == -0.0015
        assert strategy.last_signal == -0.0020
        assert strategy.last_histogram == 0.0005

    def test_signal_buy_expected_profit_price(self, strategy, sample_tick):
        """Test that BUY signal includes expected profit price."""
        macd_value = -0.0010
        signal_value = -0.0015

        signal = strategy._signal_buy(sample_tick, macd_value, signal_value)

        expected_profit_price = 50000 * (1 + 0.85 / 100.0)
        assert signal.metadata["expected_profit_price"] == expected_profit_price

    def test_signal_buy_quantity_usdc(self, strategy, sample_tick):
        """Test that BUY signal includes quantity in USDC."""
        strategy.grid_quantity_absolute = 250.0
        macd_value = -0.0010
        signal_value = -0.0015

        signal = strategy._signal_buy(sample_tick, macd_value, signal_value)

        assert signal.metadata["quantity_usdc"] == 250.0

    def test_signal_buy_confidence(self, strategy, sample_tick):
        """Test that BUY signal confidence is calculated correctly."""
        macd_value = -0.0050
        signal_value = -0.0010

        signal = strategy._signal_buy(sample_tick, macd_value, signal_value)

        expected_confidence = min(1.0, abs(macd_value - signal_value) / 10.0)
        assert signal.confidence == expected_confidence

    def test_on_position_closed(self, strategy):
        """Test that on_position_closed logs correctly."""
        strategy.on_position_closed(
            symbol="BTC/USDT",
            price=Decimal("51000"),
            exit_reason="take_profit",
        )

    def test_get_stats(self, strategy, sample_tick):
        """Test that get_stats returns correct information."""
        strategy._initialize_macd(sample_tick)
        strategy.last_macd = -0.0015
        strategy.last_signal = -0.0020
        strategy.last_histogram = 0.0005
        strategy.cross_count = 3
        strategy._tick_count = 500

        stats = strategy.get_stats()

        assert stats["strategy_id"] == "test_macd_buy"
        assert stats["last_macd"] == -0.0015
        assert stats["last_signal"] == -0.0020
        assert stats["last_histogram"] == 0.0005
        assert stats["cross_count"] == 3
        assert stats["tick_count"] == 500
        assert stats["macd_indicator_name"] == "macdindicator"
        assert stats["fast_period"] == 12
        assert stats["slow_period"] == 26
        assert stats["signal_period"] == 9
        assert stats["bottom_border_macd_to_buy"] == 0.0
        assert stats["grid_quantity_absolute"] == 100.0
        assert stats["grid_profit_pct"] == 0.85

    def test_no_sell_signal_generated(self, strategy, sample_tick):
        """Test that strategy never generates SELL signals."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.last_macd = 0.0015
        strategy.last_signal = 0.0010
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9

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

        assert signal is None

    def test_bottom_border_custom_value(self, strategy, sample_tick):
        """Test bottom border with custom negative value."""
        strategy.last_macd = -1.6
        strategy.last_signal = -1.5
        strategy.bottom_border_macd_to_buy = -1.0
        strategy.min_relative_threshold = 1e-9

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy._detect_crossover(-1.2, -1.3, tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_bottom_border_blocks_when_macd_too_high(self, strategy, sample_tick):
        """Test that bottom border blocks signals when MACD is too high."""
        strategy.last_macd = -0.5
        strategy.last_signal = -0.6
        strategy.bottom_border_macd_to_buy = -1.0
        strategy.min_relative_threshold = 1e-9

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy._detect_crossover(-0.4, -0.5, tick)

        assert signal is None

    def test_sma_filter_not_configured_allows_signal(self, strategy, sample_tick):
        """Test that signal is allowed when no SMA filter is configured."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = None
        strategy.sma_slow = None

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_800": 55000.0,
                "sma_2000": 60000.0,
            },
        )

        signal = strategy._detect_crossover(-0.0010, -0.0015, tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sma_filter_price_below_both_allows_signal(self, strategy, sample_tick):
        """Test that signal is allowed when price is below both SMAs."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("48000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy._detect_crossover(-0.0010, -0.0015, tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sma_filter_price_above_fast_blocks_signal(self, strategy, sample_tick):
        """Test that signal is blocked when price is above fast SMA."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("52000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy._detect_crossover(-0.0010, -0.0015, tick)

        assert signal is None

    def test_sma_filter_price_above_slow_blocks_signal(self, strategy, sample_tick):
        """Test that signal is blocked when price is above slow SMA."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("58000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_800": 60000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy._detect_crossover(-0.0010, -0.0015, tick)

        assert signal is None

    def test_sma_filter_only_fast_configured(self, strategy, sample_tick):
        """Test SMA filter with only fast SMA configured."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = None

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("48000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_800": 50000.0,
            },
        )

        signal = strategy._detect_crossover(-0.0010, -0.0015, tick)

        assert signal is not None

    def test_sma_filter_only_slow_configured(self, strategy, sample_tick):
        """Test SMA filter with only slow SMA configured."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = None
        strategy.sma_slow = "sma_2000"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("52000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy._detect_crossover(-0.0010, -0.0015, tick)

        assert signal is not None

    def test_sma_filter_missing_indicator_allows_signal(self, strategy, sample_tick):
        """Test that signal is allowed when SMA indicator is missing from tick."""
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("48000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
            },
        )

        signal = strategy._detect_crossover(-0.0010, -0.0015, tick)

        assert signal is not None

    def test_sma_filter_initialized_via_config(self, strategy, sample_tick):
        """Test that SMA filter is initialized from config."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")

        strategy._initialize_macd(sample_tick)

        assert strategy.sma_fast == "sma_800"
        assert strategy.sma_slow == "sma_2000"

    def test_sma_filter_defaults_to_none(self, strategy, sample_tick):
        """Test that SMA filter defaults to None when not configured."""
        strategy._initialize_macd(sample_tick)

        assert strategy.sma_fast is None
        assert strategy.sma_slow is None

    def test_get_stats_includes_sma_params(self, strategy, sample_tick):
        """Test that get_stats includes SMA filter parameters."""
        strategy._initialize_macd(sample_tick)
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"

        stats = strategy.get_stats()

        assert stats["sma_fast"] == "sma_800"
        assert stats["sma_slow"] == "sma_2000"

    def test_on_tick_with_sma_filter_generates_signal(self, strategy, sample_tick):
        """Test full on_tick flow with SMA filter allowing signal."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("48000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_on_tick_with_sma_filter_blocks_signal(self, strategy, sample_tick):
        """Test full on_tick flow with SMA filter blocking signal."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.last_macd = -0.0020
        strategy.last_signal = -0.0015
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("52000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdindicator_macd": -0.0010,
                "macdindicator_signal": -0.0015,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None
