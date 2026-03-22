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
        can_auto_fix: Whether anomaly can be automatically fixed
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
        """Check for potential wash trades."""
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
        
        if len(self._recent_trades) > self.lookback_window:
            self._recent_trades.pop(0)
        
        self._last_trade = trade
        self._last_time = trade.time
        self._seen_trade_ids.add(trade.trade_id)
        
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
        """Get current statistics."""
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
        self._volume_avg = None
