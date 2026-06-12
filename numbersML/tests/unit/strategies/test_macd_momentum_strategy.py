"""
Unit tests for MACDMomentumStrategy.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.strategies.base import EnrichedTick, SignalType
from src.strategies.user.macd_momentum_strategy import MACDMomentumStrategy


class TestMACDMomentumStrategy:
    """Test cases for MACDMomentumStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create a strategy instance for testing."""
        return MACDMomentumStrategy(
            strategy_id="test_macd_momentum",
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
        assert strategy.id == "test_macd_momentum"
        assert strategy.symbols == ["BTC/USDT"]
        assert strategy.last_macd == 0.0
        assert strategy.prev_macd == 0.0
        assert strategy.in_position is False
        assert strategy.signal_count == 0
        assert strategy._tick_count == 0
        assert strategy._initialized is False
        assert strategy.bottom_border_macd_to_buy == 0.0
        assert strategy.grid_quantity_absolute == 100.0
        assert strategy.grid_profit_pct == 0.85
        assert strategy.trend_lookback == 3

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

    def test_initialize_macd_custom(self, strategy, sample_tick):
        """Test MACD initialization with custom config values."""
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

    def test_get_macd_values_prefixed(self, strategy, sample_tick):
        """Test getting MACD values with prefixed indicator names."""
        strategy._initialize_macd(sample_tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": -0.0015,
                "macd_980_1960_100_signal": -0.0020,
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

    def test_get_macd_values_autodetect(self, strategy, sample_tick):
        """Test auto-detection of MACD indicators from available keys."""
        strategy._initialize_macd(sample_tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "my_macd_50_100_10_macd": -0.0015,
                "my_macd_50_100_10_signal": -0.0020,
                "my_macd_50_100_10_histogram": 0.0005,
            },
        )

        macd_value, signal_value, histogram_value = strategy._get_macd_values(tick)

        assert macd_value == -0.0015
        assert signal_value == -0.0020
        assert histogram_value == 0.0005

    def test_detect_trough_buy(self, strategy):
        """Test BUY signal on trough: decline then uptrend reversal."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDT"
        assert strategy.in_position is True
        assert strategy.signal_count == 1
        assert signal.metadata["momentum_type"] == "trough_buy"

    def test_detect_peak_sell(self, strategy):
        """Test SELL signal on peak: uptrend then decline reversal."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3
        strategy.in_position = True

        macd_sequence = [0.0020, 0.0025, 0.0030, 0.0028]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.symbol == "BTC/USDT"
        assert strategy.in_position is False
        assert strategy.signal_count == 1
        assert signal.metadata["momentum_type"] == "peak_sell"

    def test_detect_buy_blocked_above_bottom_border(self, strategy):
        """Test no BUY when MACD is above bottom border."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None
        assert strategy.signal_count == 0

    def test_detect_buy_blocked_in_position(self, strategy):
        """Test no BUY when already in a position."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3
        strategy._initialized = True
        strategy.max_open_positions = 0

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None
        assert strategy.signal_count == 0

    def test_detect_sell_blocked_not_in_position(self, strategy):
        """Test no SELL when not in a position."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3
        strategy.in_position = False

        macd_sequence = [0.0020, 0.0025, 0.0030, 0.0028]

        for macd_val in macd_sequence[:-1]:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None
        assert strategy.signal_count == 0

    def test_no_signal_continues_declining(self, strategy):
        """Test no signal when MACD continues declining without reversal."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        assert strategy.signal_count == 0

    def test_no_signal_continues_rising(self, strategy):
        """Test no signal when MACD continues rising without reversal."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        assert strategy.signal_count == 0

    def test_noise_filter_blocks_small_changes(self, strategy):
        """Test that small MACD changes are filtered as noise."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 0.001
        strategy.trend_lookback = 3

        # Pre-populate history with larger changes so dynamic threshold kicks in
        strategy._macd_change_history = [0.01] * 50
        strategy._last_macd_value = -0.0010
        strategy._macd_history = [-0.0015, -0.0014, -0.0013, -0.0012]

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": -0.0010001,
                "macd_980_1960_100_signal": -0.0011001,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is None
        assert strategy.signal_count == 0

    def test_on_tick_initializes_on_first_tick(self, strategy):
        """Test that on_tick initializes strategy on first tick."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": -0.0015,
                "macd_980_1960_100_signal": -0.0020,
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

    def test_on_tick_updates_state(self, strategy):
        """Test that on_tick updates MACD state variables."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy._initialized = True

        macd_sequence = [-0.0010, -0.0015, -0.0020, -0.0018]

        for macd_val in macd_sequence:
            tick = EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
                },
            )
            strategy.on_tick(tick)

        assert strategy.last_macd == -0.0018
        assert strategy.prev_macd == -0.0020
        assert strategy.last_histogram == pytest.approx(0.0001, abs=1e-10)

    def test_full_buy_sell_cycle(self, strategy):
        """Test a full BUY then later SELL cycle."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
        strategy.bottom_border_macd_to_buy = 0.0
        strategy.min_relative_threshold = 1e-9
        strategy.trend_lookback = 3

        def _tick(macd: float, price: str = "50000") -> EnrichedTick:
            return EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal(price),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={
                    "macdsmaindicator_macd": macd,
                    "macdsmaindicator_signal": macd - 0.0001,
                },
            )

        # Phase 1: decline then reversal → BUY at -0.0018
        for macd_val in [-0.0010, -0.0015, -0.0020]:
            strategy.on_tick(_tick(macd_val))

        buy_signal = strategy.on_tick(_tick(-0.0018))
        assert buy_signal is not None
        assert buy_signal.signal_type == SignalType.BUY
        assert strategy.in_position is True
        assert strategy.signal_count == 1

        # Phase 2: wait out cooldown, then build rising history for peak → SELL
        # After BUY: history=[-0.0010, -0.0015, -0.0020, -0.0018], cooldown=4
        for macd_val in [-0.0017, -0.0016, -0.0015]:
            strategy.on_tick(_tick(macd_val))
        # After 3 ticks: history ≈ [values], cooldown=1

        strategy.on_tick(_tick(-0.0014))  # cooldown → 0, still rising (no peak yet)
        assert strategy._signal_cooldown == 0

        # Build rising sequence: need 3 consecutive rises in indices 0,1,2 of history[0:3]
        for macd_val in [-0.0013, -0.0012, -0.0011]:
            strategy.on_tick(_tick(macd_val))
        # Now history should have rising values

        # Reversal: send a drop to trigger peak SELL
        sell_signal = strategy.on_tick(_tick(-0.0012))
        assert sell_signal is not None, f"Expected SELL, got None (history={strategy._macd_history})"
        assert sell_signal.signal_type == SignalType.SELL
        assert strategy.in_position is False
        assert strategy.signal_count == 2

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

    def test_signal_buy_quantity_usdc(self, strategy, sample_tick):
        """Test that BUY signal includes quantity in USDC."""
        strategy.grid_quantity_absolute = 250.0
        macd_value = -0.0010
        signal_value = -0.0015

        signal = strategy._signal_buy(sample_tick, macd_value, signal_value)

        assert signal.metadata["quantity_usdc"] == 250.0

    def test_signal_sell_metadata(self, strategy, sample_tick):
        """Test SELL signal metadata structure."""
        signal = strategy._signal_sell(sample_tick, 0.0030, 0.0025)

        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["momentum_type"] == "peak_sell"
        assert signal.metadata["macd"] == 0.0030
        assert signal.metadata["signal"] == 0.0025
        assert signal.metadata["histogram"] == 0.0005
        assert "quantity_usdc" not in signal.metadata

    def test_signal_buy_confidence(self, strategy, sample_tick):
        """Test that BUY signal confidence is calculated correctly."""
        macd_value = -0.0050
        signal_value = -0.0010

        signal = strategy._signal_buy(sample_tick, macd_value, signal_value)

        expected_confidence = min(1.0, abs(macd_value - signal_value) / 10.0)
        assert signal.confidence == expected_confidence

    def test_signal_sell_confidence(self, strategy, sample_tick):
        """Test that SELL signal confidence is calculated correctly."""
        signal = strategy._signal_sell(sample_tick, 0.0050, 0.0010)

        expected_confidence = min(1.0, abs(0.0050 - 0.0010) / 10.0)
        assert signal.confidence == expected_confidence

    def test_on_position_closed_resets_state(self, strategy):
        """Test that on_position_closed resets in_position."""
        strategy.in_position = True

        strategy.on_position_closed(
            symbol="BTC/USDT",
            price=Decimal("51000"),
            exit_reason="take_profit",
        )

        assert strategy.in_position is False

    def test_get_stats(self, strategy, sample_tick):
        """Test that get_stats returns correct information."""
        strategy._initialize_macd(sample_tick)
        strategy.last_macd = -0.0015
        strategy.last_signal = -0.0020
        strategy.last_histogram = 0.0005
        strategy.prev_macd = -0.0018
        strategy.in_position = True
        strategy.signal_count = 3
        strategy._tick_count = 500

        stats = strategy.get_stats()

        assert stats["strategy_id"] == "test_macd_momentum"
        assert stats["last_macd"] == -0.0015
        assert stats["last_signal"] == -0.0020
        assert stats["last_histogram"] == 0.0005
        assert stats["prev_macd"] == -0.0018
        assert stats["in_position"] is True
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

    def test_sma_filter_not_configured_allows_buy(self, strategy):
        """Test that BUY is allowed when no SMA filter is configured."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
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
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sma_filter_price_below_both_allows_buy(self, strategy):
        """Test that BUY is allowed when price is below both SMAs."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
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
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sma_filter_price_above_fast_blocks_buy(self, strategy):
        """Test that BUY is blocked when price is above fast SMA."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.0001,
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
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.0001,
                "sma_800": 50000.0,
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

    def test_trend_lookback_custom_value(self, strategy, sample_tick):
        """Test that trend_lookback is initialized from config."""
        strategy.set_config("trend_lookback", 5)
        strategy._initialize_macd(sample_tick)

        assert strategy.trend_lookback == 5

    def test_trend_lookback_default_value(self, strategy, sample_tick):
        """Test that trend_lookback defaults to 3."""
        strategy._initialize_macd(sample_tick)

        assert strategy.trend_lookback == 3

    def test_signal_cooldown_blocks_repeat_signals(self, strategy):
        """After signal, cooldown trend_lookback+1 ticks prevents any signal."""
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

        for macd_val in [-0.0033, -0.0034, -0.0035]:
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macd_980_1960_100_macd": macd_val,
                        "macd_980_1960_100_signal": macd_val - 0.0001,
                    },
                )
            )
        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macd_980_1960_100_macd": -0.0036, "macd_980_1960_100_signal": -0.0037},
            )
        )

        signal1 = strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macd_980_1960_100_macd": -0.0035, "macd_980_1960_100_signal": -0.0036},
            )
        )
        assert signal1 is not None
        assert strategy._signal_cooldown == 4
        assert strategy.signal_count == 1
        assert strategy.in_position is True

        for remaining in [3, 2, 1, 0]:
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={"macd_980_1960_100_macd": -0.0034, "macd_980_1960_100_signal": -0.0035},
                )
            )
            assert sig is None
            assert strategy._signal_cooldown == remaining

        assert strategy.signal_count == 1

    def test_macd_rising_each_tick_no_duplicate_signals(self, strategy):
        """After reversal, slowly rising MACD produces no extra signals."""
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

        for macd_val in [-0.0033, -0.0034, -0.0035]:
            strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.99"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macd_980_1960_100_macd": macd_val,
                        "macd_980_1960_100_signal": macd_val - 0.0001,
                    },
                )
            )
        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.99"),
                volume=Decimal("10"),
                time=datetime.now(UTC),
                indicators={"macd_980_1960_100_macd": -0.0036, "macd_980_1960_100_signal": -0.0037},
            )
        )

        strategy.on_tick(
            EnrichedTick(
                symbol="ATOM/USDC",
                price=Decimal("1.997"),
                volume=Decimal("25.08"),
                time=datetime.now(UTC),
                indicators={"macd_980_1960_100_macd": -0.0035, "macd_980_1960_100_signal": -0.0036},
            )
        )
        assert strategy.signal_count == 1

        for macd_val in [-0.0034, -0.0033, -0.0032]:
            sig = strategy.on_tick(
                EnrichedTick(
                    symbol="ATOM/USDC",
                    price=Decimal("1.997"),
                    volume=Decimal("10"),
                    time=datetime.now(UTC),
                    indicators={
                        "macd_980_1960_100_macd": macd_val,
                        "macd_980_1960_100_signal": macd_val - 0.0001,
                    },
                )
            )
            assert sig is None, f"Expected no signal at MACD={macd_val}"

        assert strategy.signal_count == 1

    def test_bottom_border_custom_value(self, strategy):
        """Test bottom border with custom negative value."""
        strategy._initialize_macd(
            EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal("50000"),
                volume=Decimal("1.5"),
                time=datetime.now(UTC),
                indicators={},
            )
        )
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
                    "macd_980_1960_100_macd": macd_val,
                    "macd_980_1960_100_signal": macd_val - 0.1,
                },
            )
            strategy.on_tick(tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "macd_980_1960_100_macd": macd_sequence[-1],
                "macd_980_1960_100_signal": macd_sequence[-1] - 0.1,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
