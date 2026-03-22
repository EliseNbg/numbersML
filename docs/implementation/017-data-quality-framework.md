# Step 017: Data Quality Framework - Implementation Guide

**Phase**: 3 - Data Quality  
**Effort**: 8 hours  
**Dependencies**: Step 004 (Data Collection) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements comprehensive data quality framework with:
- **Anomaly Detection**: Detect price spikes, volume anomalies, time gaps
- **Anomaly Correction**: Fix or flag bad data automatically
- **Gap Detection**: Detect missing data in real-time
- **Gap Filling**: Backfill missing data from exchange API
- **Quality Metrics**: Track and report data quality scores
- **Alerting**: Notify on quality issues

---

## Implementation Tasks

### Task 1: Enhanced Anomaly Detector

**File**: `src/domain/services/anomaly_detector.py`

```python
"""
Anomaly detection service for tick data.

Detects various types of anomalies in market data:
- Price spikes (sudden large moves)
- Volume anomalies (unusual volume)
- Time gaps (missing data)
- Stale data (old timestamps)
- Wash trades (suspicious patterns)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
from enum import Enum
from src.domain.models.trade import Trade
from src.domain.models.symbol import Symbol


class AnomalyType(Enum):
    """Types of data anomalies."""
    PRICE_SPIKE = "price_spike"
    PRICE_DROP = "price_drop"
    VOLUME_SPIKE = "volume_spike"
    TIME_GAP = "time_gap"
    STALE_DATA = "stale_data"
    WASH_TRADE = "wash_trade"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"


class AnomalySeverity(Enum):
    """Severity levels for anomalies."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Anomaly:
    """
    Represents a detected anomaly.
    
    Attributes:
        anomaly_type: Type of anomaly detected
        severity: Severity level
        trade: The trade that triggered the anomaly
        message: Human-readable description
        expected_value: Expected value (if applicable)
        actual_value: Actual value that triggered anomaly
        detected_at: When anomaly was detected
    """
    
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    trade: Trade
    message: str
    expected_value: Optional[Decimal] = None
    actual_value: Optional[Decimal] = None
    detected_at: datetime = field(default_factory=datetime.utcnow)
    can_auto_fix: bool = False


@dataclass
class AnomalyResult:
    """
    Result of anomaly detection.
    
    Attributes:
        is_anomaly: True if anomaly detected
        anomalies: List of detected anomalies
        should_reject: True if trade should be rejected
        should_flag: True if trade should be flagged for review
    """
    
    is_anomaly: bool = False
    anomalies: List[Anomaly] = field(default_factory=list)
    should_reject: bool = False
    should_flag: bool = False
    
    def add(self, anomaly: Anomaly) -> None:
        """Add anomaly to result."""
        self.anomalies.append(anomaly)
        self.is_anomaly = True
        
        if anomaly.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL):
            self.should_reject = True
        elif anomaly.severity == AnomalySeverity.MEDIUM:
            self.should_flag = True


class AnomalyDetector:
    """
    Detects anomalies in tick data.
    
    Uses statistical methods and configurable thresholds
    to detect various types of data anomalies.
    
    Attributes:
        symbol: Symbol being monitored
        price_spike_threshold: Price move % to trigger spike alert
        volume_spike_threshold: Volume multiplier for spike alert
        max_gap_seconds: Maximum allowed time gap
        stale_data_seconds: Time after which data is considered stale
    
    Example:
        >>> detector = AnomalyDetector(symbol)
        >>> result = detector.detect(trade)
        >>> if result.is_anomaly:
        ...     handle_anomaly(result.anomalies)
    """
    
    def __init__(
        self,
        symbol: Symbol,
        price_spike_threshold: Decimal = Decimal("5.0"),
        volume_spike_threshold: Decimal = Decimal("10.0"),
        max_gap_seconds: int = 5,
        stale_data_seconds: int = 60,
        lookback_window: int = 100,
    ) -> None:
        """
        Initialize anomaly detector.
        
        Args:
            symbol: Symbol being monitored
            price_spike_threshold: Price move % to trigger alert (default: 5%)
            volume_spike_threshold: Volume multiplier (default: 10x)
            max_gap_seconds: Maximum allowed time gap (default: 5s)
            stale_data_seconds: Stale data threshold (default: 60s)
            lookback_window: Number of trades to look back for statistics
        """
        self.symbol: Symbol = symbol
        self.price_spike_threshold: Decimal = price_spike_threshold
        self.volume_spike_threshold: Decimal = volume_spike_threshold
        self.max_gap_seconds: int = max_gap_seconds
        self.stale_data_seconds: int = stale_data_seconds
        self.lookback_window: int = lookback_window
        
        # State for detection
        self._recent_trades: List[Trade] = []
        self._last_trade: Optional[Trade] = None
        self._last_time: Optional[datetime] = None
        self._seen_trade_ids: set = set()
        
        # Rolling statistics
        self._price_std: Optional[Decimal] = None
        self._volume_avg: Optional[Decimal] = None
    
    def detect(self, trade: Trade) -> AnomalyResult:
        """
        Detect anomalies in trade.
        
        Args:
            trade: Trade to analyze
        
        Returns:
            AnomalyResult with detected anomalies
        """
        result = AnomalyResult()
        
        # Run all anomaly checks
        self._check_duplicate(trade, result)
        self._check_out_of_order(trade, result)
        self._check_time_gap(trade, result)
        self._check_stale_data(trade, result)
        self._check_price_spike(trade, result)
        self._check_volume_spike(trade, result)
        self._check_wash_trade(trade, result)
        
        # Update state
        if not result.should_reject:
            self._update_state(trade)
        
        return result
    
    def _check_duplicate(self, trade: Trade, result: AnomalyResult) -> None:
        """Check for duplicate trade ID."""
        if trade.trade_id in self._seen_trade_ids:
            result.add(Anomaly(
                anomaly_type=AnomalyType.DUPLICATE,
                severity=AnomalySeverity.HIGH,
                trade=trade,
                message=f"Duplicate trade ID: {trade.trade_id}",
                actual_value=Decimal(trade.trade_id),
                can_auto_fix=False,
            ))
    
    def _check_out_of_order(self, trade: Trade, result: AnomalyResult) -> None:
        """Check for out-of-order trades."""
        if self._last_time and trade.time < self._last_time:
            result.add(Anomaly(
                anomaly_type=AnomalyType.OUT_OF_ORDER,
                severity=AnomalySeverity.MEDIUM,
                trade=trade,
                message=f"Trade out of order: {trade.time} < {self._last_time}",
                expected_value=self._last_time,
                actual_value=trade.time,
                can_auto_fix=True,
            ))
    
    def _check_time_gap(self, trade: Trade, result: AnomalyResult) -> None:
        """Check for time gaps in data."""
        if self._last_time:
            gap = (trade.time - self._last_time).total_seconds()
            
            if gap > self.max_gap_seconds:
                result.add(Anomaly(
                    anomaly_type=AnomalyType.TIME_GAP,
                    severity=AnomalySeverity.HIGH if gap > 60 else AnomalySeverity.MEDIUM,
                    trade=trade,
                    message=f"Time gap detected: {gap:.1f}s",
                    expected_value=Decimal(str(self.max_gap_seconds)),
                    actual_value=Decimal(str(gap)),
                    can_auto_fix=False,
                ))
    
    def _check_stale_data(self, trade: Trade, result: AnomalyResult) -> None:
        """Check for stale data."""
        age = (datetime.utcnow() - trade.time).total_seconds()
        
        if age > self.stale_data_seconds:
            result.add(Anomaly(
                anomaly_type=AnomalyType.STALE_DATA,
                severity=AnomalySeverity.MEDIUM if age < 300 else AnomalySeverity.HIGH,
                trade=trade,
                message=f"Stale data: {age:.0f}s old",
                expected_value=Decimal(str(self.stale_data_seconds)),
                actual_value=Decimal(str(age)),
                can_auto_fix=False,
            ))
    
    def _check_price_spike(self, trade: Trade, result: AnomalyResult) -> None:
        """Check for price spikes."""
        if self._last_trade is None:
            return
        
        price_change = abs(trade.price - self._last_trade.price)
        pct_change = (price_change / self._last_trade.price) * Decimal("100")
        
        if pct_change > self.price_spike_threshold:
            is_spike = trade.price > self._last_trade.price
            result.add(Anomaly(
                anomaly_type=AnomalyType.PRICE_SPIKE if is_spike else AnomalyType.PRICE_DROP,
                severity=AnomalySeverity.CRITICAL if pct_change > 20 else AnomalySeverity.HIGH,
                trade=trade,
                message=f"Price {'spike' if is_spike else 'drop'}: {pct_change:.2f}%",
                expected_value=self._last_trade.price,
                actual_value=trade.price,
                can_auto_fix=False,
            ))
    
    def _check_volume_spike(self, trade: Trade, result: AnomalyResult) -> None:
        """Check for volume anomalies."""
        # Update rolling average
        self._update_volume_stats(trade)
        
        if self._volume_avg is None:
            return
        
        if trade.quantity > self._volume_avg * self.volume_spike_threshold:
            result.add(Anomaly(
                anomaly_type=AnomalyType.VOLUME_SPIKE,
                severity=AnomalySeverity.MEDIUM,
                trade=trade,
                message=f"Volume spike: {trade.quantity} vs avg {self._volume_avg}",
                expected_value=self._volume_avg,
                actual_value=trade.quantity,
                can_auto_fix=False,
            ))
    
    def _check_wash_trade(self, trade: Trade, result: AnomalyResult) -> None:
        """Check for potential wash trades (same price, similar time)."""
        if self._last_trade is None:
            return
        
        time_diff = abs((trade.time - self._last_trade.time).total_seconds())
        
        if (time_diff < 1.0 and 
            trade.price == self._last_trade.price and
            trade.quantity == self._last_trade.quantity):
            result.add(Anomaly(
                anomaly_type=AnomalyType.WASH_TRADE,
                severity=AnomalySeverity.LOW,
                trade=trade,
                message="Potential wash trade detected",
                can_auto_fix=False,
            ))
    
    def _update_state(self, trade: Trade) -> None:
        """Update internal state after valid trade."""
        self._recent_trades.append(trade)
        
        # Keep only lookback window
        if len(self._recent_trades) > self.lookback_window:
            self._recent_trades.pop(0)
        
        self._last_trade = trade
        self._last_time = trade.time
        self._seen_trade_ids.add(trade.trade_id)
        
        # Limit trade ID memory
        if len(self._seen_trade_ids) > 10000:
            self._seen_trade_ids.clear()
    
    def _update_volume_stats(self, trade: Trade) -> None:
        """Update rolling volume statistics."""
        if not self._recent_trades:
            self._volume_avg = trade.quantity
            return
        
        total = sum(t.quantity for t in self._recent_trades)
        self._volume_avg = total / Decimal(len(self._recent_trades))
    
    def get_statistics(self) -> Dict:
        """
        Get current statistics.
        
        Returns:
            Dictionary with current statistics
        """
        return {
            'recent_trades': len(self._recent_trades),
            'last_price': float(self._last_trade.price) if self._last_trade else None,
            'volume_avg': float(self._volume_avg) if self._volume_avg else None,
            'seen_trade_ids': len(self._seen_trade_ids),
        }
    
    def reset(self) -> None:
        """Reset detector state."""
        self._recent_trades.clear()
        self._last_trade = None
        self._last_time = None
        self._seen_trade_ids.clear()
        self._price_std = None
        self._volume_avg = None

```

### Task 2: Gap Detector & Filler

**File**: `src/domain/services/gap_detector.py`

```python
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
    
    Attributes:
        max_gap_seconds: Maximum allowed gap before alert
        symbols: List of symbols to monitor
    
    Example:
        >>> detector = GapDetector(max_gap_seconds=5)
        >>> detector.start_monitoring(symbol_id, symbol)
        >>> gap = detector.check_tick(symbol_id, tick)
        >>> if gap:
        ...     await filler.fill_gap(gap)
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
        """
        Start monitoring a symbol for gaps.
        
        Args:
            symbol_id: Symbol ID
            symbol: Symbol string
        """
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
                symbol=f"SYMBOL_{symbol_id}",  # Will be updated
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
    
    Attributes:
        db_pool: Database connection pool
    
    Example:
        >>> filler = GapFiller(db_pool)
        >>> result = await filler.fill_gap(gap)
        >>> if result.success:
        ...     logger.info(f"Filled {result.ticks_filled} ticks")
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
        """
        Fetch historical data from exchange.
        
        Args:
            symbol_id: Symbol ID
            start: Gap start time
            end: Gap end time
        
        Returns:
            List of tick data
        """
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
        """
        Store fetched ticks in database.
        
        Args:
            symbol_id: Symbol ID
            ticks: List of tick data
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
                ]
            )

```

### Task 3: Quality Metrics Tracker

**File**: `src/domain/services/quality_metrics.py`

```python
"""
Data quality metrics tracking service.

Tracks and reports on data quality over time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from enum import Enum


class QualityScore(Enum):
    """Quality score ranges."""
    EXCELLENT = "excellent"  # 95-100
    GOOD = "good"  # 80-94
    FAIR = "fair"  # 60-79
    POOR = "poor"  # <60


@dataclass
class QualityMetrics:
    """
    Data quality metrics for a time period.
    
    Attributes:
        symbol_id: Symbol ID
        period_start: Start of measurement period
        period_end: End of measurement period
        ticks_received: Total ticks received
        ticks_validated: Ticks that passed validation
        ticks_rejected: Ticks that failed validation
        anomalies_detected: Number of anomalies detected
        gaps_detected: Number of gaps detected
        gaps_filled: Number of gaps filled
        avg_latency_ms: Average processing latency
        quality_score: Overall quality score (0-100)
    """
    
    symbol_id: int
    period_start: datetime
    period_end: datetime
    ticks_received: int = 0
    ticks_validated: int = 0
    ticks_rejected: int = 0
    anomalies_detected: int = 0
    gaps_detected: int = 0
    gaps_filled: int = 0
    avg_latency_ms: float = 0.0
    quality_score: float = 0.0
    
    @property
    def validation_rate(self) -> float:
        """Get validation success rate."""
        if self.ticks_received == 0:
            return 0.0
        return self.ticks_validated / self.ticks_received * 100
    
    @property
    def quality_level(self) -> QualityScore:
        """Get quality level based on score."""
        if self.quality_score >= 95:
            return QualityScore.EXCELLENT
        elif self.quality_score >= 80:
            return QualityScore.GOOD
        elif self.quality_score >= 60:
            return QualityScore.FAIR
        else:
            return QualityScore.POOR


class QualityMetricsTracker:
    """
    Tracks data quality metrics over time.
    
    Attributes:
        db_pool: Database connection pool
    
    Example:
        >>> tracker = QualityMetricsTracker(db_pool)
        >>> tracker.record_tick(symbol_id, is_valid=True, latency_ms=5.2)
        >>> metrics = await tracker.get_metrics(symbol_id, hours=24)
        >>> print(f"Quality score: {metrics.quality_score}")
    """
    
    def __init__(self, db_pool) -> None:  # type: ignore
        """
        Initialize metrics tracker.
        
        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        
        # In-memory metrics (flushed to DB periodically)
        self._metrics: Dict[int, QualityMetrics] = {}
    
    def record_tick(
        self,
        symbol_id: int,
        is_valid: bool,
        latency_ms: float,
    ) -> None:
        """
        Record tick processing metrics.
        
        Args:
            symbol_id: Symbol ID
            is_valid: Whether tick passed validation
            latency_ms: Processing latency in milliseconds
        """
        if symbol_id not in self._metrics:
            self._metrics[symbol_id] = QualityMetrics(
                symbol_id=symbol_id,
                period_start=datetime.utcnow(),
                period_end=datetime.utcnow(),
            )
        
        metrics = self._metrics[symbol_id]
        metrics.ticks_received += 1
        
        if is_valid:
            metrics.ticks_validated += 1
        else:
            metrics.ticks_rejected += 1
        
        # Update rolling average latency
        n = metrics.ticks_received
        metrics.avg_latency_ms = (
            (metrics.avg_latency_ms * (n - 1) + latency_ms) / n
        )
    
    def record_anomaly(self, symbol_id: int) -> None:
        """
        Record anomaly detection.
        
        Args:
            symbol_id: Symbol ID
        """
        if symbol_id in self._metrics:
            self._metrics[symbol_id].anomalies_detected += 1
    
    def record_gap(self, symbol_id: int, is_filled: bool = False) -> None:
        """
        Record gap detection.
        
        Args:
            symbol_id: Symbol ID
            is_filled: Whether gap was filled
        """
        if symbol_id in self._metrics:
            metrics = self._metrics[symbol_id]
            metrics.gaps_detected += 1
            if is_filled:
                metrics.gaps_filled += 1
    
    def calculate_quality_score(self, symbol_id: int) -> float:
        """
        Calculate quality score for symbol.
        
        Score based on:
        - Validation rate (50%)
        - Gap rate (30%)
        - Anomaly rate (20%)
        
        Args:
            symbol_id: Symbol ID
        
        Returns:
            Quality score (0-100)
        """
        if symbol_id not in self._metrics:
            return 0.0
        
        metrics = self._metrics[symbol_id]
        
        # Validation rate component (50%)
        validation_component = metrics.validation_rate * 0.5
        
        # Gap rate component (30%)
        gap_rate = 0.0
        if metrics.ticks_received > 0:
            gap_rate = metrics.gaps_detected / metrics.ticks_received * 100
        gap_component = max(0, (100 - gap_rate * 10)) * 0.3
        
        # Anomaly rate component (20%)
        anomaly_rate = 0.0
        if metrics.ticks_received > 0:
            anomaly_rate = metrics.anomalies_detected / metrics.ticks_received * 100
        anomaly_component = max(0, (100 - anomaly_rate * 5)) * 0.2
        
        score = validation_component + gap_component + anomaly_component
        metrics.quality_score = score
        
        return score
    
    async def flush_to_database(self, symbol_id: int) -> None:
        """
        Flush metrics to database.
        
        Args:
            symbol_id: Symbol ID to flush
        """
        if symbol_id not in self._metrics:
            return
        
        metrics = self._metrics[symbol_id]
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO data_quality_metrics
                (symbol_id, date, hour, ticks_received, ticks_validated,
                 ticks_rejected, anomalies_detected, gaps_detected,
                 gaps_filled, avg_latency_ms, quality_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (symbol_id, date, hour) DO UPDATE SET
                    ticks_received = EXCLUDED.ticks_received,
                    ticks_validated = EXCLUDED.ticks_validated,
                    ticks_rejected = EXCLUDED.ticks_rejected,
                    anomalies_detected = EXCLUDED.anomalies_detected,
                    gaps_detected = EXCLUDED.gaps_detected,
                    gaps_filled = EXCLUDED.gaps_filled,
                    avg_latency_ms = EXCLUDED.avg_latency_ms,
                    quality_score = EXCLUDED.quality_score
                """,
                metrics.symbol_id,
                metrics.period_start.date(),
                metrics.period_start.hour,
                metrics.ticks_received,
                metrics.ticks_validated,
                metrics.ticks_rejected,
                metrics.anomalies_detected,
                metrics.gaps_detected,
                metrics.gaps_filled,
                metrics.avg_latency_ms,
                metrics.quality_score,
            )
        
        # Reset metrics for next period
        self._metrics[symbol_id] = QualityMetrics(
            symbol_id=symbol_id,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow(),
        )
    
    def get_metrics(self, symbol_id: int) -> Optional[QualityMetrics]:
        """
        Get current metrics for symbol.
        
        Args:
            symbol_id: Symbol ID
        
        Returns:
            QualityMetrics or None
        """
        return self._metrics.get(symbol_id)

```

---

## Acceptance Criteria

- [ ] AnomalyDetector with 8 anomaly types
- [ ] GapDetector for real-time gap detection
- [ ] GapFiller for backfilling missing data
- [ ] QualityMetricsTracker for quality scoring
- [ ] Unit tests for all services (85%+ coverage)
- [ ] Integration with data collection service

---

## Next Steps

After completing this step, proceed to **Step 018: Ticker Collector**
