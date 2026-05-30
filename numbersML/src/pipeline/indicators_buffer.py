"""
Ring buffer container for indicator calculations.

Provides efficient storage of price/volume series for a single symbol,
enabling O(1) updates and O(window) access to historical data.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
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
        self._symbol_id: int | None = None

    async def initialization(self, current_time, current_candle: dict[str, Any]) -> None:
        """
        Fill buffers with historical candles (or repeat current candle).

        This method is called once per symbol when the pipeline starts or
        when a recalculation begins. It ensures the ring buffers contain
        exactly ``max_indicator_period`` candles before any indicator is
        computed.

        The lookup order is:

        1. **PostgreSQL** — load candles from the ``candles_1s`` table for the
           range ``[current_time - max_indicator_period, current_time]``.
        2. **Binance REST API** (*fallback*) — fetch 1‑second klines when the
           DB does not have enough history (warmup / first pipeline start).
        3. **Repeated candle** — repeat ``current_candle`` ``max_indicator_period``
           times so indicators can compute without NaN (last resort).

        Args:
            current_time: datetime of the most recent candle
            current_candle: dict with keys open, high, low, close, volume
        """
        lookback_start = current_time - timedelta(seconds=self.max_indicator_period)
        rows = await self._fetch_candles(lookback_start, current_time)

        if len(rows) >= self.max_indicator_period:
            self._fill_from_rows(rows)
            return

        # ── Binance REST fallback ──────────────────────────────────────
        logger = logging.getLogger(__name__)
        logger.info(
            f"DB has {len(rows)} candles for {self.symbol}, "
            f"need {self.max_indicator_period} — trying Binance REST API"
        )
        try:
            klines = await self._fetch_klines_from_binance(lookback_start, current_time)
        except Exception:
            logger.warning(f"Binance klines fetch failed for {self.symbol}", exc_info=True)
            klines = []

        if len(klines) >= self.max_indicator_period:
            rows = self._parse_klines_to_rows(klines)
            logger.info(
                f"Loaded {len(rows)} historical klines from Binance for {self.symbol}"
            )
            self._fill_from_rows(rows)
            return

        # ── Last resort: repeat current candle ─────────────────────────
        if rows:
            logger.info(
                f"Using {len(rows)} DB candles + repeat for {self.symbol} "
                f"(Binance returned {len(klines)} klines)"
            )
            self._fill_from_rows(rows)
            # Pad remaining with the current candle
            remaining = self.max_indicator_period - len(rows)
            for _ in range(remaining):
                self.highs_buff.append(float(current_candle["high"]))
                self.lows_buff.append(float(current_candle["low"]))
                self.closes_buff.append(float(current_candle["close"]))
                self.volumes_buff.append(float(current_candle["volume"]))
        else:
            self._fill_with_candle(current_candle)

    async def add_candle(self, candle: dict[str, Any]) -> None:
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

    async def _fetch_klines_from_binance(
        self, start_time: datetime, end_time: datetime
    ) -> list[list]:
        """Fetch 1‑second klines from Binance REST API.

        Queries ``/api/v3/klines?interval=1s`` and paginates up to
        ``max_indicator_period`` rows.  Returns the raw Binance kline
        arrays so the caller can pass them to ``_parse_klines_to_rows``.

        Args:
            start_time: Earliest candle time (inclusive).
            end_time: Latest candle time (inclusive).

        Returns:
            Raw Binance kline arrays (empty on error).
        """
        binance_symbol = self.symbol.replace("/", "")
        all_klines: list[list] = []
        current_start = start_time

        async with aiohttp.ClientSession() as session:
            consecutive_errors = 0

            while current_start < end_time and len(all_klines) < self.max_indicator_period:
                try:
                    limit = min(1000, self.max_indicator_period - len(all_klines))
                    params = {
                        "symbol": binance_symbol,
                        "interval": "1s",
                        "startTime": int(current_start.timestamp() * 1000),
                        "limit": limit,
                    }

                    async with session.get(
                        "https://api.binance.com/api/v3/klines",
                        params=params,  # type: ignore[arg-type]
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status != 200:
                            consecutive_errors += 1
                            if consecutive_errors >= 3:
                                return []
                            await asyncio.sleep(0.5)
                            continue

                        consecutive_errors = 0
                        klines = await response.json()

                        if not klines:
                            break

                        all_klines.extend(klines)

                        # Advance to the next second after the last kline
                        current_start = datetime.fromtimestamp(
                            klines[-1][0] / 1000 + 1, tz=UTC
                        )

                        await asyncio.sleep(0.1)  # rate-limit courtesy

                except Exception:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        return []
                    await asyncio.sleep(0.5)

        return all_klines

    def _parse_klines_to_rows(self, klines: list[list]) -> list[dict[str, float]]:
        """Convert raw Binance kline arrays to row dicts.

        Binance format::

            [
                open_time, open, high, low, close, volume, close_time,
                quote_volume, trades, taker_buy_base, taker_buy_quote, ignore
            ]

        Returns a list of dicts with keys ``open``, ``high``, ``low``,
        ``close``, ``volume`` — compatible with ``_fill_from_rows``.
        """
        return [
            {
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
            for k in klines
        ]

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

    def _fill_with_candle(self, candle: dict[str, Any]) -> None:
        """Fill buffers by repeating the same candle max_indicator_period times."""
        self._clear_all()
        for _ in range(self.max_indicator_period):
            self.highs_buff.append(float(candle["high"]))
            self.lows_buff.append(float(candle["low"]))
            self.closes_buff.append(float(candle["close"]))
            self.volumes_buff.append(float(candle["volume"]))
