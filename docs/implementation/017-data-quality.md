# Step 017: Data Quality Framework

## Context

**Phase**: 2 - Production Hardening  
**Effort**: 8 hours  
**Priority**: **CRITICAL**  
**Dependencies**: Step 002 (Database Schema), Step 004 (Data Collection)

---

## Problem Statement

**Current State**: System blindly accepts any tick data from exchanges

**Risk**:
- Bad ticks → wrong indicators → wrong signals → **financial losses**
- Exchange glitches (fat-finger trades) corrupt database
- No way to distinguish good vs bad data

**Real Examples**:
- 2022-04-11: Binance BTC/USDT flash crash to $1 (fat finger)
- 2021-05-19: Coinbase ETH spike to $9,000 (exchange bug)
- Time synchronization issues causing "time travel" ticks

---

## Goal

Implement comprehensive data quality validation:
1. Price sanity checks (no 1000% moves)
2. Time monotonicity (no time travel)
3. Precision validation (tick_size, step_size)
4. Duplicate detection
5. Stale data detection
6. Quality metrics tracking

---

## Domain Model

### Value Objects

```python
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from enum import Enum

class Severity(Enum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class IssueType(Enum):
    PRICE_SPIKE = "price_spike"
    TIME_TRAVEL = "time_travel"
    DUPLICATE = "duplicate"
    STALE_DATA = "stale_data"
    PRECISION_ERROR = "precision_error"
    QUANTITY_SPIKE = "quantity_spike"

@dataclass
class ValidationResult:
    """Result of tick validation."""
    passed: bool
    errors: List[str]
    warnings: List[str]
    severity: Optional[Severity] = None

@dataclass
class DataQualityIssue:
    """Represents a data quality issue."""
    symbol_id: int
    symbol: str
    issue_type: IssueType
    severity: Severity
    raw_data: dict
    expected_value: Optional[Decimal]
    actual_value: Optional[Decimal]
    message: str
    detected_at: datetime = datetime.utcnow()
    resolved: bool = False
```

---

## Implementation Tasks

### Task 17.1: Tick Validator

**File**: `src/domain/services/tick_validator.py`

```python
"""Tick data quality validation."""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from ..models.symbol import Symbol
from ..models.trade import Trade
from .validation_result import ValidationResult, Severity, IssueType

logger = logging.getLogger(__name__)


class TickValidator:
    """
    Validates tick data before storage.
    
    Rules:
    1. Price sanity: No >10% move in 1 second
    2. Time monotonicity: No "time travel" (future ticks)
    3. Price precision: Aligns with tick_size
    4. Quantity precision: Aligns with step_size
    5. Not duplicate: Same trade_id
    6. Not stale: Data is recent (< 60 seconds old)
    """
    
    def __init__(
        self,
        symbol: Symbol,
        max_price_move_pct: Decimal = Decimal("0.10"),  # 10%
        max_quantity_move_pct: Decimal = Decimal("0.50"),  # 50%
        max_stale_seconds: int = 60,
    ):
        self.symbol = symbol
        self.max_price_move_pct = max_price_move_pct
        self.max_quantity_move_pct = max_quantity_move_pct
        self.max_stale_seconds = max_stale_seconds
        
        # State for comparison
        self._last_price: Optional[Decimal] = None
        self._last_quantity: Optional[Decimal] = None
        self._last_time: Optional[datetime] = None
        self._seen_trade_ids: set = set()
    
    def validate(self, tick: Trade) -> ValidationResult:
        """
        Validate tick against all rules.
        
        Returns:
            ValidationResult with pass/fail status and errors
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        # Run all checks
        checks = [
            self._check_price_sanity(tick),
            self._check_quantity_sanity(tick),
            self._check_time_monotonicity(tick),
            self._check_price_precision(tick),
            self._check_quantity_precision(tick),
            self._check_not_duplicate(tick),
            self._check_not_stale(tick),
        ]
        
        # Collect errors and warnings
        for check in checks:
            if not check.passed:
                if check.severity == Severity.ERROR:
                    errors.append(check.message)
                else:
                    warnings.append(check.message)
        
        # Update state if valid
        if not errors:
            self._update_state(tick)
        
        return ValidationResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            severity=self._calculate_severity(errors, warnings)
        )
    
    def _check_price_sanity(self, tick: Trade) -> CheckResult:
        """Price shouldn't move >X% in 1 second."""
        if self._last_price is None:
            return CheckResult.passed()
        
        # Calculate price change
        price_change = abs(tick.price - self._last_price)
        pct_change = price_change / self._last_price
        
        if pct_change > self.max_price_move_pct:
            return CheckResult.failed(
                Severity.ERROR,
                f"Price move {pct_change:.2%} exceeds {self.max_price_move_pct:.2%} threshold",
                expected_value=self._last_price,
                actual_value=tick.price,
            )
        
        # Warning for >5% move
        if pct_change > Decimal("0.05"):
            return CheckResult.warning(
                f"Large price move: {pct_change:.2%}"
            )
        
        return CheckResult.passed()
    
    def _check_quantity_sanity(self, tick: Trade) -> CheckResult:
        """Quantity shouldn't spike abnormally."""
        if self._last_quantity is None:
            return CheckResult.passed()
        
        # Calculate quantity change
        qty_change = abs(tick.quantity - self._last_quantity)
        pct_change = qty_change / self._last_quantity if self._last_quantity > 0 else Decimal(0)
        
        if pct_change > self.max_quantity_move_pct:
            return CheckResult.warning(
                f"Quantity spike: {pct_change:.2%}"
            )
        
        return CheckResult.passed()
    
    def _check_time_monotonicity(self, tick: Trade) -> CheckResult:
        """Time should move forward (no time travel)."""
        if self._last_time is None:
            return CheckResult.passed()
        
        # Allow small clock skew (1 second)
        if tick.time < self._last_time - timedelta(seconds=1):
            return CheckResult.failed(
                Severity.ERROR,
                f"Time travel detected: {tick.time} < {self._last_time}",
                expected_value=self._last_time,
                actual_value=tick.time,
            )
        
        # Warning for future ticks
        if tick.time > datetime.utcnow() + timedelta(seconds=5):
            return CheckResult.warning(
                f"Future tick: {tick.time}"
            )
        
        return CheckResult.passed()
    
    def _check_price_precision(self, tick: Trade) -> CheckResult:
        """Price should align with tick_size."""
        remainder = tick.price % self.symbol.tick_size
        
        # Allow small floating point errors
        if remainder > self.symbol.tick_size * Decimal("0.0001"):
            return CheckResult.failed(
                Severity.ERROR,
                f"Price {tick.price} not aligned with tick_size {self.symbol.tick_size}",
                expected_value=self.symbol.tick_size,
                actual_value=tick.price,
            )
        
        return CheckResult.passed()
    
    def _check_quantity_precision(self, tick: Trade) -> CheckResult:
        """Quantity should align with step_size."""
        remainder = tick.quantity % self.symbol.step_size
        
        if remainder > self.symbol.step_size * Decimal("0.0001"):
            return CheckResult.failed(
                Severity.ERROR,
                f"Quantity {tick.quantity} not aligned with step_size {self.symbol.step_size}",
                expected_value=self.symbol.step_size,
                actual_value=tick.quantity,
            )
        
        return CheckResult.passed()
    
    def _check_not_duplicate(self, tick: Trade) -> CheckResult:
        """Trade ID should be unique."""
        if tick.trade_id in self._seen_trade_ids:
            return CheckResult.failed(
                Severity.ERROR,
                f"Duplicate trade ID: {tick.trade_id}",
                actual_value=tick.trade_id,
            )
        
        # Keep last 10000 trade IDs in memory
        self._seen_trade_ids.add(tick.trade_id)
        if len(self._seen_trade_ids) > 10000:
            # Remove oldest (arbitrary, just keep memory bounded)
            self._seen_trade_ids.pop()
        
        return CheckResult.passed()
    
    def _check_not_stale(self, tick: Trade) -> CheckResult:
        """Data should be recent."""
        age = datetime.utcnow() - tick.time
        
        if age > timedelta(seconds=self.max_stale_seconds):
            return CheckResult.warning(
                f"Stale data: {age.total_seconds():.0f}s old"
            )
        
        return CheckResult.passed()
    
    def _update_state(self, tick: Trade):
        """Update internal state after valid tick."""
        self._last_price = tick.price
        self._last_quantity = tick.quantity
        self._last_time = tick.time
    
    def _calculate_severity(
        self, 
        errors: List[str], 
        warnings: List[str]
    ) -> Optional[Severity]:
        """Calculate overall severity."""
        if errors:
            return Severity.ERROR
        if warnings:
            return Severity.WARNING
        return None
    
    def reset(self):
        """Reset validator state."""
        self._last_price = None
        self._last_quantity = None
        self._last_time = None
        self._seen_trade_ids.clear()
```

---

### Task 17.2: Check Result Helper

**File**: `src/domain/services/check_result.py`

```python
"""Validation check result."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from .validation_result import Severity


@dataclass
class CheckResult:
    """Result of a single validation check."""
    
    passed: bool
    severity: Severity = Severity.WARNING
    message: str = ""
    expected_value: Optional[Decimal] = None
    actual_value: Optional[Decimal] = None
    
    @classmethod
    def passed(cls) -> "CheckResult":
        """Create passed result."""
        return cls(passed=True)
    
    @classmethod
    def failed(
        cls,
        severity: Severity,
        message: str,
        expected_value: Optional[Decimal] = None,
        actual_value: Optional[Decimal] = None,
    ) -> "CheckResult":
        """Create failed result."""
        return cls(
            passed=False,
            severity=severity,
            message=message,
            expected_value=expected_value,
            actual_value=actual_value,
        )
    
    @classmethod
    def warning(cls, message: str) -> "CheckResult":
        """Create warning result."""
        return cls(
            passed=True,  # Warnings don't fail validation
            severity=Severity.WARNING,
            message=message,
        )
```

---

### Task 17.3: Data Quality Database Schema

**File**: `migrations/002_data_quality.sql`

```sql
-- Migration: 002_data_quality
-- Description: Add data quality tracking tables

-- Track data quality issues
CREATE TABLE IF NOT EXISTS data_quality_issues (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    symbol TEXT NOT NULL,
    issue_type TEXT NOT NULL,  -- 'price_spike', 'time_travel', 'duplicate', etc.
    severity TEXT NOT NULL,    -- 'warning', 'error', 'critical'
    
    -- Raw data that caused the issue
    raw_data JSONB NOT NULL,
    
    -- Expected vs actual values
    expected_value NUMERIC,
    actual_value NUMERIC,
    
    -- Message describing the issue
    message TEXT NOT NULL,
    
    -- Timestamps
    detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved BOOLEAN NOT NULL DEFAULT false,
    resolved_at TIMESTAMP,
    resolved_by TEXT,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_quality_issues_symbol ON data_quality_issues(symbol_id);
CREATE INDEX idx_quality_issues_unresolved ON data_quality_issues(resolved) 
    WHERE resolved = false;
CREATE INDEX idx_quality_issues_type ON data_quality_issues(issue_type);
CREATE INDEX idx_quality_issues_severity ON data_quality_issues(severity);
CREATE INDEX idx_quality_issues_detected_at ON data_quality_issues(detected_at DESC);

-- Data quality metrics (aggregated per hour)
CREATE TABLE IF NOT EXISTS data_quality_metrics (
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    date DATE NOT NULL,
    hour INTEGER NOT NULL,  -- 0-23
    
    -- Tick counts
    ticks_received BIGINT NOT NULL DEFAULT 0,
    ticks_validated BIGINT NOT NULL DEFAULT 0,
    ticks_rejected BIGINT NOT NULL DEFAULT 0,
    
    -- Latency metrics (milliseconds)
    latency_p50_ms NUMERIC(10,2),
    latency_p95_ms NUMERIC(10,2),
    latency_p99_ms NUMERIC(10,2),
    
    -- Gap metrics
    gap_count INTEGER NOT NULL DEFAULT 0,
    gap_total_seconds INTEGER NOT NULL DEFAULT 0,
    
    -- Issue counts by type
    price_spike_count INTEGER NOT NULL DEFAULT 0,
    time_travel_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    stale_data_count INTEGER NOT NULL DEFAULT 0,
    
    -- Quality score (0-100)
    quality_score NUMERIC(5,2),
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (symbol_id, date, hour)
);

CREATE INDEX idx_quality_metrics_date ON data_quality_metrics(date DESC, hour);
CREATE INDEX idx_quality_metrics_score ON data_quality_metrics(quality_score);

-- Helper function to calculate quality score
CREATE OR REPLACE FUNCTION calculate_quality_score(
    p_ticks_validated BIGINT,
    p_ticks_rejected BIGINT,
    p_gap_seconds BIGINT
) RETURNS NUMERIC AS $$
BEGIN
    -- Simple formula:
    -- 100 - (rejection_rate * 100) - (gap_seconds / 60)
    -- Min score: 0, Max score: 100
    
    IF p_ticks_validated = 0 THEN
        RETURN 0;
    END IF;
    
    RETURN GREATEST(0, LEAST(100,
        100.0 
        - (p_ticks_rejected::NUMERIC / p_ticks_validated * 100)
        - (p_gap_seconds::NUMERIC / 60)
    ));
END;
$$ LANGUAGE plpgsql;
```

---

### Task 17.4: Quality Tracker Service

**File**: `src/application/services/quality_tracker.py`

```python
"""Data quality tracking service."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
import asyncpg
import logging

from ..domain.services.tick_validator import TickValidator, ValidationResult
from ..domain.models.trade import Trade
from ..domain.models.symbol import Symbol

logger = logging.getLogger(__name__)


class QualityTracker:
    """
    Tracks and reports data quality metrics.
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self._validators: Dict[int, TickValidator] = {}  # symbol_id -> validator
        self._metrics: Dict[int, Dict] = {}  # symbol_id -> hourly metrics
    
    def get_validator(self, symbol: Symbol) -> TickValidator:
        """Get or create validator for symbol."""
        if symbol.id not in self._validators:
            self._validators[symbol.id] = TickValidator(symbol)
        return self._validators[symbol.id]
    
    async def validate_and_track(
        self, 
        tick: Trade, 
        symbol: Symbol
    ) -> ValidationResult:
        """
        Validate tick and track quality metrics.
        
        Returns:
            ValidationResult with pass/fail status
        """
        validator = self.get_validator(symbol)
        result = validator.validate(tick)
        
        # Track metrics
        await self._track_validation(symbol.id, tick, result)
        
        # Log and store issues
        if not result.passed or result.warnings:
            await self._record_issue(symbol, tick, result)
        
        return result
    
    async def _track_validation(
        self, 
        symbol_id: int, 
        tick: Trade, 
        result: ValidationResult
    ):
        """Track validation metrics."""
        now = datetime.utcnow()
        hour = now.hour
        date = now.date()
        
        # Initialize metrics if needed
        if symbol_id not in self._metrics:
            self._metrics[symbol_id] = {}
        
        key = (date, hour)
        if key not in self._metrics[symbol_id]:
            self._metrics[symbol_id][key] = {
                'ticks_received': 0,
                'ticks_validated': 0,
                'ticks_rejected': 0,
                'latencies': [],
            }
        
        metrics = self._metrics[symbol_id][key]
        metrics['ticks_received'] += 1
        
        if result.passed:
            metrics['ticks_validated'] += 1
        else:
            metrics['ticks_rejected'] += 1
        
        # Track latency (if tick has timestamp)
        if hasattr(tick, 'received_at') and tick.received_at:
            latency_ms = (now - tick.received_at).total_seconds() * 1000
            metrics['latencies'].append(latency_ms)
        
        # Flush metrics every hour
        if now.minute == 0 and now.second < 10:
            await self._flush_metrics(symbol_id, date, hour - 1)
    
    async def _record_issue(
        self, 
        symbol: Symbol, 
        tick: Trade, 
        result: ValidationResult
    ):
        """Record data quality issue to database."""
        if not result.errors and not result.warnings:
            return
        
        async with self.db_pool.acquire() as conn:
            for error in result.errors:
                await conn.execute(
                    """
                    INSERT INTO data_quality_issues 
                    (symbol_id, symbol, issue_type, severity, raw_data, message)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    symbol.id,
                    symbol.symbol,
                    self._extract_issue_type(error),
                    result.severity.value if result.severity else 'warning',
                    {'trade_id': tick.trade_id, 'price': str(tick.price)},
                    error,
                )
    
    def _extract_issue_type(self, error: str) -> str:
        """Extract issue type from error message."""
        if 'Price move' in error:
            return 'price_spike'
        if 'Time travel' in error:
            return 'time_travel'
        if 'Duplicate' in error:
            return 'duplicate'
        if 'Stale' in error:
            return 'stale_data'
        if 'not aligned' in error:
            return 'precision_error'
        return 'unknown'
    
    async def _flush_metrics(
        self, 
        symbol_id: int, 
        date: datetime.date, 
        hour: int
    ):
        """Flush hourly metrics to database."""
        if symbol_id not in self._metrics:
            return
        
        key = (date, hour)
        if key not in self._metrics[symbol_id]:
            return
        
        metrics = self._metrics[symbol_id][key]
        
        # Calculate latency percentiles
        latencies = sorted(metrics['latencies'])
        p50 = self._percentile(latencies, 50) if latencies else None
        p95 = self._percentile(latencies, 95) if latencies else None
        p99 = self._percentile(latencies, 99) if latencies else None
        
        # Calculate quality score
        quality_score = await self._calculate_quality_score(
            metrics['ticks_validated'],
            metrics['ticks_rejected'],
            0,  # gap_seconds (tracked separately)
        )
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO data_quality_metrics 
                (symbol_id, date, hour, ticks_received, ticks_validated, 
                 ticks_rejected, latency_p50_ms, latency_p95_ms, latency_p99_ms,
                 quality_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (symbol_id, date, hour) DO UPDATE SET
                    ticks_received = EXCLUDED.ticks_received,
                    ticks_validated = EXCLUDED.ticks_validated,
                    ticks_rejected = EXCLUDED.ticks_rejected,
                    latency_p50_ms = EXCLUDED.latency_p50_ms,
                    latency_p95_ms = EXCLUDED.latency_p95_ms,
                    latency_p99_ms = EXCLUDED.latency_p99_ms,
                    quality_score = EXCLUDED.quality_score,
                    updated_at = NOW()
                """,
                symbol_id, date, hour,
                metrics['ticks_received'],
                metrics['ticks_validated'],
                metrics['ticks_rejected'],
                p50, p95, p99,
                quality_score,
            )
        
        # Clean up old metrics
        del self._metrics[symbol_id][key]
    
    def _percentile(self, sorted_list: List[float], percentile: int) -> float:
        """Calculate percentile from sorted list."""
        if not sorted_list:
            return None
        
        k = (len(sorted_list) - 1) * percentile / 100
        f = int(k)
        c = f + 1
        
        if c >= len(sorted_list):
            return sorted_list[-1]
        
        return sorted_list[f] + (k - f) * (sorted_list[c] - sorted_list[f])
    
    async def _calculate_quality_score(
        self, 
        validated: int, 
        rejected: int, 
        gap_seconds: int
    ) -> Decimal:
        """Calculate quality score."""
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT calculate_quality_score($1, $2, $3)",
                validated, rejected, gap_seconds
            )
            return result or Decimal("0")
    
    async def get_quality_summary(
        self, 
        symbol_id: int, 
        hours: int = 24
    ) -> Dict:
        """Get quality summary for symbol."""
        async with self.db_pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT 
                    SUM(ticks_received) AS total_ticks,
                    SUM(ticks_validated) AS validated_ticks,
                    SUM(ticks_rejected) AS rejected_ticks,
                    AVG(quality_score) AS avg_quality_score,
                    AVG(latency_p99_ms) AS avg_latency_p99
                FROM data_quality_metrics
                WHERE symbol_id = $1
                  AND (date > CURRENT_DATE - INTERVAL '1 day' * $2)
                """,
                symbol_id, hours // 24 + 1
            )
```

---

### Task 17.5: Update Data Collection Service

**File**: `src/infrastructure/exchanges/data_collector.py` (update from Step 004)

```python
# Add to DataCollectionService from Step 004

class DataCollectionService:
    def __init__(self, ...):
        # ... existing init ...
        
        # Add quality tracker
        self.quality_tracker = QualityTracker(self._db_pool)
    
    async def _process_trade_msg(self, msg: str):
        """Process incoming trade message with validation."""
        data = json.loads(msg)
        
        if data.get('e') != 'trade':
            return
        
        # Parse trade
        tick = self._parse_tick(data)
        
        # Get symbol
        symbol = await self._get_symbol(tick.symbol_id)
        
        # VALIDATE TICKET (NEW)
        result = await self.quality_tracker.validate_and_track(tick, symbol)
        
        if not result.passed:
            logger.error(
                f"Tick validation failed for {symbol.symbol}: {result.errors}"
            )
            
            # Alert on critical issues
            if result.severity == Severity.CRITICAL:
                await self.alert_service.send_alert(
                    severity='critical',
                    message=f"Data quality critical: {symbol.symbol} - {result.errors}",
                )
            
            # Skip invalid ticks
            return
        
        # Store valid tick
        await self._store_tick(tick)
```

---

## Test Requirements

### Test Coverage Target: **85%**

### Unit Tests

**File**: `tests/unit/domain/services/test_tick_validator.py`

```python
"""Test tick validator."""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from src.domain.services.tick_validator import TickValidator
from src.domain.models.symbol import Symbol
from src.domain.models.trade import Trade


class TestTickValidator:
    """Test TickValidator class."""
    
    @pytest.fixture
    def btc_symbol(self):
        """Create BTC/USDT symbol for testing."""
        return Symbol(
            id=1,
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
        )
    
    def test_valid_tick_passes(self, btc_symbol):
        """Test valid tick passes validation."""
        validator = TickValidator(btc_symbol)
        
        tick = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="123",
            price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
        )
        
        result = validator.validate(tick)
        
        assert result.passed is True
        assert len(result.errors) == 0
    
    def test_price_spike_fails(self, btc_symbol):
        """Test price spike detection."""
        validator = TickValidator(btc_symbol)
        
        # First tick at $50,000
        tick1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="1",
            price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
        )
        validator.validate(tick1)
        
        # Second tick at $60,000 (20% move)
        tick2 = Trade(
            time=datetime.utcnow() + timedelta(seconds=1),
            symbol_id=1,
            trade_id="2",
            price=Decimal("60000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
        )
        
        result = validator.validate(tick2)
        
        assert result.passed is False
        assert "Price move" in result.errors[0]
        assert "20.00%" in result.errors[0]
    
    def test_time_travel_fails(self, btc_symbol):
        """Test time travel detection."""
        validator = TickValidator(btc_symbol)
        
        # First tick at current time
        tick1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="1",
            price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
        )
        validator.validate(tick1)
        
        # Second tick 10 seconds in the past
        tick2 = Trade(
            time=datetime.utcnow() - timedelta(seconds=10),
            symbol_id=1,
            trade_id="2",
            price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
        )
        
        result = validator.validate(tick2)
        
        assert result.passed is False
        assert "Time travel" in result.errors[0]
    
    def test_duplicate_fails(self, btc_symbol):
        """Test duplicate detection."""
        validator = TickValidator(btc_symbol)
        
        tick = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="SAME_ID",
            price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
        )
        
        # First submission passes
        result1 = validator.validate(tick)
        assert result1.passed is True
        
        # Second submission fails
        result2 = validator.validate(tick)
        assert result2.passed is False
        assert "Duplicate" in result2.errors[0]
    
    def test_precision_error_fails(self, btc_symbol):
        """Test price precision validation."""
        validator = TickValidator(btc_symbol)
        
        tick = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="1",
            price=Decimal("50000.001"),  # Not aligned with 0.01 tick_size
            quantity=Decimal("0.001"),
            side="BUY",
        )
        
        result = validator.validate(tick)
        
        assert result.passed is False
        assert "not aligned" in result.errors[0]
```

### Integration Tests

**File**: `tests/integration/services/test_quality_tracker.py`

```python
"""Test quality tracker with real database."""

import pytest
import asyncpg
from testcontainers.postgres import PostgresContainer
from src.application.services.quality_tracker import QualityTracker


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quality_tracker_records_issues(postgres_container):
    """Test quality tracker records validation issues."""
    dsn = postgres_container.get_connection_url()
    pool = await asyncpg.create_pool(dsn)
    
    try:
        # Run migrations
        await pool.execute(migration_sql)
        
        tracker = QualityTracker(pool)
        
        # Create symbol
        symbol = Symbol(
            id=1,
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
        )
        
        # Create invalid tick (price spike)
        tick1 = Trade(
            time=datetime.utcnow(),
            symbol_id=1,
            trade_id="1",
            price=Decimal("50000.00"),
            quantity=Decimal("0.001"),
            side="BUY",
        )
        
        tick2 = Trade(
            time=datetime.utcnow() + timedelta(seconds=1),
            symbol_id=1,
            trade_id="2",
            price=Decimal("60000.00"),  # 20% spike
            quantity=Decimal("0.001"),
            side="BUY",
        )
        
        # Validate ticks
        await tracker.validate_and_track(tick1, symbol)
        result2 = await tracker.validate_and_track(tick2, symbol)
        
        # Second tick should fail
        assert result2.passed is False
        
        # Check issue was recorded
        async with pool.acquire() as conn:
            issues = await conn.fetch(
                "SELECT * FROM data_quality_issues WHERE symbol_id = 1"
            )
            assert len(issues) == 1
            assert issues[0]['issue_type'] == 'price_spike'
    
    finally:
        await pool.close()
```

---

## Acceptance Criteria

- [ ] TickValidator implemented with all checks
- [ ] Price sanity check (configurable threshold)
- [ ] Time monotonicity check
- [ ] Precision validation (tick_size, step_size)
- [ ] Duplicate detection
- [ ] Stale data detection
- [ ] Data quality database tables created
- [ ] QualityTracker service implemented
- [ ] Metrics tracked per hour
- [ ] Quality score calculated
- [ ] Data collection service updated to validate
- [ ] Unit tests pass (85%+ coverage)
- [ ] Integration tests pass

---

## Verification Commands

```bash
# Run unit tests
pytest tests/unit/domain/services/test_tick_validator.py -v --cov

# Run integration tests
pytest tests/integration/services/test_quality_tracker.py -v --cov

# Check quality issues in database
psql postgresql://crypto:crypto@localhost/crypto_trading_dev

SELECT 
    symbol, 
    issue_type, 
    severity, 
    message, 
    detected_at
FROM data_quality_issues
WHERE resolved = false
ORDER BY detected_at DESC
LIMIT 10;

-- Check quality metrics
SELECT 
    s.symbol,
    dm.date,
    dm.hour,
    dm.ticks_received,
    dm.ticks_validated,
    dm.ticks_rejected,
    dm.quality_score,
    dm.latency_p99_ms
FROM data_quality_metrics dm
JOIN symbols s ON s.id = dm.symbol_id
ORDER BY dm.date DESC, dm.hour DESC
LIMIT 24;
```

---

## Next Step

After completing this step, proceed to **[018-circuit-breaker-pattern.md](018-circuit-breaker-pattern.md)**
