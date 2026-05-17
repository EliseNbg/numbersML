"""Stdout collector for strategy execution output.

Thread-safe per-strategy stdout buffer with size limits and retrieval.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class StdoutCollector:
    """Thread-safe stdout collector per strategy.

    Attributes:
        max_buffer_size: Maximum characters per strategy buffer
        max_lines: Maximum lines per strategy buffer
    """

    MAX_BUFFER_SIZE = 100_000  # chars per strategy
    MAX_LINES = 1000

    def __init__(
        self,
        max_buffer_size: int = MAX_BUFFER_SIZE,
        max_lines: int = MAX_LINES,
    ) -> None:
        """Initialize stdout collector.

        Args:
            max_buffer_size: Maximum characters per strategy buffer
            max_lines: Maximum lines per strategy buffer
        """
        self._buffers: dict[UUID, deque[str]] = {}
        self._sizes: dict[UUID, int] = {}
        self._lock = threading.Lock()
        self._max_buffer_size = max_buffer_size
        self._max_lines = max_lines

    def capture(self, strategy_id: UUID, text: str) -> None:
        """Append captured text to strategy buffer.

        Args:
            strategy_id: Strategy UUID
            text: Captured stdout text
        """
        if not text:
            return

        with self._lock:
            if strategy_id not in self._buffers:
                self._buffers[strategy_id] = deque(maxlen=self._max_lines)
                self._sizes[strategy_id] = 0

            buffer = self._buffers[strategy_id]
            lines = text.splitlines()

            for line in lines:
                if self._sizes[strategy_id] + len(line) > self._max_buffer_size:
                    # Remove oldest lines until we fit
                    while buffer and self._sizes[strategy_id] + len(line) > self._max_buffer_size:
                        old = buffer.popleft()
                        self._sizes[strategy_id] -= len(old)

                buffer.append(line)
                self._sizes[strategy_id] += len(line)

    def get_output(self, strategy_id: UUID, limit: int = 100) -> list[str]:
        """Get last N lines of stdout for a strategy.

        Args:
            strategy_id: Strategy UUID
            limit: Maximum lines to return

        Returns:
            List of stdout lines
        """
        with self._lock:
            buffer = self._buffers.get(strategy_id)
            if buffer is None:
                return []
            return list(buffer)[-limit:]

    def clear(self, strategy_id: UUID) -> None:
        """Clear stdout buffer for a strategy.

        Args:
            strategy_id: Strategy UUID
        """
        with self._lock:
            if strategy_id in self._buffers:
                self._buffers[strategy_id].clear()
                self._sizes[strategy_id] = 0

    def clear_all(self) -> None:
        """Clear all stdout buffers."""
        with self._lock:
            for buffer in self._buffers.values():
                buffer.clear()
            self._sizes.clear()

    def get_line_count(self, strategy_id: UUID) -> int:
        """Get number of lines in buffer for a strategy.

        Args:
            strategy_id: Strategy UUID

        Returns:
            Number of lines
        """
        with self._lock:
            buffer = self._buffers.get(strategy_id)
            return len(buffer) if buffer else 0

    def get_buffer_size(self, strategy_id: UUID) -> int:
        """Get character count in buffer for a strategy.

        Args:
            strategy_id: Strategy UUID

        Returns:
            Number of characters
        """
        with self._lock:
            return self._sizes.get(strategy_id, 0)

    def get_all_strategy_ids(self) -> list[UUID]:
        """Get all strategy IDs that have stdout buffers.

        Returns:
            List of strategy UUIDs
        """
        with self._lock:
            return list(self._buffers.keys())

    def to_dict(self, strategy_id: UUID) -> dict[str, Any]:
        """Get buffer info as dictionary.

        Args:
            strategy_id: Strategy UUID

        Returns:
            Dictionary with line_count and buffer_size
        """
        with self._lock:
            buffer = self._buffers.get(strategy_id)
            return {
                "strategy_id": str(strategy_id),
                "line_count": len(buffer) if buffer else 0,
                "buffer_size": self._sizes.get(strategy_id, 0),
            }
