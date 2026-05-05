"""
Tests for Sample Trading Algorithms.

Tests RSI, MACD, SMA Crossover, Bollinger Bands, and Multi-Indicator algorithms.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.algorithms.base import (
    EnrichedTick,
    SignalType,
)
from src.domain.algorithms.algorithms_impl import (
    BollingerBandsAlgorithm,
    MACDAlgorithm,
    MultiIndicatorAlgorithm,
    RSIAlgorithm,
    SMACrossoverAlgorithm,
)


class TestRSIAlgorithm:
    """Test RSI Oversold/Overbought Algorithm."""

    @pytest.fixture
    def rsi_algorithm(self) -> RSIAlgorithm:
        """Create RSI algorithm instance."""
        return RSIAlgorithm(
            algorithm_id="test_rsi",
            symbols=["BTC/USDT"],
            rsi_period=14,
            oversold_threshold=30.0,
            overbought_threshold=70.0,
            confidence=0.75,
        )

    @pytest.fixture
    def create_tick(self) -> callable:
        """Factory for creating enriched ticks."""

        def _create(rsi_value: float, price: float = 50000.0) -> EnrichedTick:
            return EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal(str(price)),
                volume=Decimal("1.0"),
                time=datetime.now(UTC),
                indicators={"rsiindicator_period14_rsi": rsi_value},
            )

        return _create

    def test_rsi_algorithm_initialization(self, rsi_algorithm: RSIAlgorithm) -> None:
        """Test RSI algorithm initializes correctly."""
        assert rsi_algorithm.id == "test_rsi"
        assert rsi_algorithm.symbols == ["BTC/USDT"]
        assert rsi_algorithm.rsi_period == 14
        assert rsi_algorithm.oversold_threshold == 30.0
        assert rsi_algorithm.overbought_threshold == 70.0
        assert rsi_algorithm.confidence == 0.75

    @pytest.mark.asyncio
    async def test_rsi_oversold_signal(
        self,
        rsi_algorithm: RSIAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test RSI algorithm generates BUY signal when oversold."""

        # Create oversold tick (RSI = 25)
        tick = create_tick(rsi_value=25.0)
        signal = rsi_algorithm.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.75
        assert signal.metadata["rsi"] == 25.0
        assert signal.metadata["condition"] == "oversold"

    @pytest.mark.asyncio
    async def test_rsi_overbought_signal(
        self,
        rsi_algorithm: RSIAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test RSI algorithm generates SELL signal when overbought."""

        # Create overbought tick (RSI = 75)
        tick = create_tick(rsi_value=75.0)
        signal = rsi_algorithm.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence == 0.75
        assert signal.metadata["rsi"] == 75.0
        assert signal.metadata["condition"] == "overbought"

    @pytest.mark.asyncio
    async def test_rsi_no_signal_neutral(
        self,
        rsi_algorithm: RSIAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test RSI algorithm generates no signal in neutral zone."""

        # Create neutral tick (RSI = 50)
        tick = create_tick(rsi_value=50.0)
        signal = rsi_algorithm.on_tick(tick)

        assert signal is None

    @pytest.mark.asyncio
    async def test_rsi_threshold_boundaries(
        self,
        rsi_algorithm: RSIAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test RSI algorithm at threshold boundaries."""

        # At oversold threshold (should not trigger)
        tick = create_tick(rsi_value=30.0)
        signal = rsi_algorithm.on_tick(tick)
        assert signal is None

        # Just below oversold (should trigger)
        tick = create_tick(rsi_value=29.9)
        signal = rsi_algorithm.on_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY

        # At overbought threshold (should not trigger)
        tick = create_tick(rsi_value=70.0)
        signal = rsi_algorithm.on_tick(tick)
        assert signal is None

        # Just above overbought (should trigger)
        tick = create_tick(rsi_value=70.1)
        signal = rsi_algorithm.on_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL


class TestMACDAlgorithm:
    """Test MACD Crossover Algorithm."""

    @pytest.fixture
    def macd_algorithm(self) -> MACDAlgorithm:
        """Create MACD algorithm instance."""
        return MACDAlgorithm(
            algorithm_id="test_macd",
            symbols=["BTC/USDT"],
            fast_period=12,
            slow_period=26,
            signal_period=9,
            confidence=0.7,
        )

    @pytest.fixture
    def create_tick(self) -> callable:
        """Factory for creating enriched ticks."""

        def _create(macd: float, signal: float, price: float = 50000.0) -> EnrichedTick:
            return EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal(str(price)),
                volume=Decimal("1.0"),
                time=datetime.now(UTC),
                indicators={
                    "macdindicator_fast_period12_slow_period26_signal_period9_macd": macd,
                    "macdindicator_fast_period12_slow_period26_signal_period9_signal": signal,
                },
            )

        return _create

    def test_macd_algorithm_initialization(self, macd_algorithm: MACDAlgorithm) -> None:
        """Test MACD algorithm initializes correctly."""
        assert macd_algorithm.fast_period == 12
        assert macd_algorithm.slow_period == 26
        assert macd_algorithm.signal_period == 9

    @pytest.mark.asyncio
    async def test_macd_bullish_crossover(
        self,
        macd_algorithm: MACDAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test MACD algorithm generates BUY signal on bullish crossover."""

        # First tick: MACD below signal
        tick1 = create_tick(macd=100.0, signal=110.0)
        macd_algorithm.on_tick(tick1)

        # Second tick: MACD crosses above signal
        tick2 = create_tick(macd=120.0, signal=115.0)
        signal = macd_algorithm.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["condition"] == "bullish_crossover"

    @pytest.mark.asyncio
    async def test_macd_bearish_crossover(
        self,
        macd_algorithm: MACDAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test MACD algorithm generates SELL signal on bearish crossover."""

        # First tick: MACD above signal
        tick1 = create_tick(macd=120.0, signal=110.0)
        macd_algorithm.on_tick(tick1)

        # Second tick: MACD crosses below signal
        tick2 = create_tick(macd=100.0, signal=105.0)
        signal = macd_algorithm.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["condition"] == "bearish_crossover"

    @pytest.mark.asyncio
    async def test_macd_no_crossover(
        self,
        macd_algorithm: MACDAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test MACD algorithm generates no signal without crossover."""

        # First tick
        tick1 = create_tick(macd=100.0, signal=90.0)
        macd_algorithm.on_tick(tick1)

        # Second tick: No crossover
        tick2 = create_tick(macd=105.0, signal=95.0)
        signal = macd_algorithm.on_tick(tick2)

        assert signal is None


class TestSMACrossoverAlgorithm:
    """Test SMA Crossover Algorithm."""

    @pytest.fixture
    def sma_algorithm(self) -> SMACrossoverAlgorithm:
        """Create SMA crossover algorithm instance."""
        return SMACrossoverAlgorithm(
            algorithm_id="test_sma_cross",
            symbols=["BTC/USDT"],
            fast_period=20,
            slow_period=50,
            confidence=0.65,
        )

    @pytest.fixture
    def create_tick(self) -> callable:
        """Factory for creating enriched ticks."""

        def _create(fast_sma: float, slow_sma: float, price: float = 50000.0) -> EnrichedTick:
            return EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal(str(price)),
                volume=Decimal("1.0"),
                time=datetime.now(UTC),
                indicators={
                    "smaindicator_period20_sma": fast_sma,
                    "smaindicator_period50_sma": slow_sma,
                },
            )

        return _create

    def test_sma_algorithm_initialization(self, sma_algorithm: SMACrossoverAlgorithm) -> None:
        """Test SMA crossover algorithm initializes correctly."""
        assert sma_algorithm.fast_period == 20
        assert sma_algorithm.slow_period == 50

    @pytest.mark.asyncio
    async def test_golden_cross(
        self,
        sma_algorithm: SMACrossoverAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test SMA algorithm generates BUY signal on golden cross."""

        # First tick: Fast SMA below slow SMA
        tick1 = create_tick(fast_sma=49000.0, slow_sma=50000.0)
        sma_algorithm.on_tick(tick1)

        # Second tick: Fast SMA crosses above slow SMA
        tick2 = create_tick(fast_sma=50500.0, slow_sma=50000.0)
        signal = sma_algorithm.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["condition"] == "golden_cross"

    @pytest.mark.asyncio
    async def test_death_cross(
        self,
        sma_algorithm: SMACrossoverAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test SMA algorithm generates SELL signal on death cross."""

        # First tick: Fast SMA above slow SMA
        tick1 = create_tick(fast_sma=51000.0, slow_sma=50000.0)
        sma_algorithm.on_tick(tick1)

        # Second tick: Fast SMA crosses below slow SMA
        tick2 = create_tick(fast_sma=49500.0, slow_sma=50000.0)
        signal = sma_algorithm.on_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["condition"] == "death_cross"


class TestBollingerBandsAlgorithm:
    """Test Bollinger Bands Mean Reversion Algorithm."""

    @pytest.fixture
    def bb_algorithm(self) -> BollingerBandsAlgorithm:
        """Create Bollinger Bands algorithm instance."""
        return BollingerBandsAlgorithm(
            algorithm_id="test_bb",
            symbols=["BTC/USDT"],
            period=20,
            std_dev=2.0,
            confidence=0.6,
        )

    @pytest.fixture
    def create_tick(self) -> callable:
        """Factory for creating enriched ticks."""

        def _create(
            price: float,
            upper: float = 51000.0,
            middle: float = 50000.0,
            lower: float = 49000.0,
        ) -> EnrichedTick:
            return EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal(str(price)),
                volume=Decimal("1.0"),
                time=datetime.now(UTC),
                indicators={
                    "bbindicator_period20_std_dev2.0_upper": upper,
                    "bbindicator_period20_std_dev2.0_middle": middle,
                    "bbindicator_period20_std_dev2.0_lower": lower,
                },
            )

        return _create

    def test_bb_algorithm_initialization(self, bb_algorithm: BollingerBandsAlgorithm) -> None:
        """Test Bollinger Bands algorithm initializes correctly."""
        assert bb_algorithm.period == 20
        assert bb_algorithm.std_dev == 2.0

    @pytest.mark.asyncio
    async def test_bb_lower_band_buy(
        self,
        bb_algorithm: BollingerBandsAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test BB algorithm generates BUY signal at lower band."""

        # Price at lower band
        tick = create_tick(price=49000.0, lower=49000.0)
        signal = bb_algorithm.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["condition"] == "touching_lower_band"

    @pytest.mark.asyncio
    async def test_bb_upper_band_sell(
        self,
        bb_algorithm: BollingerBandsAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test BB algorithm generates SELL signal at upper band."""

        # Price at upper band
        tick = create_tick(price=51000.0, upper=51000.0)
        signal = bb_algorithm.on_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["condition"] == "touching_upper_band"

    @pytest.mark.asyncio
    async def test_bb_no_signal_middle(
        self,
        bb_algorithm: BollingerBandsAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test BB algorithm generates no signal in middle."""

        # Price in middle
        tick = create_tick(price=50000.0)
        signal = bb_algorithm.on_tick(tick)

        assert signal is None


class TestMultiIndicatorAlgorithm:
    """Test Multi-Indicator Composite Algorithm."""

    @pytest.fixture
    def multi_algorithm(self) -> MultiIndicatorAlgorithm:
        """Create multi-indicator algorithm instance."""
        return MultiIndicatorAlgorithm(
            algorithm_id="test_multi",
            symbols=["BTC/USDT"],
            rsi_period=14,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            sma_period=200,
            require_all_signals=False,
            confidence=0.8,
        )

    @pytest.fixture
    def create_tick(self) -> callable:
        """Factory for creating enriched ticks."""

        def _create(
            rsi: float,
            macd: float,
            macd_signal: float,
            sma: float,
            price: float = 50000.0,
            prev_macd: float = None,
            prev_macd_signal: float = None,
        ) -> EnrichedTick:
            indicators = {
                "rsiindicator_period14_rsi": rsi,
                "macdindicator_fast_period12_slow_period26_signal_period9_macd": macd,
                "macdindicator_fast_period12_slow_period26_signal_period9_signal": macd_signal,
                "smaindicator_period200_sma": sma,
            }
            return EnrichedTick(
                symbol="BTC/USDT",
                price=Decimal(str(price)),
                volume=Decimal("1.0"),
                time=datetime.now(UTC),
                indicators=indicators,
            )

        return _create

    def test_multi_algorithm_initialization(self, multi_algorithm: MultiIndicatorAlgorithm) -> None:
        """Test multi-indicator algorithm initializes correctly."""
        assert multi_algorithm.rsi_period == 14
        assert multi_algorithm.sma_period == 200
        assert multi_algorithm.require_all_signals is False

    @pytest.mark.asyncio
    async def test_multi_algorithm_majority_buy(
        self,
        multi_algorithm: MultiIndicatorAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test multi-indicator algorithm with majority buy signals."""

        # Setup: 2 out of 3 bullish (RSI oversold, price > SMA)
        # First tick for MACD state
        tick1 = create_tick(
            rsi=35.0,
            macd=100.0,
            macd_signal=110.0,
            sma=49000.0,
            price=50000.0,
        )
        multi_algorithm.on_tick(tick1)

        # Second tick: RSI oversold + MACD bullish crossover + price > SMA
        tick2 = create_tick(
            rsi=25.0,  # Oversold
            macd=120.0,
            macd_signal=115.0,  # Bullish crossover
            sma=49000.0,
            price=50500.0,  # Above SMA
        )
        signal = multi_algorithm.on_tick(tick2)

        # Should generate BUY signal (3 out of 3 bullish)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    @pytest.mark.asyncio
    async def test_multi_algorithm_majority_sell(
        self,
        multi_algorithm: MultiIndicatorAlgorithm,
        create_tick: callable,
    ) -> None:
        """Test multi-indicator algorithm with majority sell signals."""

        # First tick for MACD state
        tick1 = create_tick(
            rsi=65.0,
            macd=120.0,
            macd_signal=110.0,
            sma=51000.0,
            price=50000.0,
        )
        multi_algorithm.on_tick(tick1)

        # Second tick: RSI overbought + MACD bearish + price < SMA
        tick2 = create_tick(
            rsi=75.0,  # Overbought
            macd=100.0,
            macd_signal=105.0,  # Bearish crossover
            sma=51000.0,
            price=50500.0,  # Below SMA
        )
        signal = multi_algorithm.on_tick(tick2)

        # Should generate SELL signal (3 out of 3 bearish)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
