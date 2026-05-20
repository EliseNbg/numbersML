"""Symbol price statistics tracker.

Provides average price calculations per symbol for configurable time windows
(day, week). Updates are throttled to once per hour to avoid unnecessary
computation on every tick.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class _SymbolPriceBuffer:
    """Internal price buffer for a single symbol."""

    prices: list[tuple[datetime, Decimal]] = field(default_factory=list)
    last_update: datetime | None = None
    cached_avg_day: Decimal | None = None
    cached_avg_week: Decimal | None = None
    cache_valid_until: datetime | None = None

    UPDATE_INTERVAL = timedelta(hours=1)

    def add_price(self, ts: datetime, price: Decimal) -> None:
        """Add a new price sample."""
        self.prices.append((ts, price))

    def _prune_old(self, now: datetime) -> None:
        """Remove entries older than 7 days."""
        cutoff = now - timedelta(days=7)
        self.prices = [(t, p) for t, p in self.prices if t >= cutoff]

    def _needs_update(self, now: datetime) -> bool:
        """Check if cached averages need refreshing."""
        if self.last_update is None:
            return True
        if self.cache_valid_until is None:
            return True
        return now >= self.cache_valid_until

    def _compute_avg(self, window: timedelta) -> Decimal | None:
        """Compute average price within the given time window."""
        if not self.prices:
            return None

        now = self.prices[-1][0]
        cutoff = now - window

        samples = [(t, p) for t, p in self.prices if t >= cutoff]
        if not samples:
            return None

        total = sum(p for _, p in samples)
        return total / len(samples)

    def refresh(self, now: datetime) -> None:
        """Recompute cached averages if needed."""
        if not self._needs_update(now):
            return

        self._prune_old(now)
        self.cached_avg_day = self._compute_avg(timedelta(days=1))
        self.cached_avg_week = self._compute_avg(timedelta(weeks=1))
        self.last_update = now
        self.cache_valid_until = now + self.UPDATE_INTERVAL

        logger.debug(
            f"Price stats refreshed: avg_day={self.cached_avg_day}, "
            f"avg_week={self.cached_avg_week}, samples={len(self.prices)}"
        )


class SymbolPriceStatistics:
    """Tracks and computes average prices per symbol.

    Averages are cached and refreshed at most once per hour per symbol.
    Call ``record_price`` on every tick; call ``refresh`` periodically
    (e.g. once per tick or from a timer) to update caches.

    Example:
        >>> stats = SymbolPriceStatistics()
        >>> stats.record_price("BTC/USDC", Decimal("50000"), datetime.now(UTC))
        >>> stats.refresh(datetime.now(UTC))
        >>> stats.get_avg_price("BTC/USDC", "day")
        Decimal('50000')
        >>> stats.get_avg_price("BTC/USDC", "week")
        Decimal('50000')
    """

    def __init__(self) -> None:
        self._buffers: dict[str, _SymbolPriceBuffer] = {}
        self._loaded: set[str] = set()

    def load_historical_prices(
        self,
        symbol: str,
        prices: list[tuple[datetime, Decimal]],
    ) -> None:
        """Bulk-load historical prices for a symbol (e.g. from DB candles).

        Args:
            symbol: Trading pair (e.g. "BTC/USDC")
            prices: List of (timestamp, price) tuples, should be sorted by time.
        """
        if symbol in self._loaded:
            return
        buf = _SymbolPriceBuffer(prices=list(prices))
        self._buffers[symbol] = buf
        self._loaded.add(symbol)

        now = datetime.now(UTC)
        buf.refresh(now)

        logger.info(
            f"Loaded {len(prices)} historical prices for {symbol}, "
            f"avg_day={buf.cached_avg_day}, avg_week={buf.cached_avg_week}"
        )

    def record_price(self, symbol: str, price: Decimal, ts: datetime) -> None:
        """Record a price sample for the given symbol.

        Args:
            symbol: Trading pair (e.g. "BTC/USDC")
            price: Price value
            ts: Timestamp of the price sample
        """
        if symbol not in self._buffers:
            self._buffers[symbol] = _SymbolPriceBuffer()
        self._buffers[symbol].add_price(ts, price)

    def refresh(self, now: datetime | None = None) -> None:
        """Refresh cached averages for all symbols.

        Safe to call every tick — actual recomputation happens at most
        once per hour per symbol.

        Args:
            now: Current time. Defaults to ``datetime.now(UTC)``.
        """
        if now is None:
            now = datetime.now(UTC)
        for buf in self._buffers.values():
            buf.refresh(now)

    def get_avg_price(self, symbol: str, window: str) -> Decimal | None:
        """Get cached average price for a symbol and time window.

        Args:
            symbol: Trading pair (e.g. "BTC/USDC")
            window: One of ``"day"`` or ``"week"``

        Returns:
            Average price as ``Decimal``, or ``None`` if no data available.

        Raises:
            ValueError: If ``window`` is not ``"day"`` or ``"week"``.
        """
        buf = self._buffers.get(symbol)
        if buf is None:
            return None

        window_lower = window.lower()
        if window_lower == "day":
            return buf.cached_avg_day
        if window_lower == "week":
            return buf.cached_avg_week

        raise ValueError(f"Unknown window: {window!r}. Use 'day' or 'week'.")

    def get_stats(self, symbol: str) -> dict[str, Decimal | None]:
        """Get all cached averages for a symbol.

        Args:
            symbol: Trading pair (e.g. "BTC/USDC")

        Returns:
            Dict with keys ``"day"`` and ``"week"``.
        """
        return {
            "day": self.get_avg_price(symbol, "day"),
            "week": self.get_avg_price(symbol, "week"),
        }
