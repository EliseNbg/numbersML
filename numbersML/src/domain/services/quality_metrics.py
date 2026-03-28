"""
Data quality metrics tracking service.

Tracks and reports on data quality over time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional
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
                period_start=datetime.now(timezone.utc),
                period_end=datetime.now(timezone.utc),
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
        """Record anomaly detection."""
        if symbol_id in self._metrics:
            self._metrics[symbol_id].anomalies_detected += 1
    
    def record_gap(self, symbol_id: int, is_filled: bool = False) -> None:
        """Record gap detection."""
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
        """Flush metrics to database."""
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
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
        )
    
    def get_metrics(self, symbol_id: int) -> Optional[QualityMetrics]:
        """Get current metrics for symbol."""
        return self._metrics.get(symbol_id)
