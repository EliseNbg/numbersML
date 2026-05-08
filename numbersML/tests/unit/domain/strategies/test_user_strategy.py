"""Unit tests for user-written (class-based) strategies."""

from typing import Any

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from src.domain.strategies.base import (
    EnrichedTick,
    Signal,
    SignalType,
    Strategy,
    StrategyState,
)


class MockRSIStrategy(Strategy):
    """Test strategy that simulates RSI-based signals with persistent state."""
    
    def __init__(self, strategy_id: str, symbols: list[str], **kwargs: Any):
        super().__init__(strategy_id, symbols, **kwargs)
        self.rsi_values_seen: list[float] = []
        self.tick_count = 0
        self.last_signal_type: SignalType | None = None
        self.last_rsi = 0.0
        self.position_open = False

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        self.tick_count += 1
        rsi = tick.get_indicator("rsi", 50.0)
        self.rsi_values_seen.append(rsi)
        
        threshold_oversold = self.get_config("oversold_threshold", 30)
        threshold_overbought = self.get_config("overbought_threshold", 70)
        
        if rsi < threshold_oversold:
            signal = Signal(
                strategy_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.BUY,
                price=tick.price,
                confidence=1.0 - (rsi / 100.0),
                metadata={"rsi": rsi},
            )
            self.last_signal_type = SignalType.BUY
            return signal
        
        if rsi > threshold_overbought:
            signal = Signal(
                strategy_id=self.id,
                symbol=tick.symbol,
                signal_type=SignalType.SELL,
                price=tick.price,
                confidence=rsi / 100.0,
                metadata={"rsi": rsi},
            )
            self.last_signal_type = SignalType.SELL
            return signal
        
        return None

    def get_stats(self) -> dict[str, Any]:
        """Override to include custom state in stats."""
        stats = super().get_stats()
        stats.update({
            "tick_count": self.tick_count,
            "rsi_values_seen": self.rsi_values_seen,
            "last_signal_type": self.last_signal_type,
            "last_rsi": self.last_rsi,
            "position_open": self.position_open,
        })
        return stats


class TestUserStrategyState:
    """Test persistent state between ticks."""

    def test_state_persists_between_ticks(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING

        # Create ticks with different RSI values
        for i, rsi in enumerate([25.0, 28.0, 31.0, 75.0, 80.0]):
            tick = EnrichedTick(
                symbol="BTC/USDC",
                price=Decimal("50000.0"),
                volume=Decimal("1.0"),
                time=datetime.now(UTC),
                indicators={"rsi": rsi},
            )
            strategy.process_tick(tick)

        assert strategy.tick_count == 5
        assert len(strategy.rsi_values_seen) == 5
        assert strategy.rsi_values_seen == [25.0, 28.0, 31.0, 75.0, 80.0]

    def test_instance_variables_persist(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING

        # Process a tick
        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("50000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 25.0},
        )
        strategy.process_tick(tick)

        assert strategy.tick_count == 1
        assert strategy.last_signal_type == SignalType.BUY

        # Process another tick
        tick2 = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("51000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 80.0},
        )
        strategy.process_tick(tick2)

        assert strategy.tick_count == 2
        assert strategy.last_signal_type == SignalType.SELL  # type: ignore[comparison-overlap]


class TestUserStrategyIndicators:
    """Test indicator access via EnrichedTick."""

    def test_get_indicator_from_tick(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING

        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("50000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={
                "rsiindicator_period14_rsi": 45.0,
                "smaindicator_period20_sma": 49500.0,
            },
        )

        # Test convenience method
        rsi = strategy.get_indicator(tick, "rsiindicator_period14_rsi")
        assert rsi == 45.0

        sma = strategy.get_indicator(tick, "smaindicator_period20_sma")
        assert sma == 49500.0

        # Test default value
        missing = strategy.get_indicator(tick, "missing_indicator", 99.0)
        assert missing == 99.0

    def test_indicator_access_in_on_tick(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING

        # Set custom threshold
        strategy.set_config("oversold_threshold", 40)

        # RSI 35 should trigger BUY (35 < 40)
        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("50000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 35.0},
        )

        signal = strategy.process_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY


class TestUserStrategyConfig:
    """Test config loading and access."""

    def test_config_loaded_into_strategy(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])

        # Simulate config loading (done by StrategyLifecycleService)
        strategy._config = {
            "oversold_threshold": 25,
            "overbought_threshold": 75,
            "rsi_indicator_name": "custom_rsi",
        }

        assert strategy.get_config("oversold_threshold") == 25
        assert strategy.get_config("overbought_threshold") == 75
        assert strategy.get_config("missing_key", "default") == "default"

    def test_config_affects_signal_generation(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING

        # Set config
        strategy._config = {
            "oversold_threshold": 20,
            "overbought_threshold": 80,
        }

        # RSI 25 should NOT trigger with threshold 20
        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("50000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 25.0},
        )

        signal = strategy.process_tick(tick)
        assert signal is None  # 25 > 20, no signal

        # RSI 15 should trigger
        tick.indicators["rsi"] = 15.0
        signal = strategy.process_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.BUY


class TestUserStrategySignals:
    """Test BUY/SELL signal generation."""

    def test_buy_signal_generation(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING
        strategy._config = {"oversold_threshold": 30, "overbought_threshold": 70}

        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("48000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 25.0},
        )

        signal = strategy.process_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDC"
        assert signal.price == Decimal("48000.0")
        assert signal.confidence > 0.0
        assert "rsi" in signal.metadata

    def test_sell_signal_generation(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING
        strategy._config = {"oversold_threshold": 30, "overbought_threshold": 70}

        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("52000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 75.0},
        )

        signal = strategy.process_tick(tick)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.symbol == "BTC/USDC"
        assert signal.price == Decimal("52000.0")

    def test_no_signal_when_neutral(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING
        strategy._config = {"oversold_threshold": 30, "overbought_threshold": 70}

        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("50000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 50.0},  # Neutral
        )

        signal = strategy.process_tick(tick)
        assert signal is None


class TestUserStrategyStats:
    """Test strategy statistics with custom state."""

    def test_stats_include_custom_state(self):
        strategy = MockRSIStrategy(str(uuid4()), ["BTC/USDC"])
        strategy._state = StrategyState.RUNNING

        tick = EnrichedTick(
            symbol="BTC/USDC",
            price=Decimal("50000.0"),
            volume=Decimal("1.0"),
            time=datetime.now(UTC),
            indicators={"rsi": 25.0},
        )
        strategy.process_tick(tick)

        stats = strategy.get_stats()

        assert "tick_count" in stats
        assert stats["tick_count"] == 1
        assert "last_rsi" in stats
        assert "position_open" in stats
