"""
Gap detection and filling service.

Detects gaps in tick data and provides mechanisms to fill them.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
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
    detected_at: datetime = field(default_factory=datetime.utcnow)
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
        self._last_tick_time[symbol_id] = datetime.utcnow()
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
        gap.filled_at = datetime.utcnow()
        logger.info(f"Gap filled: {gap.gap_seconds}s for symbol {gap.symbol_id}")


class GapFiller:
    """
    Fills gaps in historical data.
    
    Fetches missing data from exchange API and stores it.
    """
    
    def __init__(self, db_pool) -> None:  # type: ignore
        """
        Initialize gap filler.
        
        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
    
    async def fill_gap(self, gap: DataGap) -> GapFillResult:
        """
        Fill a data gap.
        
        Args:
            gap: Gap to fill
        
        Returns:
            GapFillResult with filling status
        """
        try:
            # Fetch historical data for gap period
            ticks = await self._fetch_historical_data(
                gap.symbol_id,
                gap.gap_start,
                gap.gap_end,
            )
            
            # Store fetched data
            await self._store_ticks(gap.symbol_id, ticks)
            
            gap.is_filled = True
            gap.filled_at = datetime.utcnow()
            
            logger.info(
                f"Filled gap for symbol {gap.symbol_id}: "
                f"{len(ticks)} ticks from {gap.gap_start} to {gap.gap_end}"
            )
            
            return GapFillResult(
                gap=gap,
                ticks_filled=len(ticks),
                success=True,
            )
        
        except Exception as e:
            logger.error(f"Failed to fill gap: {e}")
            return GapFillResult(
                gap=gap,
                ticks_filled=0,
                success=False,
                error=str(e),
            )
    
    async def _fetch_historical_data(
        self,
        symbol_id: int,
        start: datetime,
        end: datetime,
    ) -> List[Dict]:
        """Fetch historical data from exchange."""
        # This would call Binance API
        # For now, return empty list
        logger.debug(
            f"Would fetch historical data for symbol {symbol_id} "
            f"from {start} to {end}"
        )
        return []
    
    async def _store_ticks(
        self,
        symbol_id: int,
        ticks: List[Dict],
    ) -> None:
        """Store fetched ticks in database."""
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
                ]
            )
