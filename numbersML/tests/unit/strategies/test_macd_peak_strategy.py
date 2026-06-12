"""
Unit tests for MACDPeakStrategy.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.strategies.base import EnrichedTick, SignalType
from src.strategies.user.macd_peak_strategy import MACDPeakStrategy


class TestMACDPeakStrategy:
    """Test cases for MACDPeakStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create a strategy instance for testing."""
        return MACDPeakStrategy(
            strategy_id="test_macd_peak",
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
        assert strategy.id == "test_macd_peak"
        assert strategy.symbols == ["BTC/USDT"]
        assert strategy.last_macd == 0.0
        assert strategy.prev_macd == 0.0
        assert strategy.signal_count == 0
        assert strategy._tick_count == 0
        assert strategy._initialized is False
        assert strategy.bottom_border_macd_to_buy == 0.0
        assert strategy.grid_quantity_absolute == 100.0
        assert strategy.grid_profit_pct == 0.85
        assert strategy.trend_lookback == 3

    def test_initialize_macd(self, strategy, sample_tick):
        """Test MACD initialization with config values."""
        strategy.set_config("macd_indicator_name", "custom_macd")
        strategy.set_config("fast_period", 10)
        strategy.set_config("slow_period", 20)
        strategy.set_config("signal_period", 8)
        strategy.set_config("bottom_border_macd_to_buy", -0.5)
        strategy.set_config("grid_quantity_absolute", 200.0)
        strategy.set_config("grid_profit_pct", 1.5)
        strategy.set_config("trend_lookback", 5)

        strategy._initialize_macd(sample_tick)

        assert strategy.macd_indicator_name == "custom_macd"
        assert strategy.fast_period == 10
        assert strategy.slow_period == 20
        assert strategy.signal_period == 8
        assert strategy.bottom_border_macd_to_buy == -0.5
        assert strategy.grid_quantity_absolute == 200.0
        assert strategy.grid_profit_pct == 1.5
        assert strategy.trend_lookback == 5

    def test_initialize_macd_defaults(self, strategy, sample_tick):
        """Test MACD initialization with default values."""
        strategy._initialize_macd(sample_tick)

        assert strategy.macd_indicator_name == "macdsmaindicator"
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.signal_period == 9
        assert strategy.bottom_border_macd_to_buy == 0.0
        assert strategy.grid_quantity_absolute == 100.0
        assert strategy.grid_profit_pct == 0.85
        assert strategy.trend_lookback == 3

    def test_get_macd_values_prefixed(self, strategy, sample_tick):
        """Test getting MACD values with prefixed indicator names."""
        strategy._initialize_macd(sample_tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": -0.0015,
                "macdsmaindicator_signal": -0.0020,
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

    def test_detect_trend_reversal_decline_to_uptrend(self, strategy, sample_tick):
        """Test trend reversal detection when MACD turns from decline to uptrend."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDT"
        assert strategy.signal_count == 1
        assert signal.metadata["reversal_type"] == "decline_to_uptrend"

    def test_detect_trend_reversal_blocked_above_border(self, strategy, sample_tick):
        """Test no signal when MACD is above bottom border."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [0.0010, 0.0005, 0.0001, 0.0003]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None
        assert strategy.signal_count == 0

    def test_detect_trend_reversal_no_reversal(self, strategy, sample_tick):
        """Test no signal when MACD continues declining."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0025]

        for macd_val in macd_sequence:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        assert strategy.signal_count == 0

    def test_detect_trend_reversal_noise_filter(self, strategy, sample_tick):
        """Test that small MACD changes are filtered as noise."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 0.001
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0010001, -0.0010002, -0.0010001]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None
        assert strategy.signal_count == 0

    def test_on_tick_initializes_on_first_tick(self, strategy, sample_tick):
        """Test that on_tick initializes strategy on first tick."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": -0.0015,
                "macdsmaindicator_signal": -0.0020,
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

    def test_on_tick_updates_state(self, strategy, sample_tick):
        """Test that on_tick updates MACD state variables."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        assert strategy.last_macd == -0.0018
        assert strategy.prev_macd == -0.0020
        assert strategy.last_histogram == pytest.approx(0.0001, abs=1e-10)

    def test_signal_buy_expected_profit_price(self, strategy, sample_tick):
        """Test that BUY signal includes expected profit price."""
        macd_value = -0.0010
        signal_value = -0.0015

        signal = strategy._signal_buy(sample_tick, macd_value, signal_value)

        expected_profit_price = Decimal("50000") * (Decimal("1") + Decimal("0.85") / Decimal("100"))
        assert signal.metadata["expected_profit_price"] == expected_profit_price
        assert isinstance(signal.metadata["expected_profit_price"], Decimal)

    def test_signal_buy_expected_profit_price_decimal(self, strategy):
        """Expected_profit_price uses Decimal — no float precision loss."""
        strategy.grid_profit_pct = 0.5
        tick = EnrichedTick(
            symbol="ATOM/USDC",
            price=Decimal("1.922"),
            volume=Decimal("10"),
            time=datetime.now(UTC),
            indicators={},
        )
        signal = strategy._signal_buy(tick, -0.0045, -0.0043)

        expected = Decimal("1.922") * (Decimal("1") + Decimal("0.5") / Decimal("100"))
        assert signal.metadata["expected_profit_price"] == expected
        assert isinstance(signal.metadata["expected_profit_price"], Decimal)

    def test_signal_buy_entry_sum_equals_tp_sum(self, strategy):
        """Entry sum (qty × price) equals TP sum ÷ (1 + profit_pct/100).

        The same quantity bought at entry price is sold at take-profit
        price — the total sum must scale by exactly grid_profit_pct.
        """
        strategy.grid_profit_pct = 0.5
        strategy.grid_quantity_absolute = Decimal("25")
        tick = EnrichedTick(
            symbol="ATOM/USDC",
            price=Decimal("1.962"),
            volume=Decimal("10"),
            time=datetime.now(UTC),
            indicators={},
        )
        signal = strategy._signal_buy(tick, -0.0003, -0.0003)

        entry_sum = Decimal(str(signal.metadata["quantity_usdc"]))
        assert entry_sum == Decimal("25")

        qty = entry_sum / signal.price
        tp_price = signal.metadata["expected_profit_price"]

        # Verify: entry_sum = qty × price
        assert (qty * signal.price).quantize(Decimal("0.00000001")) == entry_sum.quantize(
            Decimal("0.00000001")
        )

        # Verify: tp_sum = entry_sum × (1 + profit_pct/100)
        tp_sum = qty * tp_price
        expected_tp_sum = entry_sum * (
            Decimal("1") + Decimal(str(strategy.grid_profit_pct)) / Decimal("100")
        )
        assert tp_sum.quantize(Decimal("0.00000001")) == expected_tp_sum.quantize(
            Decimal("0.00000001")
        ), f"TP sum {tp_sum} ≠ entry_sum × (1 + profit_pct/100) = {expected_tp_sum}"

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
        strategy.prev_macd = -0.0018
        strategy.signal_count = 3
        strategy._tick_count = 500

        stats = strategy.get_stats()

        assert stats["strategy_id"] == "test_macd_peak"
        assert stats["last_macd"] == -0.0015
        assert stats["last_signal"] == -0.0020
        assert stats["last_histogram"] == 0.0005
        assert stats["prev_macd"] == -0.0018
        assert stats["signal_count"] == 3
        assert stats["tick_count"] == 500
        assert stats["macd_indicator_name"] == "macdsmaindicator"
        assert stats["fast_period"] == 12
        assert stats["slow_period"] == 26
        assert stats["signal_period"] == 9
        assert stats["bottom_border_macd_to_buy"] == 0.0
        assert stats["grid_quantity_absolute"] == 100.0
        assert stats["grid_profit_pct"] == 0.85
        assert stats["trend_lookback"] == 3

    def test_bottom_border_custom_value(self, strategy, sample_tick):
        """Test bottom border with custom negative value."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = -1.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-1.5, -1.6, -1.7, -1.5]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.1,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.1,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sma_filter_not_configured_allows_signal(self, strategy, sample_tick):
        """Test that signal is allowed when no SMA filter is configured."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("48000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                    "sma_800": 50000.0,
                    "sma_2000": 55000.0,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("48000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sma_filter_price_below_both_allows_signal(self, strategy, sample_tick):
        """Test that signal is allowed when price is below both SMAs."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("48000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                    "sma_800": 50000.0,
                    "sma_2000": 55000.0,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("48000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sma_filter_price_above_fast_blocks_signal(self, strategy, sample_tick):
        """Test that signal is blocked when price is above fast SMA."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("52000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                    "sma_800": 50000.0,
                    "sma_2000": 55000.0,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("52000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None

    def test_sma_filter_price_above_slow_blocks_signal(self, strategy, sample_tick):
        """Test that signal is blocked when price is above slow SMA."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("58000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                    "sma_800": 60000.0,
                    "sma_2000": 55000.0,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("58000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                "sma_800": 60000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None

    def test_sma_multiplicator_initialized_from_config(self, strategy, sample_tick):
        """Test that sma_multiplicator is initialized from config."""
        strategy.set_config("sma_multiplicator", 0.995)

        strategy._initialize_macd(sample_tick)

        assert strategy.sma_multiplicator == 0.995

    def test_sma_multiplicator_default_value(self, strategy, sample_tick):
        """Test that sma_multiplicator defaults to 0.997."""
        strategy._initialize_macd(sample_tick)

        assert strategy.sma_multiplicator == 0.997

    def test_get_stats_includes_sma_params(self, strategy, sample_tick):
        """Test that get_stats includes SMA filter parameters."""
        strategy._initialize_macd(sample_tick)
        strategy.sma_fast = "sma_800"
        strategy.sma_slow = "sma_2000"
        strategy.sma_multiplicator = 0.995

        stats = strategy.get_stats()

        assert stats["sma_fast"] == "sma_800"
        assert stats["sma_slow"] == "sma_2000"
        assert stats["sma_multiplicator"] == 0.995

    def test_trend_lookback_custom_value(self, strategy, sample_tick):
        """Test that trend_lookback is initialized from config."""
        strategy.set_config("trend_lookback", 5)

        strategy._initialize_macd(sample_tick)

        assert strategy.trend_lookback == 5

    def test_trend_lookback_default_value(self, strategy, sample_tick):
        """Test that trend_lookback defaults to 3."""
        strategy._initialize_macd(sample_tick)

        assert strategy.trend_lookback == 3

    def test_macd_increasing_no_signal(self, strategy, sample_tick):
        """Test no signal when MACD is continuously increasing."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0020, -0.0015, -0.0010, -0.0005]

        for macd_val in macd_sequence:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        assert strategy.signal_count == 0

    def test_macd_flat_then_rising_no_signal(self, strategy, sample_tick):
        """Test no signal when MACD was flat then starts rising."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0010, -0.0010, -0.0008]

        for macd_val in macd_sequence:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        assert strategy.signal_count == 0

    def test_signal_cooldown_blocks_repeat_signals(self, strategy):
        """After reversal, cooldown trend_lookback+1 ticks prevents any signal.
        Cooldown = 4 when trend_lookback = 3.
        """
        strategy.set_config("min_relative_threshold", 1e-9)
        strategy._initialize_macd(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("2.0"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.trend_lookback = 3

        # Build declining history then fire reversal
        for macd_val in [-0.0033, -0.0034, -0.0035]:
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )
        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0036, "macdsmaindicator_signal": -0.0037},
            )
        )

        signal1 = strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0035, "macdsmaindicator_signal": -0.0036},
            )
        )
        assert signal1 is not None
        assert strategy._signal_cooldown == 4  # trend_lookback + 1
        assert strategy.signal_count == 1

        # Each of the next 4 ticks decrements cooldown and blocks signals
        for remaining in [3, 2, 1, 0]:
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={"macdsmaindicator_macd": -0.0034, "macdsmaindicator_signal": -0.0035},
                )
            )
            assert sig is None
            assert strategy._signal_cooldown == remaining

        assert strategy.signal_count == 1

    def test_macd_rising_each_tick_no_duplicate_signals(self, strategy):
        """Real scenario: after reversal, MACD keeps rising slightly each tick
        (-0.0033→-0.0032→-0.0032→-0.0031) but no more signals.
        """
        strategy.set_config("min_relative_threshold", 1e-9)
        strategy._initialize_macd(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("2.0"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.trend_lookback = 3

        # Build declining history: -0.0033, -0.0034, -0.0035, -0.0036
        for macd_val in [-0.0033, -0.0034, -0.0035]:
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )

        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0036, "macdsmaindicator_signal": -0.0037},
            )
        )

        # Reversal: MACD=-0.0035 (up from -0.0036)
        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.997"),
                volume=Decimal("25.08"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0035, "macdsmaindicator_signal": -0.0036},
            )
        )
        assert strategy.signal_count == 1

        # 3 more ticks with slowly rising MACD — should NOT produce signals
        for macd_val in [-0.0034, -0.0033, -0.0032]:
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.997"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )
            assert sig is None, f"Expected no signal at MACD={macd_val}"

        assert strategy.signal_count == 1

        # Phase 3 — slowly rising MACD (the real scenario from logs)
        # Each of these would have is_turning_up=True, but _reversal_active blocks
        for macd_val in [-0.0032, -0.0032, -0.0032, -0.0031, -0.0031]:
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )
            assert sig is None, f"Expected no signal at MACD={macd_val}"

        # Phase 4 — enough ticks pass that the old decline rolls out of the 4-value window
        # Feed values that break the strict decline pattern, then a new decline → reversal
        for macd_val in [-0.0030, -0.0029, -0.0028]:
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )
            assert sig is None

        # Now decline pattern should have cleared → cooldown expired
        assert strategy._signal_cooldown == 0, "Cooldown should have expired"

        # Phase 5 — a new decline then reversal should fire a new signal
        for macd_val in [-0.0030, -0.0031, -0.0032]:
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )

        signal2 = strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0030, "macdsmaindicator_signal": -0.0031},
            )
        )
        assert signal2 is not None, "New decline → reversal should fire again"
        assert strategy.signal_count == 2

    def test_macd_flat_after_reversal_no_extra_signals(self, strategy):
        """MACD jumps to -0.0033 after reversal then stays flat for 10 ticks:
        only one signal should fire."""
        strategy.set_config("min_relative_threshold", 1e-9)
        strategy._initialize_macd(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("2.0"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.trend_lookback = 3

        for macd_val in [-0.0036, -0.0037, -0.0038]:
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )
        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0039, "macdsmaindicator_signal": -0.0040},
            )
        )

        signal1 = strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0033, "macdsmaindicator_signal": -0.0034},
            )
        )
        assert signal1 is not None
        assert strategy.signal_count == 1

        for _ in range(10):
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={"macdsmaindicator_macd": -0.0033, "macdsmaindicator_signal": -0.0034},
                )
            )
            assert sig is None, "Flat MACD should not produce signals"

        assert strategy.signal_count == 1

    def test_macd_flat_after_decline_no_signal(self, strategy):
        """MACD declines then goes flat (-0.0033 for 10 ticks) without reversing."""
        strategy.set_config("min_relative_threshold", 1e-9)
        strategy._initialize_macd(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("2.0"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.trend_lookback = 3

        for macd_val in [-0.0030, -0.0031, -0.0032]:
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": macd_val,
                        "macdsmaindicator_signal": macd_val - 0.0001,
                    },
                )
            )
        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macdsmaindicator_macd": -0.0033, "macdsmaindicator_signal": -0.0034},
            )
        )

        for _ in range(10):
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={"macdsmaindicator_macd": -0.0033, "macdsmaindicator_signal": -0.0034},
                )
            )
            assert sig is None

        assert strategy.signal_count == 0

    def test_multiple_decline_reversal_cycles_one_signal_each(self, strategy):
        """Three separate decline→reversal cycles produce exactly three signals."""
        strategy.set_config("min_relative_threshold", 1e-9)
        strategy._initialize_macd(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("2.0"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.trend_lookback = 3

        for cycle in range(3):
            base = -0.0030 - cycle * 0.0010
            for step in range(3):
                strategy.on_tick(
                    EnrichedTick(
                        symbol="ATOM/USDC",
                        price=Decimal("1.99"),
                        volume=Decimal("10"),
                        time=datetime.now(UTC),
                        indicators={
                            "macdsmaindicator_macd": base - step * 0.0001,
                            "macdsmaindicator_signal": base - step * 0.0001 - 0.0001,
                        },
                    )
                )
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": base - 0.0003,
                        "macdsmaindicator_signal": base - 0.0003 - 0.0001,
                    },
                )
            )

            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macdsmaindicator_macd": base - 0.0002,
                        "macdsmaindicator_signal": base - 0.0002 - 0.0001,
                    },
                )
            )
            assert sig is not None, f"Cycle {cycle} should produce a signal"
            assert strategy.signal_count == cycle + 1

            for step in range(4):
                strategy.on_tick(
                    EnrichedTick(
                        symbol="ATOM/USDC",
                        price=Decimal("1.99"),
                        volume=Decimal("10"),
                        time=datetime.now(UTC),
                        indicators={
                            "macdsmaindicator_macd": base - 0.0002 + (step + 1) * 0.0001,
                            "macdsmaindicator_signal": base - 0.0002 + (step + 1) * 0.0001 - 0.0001,
                        },
                    )
                )

        assert strategy.signal_count == 3

    def test_slow_macd_positive_blocks_buy(self, strategy, sample_tick):
        """Test BUY is blocked when slow MACD >= 0."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                    "macd_8590_13800_195_macd": 0.001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                "macd_8590_13800_195_macd": 0.001,
            },
        )

        signal = strategy.on_tick(tick)
        assert signal is None
        assert strategy.signal_count == 0

    def test_slow_macd_negative_allows_buy(self, strategy, sample_tick):
        """Test BUY is allowed when slow MACD < 0."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                    "macd_8590_13800_195_macd": -0.001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                "macd_8590_13800_195_macd": -0.001,
            },
        )

        signal = strategy.on_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert strategy.signal_count == 1

    def test_slow_macd_not_in_indicators_allows_buy(self, strategy, sample_tick):
        """Test BUY is allowed when slow MACD indicator is not in data (backward compatible)."""
        strategy._initialize_macd(sample_tick)
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert strategy.signal_count == 1

    def test_slow_macd_custom_indicator_name(self, strategy, sample_tick):
        """Test slow MACD filter uses custom indicator name from config."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.macd_slow_indicator_name = "macd_custom"
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                    "macd_custom_macd": 0.005,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macdsmaindicator_macd": macd_sequence[-1],
                "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                "macd_custom_macd": 0.005,
            },
        )

        signal = strategy.on_tick(tick)
        assert signal is None
        assert strategy.signal_count == 0

    def test_quantity_multiplier_at_avg_day(self, strategy):
        """Test multiplier is 1.0 when price equals avg_day."""
        assert strategy._calculate_quantity_multiplier("BTC/USDT", Decimal("100")) == 1.0

    def test_quantity_multiplier_1pct_below(self, strategy):
        """Test multiplier is ~1.5 when price is 1% below avg_day."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(strategy, "get_avg_price", lambda s, p: Decimal("100"))
            mult = strategy._calculate_quantity_multiplier("BTC/USDT", Decimal("99"))
            assert abs(mult - 1.5) < 0.01

    def test_quantity_multiplier_2pct_below(self, strategy):
        """Test multiplier is ~2.0 when price is 2% below avg_day."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(strategy, "get_avg_price", lambda s, p: Decimal("100"))
            mult = strategy._calculate_quantity_multiplier("BTC/USDT", Decimal("98"))
            assert abs(mult - 2.0) < 0.01

    def test_quantity_multiplier_4pct_below(self, strategy):
        """Test multiplier is ~3.0 when price is 4% below avg_day."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(strategy, "get_avg_price", lambda s, p: Decimal("100"))
            mult = strategy._calculate_quantity_multiplier("BTC/USDT", Decimal("96"))
            assert abs(mult - 3.0) < 0.01

    def test_quantity_multiplier_above_avg_day(self, strategy):
        """Test multiplier is 1.0 when price is above avg_day."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(strategy, "get_avg_price", lambda s, p: Decimal("100"))
            assert strategy._calculate_quantity_multiplier("BTC/USDT", Decimal("105")) == 1.0

    def test_quantity_multiplier_no_avg_day(self, strategy):
        """Test multiplier is 1.0 when avg_day is not available."""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(strategy, "get_avg_price", lambda s, p: None)
            assert strategy._calculate_quantity_multiplier("BTC/USDT", Decimal("100")) == 1.0

    def test_quantity_multiplier_in_signal_metadata(self, strategy, sample_tick):
        """Test that quantity_multiplier and effective_quantity_usdc appear in signal metadata."""
        strategy._initialize_macd(sample_tick)
        strategy._initialized = True
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_val,
                    "macdsmaindicator_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        with pytest.MonkeyPatch.context() as m:
            m.setattr(strategy, "get_avg_price", lambda s, p: Decimal("51000"))
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd_sequence[-1],
                    "macdsmaindicator_signal": macd_sequence[-1] - 0.0001,
                },
            )
            signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert "quantity_multiplier" in signal.metadata
        assert "effective_quantity_usdc" in signal.metadata
        assert signal.metadata["quantity_multiplier"] > 1.0
        assert signal.metadata["effective_quantity_usdc"] > signal.metadata["quantity_usdc"]
