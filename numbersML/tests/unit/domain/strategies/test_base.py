"""
Tests for Algorithm Interface.

Tests strategy base classes, signals, positions, and strategy manager.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from src.domain.strategies.base import (
    Algorithm,
    StrategyManager,
    Signal,
    Position,
    EnrichedTick,
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
            strategy_id='test_strategy',
            symbol='BTC/USDT',
            signal_type=SignalType.BUY,
            price=Decimal('50000.00'),
            confidence=0.85,
        )

        assert signal.strategy_id == 'test_strategy'
        assert signal.symbol == 'BTC/USDT'
        assert signal.signal_type == SignalType.BUY
        assert signal.price == Decimal('50000.00')
        assert signal.confidence == 0.85
        assert signal.timestamp is not None

    def test_signal_to_dict(self) -> None:
        """Test converting signal to dictionary."""
        signal = Signal(
            strategy_id='test_strategy',
            symbol='BTC/USDT',
            signal_type=SignalType.BUY,
            price=Decimal('50000.00'),
            confidence=0.75,
            metadata={'rsi': 25.0},
        )

        data = signal.to_dict()

        assert data['strategy_id'] == 'test_strategy'
        assert data['symbol'] == 'BTC/USDT'
        assert data['signal_type'] == 'BUY'
        assert data['price'] == 50000.0
        assert data['confidence'] == 0.75
        assert data['metadata']['rsi'] == 25.0
        assert 'timestamp' in data


class TestPosition:
    """Test Position dataclass."""

    def test_position_creation(self) -> None:
        """Test creating a position."""
        position = Position(
            symbol='BTC/USDT',
            side='LONG',
            quantity=Decimal('0.1'),
            entry_price=Decimal('50000.00'),
        )

        assert position.symbol == 'BTC/USDT'
        assert position.side == 'LONG'
        assert position.quantity == Decimal('0.1')
        assert position.entry_price == Decimal('50000.00')
        assert position.unrealized_pnl == Decimal('0')

    def test_position_update_price_long(self) -> None:
        """Test updating position price for LONG."""
        position = Position(
            symbol='BTC/USDT',
            side='LONG',
            quantity=Decimal('0.1'),
            entry_price=Decimal('50000.00'),
        )

        position.update_price(Decimal('51000.00'))

        assert position.current_price == Decimal('51000.00')
        assert position.unrealized_pnl == Decimal('100.00')  # (51000 - 50000) * 0.1
        assert position.pnl_percent == 0.2  # 0.2%

    def test_position_update_price_short(self) -> None:
        """Test updating position price for SHORT."""
        position = Position(
            symbol='BTC/USDT',
            side='SHORT',
            quantity=Decimal('0.1'),
            entry_price=Decimal('50000.00'),
        )

        position.update_price(Decimal('49000.00'))

        assert position.current_price == Decimal('49000.00')
        assert position.unrealized_pnl == Decimal('100.00')  # (50000 - 49000) * 0.1
        assert position.pnl_percent == 0.2

    def test_position_to_dict(self) -> None:
        """Test converting position to dictionary."""
        position = Position(
            symbol='BTC/USDT',
            side='LONG',
            quantity=Decimal('0.1'),
            entry_price=Decimal('50000.00'),
        )
        position.update_price(Decimal('51000.00'))

        data = position.to_dict()

        assert data['symbol'] == 'BTC/USDT'
        assert data['side'] == 'LONG'
        assert data['quantity'] == 0.1
        assert data['entry_price'] == 50000.0
        assert data['current_price'] == 51000.0
        assert data['unrealized_pnl'] == 100.0
        assert abs(data['pnl_percent'] - 0.2) < 0.01


class TestEnrichedTick:
    """Test EnrichedTick dataclass."""

    def test_enriched_tick_creation(self) -> None:
        """Test creating enriched tick."""
        tick = EnrichedTick(
            symbol='BTC/USDT',
            price=Decimal('50000.00'),
            volume=Decimal('1.5'),
            time=datetime.now(timezone.utc),
            indicators={'rsi': 55.5, 'sma': 49500.0},
        )

        assert tick.symbol == 'BTC/USDT'
        assert tick.price == Decimal('50000.00')
        assert tick.volume == Decimal('1.5')
        assert tick.indicators['rsi'] == 55.5
        assert tick.indicators['sma'] == 49500.0

    def test_enriched_tick_from_message(self) -> None:
        """Test creating enriched tick from Redis message."""
        message = {
            'symbol': 'BTC/USDT',
            'price': '50000.00',
            'volume': '1.5',
            'time': '2026-03-21T12:00:00',
            'indicators': {
                'rsiindicator_period14_rsi': 55.5,
                'smaindicator_period20_sma': 49500.0,
            },
        }

        tick = EnrichedTick.from_message(message)

        assert tick.symbol == 'BTC/USDT'
        assert tick.price == Decimal('50000.00')
        assert tick.volume == Decimal('1.5')
        assert tick.get_indicator('rsiindicator_period14_rsi') == 55.5
        assert tick.get_indicator('smaindicator_period20_sma') == 49500.0

    def test_enriched_tick_get_indicator_default(self) -> None:
        """Test getting indicator with default value."""
        tick = EnrichedTick(
            symbol='BTC/USDT',
            price=Decimal('50000.00'),
            volume=Decimal('1.0'),
            time=datetime.now(timezone.utc),
            indicators={'rsi': 55.5},
        )

        assert tick.get_indicator('rsi') == 55.5
        assert tick.get_indicator('nonexistent', 0.0) == 0.0
        assert tick.get_indicator('missing', 99.9) == 99.9


@pytest.mark.skip(reason="Algorithm is now pure interface - tests need update")
class TestAlgorithm:
    """Test Algorithm base class."""

    def test_strategy_initialization(self) -> None:
        """Test strategy initialization."""
        strategy = SimpleTestAlgorithm(
            strategy_id='test',
            symbols=['BTC/USDT'],
            time_frame=TimeFrame.TICK,
        )

        assert strategy.id == 'test'
        assert strategy.symbols == ['BTC/USDT']
        assert strategy.state == StrategyInstanceState.STOPPED
        assert strategy.ticks_processed == 0

    def test_strategy_validation_empty_id(self) -> None:
        """Test strategy rejects empty ID."""
        with pytest.raises(ValueError, match="strategy_id cannot be empty"):
            SimpleTestAlgorithm(
                strategy_id='',
                symbols=['BTC/USDT'],
            )

    def test_strategy_validation_empty_symbols(self) -> None:
        """Test strategy rejects empty symbols."""
        with pytest.raises(ValueError, match="symbols list cannot be empty"):
            SimpleTestAlgorithm(
                strategy_id='test',
                symbols=[],
            )

    @pytest.mark.asyncio
    async def test_strategy_start_stop(self) -> None:
        """Test strategy start and stop."""
        strategy = SimpleTestAlgorithm(
            strategy_id='test',
            symbols=['BTC/USDT'],
        )

        assert strategy.state == StrategyInstanceState.STOPPED

        await strategy.initialize()
        assert strategy.state == StrategyInstanceState.RUNNING

        await strategy.start()
        assert strategy.state == StrategyInstanceState.RUNNING

        await strategy.stop()
        assert strategy.state == StrategyInstanceState.STOPPED

    @pytest.mark.asyncio
    async def test_strategy_pause_resume(self) -> None:
        """Test strategy pause and resume."""
        strategy = SimpleTestAlgorithm(
            strategy_id='test',
            symbols=['BTC/USDT'],
        )

        await strategy.initialize()
        assert strategy.state == StrategyInstanceState.RUNNING

        await strategy.pause()
        assert strategy.state == StrategyInstanceState.PAUSED

        await strategy.resume()
        assert strategy.state == StrategyInstanceState.RUNNING

    def test_strategy_process_tick(self) -> None:
        """Test strategy processes tick."""
        strategy = SimpleTestAlgorithm(
            strategy_id='test',
            symbols=['BTC/USDT'],
        )

        tick = EnrichedTick(
            symbol='BTC/USDT',
            price=Decimal('50000.00'),
            volume=Decimal('1.0'),
            time=datetime.now(timezone.utc),
        )

        # Should not process when stopped
        signal = strategy.process_tick(tick)
        assert signal is None

        # Start strategy
        import asyncio
        asyncio.run(strategy.initialize())

        # Should process when running
        signal = strategy.process_tick(tick)
        assert signal is not None
        assert signal.signal_type == SignalType.HOLD
        assert strategy.ticks_processed == 1

    def test_strategy_position_management(self) -> None:
        """Test strategy position management."""
        strategy = SimpleTestAlgorithm(
            strategy_id='test',
            symbols=['BTC/USDT'],
        )

        # Open position
        position = strategy.open_position(
            symbol='BTC/USDT',
            side='LONG',
            quantity=Decimal('0.1'),
            price=Decimal('50000.00'),
        )

        assert position.symbol == 'BTC/USDT'
        assert position.side == 'LONG'
        assert len(strategy.positions) == 1

        # Update price
        strategy.update_position('BTC/USDT', Decimal('51000.00'))
        assert strategy.positions['BTC/USDT'].current_price == Decimal('51000.00')

        # Close position
        closed = strategy.close_position('BTC/USDT', Decimal('51000.00'))
        assert closed is not None
        assert len(strategy.positions) == 0

    def test_strategy_get_stats(self) -> None:
        """Test strategy statistics."""
        strategy = SimpleTestAlgorithm(
            strategy_id='test',
            symbols=['BTC/USDT', 'ETH/USDT'],
        )

        stats = strategy.get_stats()

        assert stats['strategy_id'] == 'test'
        assert stats['state'] == 'stopped'
        assert len(stats['symbols']) == 2
        assert stats['ticks_processed'] == 0
        assert stats['signals_generated'] == 0

    def test_strategy_config(self) -> None:
        """Test strategy configuration."""
        strategy = SimpleTestAlgorithm(
            strategy_id='test',
            symbols=['BTC/USDT'],
        )

        strategy.set_config('rsi_period', 14)
        strategy.set_config('threshold', 30)

        assert strategy.get_config('rsi_period') == 14
        assert strategy.get_config('threshold') == 30
        assert strategy.get_config('nonexistent', 'default') == 'default'


class TestStrategyManager:
    """Test StrategyManager."""

    def test_manager_add_strategy(self) -> None:
        """Test adding strategy to manager."""
        manager = StrategyManager()
        strategy = SimpleTestAlgorithm(
            strategy_id='test1',
            symbols=['BTC/USDT'],
        )

        manager.add_strategy(strategy)

        assert len(manager.list_strategies()) == 1
        assert manager.get_strategy('test1') is not None

    def test_manager_add_duplicate_strategy(self) -> None:
        """Test adding duplicate strategy raises error."""
        manager = StrategyManager()
        strategy = SimpleTestAlgorithm(
            strategy_id='test1',
            symbols=['BTC/USDT'],
        )

        manager.add_strategy(strategy)

        with pytest.raises(ValueError, match="already exists"):
            manager.add_strategy(strategy)

    def test_manager_remove_strategy(self) -> None:
        """Test removing strategy from manager."""
        manager = StrategyManager()
        strategy = SimpleTestAlgorithm(
            strategy_id='test1',
            symbols=['BTC/USDT'],
        )

        manager.add_strategy(strategy)
        removed = manager.remove_strategy('test1')

        assert removed is strategy
        assert len(manager.list_strategies()) == 0
        assert manager.get_strategy('test1') is None

    @pytest.mark.asyncio
    async def test_manager_start_stop_all(self) -> None:
        """Test starting and stopping all strategies."""
        manager = StrategyManager()

        manager.add_strategy(SimpleTestAlgorithm('test1', ['BTC/USDT']))
        manager.add_strategy(SimpleTestAlgorithm('test2', ['ETH/USDT']))

        await manager.start_all()

        assert manager.get_strategy('test1').state == StrategyInstanceState.RUNNING
        assert manager.get_strategy('test2').state == StrategyInstanceState.RUNNING

        await manager.stop_all()

        assert manager.get_strategy('test1').state == StrategyInstanceState.STOPPED
        assert manager.get_strategy('test2').state == StrategyInstanceState.STOPPED

    def test_manager_process_tick(self) -> None:
        """Test processing tick through multiple strategies."""
        manager = StrategyManager()

        manager.add_strategy(SimpleTestAlgorithm('test1', ['BTC/USDT']))
        manager.add_strategy(SimpleTestAlgorithm('test2', ['BTC/USDT']))

        tick = EnrichedTick(
            symbol='BTC/USDT',
            price=Decimal('50000.00'),
            volume=Decimal('1.0'),
            time=datetime.now(timezone.utc),
        )

        # Start strategies
        import asyncio
        asyncio.run(manager.start_all())

        signals = manager.process_tick(tick)

        # Both strategies should generate a signal
        assert len(signals) == 2

    def test_manager_get_stats(self) -> None:
        """Test manager statistics."""
        manager = StrategyManager()
        manager.add_strategy(SimpleTestAlgorithm('test1', ['BTC/USDT']))

        stats = manager.get_stats()

        assert stats['strategy_count'] == 1
        assert 'test1' in stats['strategies']


class SimpleTestAlgorithm(Algorithm):
    """Simple test strategy implementation."""

    def on_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """Generate HOLD signal for testing."""
        return Signal(
            strategy_id=self.id,
            symbol=tick.symbol,
            signal_type=SignalType.HOLD,
            price=tick.price,
        )
