"""Signal aggregator for recent signal history and statistics.

In-memory cache of recent signals for fast GUI access and analytics.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.domain.strategies.signal import TradeSignal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalStats:
    """Statistics for a strategy's signals.

    Attributes:
        total_signals: Total number of signals
        buy_count: Number of BUY signals
        sell_count: Number of SELL signals
        executed_count: Number of executed signals
        rejected_count: Number of rejected signals
        failed_count: Number of failed signals
        pending_count: Number of pending signals
        avg_quantity: Average signal quantity
    """

    total_signals: int = 0
    buy_count: int = 0
    sell_count: int = 0
    executed_count: int = 0
    rejected_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    avg_quantity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_signals": self.total_signals,
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "executed_count": self.executed_count,
            "rejected_count": self.rejected_count,
            "failed_count": self.failed_count,
            "pending_count": self.pending_count,
            "avg_quantity": round(self.avg_quantity, 6),
        }


class SignalAggregator:
    """In-memory cache of recent signals for fast GUI access.

    Attributes:
        max_history: Maximum signals stored per strategy
    """

    MAX_HISTORY = 500  # per strategy

    def __init__(self, max_history: int = MAX_HISTORY) -> None:
        """Initialize signal aggregator.

        Args:
            max_history: Maximum signals stored per strategy
        """
        self._history: dict[UUID, deque[TradeSignal]] = {}
        self._global_history: deque[TradeSignal] = deque(maxlen=max_history * 10)
        self._lock = threading.Lock()
        self._max_history = max_history

    def add_signal(self, signal: TradeSignal) -> None:
        """Add signal to history.

        Args:
            signal: TradeSignal to add
        """
        with self._lock:
            strategy_id = signal.strategy_id
            if strategy_id not in self._history:
                self._history[strategy_id] = deque(maxlen=self._max_history)

            self._history[strategy_id].append(signal)
            self._global_history.append(signal)

    def get_recent(
        self,
        strategy_id: UUID | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[TradeSignal]:
        """Get recent signals with optional filters.

        Args:
            strategy_id: Filter by strategy
            symbol: Filter by symbol
            limit: Maximum signals to return

        Returns:
            List of recent signals
        """
        with self._lock:
            if strategy_id is not None:
                history = list(self._history.get(strategy_id, []))
            else:
                history = list(self._global_history)

            if symbol:
                history = [s for s in history if s.symbol == symbol]

            return history[-limit:]

    def get_stats(self, strategy_id: UUID) -> SignalStats:
        """Get signal statistics for a strategy.

        Args:
            strategy_id: Strategy UUID

        Returns:
            SignalStats for the strategy
        """
        with self._lock:
            signals = list(self._history.get(strategy_id, []))

        if not signals:
            return SignalStats()

        buy_count = sum(1 for s in signals if s.side == "BUY")
        sell_count = sum(1 for s in signals if s.side == "SELL")
        executed_count = sum(1 for s in signals if s.status.value == "EXECUTED")
        rejected_count = sum(1 for s in signals if s.status.value == "REJECTED")
        failed_count = sum(1 for s in signals if s.status.value == "FAILED")
        pending_count = sum(1 for s in signals if s.status.value == "PENDING")
        avg_quantity = float(sum(s.quantity for s in signals)) / len(signals)

        return SignalStats(
            total_signals=len(signals),
            buy_count=buy_count,
            sell_count=sell_count,
            executed_count=executed_count,
            rejected_count=rejected_count,
            failed_count=failed_count,
            pending_count=pending_count,
            avg_quantity=avg_quantity,
        )

    def get_all_strategy_ids(self) -> list[UUID]:
        """Get all strategy IDs that have signals.

        Returns:
            List of strategy UUIDs
        """
        with self._lock:
            return list(self._history.keys())

    def clear(self, strategy_id: UUID | None = None) -> None:
        """Clear signal history.

        Args:
            strategy_id: Clear specific strategy, or all if None
        """
        with self._lock:
            if strategy_id is not None:
                self._history.pop(strategy_id, None)
            else:
                self._history.clear()
                self._global_history.clear()

    def get_signal_count(self, strategy_id: UUID | None = None) -> int:
        """Get number of stored signals.

        Args:
            strategy_id: Count for specific strategy, or total if None

        Returns:
            Number of signals
        """
        with self._lock:
            if strategy_id is not None:
                return len(self._history.get(strategy_id, []))
            return len(self._global_history)

    def to_dict(self, strategy_id: UUID | None = None) -> dict[str, Any]:
        """Get aggregator state as dictionary.

        Args:
            strategy_id: Get state for specific strategy, or global if None

        Returns:
            Dictionary with signal counts and stats
        """
        with self._lock:
            result: dict[str, Any] = {
                "total_strategies": len(self._history),
                "total_signals": len(self._global_history),
            }

            if strategy_id is not None:
                signals = list(self._history.get(strategy_id, []))
                result["strategy_signals"] = len(signals)
                if signals:
                    # Compute stats inline to avoid deadlock (get_stats acquires lock)
                    buy_count = sum(1 for s in signals if s.side == "BUY")
                    sell_count = sum(1 for s in signals if s.side == "SELL")
                    executed_count = sum(1 for s in signals if s.status.value == "EXECUTED")
                    rejected_count = sum(1 for s in signals if s.status.value == "REJECTED")
                    failed_count = sum(1 for s in signals if s.status.value == "FAILED")
                    pending_count = sum(1 for s in signals if s.status.value == "PENDING")
                    avg_quantity = float(sum(s.quantity for s in signals)) / len(signals)
                    result["stats"] = {
                        "total_signals": len(signals),
                        "buy_count": buy_count,
                        "sell_count": sell_count,
                        "executed_count": executed_count,
                        "rejected_count": rejected_count,
                        "failed_count": failed_count,
                        "pending_count": pending_count,
                        "avg_quantity": round(avg_quantity, 6),
                    }

            return result
