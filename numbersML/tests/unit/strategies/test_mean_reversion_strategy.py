"""
Unit tests for MeanReversionStrategy.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.strategies.base import EnrichedTick, SignalType
from src.strategies.user.mean_reversion_strategy import MeanReversionStrategy


class TestMeanReversionStrategy:
    """Test cases for MeanReversionStrategy."""

    @pytest.fixture
    def strategy(self) -> MeanReversionStrategy:
        """Create a strategy instance for testing."""
        return MeanReversionStrategy(
            strategy_id="test_mean_reversion",
            symbols=["BTC/USDT"],
        )

    @pytest.fixture
    def sample_tick(self) -> EnrichedTick:
        """Create a sample enriched tick."""
        return EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

    def test_initialization(self, strategy: MeanReversionStrategy) -> None:
        """Test strategy initializes correctly."""
        assert strategy.id == "test_mean_reversion"
        assert strategy.symbols == ["BTC/USDT"]
        assert strategy.last_bb_lower == 0.0
        assert strategy.last_bb_upper == 0.0
        assert strategy.last_rsi == 0.0
        assert strategy.signal_count == 0
        assert strategy._tick_count == 0
        assert strategy._initialized is False
        assert strategy.grid_quantity_absolute == 100.0
        assert strategy.grid_profit_pct == 0.85

    def test_initialize_with_config(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test initialization with custom config values."""
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("overbought_threshold", 70.0)
        strategy.set_config("grid_quantity_absolute", 50.0)
        strategy.set_config("grid_profit_pct", 1.0)

        strategy._initialize(sample_tick)

        assert strategy.bb_indicator_lower == "bb_500_2_lower"
        assert strategy.bb_indicator_upper == "bb_500_2_upper"
        assert strategy.rsi_indicator_name == "rsi_99"
        assert strategy.oversold_threshold == 30.0
        assert strategy.overbought_threshold == 70.0
        assert strategy.grid_quantity_absolute == 50.0
        assert strategy.grid_profit_pct == 1.0

    def test_initialize_autodetect_bb(self, strategy: MeanReversionStrategy) -> None:
        """Test auto-detection of Bollinger Bands indicators."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_middle": 1.99,
                "bb_500_2_upper": 2.00,
            },
        )

        strategy._initialize(tick)

        assert strategy.bb_indicator_lower == "bb_500_2_lower"
        assert strategy.bb_indicator_upper == "bb_500_2_upper"

    def test_initialize_autodetect_rsi(self, strategy: MeanReversionStrategy) -> None:
        """Test auto-detection of RSI indicator."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "rsi_99": 25.0,
            },
        )

        strategy._initialize(tick)

        assert strategy.rsi_indicator_name == "rsi_99"

    def test_get_bb_values_with_middle(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test getting BB values including middle band."""
        strategy._initialize(sample_tick)
        strategy.bb_indicator_lower = "bb_500_2_lower"
        strategy.bb_indicator_upper = "bb_500_2_upper"
        strategy.bb_indicator_middle = "bb_500_2_middle"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_middle": 1.99,
                "bb_500_2_upper": 2.00,
            },
        )

        lower, upper, middle = strategy._get_bb_values(tick)

        assert lower == 1.98
        assert upper == 2.00
        assert middle == 1.99

    def test_get_bb_values_without_middle(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test getting BB values without middle band (computed from lower/upper)."""
        strategy._initialize(sample_tick)
        strategy.bb_indicator_lower = "bb_500_2_lower"
        strategy.bb_indicator_upper = "bb_500_2_upper"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
            },
        )

        lower, upper, middle = strategy._get_bb_values(tick)

        assert lower == 1.98
        assert upper == 2.00
        assert middle == 1.99

    def test_get_bb_values_missing(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test getting BB values when indicators are missing."""
        strategy._initialize(sample_tick)
        strategy.bb_indicator_lower = "bb_500_2_lower"
        strategy.bb_indicator_upper = "bb_500_2_upper"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        lower, upper, middle = strategy._get_bb_values(tick)

        assert lower is None
        assert upper is None
        assert middle is None

    def test_get_rsi_value_found(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test getting RSI value when indicator is available."""
        strategy._initialize(sample_tick)
        strategy.rsi_indicator_name = "rsi_99"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={"rsi_99": 25.0},
        )

        rsi = strategy._get_rsi_value(tick)

        assert rsi == 25.0

    def test_get_rsi_value_missing(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test getting RSI value when indicator is missing."""
        strategy._initialize(sample_tick)
        strategy.rsi_indicator_name = "rsi_99"

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        rsi = strategy._get_rsi_value(tick)

        assert rsi is None

    def test_buy_signal_lower_band_with_rsi_oversold(self, strategy: MeanReversionStrategy) -> None:
        """Test BUY signal when price is at lower band and RSI is oversold."""
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        # First tick: initialize, RSI not oversold so no signal
        tick_init = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.99"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 50.0,
            },
        )
        strategy.on_tick(tick_init)

        # Second tick: conditions met -> BUY signal
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        signal = strategy.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDT"
        assert strategy.signal_count == 1
        assert signal.metadata["signal_reason"] == "mean_reversion_lower_band"

    def test_buy_signal_price_below_lower_band(self, strategy: MeanReversionStrategy) -> None:
        """Test BUY signal when price is below lower band and RSI is oversold."""
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        strategy.on_tick(tick)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        signal = strategy.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_no_buy_when_rsi_not_oversold(self, strategy: MeanReversionStrategy) -> None:
        """Test no BUY signal when RSI is above oversold threshold."""
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 35.0,
            },
        )

        strategy.on_tick(tick)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 35.0,
            },
        )

        signal = strategy.on_tick(tick2)

        assert signal is None
        assert strategy.signal_count == 0

    def test_no_buy_when_price_above_lower_band(self, strategy: MeanReversionStrategy) -> None:
        """Test no BUY signal when price is above lower band."""
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.99"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        strategy.on_tick(tick)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.99"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        signal = strategy.on_tick(tick2)

        assert signal is None
        assert strategy.signal_count == 0

    def test_on_tick_returns_none_when_bb_missing(self, strategy: MeanReversionStrategy) -> None:
        """Test that on_tick returns None when BB indicators are missing."""
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")
        strategy.set_config("rsi_indicator_name", "rsi_99")

        # Initialize with valid tick then set attributes
        init_tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 50.0,
            },
        )
        strategy._initialize(init_tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy.on_tick(tick)

        assert signal is None

    def test_sma_filter_blocks_signal(self, strategy: MeanReversionStrategy) -> None:
        """Test that SMA filter blocks signal when price is above SMA."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
                "sma_800": 49900.0,
                "sma_2000": 49900.0,
            },
        )

        strategy.on_tick(tick)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
                "sma_800": 49900.0,
                "sma_2000": 49900.0,
            },
        )

        signal = strategy.on_tick(tick2)

        assert signal is None

    def test_sma_filter_allows_signal(self, strategy: MeanReversionStrategy) -> None:
        """Test that signal is allowed when price is below SMA filter."""
        strategy.set_config("sma_fast", "sma_800")
        strategy.set_config("sma_slow", "sma_2000")
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
                "sma_800": 50000.0,
                "sma_2000": 50000.0,
            },
        )

        strategy.on_tick(tick)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
                "sma_800": 50000.0,
                "sma_2000": 50000.0,
            },
        )

        signal = strategy.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_on_tick_updates_state(self, strategy: MeanReversionStrategy) -> None:
        """Test that on_tick updates state variables."""
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")
        strategy.set_config("rsi_indicator_name", "rsi_99")

        init_tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.99"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 50.0,
            },
        )
        strategy._initialize(init_tick)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        strategy.on_tick(tick)

        assert strategy.last_bb_lower == 1.98
        assert strategy.last_bb_upper == 2.00
        assert strategy.last_rsi == 25.0

    def test_on_position_closed(self, strategy: MeanReversionStrategy) -> None:
        """Test that on_position_closed logs correctly."""
        strategy.on_position_closed(
            symbol="BTC/USDT",
            price=Decimal("51000"),
            exit_reason="take_profit",
        )

    def test_get_stats(self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick) -> None:
        """Test that get_stats returns correct information."""
        strategy._initialize(sample_tick)
        strategy.last_bb_lower = 1.98
        strategy.last_bb_upper = 2.00
        strategy.last_rsi = 25.0
        strategy.signal_count = 3
        strategy._tick_count = 500
        strategy.bb_indicator_lower = "bb_500_2_lower"
        strategy.bb_indicator_upper = "bb_500_2_upper"
        strategy.rsi_indicator_name = "rsi_99"
        strategy.oversold_threshold = 30.0
        strategy.overbought_threshold = 70.0

        stats = strategy.get_stats()

        assert stats["strategy_id"] == "test_mean_reversion"
        assert stats["last_bb_lower"] == 1.98
        assert stats["last_bb_upper"] == 2.00
        assert stats["last_rsi"] == 25.0
        assert stats["signal_count"] == 3
        assert stats["tick_count"] == 500
        assert stats["bb_indicator_lower"] == "bb_500_2_lower"
        assert stats["bb_indicator_upper"] == "bb_500_2_upper"
        assert stats["rsi_indicator_name"] == "rsi_99"
        assert stats["oversold_threshold"] == 30.0
        assert stats["overbought_threshold"] == 70.0
        assert stats["grid_quantity_absolute"] == 100.0
        assert stats["grid_profit_pct"] == 0.85

    def test_signal_buy_expected_profit_price(self, strategy: MeanReversionStrategy) -> None:
        """Test that BUY signal includes expected profit price."""
        strategy.grid_profit_pct = 0.49
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy._signal_buy(tick, 1.98, 2.00, 25.0)

        expected_profit_price = Decimal("1.98") * (Decimal("1") + Decimal("0.49") / Decimal("100"))
        assert signal.metadata["expected_profit_price"] == expected_profit_price
        assert isinstance(signal.metadata["expected_profit_price"], Decimal)

    def test_signal_buy_quantity_usdc(self, strategy: MeanReversionStrategy) -> None:
        """Test that BUY signal includes quantity in USDC."""
        strategy.grid_quantity_absolute = 25.0
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy._signal_buy(tick, 1.98, 2.00, 25.0)

        assert signal.metadata["quantity_usdc"] == 25.0

    def test_signal_buy_confidence(self, strategy: MeanReversionStrategy) -> None:
        """Test that BUY signal confidence is calculated correctly."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy._signal_buy(tick, 1.98, 2.00, 25.0)

        expected_confidence = min(1.0, (2.00 - 1.97) / (2.00 - 1.98))
        assert signal.confidence == expected_confidence

    def test_on_tick_initializes_on_first_tick(self, strategy: MeanReversionStrategy) -> None:
        """Test that on_tick initializes strategy on first tick."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        assert strategy._initialized is False
        strategy.on_tick(tick)
        assert strategy._initialized is True
        assert strategy._tick_count == 1

    def test_no_buy_when_missing_bb_on_second_tick(self, strategy: MeanReversionStrategy) -> None:
        """Test no signal when BB indicators disappear on subsequent tick."""
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        tick1 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
            },
        )

        strategy.on_tick(tick1)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.98"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={},
        )

        signal = strategy.on_tick(tick2)

        assert signal is None

    def test_default_thresholds(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test that default RSI thresholds are 31.9 and 68.1."""
        strategy._initialize(sample_tick)

        assert strategy.oversold_threshold == 31.9
        assert strategy.overbought_threshold == pytest.approx(68.1, abs=1e-10)

    def test_custom_oversold_from_config(
        self, strategy: MeanReversionStrategy, sample_tick: EnrichedTick
    ) -> None:
        """Test that oversold threshold is loaded from config."""
        strategy.set_config("oversold_threshold", 25.0)

        strategy._initialize(sample_tick)

        assert strategy.oversold_threshold == 25.0
        assert strategy.overbought_threshold == pytest.approx(68.1, abs=1e-10)

    def test_missing_rsi_still_allows_bb_signal(self, strategy: MeanReversionStrategy) -> None:
        """Test that missing RSI still allows signal if other conditions met."""
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")
        strategy.set_config("oversold_threshold", 30.0)

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
            },
        )

        strategy.on_tick(tick)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
            },
        )

        signal = strategy.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_autodetect_no_bb_indicators(self, strategy: MeanReversionStrategy) -> None:
        """Test auto-detect with no BB indicators in tick."""
        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("50000"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "rsi_99": 25.0,
                "sma_800": 1.99,
            },
        )

        strategy._initialize(tick)

        assert strategy.bb_indicator_lower is None
        assert strategy.bb_indicator_upper is None
        assert strategy.rsi_indicator_name == "rsi_99"

    def test_sma_filter_not_configured_allows_signal(self, strategy: MeanReversionStrategy) -> None:
        """Test that signal is allowed when no SMA filter is configured."""
        strategy.set_config("oversold_threshold", 30.0)
        strategy.set_config("rsi_indicator_name", "rsi_99")
        strategy.set_config("bb_indicator_lower", "bb_500_2_lower")
        strategy.set_config("bb_indicator_upper", "bb_500_2_upper")

        tick = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        strategy.on_tick(tick)

        tick2 = EnrichedTick(
            symbol="BTC/USDT",
            price=Decimal("1.97"),
            volume=Decimal("1.5"),
            time=datetime.now(UTC),
            indicators={
                "bb_500_2_lower": 1.98,
                "bb_500_2_upper": 2.00,
                "rsi_99": 25.0,
                "sma_800": 50000.0,
                "sma_2000": 55000.0,
            },
        )

        signal = strategy.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
