"""
StrategyInstance domain entity.

Represents a deployed algorithm with specific configuration.
Links Algorithm (logic) with ConfigurationSet (parameters).
Manages lifecycle state, positions, signals, and runtime statistics.

Architecture: Domain Layer (pure Python, no external dependencies)
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.models.base import Entity
from src.domain.strategies.base import EnrichedTick, Position, Signal

if TYPE_CHECKING:
    from src.domain.strategies.base import Algorithm

logger = logging.getLogger(__name__)


class StrategyInstanceState(StrEnum):
    """Strategy instance lifecycle states."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


VALID_TRANSITIONS: dict[StrategyInstanceState, set[StrategyInstanceState]] = {
    StrategyInstanceState.STOPPED: {StrategyInstanceState.RUNNING},
    StrategyInstanceState.RUNNING: {
        StrategyInstanceState.PAUSED,
        StrategyInstanceState.STOPPED,
        StrategyInstanceState.ERROR,
    },
    StrategyInstanceState.PAUSED: {
        StrategyInstanceState.RUNNING,
        StrategyInstanceState.STOPPED,
    },
    StrategyInstanceState.ERROR: {StrategyInstanceState.STOPPED},
}


@dataclass(frozen=True)
class RuntimeStats:
    """Immutable runtime statistics for a StrategyInstance.

    Tracks PnL, trades, and uptime for monitoring.
    """

    pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    uptime_seconds: float = 0.0
    last_tick_at: datetime | None = None
    last_signal_at: datetime | None = None
    last_error: str | None = None

    @property
    def win_rate(self) -> float:
        """Calculate win rate as percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pnl": self.pnl,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "uptime_seconds": self.uptime_seconds,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_signal_at": self.last_signal_at.isoformat() if self.last_signal_at else None,
            "last_error": self.last_error,
        }


class StrategyInstance(Entity):
    """Domain entity for strategy instances.

    Links an Algorithm (logic) with a ConfigurationSet (parameters).
    Manages lifecycle state and tracks runtime statistics.

    Lifecycle:
        Created → Stopped → Running → Paused → Stopped

    Example:
        >>> instance = StrategyInstance(
        ...     strategy=RSIAlgorithm(...),
        ...     config_set_id=uuid4(),
        ... )
        >>> instance.can_start()
        True
        >>> instance.start()
        >>> instance.status
        <StrategyInstanceState.RUNNING: 'running'>
    """

    def __init__(
        self,
        strategy_id: UUID,
        config_set_id: UUID,
        id: UUID | None = None,
        status: StrategyInstanceState = StrategyInstanceState.STOPPED,
        runtime_stats: RuntimeStats | None = None,
        started_at: datetime | None = None,
        stopped_at: datetime | None = None,
    ) -> None:
        """Initialize StrategyInstance.

        Args:
            strategy_id: UUID of the Algorithm
            config_set_id: UUID of the ConfigurationSet
            id: UUID (auto-generated if None)
            status: Initial status (default: STOPPED)
            runtime_stats: Initial runtime stats
            started_at: When instance was started
            stopped_at: When instance was stopped

        Raises:
            ValueError: If strategy_id or config_set_id is None
        """
        super().__init__(id or uuid4())

        if not strategy_id:
            raise ValueError("strategy_id cannot be None")
        if not config_set_id:
            raise ValueError("config_set_id cannot be None")

        self._strategy_id = strategy_id
        self._config_set_id = config_set_id
        self._status = status
        self._runtime_stats = runtime_stats or RuntimeStats()
        self._started_at = started_at
        self._stopped_at = stopped_at
        self.created_at = datetime.now(UTC)
        self.updated_at = self.created_at

        # State from Strategy (now managed here)
        self._positions: dict[str, Position] = {}
        self._signals: list[Signal] = []
        self._ticks_processed: int = 0
        self._errors: int = 0
        self._config: dict[str, Any] = {}
        self._strategy: Optional[Algorithm] = None

    @property
    def strategy_id(self) -> UUID:
        """Get strategy ID."""
        return self._strategy_id

    @property
    def config_set_id(self) -> UUID:
        """Get configuration set ID."""
        return self._config_set_id

    @property
    def strategy(self) -> "Optional[Algorithm]":
        """Get algorithm object (None if loaded from DB without strategy)."""
        return self._strategy

    @property
    def symbols(self) -> list[str]:
        """Get symbols list."""
        return self._strategy.symbols.copy()

    @property
    def status(self) -> StrategyInstanceState:
        """Get current status."""
        return self._status

    @property
    def runtime_stats(self) -> RuntimeStats:
        """Get runtime statistics (defensive copy not needed - frozen)."""
        return self._runtime_stats

    @property
    def positions(self) -> dict[str, Position]:
        """Get current positions."""
        return self._positions.copy()

    @property
    def ticks_processed(self) -> int:
        """Get number of ticks processed."""
        return self._ticks_processed

    @property
    def errors(self) -> int:
        """Get error count."""
        return self._errors

    @property
    def started_at(self) -> datetime | None:
        """Get start timestamp."""
        return self._started_at

    @property
    def stopped_at(self) -> datetime | None:
        """Get stop timestamp."""
        return self._stopped_at

    def can_start(self) -> bool:
        """Check if instance can transition to RUNNING (only from STOPPED)."""
        return self._status == StrategyInstanceState.STOPPED

    def can_stop(self) -> bool:
        """Check if instance can transition to STOPPED (from RUNNING or PAUSED)."""
        return self._status in (
            StrategyInstanceState.RUNNING,
            StrategyInstanceState.PAUSED,
        )

    def can_pause(self) -> bool:
        """Check if instance can transition to PAUSED (only from RUNNING)."""
        return self._status == StrategyInstanceState.RUNNING

    def start(self) -> None:
        """Start the instance (transition to RUNNING).

        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_start():
            raise ValueError(f"Cannot start from state: {self._status.value}")

        self._status = StrategyInstanceState.RUNNING
        self._started_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def stop(self) -> None:
        """Stop the instance (transition to STOPPED).

        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_stop():
            raise ValueError(f"Cannot stop from state: {self._status.value}")

        self._status = StrategyInstanceState.STOPPED
        self._stopped_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def pause(self) -> None:
        """Pause the instance (transition to PAUSED).

        Raises:
            ValueError: If transition is not valid
        """
        if not self.can_pause():
            raise ValueError(f"Cannot pause from state: {self._status.value}")

        self._status = StrategyInstanceState.PAUSED
        self.updated_at = datetime.now(UTC)

    def resume(self) -> None:
        """Resume from paused state (transition to RUNNING).

        Raises:
            ValueError: If not currently paused
        """
        if self._status != StrategyInstanceState.PAUSED:
            raise ValueError(f"Cannot resume from state: {self._status.value}")

        self._status = StrategyInstanceState.RUNNING
        self.updated_at = datetime.now(UTC)

    def record_error(self, error: str) -> None:
        """Record an error and transition to ERROR state.

        Args:
            error: Error message
        """
        self._status = StrategyInstanceState.ERROR
        self._runtime_stats = RuntimeStats(
            pnl=self._runtime_stats.pnl,
            total_trades=self._runtime_stats.total_trades,
            winning_trades=self._runtime_stats.winning_trades,
            losing_trades=self._runtime_stats.losing_trades,
            uptime_seconds=self._runtime_stats.uptime_seconds,
            last_tick_at=self._runtime_stats.last_tick_at,
            last_signal_at=self._runtime_stats.last_signal_at,
            last_error=error,
        )
        self.updated_at = datetime.now(UTC)

    def update_stats(self, **kwargs: Any) -> None:
        """Update runtime statistics.

        Args:
            **kwargs: Fields to update (pnl, total_trades, etc.)
        """
        self._runtime_stats = RuntimeStats(
            pnl=kwargs.get("pnl", self._runtime_stats.pnl),
            total_trades=kwargs.get("total_trades", self._runtime_stats.total_trades),
            winning_trades=kwargs.get("winning_trades", self._runtime_stats.winning_trades),
            losing_trades=kwargs.get("losing_trades", self._runtime_stats.losing_trades),
            uptime_seconds=kwargs.get("uptime_seconds", self._runtime_stats.uptime_seconds),
            last_tick_at=kwargs.get("last_tick_at", self._runtime_stats.last_tick_at),
            last_signal_at=kwargs.get("last_signal_at", self._runtime_stats.last_signal_at),
            last_error=kwargs.get("last_error", self._runtime_stats.last_error),
        )
        self.updated_at = datetime.now(UTC)

    def process_tick(self, tick: EnrichedTick) -> Optional[Signal]:
        """Process tick using strategy logic, handle state/error tracking.

        Args:
            tick: Enriched tick data

        Returns:
            Signal if generated, None otherwise
        """
        if self._status != StrategyInstanceState.RUNNING:
            return None

        if not self._strategy:
            logger.error(f"No strategy object set for instance {self.id}")
            return None

        if tick.symbol not in self._strategy.symbols:
            return None

        try:
            self._ticks_processed += 1
            signal = self._strategy.on_tick(tick)

            if signal:
                self._signals.append(signal)
                logger.info(
                    f"Signal generated: {signal.signal_type.value} "
                    f"{signal.symbol} @ {signal.price}"
                )

            return signal

        except Exception as e:
            logger.error(f"Error processing tick in {self._strategy_id}: {e}")
            self._errors += 1
            return None

    def update_position(self, symbol: str, price: Decimal) -> None:
        """Update position with current price.

        Args:
            symbol: Trading pair symbol
            price: Current price
        """
        if symbol in self._positions:
            self._positions[symbol].update_price(price)

    def open_position(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
    ) -> Position:
        """Open new position.

        Args:
            symbol: Trading pair
            side: LONG or SHORT
            quantity: Position size
            price: Entry price

        Returns:
            New position
        """
        position = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=price,
            current_price=price,
        )
        self._positions[symbol] = position
        logger.info(f"Opened {side} position: {quantity} {symbol} @ {price}")
        return position

    def close_position(self, symbol: str, price: Decimal) -> Optional[Position]:
        """Close existing position.

        Args:
            symbol: Trading pair
            price: Close price

        Returns:
            Closed position if existed, None otherwise
        """
        if symbol not in self._positions:
            return None

        position = self._positions.pop(symbol)
        position.update_price(price)

        logger.info(
            f"Closed position: {position.side} {symbol} "
            f"PnL: {position.unrealized_pnl} ({position.pnl_percent:.2f}%)"
        )

        return position

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self._config[key] = value

    def get_stats(self) -> dict[str, Any]:
        """Get strategy statistics.

        Returns:
            Dictionary with strategy statistics
        """
        active_positions = len([p for p in self._positions.values() if p.unrealized_pnl != 0])
        total_pnl = sum(p.unrealized_pnl for p in self._positions.values())

        return {
            "strategy_id": str(self._strategy_id),
            "status": self._status.value,
            "symbols": self._strategy.symbols,
            "ticks_processed": self._ticks_processed,
            "signals_generated": len(self._signals),
            "active_positions": active_positions,
            "total_unrealized_pnl": float(total_pnl),
            "errors": self._errors,
            "runtime_stats": self._runtime_stats.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "id": str(self.id),
            "strategy_id": str(self._strategy_id),
            "config_set_id": str(self._config_set_id),
            "status": self._status.value,
            "runtime_stats": self._runtime_stats.to_dict(),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
