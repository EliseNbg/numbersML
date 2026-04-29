"""
Ring buffer container for indicator calculations.

Provides efficient storage of price/volume series for a single symbol,
enabling O(1) updates and O(window) access to historical data.
"""

from typing import Optional, Dict, Any
import numpy as np
from numpy_ringbuffer import RingBuffer


class IndicatorsBuffer:
    """
    Ring buffers for HLCV data of a single symbol (open prices not needed).

    Maintains separate ring buffers for high, low, close, and volume,
    each with capacity equal to the maximum indicator period (in seconds).
    Buffers are always kept filled (no NaN gaps) to ensure indicator
    calculations never produce NaN/inf due to insufficient history.

    Note: Open prices are not stored since no indicator uses them.
    """

    def __init__(self, dbconn, symbol: str, max_indicator_period: int) -> None:
        """
        Initialize buffers for a symbol.

        Args:
            dbconn: Database connection (asyncpg.Connection or Pool)
            symbol: Symbol name (e.g. 'BTC/USDC')
            max_indicator_period: Maximum indicator look‑back in seconds
        """
        self.dbconn = dbconn
        self.symbol = symbol
        self.max_indicator_period = max_indicator_period

        # Ring buffers with capacity = max_indicator_period candles
        # opens_buff excluded - no indicator uses open prices
        self.closes_buff = RingBuffer(capacity=max_indicator_period, dtype=np.float64)
        self.volumes_buff = RingBuffer(capacity=max_indicator_period, dtype=np.float64)
        self.highs_buff = RingBuffer(capacity=max_indicator_period, dtype=np.float64)
        self.lows_buff = RingBuffer(capacity=max_indicator_period, dtype=np.float64)

        # Symbol ID cache (populated on first DB fetch)
        self._symbol_id: Optional[int] = None

    async def initialization(self, current_time, current_candle: Dict[str, Any]) -> None:
        """
        Fill buffers with historical candles (or repeat current candle).

        This method is called once per symbol when the pipeline starts or
        when a recalculation begins. It ensures the ring buffers contain
        exactly ``max_indicator_period`` candles before any indicator is
        computed.

        If there are enough candles in the DB for the time range
        [current_time - max_indicator_period, current_time], they are loaded.
        Otherwise, the buffers are filled with ``current_candle`` repeated
        ``max_indicator_period`` times (so indicators can still be computed
        without NaN/inf).

        Args:
            current_time: datetime of the most recent candle
            current_candle: dict with keys open, high, low, close, volume
        """
        from datetime import timedelta

        lookback_start = current_time - timedelta(seconds=self.max_indicator_period)
        rows = await self._fetch_candles(lookback_start, current_time)

        if len(rows) >= self.max_indicator_period:
            # Enough history: load into buffers (chronological order)
            self._fill_from_rows(rows)
        else:
            # Not enough history: repeat current candle to fill capacity
            self._fill_with_candle(current_candle)

    async def add_candle(self, candle: Dict[str, Any]) -> None:
        """
        Append a new candle to all ring buffers (O(1)).

        Args:
            candle: dict with keys open, high, low, close, volume
            (open is ignored - not used by any indicator)
        """
        self.highs_buff.append(float(candle["high"]))
        self.lows_buff.append(float(candle["low"]))
        self.closes_buff.append(float(candle["close"]))
        self.volumes_buff.append(float(candle["volume"]))

    # -- internal helpers --

    async def _fetch_candles(self, start_time, end_time) -> list:
        """Fetch candles from DB for this symbol between start_time and end_time."""
        if self._symbol_id is None:
            # Resolve symbol -> id once
            if hasattr(self.dbconn, "fetchval"):
                # assume asyncpg.Connection
                self._symbol_id = await self.dbconn.fetchval(
                    "SELECT id FROM symbols WHERE symbol = $1", self.symbol
                )
            else:
                # assume pool
                async with self.dbconn.acquire() as conn:
                    self._symbol_id = await conn.fetchval(
                        "SELECT id FROM symbols WHERE symbol = $1", self.symbol
                    )
        if self._symbol_id is None:
            return []

        if hasattr(self.dbconn, "fetch"):
            # connection
            rows = await self.dbconn.fetch(
                """
                SELECT open, high, low, close, volume
                FROM candles_1s
                WHERE symbol_id = $1
                  AND time >= $2 AND time <= $3
                ORDER BY time ASC
                """,
                self._symbol_id,
                start_time,
                end_time,
            )
        else:
            # pool
            async with self.dbconn.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT open, high, low, close, volume
                    FROM candles_1s
                    WHERE symbol_id = $1
                      AND time >= $2 AND time <= $3
                    ORDER BY time ASC
                    """,
                    self._symbol_id,
                    start_time,
                    end_time,
                )
        return rows

    def _clear_all(self) -> None:
        """Reset all ring buffers to empty."""
        self.highs_buff = RingBuffer(capacity=self.max_indicator_period, dtype=np.float64)
        self.lows_buff = RingBuffer(capacity=self.max_indicator_period, dtype=np.float64)
        self.closes_buff = RingBuffer(capacity=self.max_indicator_period, dtype=np.float64)
        self.volumes_buff = RingBuffer(capacity=self.max_indicator_period, dtype=np.float64)

    def _fill_from_rows(self, rows: list) -> None:
        """Load rows into ring buffers (assumes rows are chronological)."""
        self._clear_all()
        for r in rows:
            self.highs_buff.append(float(r["high"]))
            self.lows_buff.append(float(r["low"]))
            self.closes_buff.append(float(r["close"]))
            self.volumes_buff.append(float(r["volume"]))

    def _fill_with_candle(self, candle: Dict[str, Any]) -> None:
        """Fill buffers by repeating the same candle max_indicator_period times."""
        self._clear_all()
        for _ in range(self.max_indicator_period):
            self.highs_buff.append(float(candle["high"]))
            self.lows_buff.append(float(candle["low"]))
            self.closes_buff.append(float(candle["close"]))
            self.volumes_buff.append(float(candle["volume"]))
