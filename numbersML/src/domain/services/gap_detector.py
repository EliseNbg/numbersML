"""
Gap detection and filling service.

Detects gaps in tick data and provides mechanisms to fill them.

Enhanced with:
- Binance REST API integration for historical data
- Rate limiting
- Batch fetching
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class DataGap:
    """
    Represents a gap in data.

    Attributes:
        symbol_id: Symbol ID
        symbol: Symbol string
        gap_start: Start of gap
        gap_end: End of gap
        gap_seconds: Duration of gap in seconds
        detected_at: When gap was detected
        is_filled: Whether gap has been filled
        filled_at: When gap was filled
    """

    symbol_id: int
    symbol: str
    gap_start: datetime
    gap_end: datetime
    gap_seconds: float
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_filled: bool = False
    filled_at: Optional[datetime] = None

    @property
    def is_critical(self) -> bool:
        """Check if gap is critical (>1 minute)."""
        return self.gap_seconds > 60


@dataclass
class GapFillResult:
    """
    Result of gap filling operation.

    Attributes:
        gap: The gap that was filled
        ticks_filled: Number of ticks filled
        success: Whether filling was successful
        error: Error message if failed
    """

    gap: DataGap
    ticks_filled: int = 0
    success: bool = False
    error: Optional[str] = None


class GapDetector:
    """
    Detects gaps in tick data stream.

    Monitors incoming ticks and detects when data is missing
    for a configured time period.
    """

    def __init__(
        self,
        max_gap_seconds: int = 5,
    ) -> None:
        """
        Initialize gap detector.

        Args:
            max_gap_seconds: Maximum allowed gap (default: 5s)
        """
        self.max_gap_seconds: int = max_gap_seconds

        # State per symbol
        self._last_tick_time: Dict[int, datetime] = {}
        self._gaps: List[DataGap] = []

    def start_monitoring(self, symbol_id: int, symbol: str) -> None:
        """Start monitoring a symbol for gaps."""
        self._last_tick_time[symbol_id] = datetime.now(timezone.utc)
        logger.info(f"Started monitoring {symbol} for gaps")

    def check_tick(
        self,
        symbol_id: int,
        tick_time: datetime,
    ) -> Optional[DataGap]:
        """
        Check if there's a gap since last tick.

        Args:
            symbol_id: Symbol ID
            tick_time: Time of incoming tick

        Returns:
            DataGap if gap detected, None otherwise
        """
        if symbol_id not in self._last_tick_time:
            self._last_tick_time[symbol_id] = tick_time
            return None

        last_time = self._last_tick_time[symbol_id]
        gap_seconds = (tick_time - last_time).total_seconds()

        if gap_seconds > self.max_gap_seconds:
            gap = DataGap(
                symbol_id=symbol_id,
                symbol=f"SYMBOL_{symbol_id}",
                gap_start=last_time,
                gap_end=tick_time,
                gap_seconds=gap_seconds,
            )

            self._gaps.append(gap)
            self._last_tick_time[symbol_id] = tick_time

            logger.warning(
                f"Gap detected for symbol {symbol_id}: "
                f"{gap_seconds:.1f}s from {last_time} to {tick_time}"
            )

            return gap

        self._last_tick_time[symbol_id] = tick_time
        return None

    def get_unfilled_gaps(self) -> List[DataGap]:
        """Get list of unfilled gaps."""
        return [gap for gap in self._gaps if not gap.is_filled]

    def get_all_gaps(self) -> List[DataGap]:
        """Get all detected gaps."""
        return self._gaps.copy()

    def mark_gap_filled(self, gap: DataGap) -> None:
        """Mark a gap as filled."""
        gap.is_filled = True
        gap.filled_at = datetime.now(timezone.utc)
        logger.info(f"Gap filled: {gap.gap_seconds}s for symbol {gap.symbol_id}")


class GapFiller:
    """
    Fills gaps in historical data.

    Fetches missing data from Binance API and stores it.

    Features:
    - Binance REST API integration
    - Rate limiting (1200 weight/min)
    - Batch gap filling
    - Progress tracking
    """

    def __init__(
        self,
        db_pool: Any,
        binance_api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize gap filler.

        Args:
            db_pool: Database connection pool
            binance_api_key: Binance API key (optional)
        """
        self.db_pool = db_pool
        self.binance_api_key = binance_api_key
        self._rest_client: Optional[Any] = None

        # Statistics
        self._stats: Dict[str, int] = {
            'gaps_filled': 0,
            'ticks_fetched': 0,
            'errors': 0,
        }

    async def __aenter__(self) -> 'GapFiller':
        """Async context manager entry."""
        from src.infrastructure.exchanges.binance_rest_client import BinanceRESTClient
        self._rest_client = BinanceRESTClient(api_key=self.binance_api_key)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._rest_client:
            await self._rest_client.close()

    async def fill_gap(self, gap: DataGap) -> GapFillResult:
        """
        Fill a data gap.

        Args:
            gap: Gap to fill

        Returns:
            GapFillResult with filling status
        """
        try:
            # Ensure we have a REST client
            if self._rest_client is None:
                from src.infrastructure.exchanges.binance_rest_client import BinanceRESTClient
                self._rest_client = BinanceRESTClient(api_key=self.binance_api_key)

            # Fetch historical data for gap period
            ticks = await self._fetch_historical_data(
                gap.symbol,
                gap.gap_start,
                gap.gap_end,
            )

            if not ticks:
                logger.warning(f"No historical data found for gap: {gap.symbol}")
                return GapFillResult(
                    gap=gap,
                    ticks_filled=0,
                    success=False,
                    error="No historical data found",
                )

            # Store fetched data
            await self._store_ticks(gap.symbol_id, ticks)

            gap.is_filled = True
            gap.filled_at = datetime.now(timezone.utc)

            self._stats['gaps_filled'] += 1
            self._stats['ticks_fetched'] += len(ticks)

            logger.info(
                f"Filled gap for symbol {gap.symbol}: "
                f"{len(ticks)} ticks from {gap.gap_start} to {gap.gap_end}"
            )

            return GapFillResult(
                gap=gap,
                ticks_filled=len(ticks),
                success=True,
            )

        except Exception as e:
            logger.error(f"Failed to fill gap: {e}")
            self._stats['errors'] += 1
            return GapFillResult(
                gap=gap,
                ticks_filled=0,
                success=False,
                error=str(e),
            )

    async def fill_gaps_batch(
        self,
        gaps: List[DataGap],
        max_concurrent: int = 3,
    ) -> List[GapFillResult]:
        """
        Fill multiple gaps in batch.

        Args:
            gaps: List of gaps to fill
            max_concurrent: Maximum concurrent fills

        Returns:
            List of GapFillResults
        """
        logger.info(f"Filling {len(gaps)} gaps (max concurrent: {max_concurrent})")

        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fill_with_semaphore(gap: DataGap) -> GapFillResult:
            async with semaphore:
                return await self.fill_gap(gap)

        # Fill all gaps concurrently
        tasks = [fill_with_semaphore(gap) for gap in gaps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        fill_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                fill_results.append(GapFillResult(
                    gap=gaps[i],
                    ticks_filled=0,
                    success=False,
                    error=str(result),
                ))
            else:
                fill_results.append(result)

        # Log summary
        successful = sum(1 for r in fill_results if r.success)
        total_ticks = sum(r.ticks_filled for r in fill_results)
        logger.info(f"Batch fill complete: {successful}/{len(gaps)} gaps, {total_ticks} ticks")

        return fill_results

    async def _fetch_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical data from Binance API.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            start: Start of time range
            end: End of time range

        Returns:
            List of trade dictionaries
        """
        if self._rest_client is None:
            from src.infrastructure.exchanges.binance_rest_client import BinanceRESTClient
            self._rest_client = BinanceRESTClient(api_key=self.binance_api_key)

        # Convert symbol format (BTC/USDT -> BTCUSDT)
        binance_symbol = symbol.replace('/', '')

        # Fetch aggregate trades
        raw_trades = await self._rest_client.get_historical_trades(
            symbol=binance_symbol,
            start_time=start,
            end_time=end,
            limit=1000,
        )

        # Parse trades
        from src.infrastructure.exchanges.binance_rest_client import parse_trade_data
        parsed_trades = [parse_trade_data(trade) for trade in raw_trades]

        logger.debug(f"Fetched {len(parsed_trades)} trades for {symbol}")
        return parsed_trades

    async def _store_ticks(
        self,
        symbol_id: int,
        ticks: List[Dict[str, Any]],
    ) -> None:
        """
        Store fetched ticks in database.

        Args:
            symbol_id: Symbol ID
            ticks: List of tick dictionaries
        """
        if not ticks:
            return

        async with self.db_pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO trades (time, symbol_id, trade_id, price, quantity, side, is_buyer_maker)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (trade_id, symbol_id) DO NOTHING
                """,
                [
                    (
                        t['time'],
                        symbol_id,
                        t['trade_id'],
                        t['price'],
                        t['quantity'],
                        t['side'],
                        t['is_buyer_maker'],
                    )
                    for t in ticks
                ],
            )

    def get_stats(self) -> Dict[str, int]:
        """Get gap filler statistics."""
        return self._stats.copy()
