"""
Tests for Sample Trading Strategies.

Tests RSI, MACD, SMA Crossover, Bollinger Bands, and Multi-Indicator strategies.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from src.domain.strategies.base import (
    EnrichedTick,
    Signal,
    SignalType,
    StrategyState,
)
from src.domain.strategies.strategies import (
    RSIStrategy,
    MACDStrategy,
    SMACrossoverStrategy,
    BollingerBandsStrategy,
    MultiIndicatorStrategy,
)


class TestRSIStrategy:
    """Test RSI Oversold/Overbought Strategy."""

    @pytest.fixture
    def rsi_strategy(self) -> RSIStrategy:
        """Create RSI strategy instance."""
        return RSIStrategy(
            strategy_id='test_rsi',
            symbols=['BTC/USDT'],
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
                symbol='BTC/USDT',
                price=Decimal(str(price)),
                volume=Decimal('1.0'),
                time=datetime.utcnow(),
                indicators={'rsiindicator_period14_rsi': rsi_value},
            )
        return _create

    def test_rsi_strategy_initialization(self, rsi_strategy: RSIStrategy) -> None:
        """Test RSI strategy initializes correctly."""
        assert rsi_strategy.id == 'test_rsi'
        assert rsi_strategy.symbols == ['BTC/USDT']
        assert rsi_strategy.rsi_period == 14
        assert rsi_strategy.oversold_threshold == 30.0
        assert rsi_strategy.overbought_threshold == 70.0
        assert rsi_strategy.confidence == 0.75

    @pytest.mark.asyncio
    async def test_rsi_oversold_signal(
        self,
        rsi_strategy: RSIStrategy,
        create_tick: callable,
    ) -> None:
        """Test RSI strategy generates BUY signal when oversold."""
        await rsi_strategy.initialize()

        # Create oversold tick (RSI = 25)
        tick = create_tick(rsi_value=25.0)
        signal = rsi_strategy.process_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.75
        assert signal.metadata['rsi'] == 25.0
        assert signal.metadata['condition'] == 'oversold'

    @pytest.mark.asyncio
    async def test_rsi_overbought_signal(
        self,
        rsi_strategy: RSIStrategy,
        create_tick: callable,
    ) -> None:
        """Test RSI strategy generates SELL signal when overbought."""
        await rsi_strategy.initialize()

        # Create overbought tick (RSI = 75)
        tick = create_tick(rsi_value=75.0)
        signal = rsi_strategy.process_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence == 0.75
        assert signal.metadata['rsi'] == 75.0
        assert signal.metadata['condition'] == 'overbought'

    @pytest.mark.asyncio
    async def test_rsi_no_signal_neutral(
        self,
        rsi_strategy: RSIStrategy,
        create_tick: callable,
    ) -> None:
        """Test RSI strategy generates no signal in neutral zone."""
        await rsi_strategy.initialize()

        # Create neutral tick (RSI = 50)
        tick = create_tick(rsi_value=50.0)
        signal = rsi_strategy.process_tick(tick)

        assert signal is None

    @pytest.mark.asyncio
    async def test_rsi_threshold_boundaries(
        self,
        rsi_strategy: RSIStrategy,
        create_tick: callable,
    ) -> None:
        """Test RSI strategy at threshold boundaries."""
        await rsi_strategy.initialize()

        # At oversold threshold (should not trigger)
        tick = create_tick(rsi_value=30.0)
        signal = rsi_strategy.process_tick(tick)
        assert signal is None

        # Just below oversold (should trigger)
        tick = create_tick(rsi_value=29.9)
        signal = rsi_strategy.process_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY

        # At overbought threshold (should not trigger)
        tick = create_tick(rsi_value=70.0)
        signal = rsi_strategy.process_tick(tick)
        assert signal is None

        # Just above overbought (should trigger)
        tick = create_tick(rsi_value=70.1)
        signal = rsi_strategy.process_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL


class TestMACDStrategy:
    """Test MACD Crossover Strategy."""

    @pytest.fixture
    def macd_strategy(self) -> MACDStrategy:
        """Create MACD strategy instance."""
        return MACDStrategy(
            strategy_id='test_macd',
            symbols=['BTC/USDT'],
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
                symbol='BTC/USDT',
                price=Decimal(str(price)),
                volume=Decimal('1.0'),
                time=datetime.utcnow(),
                indicators={
                    'macdindicator_fast_period12_slow_period26_signal_period9_macd': macd,
                    'macdindicator_fast_period12_slow_period26_signal_period9_signal': signal,
                },
            )
        return _create

    def test_macd_strategy_initialization(self, macd_strategy: MACDStrategy) -> None:
        """Test MACD strategy initializes correctly."""
        assert macd_strategy.fast_period == 12
        assert macd_strategy.slow_period == 26
        assert macd_strategy.signal_period == 9

    @pytest.mark.asyncio
    async def test_macd_bullish_crossover(
        self,
        macd_strategy: MACDStrategy,
        create_tick: callable,
    ) -> None:
        """Test MACD strategy generates BUY signal on bullish crossover."""
        await macd_strategy.initialize()

        # First tick: MACD below signal
        tick1 = create_tick(macd=100.0, signal=110.0)
        macd_strategy.process_tick(tick1)

        # Second tick: MACD crosses above signal
        tick2 = create_tick(macd=120.0, signal=115.0)
        signal = macd_strategy.process_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata['condition'] == 'bullish_crossover'

    @pytest.mark.asyncio
    async def test_macd_bearish_crossover(
        self,
        macd_strategy: MACDStrategy,
        create_tick: callable,
    ) -> None:
        """Test MACD strategy generates SELL signal on bearish crossover."""
        await macd_strategy.initialize()

        # First tick: MACD above signal
        tick1 = create_tick(macd=120.0, signal=110.0)
        macd_strategy.process_tick(tick1)

        # Second tick: MACD crosses below signal
        tick2 = create_tick(macd=100.0, signal=105.0)
        signal = macd_strategy.process_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata['condition'] == 'bearish_crossover'

    @pytest.mark.asyncio
    async def test_macd_no_crossover(
        self,
        macd_strategy: MACDStrategy,
        create_tick: callable,
    ) -> None:
        """Test MACD strategy generates no signal without crossover."""
        await macd_strategy.initialize()

        # First tick
        tick1 = create_tick(macd=100.0, signal=90.0)
        macd_strategy.process_tick(tick1)

        # Second tick: No crossover
        tick2 = create_tick(macd=105.0, signal=95.0)
        signal = macd_strategy.process_tick(tick2)

        assert signal is None


class TestSMACrossoverStrategy:
    """Test SMA Crossover Strategy."""

    @pytest.fixture
    def sma_strategy(self) -> SMACrossoverStrategy:
        """Create SMA crossover strategy instance."""
        return SMACrossoverStrategy(
            strategy_id='test_sma_cross',
            symbols=['BTC/USDT'],
            fast_period=20,
            slow_period=50,
            confidence=0.65,
        )

    @pytest.fixture
    def create_tick(self) -> callable:
        """Factory for creating enriched ticks."""
        def _create(fast_sma: float, slow_sma: float, price: float = 50000.0) -> EnrichedTick:
            return EnrichedTick(
                symbol='BTC/USDT',
                price=Decimal(str(price)),
                volume=Decimal('1.0'),
                time=datetime.utcnow(),
                indicators={
                    'smaindicator_period20_sma': fast_sma,
                    'smaindicator_period50_sma': slow_sma,
                },
            )
        return _create

    def test_sma_strategy_initialization(self, sma_strategy: SMACrossoverStrategy) -> None:
        """Test SMA crossover strategy initializes correctly."""
        assert sma_strategy.fast_period == 20
        assert sma_strategy.slow_period == 50

    @pytest.mark.asyncio
    async def test_golden_cross(
        self,
        sma_strategy: SMACrossoverStrategy,
        create_tick: callable,
    ) -> None:
        """Test SMA strategy generates BUY signal on golden cross."""
        await sma_strategy.initialize()

        # First tick: Fast SMA below slow SMA
        tick1 = create_tick(fast_sma=49000.0, slow_sma=50000.0)
        sma_strategy.process_tick(tick1)

        # Second tick: Fast SMA crosses above slow SMA
        tick2 = create_tick(fast_sma=50500.0, slow_sma=50000.0)
        signal = sma_strategy.process_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata['condition'] == 'golden_cross'

    @pytest.mark.asyncio
    async def test_death_cross(
        self,
        sma_strategy: SMACrossoverStrategy,
        create_tick: callable,
    ) -> None:
        """Test SMA strategy generates SELL signal on death cross."""
        await sma_strategy.initialize()

        # First tick: Fast SMA above slow SMA
        tick1 = create_tick(fast_sma=51000.0, slow_sma=50000.0)
        sma_strategy.process_tick(tick1)

        # Second tick: Fast SMA crosses below slow SMA
        tick2 = create_tick(fast_sma=49500.0, slow_sma=50000.0)
        signal = sma_strategy.process_tick(tick2)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata['condition'] == 'death_cross'


class TestBollingerBandsStrategy:
    """Test Bollinger Bands Mean Reversion Strategy."""

    @pytest.fixture
    def bb_strategy(self) -> BollingerBandsStrategy:
        """Create Bollinger Bands strategy instance."""
        return BollingerBandsStrategy(
            strategy_id='test_bb',
            symbols=['BTC/USDT'],
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
                symbol='BTC/USDT',
                price=Decimal(str(price)),
                volume=Decimal('1.0'),
                time=datetime.utcnow(),
                indicators={
                    'bbindicator_period20_std_dev2.0_upper': upper,
                    'bbindicator_period20_std_dev2.0_middle': middle,
                    'bbindicator_period20_std_dev2.0_lower': lower,
                },
            )
        return _create

    def test_bb_strategy_initialization(self, bb_strategy: BollingerBandsStrategy) -> None:
        """Test Bollinger Bands strategy initializes correctly."""
        assert bb_strategy.period == 20
        assert bb_strategy.std_dev == 2.0

    @pytest.mark.asyncio
    async def test_bb_lower_band_buy(
        self,
        bb_strategy: BollingerBandsStrategy,
        create_tick: callable,
    ) -> None:
        """Test BB strategy generates BUY signal at lower band."""
        await bb_strategy.initialize()

        # Price at lower band
        tick = create_tick(price=49000.0, lower=49000.0)
        signal = bb_strategy.process_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata['condition'] == 'touching_lower_band'

    @pytest.mark.asyncio
    async def test_bb_upper_band_sell(
        self,
        bb_strategy: BollingerBandsStrategy,
        create_tick: callable,
    ) -> None:
        """Test BB strategy generates SELL signal at upper band."""
        await bb_strategy.initialize()

        # Price at upper band
        tick = create_tick(price=51000.0, upper=51000.0)
        signal = bb_strategy.process_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata['condition'] == 'touching_upper_band'

    @pytest.mark.asyncio
    async def test_bb_no_signal_middle(
        self,
        bb_strategy: BollingerBandsStrategy,
        create_tick: callable,
    ) -> None:
        """Test BB strategy generates no signal in middle."""
        await bb_strategy.initialize()

        # Price in middle
        tick = create_tick(price=50000.0)
        signal = bb_strategy.process_tick(tick)

        assert signal is None


class TestMultiIndicatorStrategy:
    """Test Multi-Indicator Composite Strategy."""

    @pytest.fixture
    def multi_strategy(self) -> MultiIndicatorStrategy:
        """Create multi-indicator strategy instance."""
        return MultiIndicatorStrategy(
            strategy_id='test_multi',
            symbols=['BTC/USDT'],
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
                'rsiindicator_period14_rsi': rsi,
                'macdindicator_fast_period12_slow_period26_signal_period9_macd': macd,
                'macdindicator_fast_period12_slow_period26_signal_period9_signal': macd_signal,
                'smaindicator_period200_sma': sma,
            }
            return EnrichedTick(
                symbol='BTC/USDT',
                price=Decimal(str(price)),
                volume=Decimal('1.0'),
                time=datetime.utcnow(),
                indicators=indicators,
            )
        return _create

    def test_multi_strategy_initialization(self, multi_strategy: MultiIndicatorStrategy) -> None:
        """Test multi-indicator strategy initializes correctly."""
        assert multi_strategy.rsi_period == 14
        assert multi_strategy.sma_period == 200
        assert multi_strategy.require_all_signals is False

    @pytest.mark.asyncio
    async def test_multi_strategy_majority_buy(
        self,
        multi_strategy: MultiIndicatorStrategy,
        create_tick: callable,
    ) -> None:
        """Test multi-indicator strategy with majority buy signals."""
        await multi_strategy.initialize()

        # Setup: 2 out of 3 bullish (RSI oversold, price > SMA)
        # First tick for MACD state
        tick1 = create_tick(
            rsi=35.0,
            macd=100.0,
            macd_signal=110.0,
            sma=49000.0,
            price=50000.0,
        )
        multi_strategy.process_tick(tick1)

        # Second tick: RSI oversold + MACD bullish crossover + price > SMA
        tick2 = create_tick(
            rsi=25.0,  # Oversold
            macd=120.0,
            macd_signal=115.0,  # Bullish crossover
            sma=49000.0,
            price=50500.0,  # Above SMA
        )
        signal = multi_strategy.process_tick(tick2)

        # Should generate BUY signal (3 out of 3 bullish)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    @pytest.mark.asyncio
    async def test_multi_strategy_majority_sell(
        self,
        multi_strategy: MultiIndicatorStrategy,
        create_tick: callable,
    ) -> None:
        """Test multi-indicator strategy with majority sell signals."""
        await multi_strategy.initialize()

        # First tick for MACD state
        tick1 = create_tick(
            rsi=65.0,
            macd=120.0,
            macd_signal=110.0,
            sma=51000.0,
            price=50000.0,
        )
        multi_strategy.process_tick(tick1)

        # Second tick: RSI overbought + MACD bearish + price < SMA
        tick2 = create_tick(
            rsi=75.0,  # Overbought
            macd=100.0,
            macd_signal=105.0,  # Bearish crossover
            sma=51000.0,
            price=50500.0,  # Below SMA
        )
        signal = multi_strategy.process_tick(tick2)

        # Should generate SELL signal (3 out of 3 bearish)
        assert signal is not None
        assert signal.signal_type == SignalType.SELL

    @pytest.mark.asyncio
    async def test_multi_strategy_require_all(
        self,
        create_tick: callable,
    ) -> None:
        """Test multi-indicator strategy with require_all_signals=True."""
        strategy = MultiIndicatorStrategy(
            strategy_id='test_multi_strict',
            symbols=['BTC/USDT'],
            require_all_signals=True,
        )
        await strategy.initialize()

        # First tick for MACD state
        tick1 = create_tick(
            rsi=25.0,
            macd=100.0,
            macd_signal=110.0,
            sma=49000.0,
            price=50000.0,
        )
        strategy.process_tick(tick1)

        # Second tick: Only 2 out of 3 bullish (not all)
        tick2 = create_tick(
            rsi=25.0,  # Oversold
            macd=120.0,
            macd_signal=115.0,  # Bullish
            sma=51000.0,
            price=50500.0,  # Below SMA (not bullish)
        )
        signal = strategy.process_tick(tick2)

        # Should NOT generate signal (not all agree)
        assert signal is None


class TestStrategyIntegration:
    """Test multiple strategies working together."""

    @pytest.mark.asyncio
    async def test_multiple_strategies_same_tick(self) -> None:
        """Test running multiple strategies on same tick."""
        from src.domain.strategies.base import StrategyManager

        # Create strategies
        rsi_strategy = RSIStrategy('rsi', ['BTC/USDT'])
        macd_strategy = MACDStrategy('macd', ['BTC/USDT'])
        sma_strategy = SMACrossoverStrategy('sma', ['BTC/USDT'])

        # Create manager
        manager = StrategyManager()
        manager.add_strategy(rsi_strategy)
        manager.add_strategy(macd_strategy)
        manager.add_strategy(sma_strategy)

        # Start all
        await manager.start_all()

        # Create tick with all indicators
        tick = EnrichedTick(
            symbol='BTC/USDT',
            price=Decimal('50000.00'),
            volume=Decimal('1.0'),
            time=datetime.utcnow(),
            indicators={
                'rsiindicator_period14_rsi': 25.0,  # Oversold
                'macdindicator_fast_period12_slow_period26_signal_period9_macd': 100.0,
                'macdindicator_fast_period12_slow_period26_signal_period9_signal': 90.0,
                'smaindicator_period20_sma': 49000.0,
                'smaindicator_period50_sma': 48000.0,
            },
        )

        # Process through all strategies
        signals = manager.process_tick(tick)

        # Should get signals from multiple strategies
        assert len(signals) >= 1

        # Get stats
        stats = manager.get_stats()
        assert stats['strategy_count'] == 3
