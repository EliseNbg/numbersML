"""
Sample Trading Algorithms.

Implements example trading algorithms:
- RSI Oversold/Overbought
- MACD Crossover
- SMA Golden Cross / Death Cross
- Bollinger Bands Mean Reversion
"""

import logging
from typing import Optional

from src.domain.algorithms.base import (
    Algorithm,
    EnrichedTick,
    Signal,
    SignalType,
)

logger = logging.getLogger(__name__)


class RSIAlgorithm(Algorithm):
    """
    RSI Oversold/Overbought Algorithm.

    Logic:
        - BUY when RSI < oversold_threshold (typically 30)
        - SELL when RSI > overbought_threshold (typically 70)

    Parameters:
        rsi_period: RSI calculation period (default: 14)
        oversold_threshold: RSI level for buy signal (default: 30)
        overbought_threshold: RSI level for sell signal (default: 70)

    Example:
        >>> algorithm = RSIAlgorithm(
        ...     algorithm_id='rsi_v1',
        ...     symbols=['BTC/USDT'],
        ...     rsi_period=14,
        ...     oversold_threshold=30,
        ...     overbought_threshold=70,
        ... )
    """

    def __init__(
        self,
        algorithm_id: str,
        symbols: list[str],
        rsi_period: int = 14,
        oversold_threshold: float = 30.0,
        overbought_threshold: float = 70.0,
        confidence: float = 0.75,
    ) -> None:
        """
        Initialize RSI algorithm.

        Args:
            algorithm_id: Unique algorithm identifier
            symbols: List of symbols to trade
            rsi_period: RSI calculation period
            oversold_threshold: RSI level for buy signals
            overbought_threshold: RSI level for sell signals
            confidence: Signal confidence (0.0-1.0)
        """
        super().__init__(algorithm_id, symbols)

        self.rsi_period = rsi_period
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold
        self.confidence = confidence

        # State tracking
        self._last_rsi: dict[str, float] = {}

        logger.info(
            f"RSIAlgorithm initialized: period={rsi_period}, "
            f"oversold={oversold_threshold}, overbought={overbought_threshold}"
        )

    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """
        Process tick and generate RSI signal.

        Args:
            tick: Enriched tick with RSI indicator

        Returns:
            Signal if RSI crosses threshold, None otherwise
        """
        # Get RSI from indicators
        rsi_key = f"rsiindicator_period{self.rsi_period}_rsi"
        rsi = tick.get_indicator(rsi_key)

        if rsi is None or rsi == 0:
            return None

        # Track last RSI
        self._last_rsi[tick.symbol] = rsi

        # Check for oversold (BUY signal)
        if rsi < self.oversold_threshold:
            logger.info(
                f"RSI oversold: {rsi:.2f} < {self.oversold_threshold} " f"for {tick.symbol}"
            )
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "rsi": rsi,
                    "threshold": self.oversold_threshold,
                    "condition": "oversold",
                },
            )

        # Check for overbought (SELL signal)
        if rsi > self.overbought_threshold:
            logger.info(
                f"RSI overbought: {rsi:.2f} > {self.overbought_threshold} " f"for {tick.symbol}"
            )
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "rsi": rsi,
                    "threshold": self.overbought_threshold,
                    "condition": "overbought",
                },
            )

        return None


class MACDAlgorithm(Algorithm):
    """
    MACD Crossover Algorithm.

    Logic:
        - BUY when MACD line crosses above signal line (bullish)
        - SELL when MACD line crosses below signal line (bearish)

    Parameters:
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal line period (default: 9)

    Example:
        >>> algorithm = MACDAlgorithm(
        ...     algorithm_id='macd_v1',
        ...     symbols=['BTC/USDT'],
        ...     fast_period=12,
        ...     slow_period=26,
        ...     signal_period=9,
        ... )
    """

    def __init__(
        self,
        algorithm_id: str,
        symbols: list[str],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        confidence: float = 0.7,
    ) -> None:
        """
        Initialize MACD algorithm.

        Args:
            algorithm_id: Unique algorithm identifier
            symbols: List of symbols to trade
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period
            confidence: Signal confidence (0.0-1.0)
        """
        super().__init__(algorithm_id, symbols)

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.confidence = confidence

        # State tracking (previous MACD values)
        self._prev_macd: dict[str, float] = {}
        self._prev_signal: dict[str, float] = {}

        logger.info(
            f"MACDAlgorithm initialized: fast={fast_period}, "
            f"slow={slow_period}, signal={signal_period}"
        )

    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """
        Process tick and generate MACD crossover signal.

        Args:
            tick: Enriched tick with MACD indicators

        Returns:
            Signal if crossover detected, None otherwise
        """
        # Get MACD values from indicators
        macd_key = f"macdindicator_fast_period{self.fast_period}_slow_period{self.slow_period}_signal_period{self.signal_period}_macd"
        signal_key = f"macdindicator_fast_period{self.fast_period}_slow_period{self.slow_period}_signal_period{self.signal_period}_signal"

        macd = tick.get_indicator(macd_key)
        signal_line = tick.get_indicator(signal_key)

        if macd is None or signal_line is None:
            return None

        # Get previous values
        prev_macd = self._prev_macd.get(tick.symbol)
        prev_signal = self._prev_signal.get(tick.symbol)

        # Update previous values
        self._prev_macd[tick.symbol] = macd
        self._prev_signal[tick.symbol] = signal_line

        # Need previous values to detect crossover
        if prev_macd is None or prev_signal is None:
            return None

        # Detect bullish crossover (MACD crosses above signal)
        if prev_macd <= prev_signal and macd > signal_line:
            logger.info(
                f"MACD bullish crossover: MACD={macd:.2f} > Signal={signal_line:.2f} "
                f"for {tick.symbol}"
            )
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "macd": macd,
                    "signal": signal_line,
                    "prev_macd": prev_macd,
                    "prev_signal": prev_signal,
                    "condition": "bullish_crossover",
                },
            )

        # Detect bearish crossover (MACD crosses below signal)
        if prev_macd >= prev_signal and macd < signal_line:
            logger.info(
                f"MACD bearish crossover: MACD={macd:.2f} < Signal={signal_line:.2f} "
                f"for {tick.symbol}"
            )
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "macd": macd,
                    "signal": signal_line,
                    "prev_macd": prev_macd,
                    "prev_signal": prev_signal,
                    "condition": "bearish_crossover",
                },
            )

        return None


class SMACrossoverAlgorithm(Algorithm):
    """
    Simple Moving Average Crossover Algorithm.

    Logic:
        - BUY when fast SMA crosses above slow SMA (golden cross)
        - SELL when fast SMA crosses below slow SMA (death cross)

    Parameters:
        fast_period: Fast SMA period (default: 20)
        slow_period: Slow SMA period (default: 50)

    Example:
        >>> algorithm = SMACrossoverAlgorithm(
        ...     algorithm_id='sma_cross_v1',
        ...     symbols=['BTC/USDT'],
        ...     fast_period=20,
        ...     slow_period=50,
        ... )
    """

    def __init__(
        self,
        algorithm_id: str,
        symbols: list[str],
        fast_period: int = 20,
        slow_period: int = 50,
        confidence: float = 0.65,
    ) -> None:
        """
        Initialize SMA crossover algorithm.

        Args:
            algorithm_id: Unique algorithm identifier
            symbols: List of symbols to trade
            fast_period: Fast SMA period
            slow_period: Slow SMA period
            confidence: Signal confidence (0.0-1.0)
        """
        super().__init__(algorithm_id, symbols)

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.confidence = confidence

        # State tracking
        self._prev_fast_sma: dict[str, float] = {}
        self._prev_slow_sma: dict[str, float] = {}

        logger.info(f"SMACrossoverAlgorithm initialized: fast={fast_period}, slow={slow_period}")

    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """
        Process tick and generate SMA crossover signal.

        Args:
            tick: Enriched tick with SMA indicators

        Returns:
            Signal if crossover detected, None otherwise
        """
        # Get SMA values
        fast_key = f"smaindicator_period{self.fast_period}_sma"
        slow_key = f"smaindicator_period{self.slow_period}_sma"

        fast_sma = tick.get_indicator(fast_key)
        slow_sma = tick.get_indicator(slow_key)

        if fast_sma is None or slow_sma is None:
            return None

        # Get previous values
        prev_fast = self._prev_fast_sma.get(tick.symbol)
        prev_slow = self._prev_slow_sma.get(tick.symbol)

        # Update previous values
        self._prev_fast_sma[tick.symbol] = fast_sma
        self._prev_slow_sma[tick.symbol] = slow_sma

        # Need previous values to detect crossover
        if prev_fast is None or prev_slow is None:
            return None

        # Detect golden cross (fast crosses above slow)
        if prev_fast <= prev_slow and fast_sma > slow_sma:
            logger.info(
                f"Golden Cross: SMA{self.fast_period}={fast_sma:.2f} > "
                f"SMA{self.slow_period}={slow_sma:.2f} for {tick.symbol}"
            )
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "fast_sma": fast_sma,
                    "slow_sma": slow_sma,
                    "condition": "golden_cross",
                },
            )

        # Detect death cross (fast crosses below slow)
        if prev_fast >= prev_slow and fast_sma < slow_sma:
            logger.info(
                f"Death Cross: SMA{self.fast_period}={fast_sma:.2f} < "
                f"SMA{self.slow_period}={slow_sma:.2f} for {tick.symbol}"
            )
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "fast_sma": fast_sma,
                    "slow_sma": slow_sma,
                    "condition": "death_cross",
                },
            )

        return None


class BollingerBandsAlgorithm(Algorithm):
    """
    Bollinger Bands Mean Reversion Algorithm.

    Logic:
        - BUY when price touches lower band (oversold)
        - SELL when price touches upper band (overbought)

    Parameters:
        period: Bollinger Bands period (default: 20)
        std_dev: Standard deviation multiplier (default: 2.0)

    Example:
        >>> algorithm = BollingerBandsAlgorithm(
        ...     algorithm_id='bb_v1',
        ...     symbols=['BTC/USDT'],
        ...     period=20,
        ...     std_dev=2.0,
        ... )
    """

    def __init__(
        self,
        algorithm_id: str,
        symbols: list[str],
        period: int = 20,
        std_dev: float = 2.0,
        confidence: float = 0.6,
    ) -> None:
        """
        Initialize Bollinger Bands algorithm.

        Args:
            algorithm_id: Unique algorithm identifier
            symbols: List of symbols to trade
            period: Bollinger Bands period
            std_dev: Standard deviation multiplier
            confidence: Signal confidence (0.0-1.0)
        """
        super().__init__(algorithm_id, symbols)

        self.period = period
        self.std_dev = std_dev
        self.confidence = confidence

        logger.info(f"BollingerBandsAlgorithm initialized: period={period}, std_dev={std_dev}")

    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """
        Process tick and generate Bollinger Bands signal.

        Args:
            tick: Enriched tick with Bollinger Bands indicators

        Returns:
            Signal if price touches bands, None otherwise
        """
        # Get Bollinger Bands values
        bb_prefix = f"bbindicator_period{self.period}_std_dev{self.std_dev}"
        upper_key = f"{bb_prefix}_upper"
        middle_key = f"{bb_prefix}_middle"
        lower_key = f"{bb_prefix}_lower"

        upper = tick.get_indicator(upper_key)
        middle = tick.get_indicator(middle_key)
        lower = tick.get_indicator(lower_key)

        if upper is None or lower is None or middle is None:
            return None

        price = float(tick.price)

        # Check if price touches lower band (BUY signal)
        if price <= lower * 1.001:  # Within 0.1% of lower band
            logger.info(f"Price at lower BB: {price:.2f} <= {lower:.2f} for {tick.symbol}")
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "price": price,
                    "upper": upper,
                    "middle": middle,
                    "lower": lower,
                    "condition": "touching_lower_band",
                },
            )

        # Check if price touches upper band (SELL signal)
        if price >= upper * 0.999:  # Within 0.1% of upper band
            logger.info(f"Price at upper BB: {price:.2f} >= {upper:.2f} for {tick.symbol}")
            return Signal(
                algorithm_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=self.confidence,
                metadata={
                    "price": price,
                    "upper": upper,
                    "middle": middle,
                    "lower": lower,
                    "condition": "touching_upper_band",
                },
            )

        return None


class MultiIndicatorAlgorithm(Algorithm):
    """
    Multi-Indicator Composite Algorithm.

    Combines multiple indicators for stronger signals:
    - RSI for momentum
    - MACD for trend
    - SMA for direction

    Logic:
        - BUY when RSI < 30 AND MACD bullish AND price > SMA
        - SELL when RSI > 70 AND MACD bearish AND price < SMA

    Example:
        >>> algorithm = MultiIndicatorAlgorithm(
        ...     algorithm_id='multi_v1',
        ...     symbols=['BTC/USDT'],
        ...     require_all_signals=True,
        ... )
    """

    def __init__(
        self,
        algorithm_id: str,
        symbols: list[str],
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        sma_period: int = 200,
        require_all_signals: bool = False,
        confidence: float = 0.8,
    ) -> None:
        """
        Initialize multi-indicator algorithm.

        Args:
            algorithm_id: Unique algorithm identifier
            symbols: List of symbols to trade
            rsi_period: RSI calculation period
            rsi_oversold: RSI oversold threshold
            rsi_overbought: RSI overbought threshold
            macd_fast: MACD fast period
            macd_slow: MACD slow period
            macd_signal: MACD signal period
            sma_period: SMA period for trend direction
            require_all_signals: Require all indicators to agree
            confidence: Signal confidence (0.0-1.0)
        """
        super().__init__(algorithm_id, symbols)

        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal_param = macd_signal
        self.sma_period = sma_period
        self.require_all_signals = require_all_signals
        self.confidence = confidence

        # State for MACD
        self._prev_macd: dict[str, float] = {}
        self._prev_signal: dict[str, float] = {}

        logger.info(
            f"MultiIndicatorAlgorithm initialized: "
            f"RSI({rsi_period}), MACD({macd_fast},{macd_slow},{macd_signal}), SMA({sma_period})"
        )

    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """
        Process tick and generate composite signal.

        Args:
            tick: Enriched tick with multiple indicators

        Returns:
            Signal if conditions met, None otherwise
        """
        symbol = tick.symbol
        price = float(tick.price)

        # Get RSI
        rsi_key = f"rsiindicator_period{self.rsi_period}_rsi"
        rsi = tick.get_indicator(rsi_key)

        # Get MACD
        macd_key = (
            f"macdindicator_fast_period{self.macd_fast}_"
            f"slow_period{self.macd_slow}_signal_period{self.macd_signal_param}_macd"
        )
        signal_key = (
            f"macdindicator_fast_period{self.macd_fast}_"
            f"slow_period{self.macd_slow}_signal_period{self.macd_signal_param}_signal"
        )
        macd = tick.get_indicator(macd_key)
        macd_signal = tick.get_indicator(signal_key)

        # Get SMA
        sma_key = f"smaindicator_period{self.sma_period}_sma"
        sma = tick.get_indicator(sma_key)

        if rsi is None or macd is None or macd_signal is None or sma is None:
            return None

        # Track MACD state
        prev_macd = self._prev_macd.get(symbol)
        prev_signal = self._prev_signal.get(symbol)
        self._prev_macd[symbol] = macd
        self._prev_signal[symbol] = macd_signal

        # Calculate signals
        rsi_buy = rsi < self.rsi_oversold
        rsi_sell = rsi > self.rsi_overbought

        macd_buy = prev_macd is not None and prev_macd <= prev_signal and macd > macd_signal
        macd_sell = prev_macd is not None and prev_macd >= prev_signal and macd < macd_signal

        trend_up = price > sma
        trend_down = price < sma

        # Count bullish and bearish signals
        bullish_count = sum([rsi_buy, macd_buy, trend_up])
        bearish_count = sum([rsi_sell, macd_sell, trend_down])

        # Generate signal based on agreement
        if self.require_all_signals:
            # All indicators must agree
            if bullish_count == 3:
                return self._create_signal(tick, "strong_buy", rsi, macd, sma)
            elif bearish_count == 3:
                return self._create_signal(tick, "strong_sell", rsi, macd, sma)
        else:
            # Majority vote (at least 2 out of 3)
            if bullish_count >= 2:
                return self._create_signal(tick, "buy", rsi, macd, sma, bullish_count / 3)
            elif bearish_count >= 2:
                return self._create_signal(tick, "sell", rsi, macd, sma, bearish_count / 3)

        return None

    def _create_signal(
        self,
        tick: EnrichedTick,
        condition: str,
        rsi: float,
        macd: float,
        sma: float,
        confidence: Optional[float] = None,
    ) -> Signal:
        """Create signal with metadata."""
        signal_type = SignalType.BUY if "buy" in condition else SignalType.SELL

        return Signal(
            algorithm_id=self.id,
            symbol=tick.symbol,
            signal_type=signal_type,
            price=tick.price,
            confidence=confidence or self.confidence,
            metadata={
                "rsi": rsi,
                "macd": macd,
                "sma": sma,
                "condition": condition,
            },
        )
