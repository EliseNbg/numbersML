"""
Tick validation service.

Validates incoming tick data to ensure data quality before storage.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List
from src.domain.models.symbol import Symbol
from src.domain.models.trade import Trade


@dataclass
class ValidationResult:
    """
    Result of tick validation.
    
    Attributes:
        is_valid: True if tick passed all validation rules
        errors: List of error messages (critical issues)
        warnings: List of warning messages (non-critical)
    """
    
    is_valid: bool = True
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self) -> None:
        """Initialize error and warning lists."""
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class TickValidator:
    """
    Validates tick data before storage.
    
    Applies validation rules:
    - Price sanity (no extreme moves)
    - Time monotonicity (no time travel)
    - Precision (aligned with tick_size/step_size)
    - Duplicates detection
    - Stale data detection
    """
    
    def __init__(
        self,
        symbol: Symbol,
        max_price_move_pct: Decimal = Decimal("10.0"),
        max_gap_seconds: int = 5,
    ) -> None:
        """
        Initialize tick validator.
        
        Args:
            symbol: Symbol being validated
            max_price_move_pct: Maximum allowed price move % (default: 10%)
            max_gap_seconds: Maximum allowed time gap (default: 5 seconds)
        """
        self.symbol: Symbol = symbol
        self.max_price_move_pct: Decimal = max_price_move_pct
        self.max_gap_seconds: int = max_gap_seconds
        
        # State for comparison
        self._last_price: Optional[Decimal] = None
        self._last_time: Optional[datetime] = None
        self._seen_trade_ids: set = set()
    
    def validate(self, tick: Trade) -> ValidationResult:
        """
        Validate tick against all rules.
        
        Args:
            tick: Tick to validate
        
        Returns:
            ValidationResult with validation status
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        # Run all validation checks
        self._check_price_sanity(tick, errors, warnings)
        self._check_time_monotonicity(tick, errors, warnings)
        self._check_precision(tick, errors, warnings)
        self._check_duplicate(tick, errors, warnings)
        
        # Update state if valid
        if not errors:
            self._update_state(tick)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    def _check_price_sanity(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Check price sanity (no extreme moves)."""
        if self._last_price is None:
            return
        
        price_change = abs(tick.price - self._last_price)
        pct_change = price_change / self._last_price * Decimal("100")
        
        if pct_change > self.max_price_move_pct:
            errors.append(
                f"Price move {pct_change:.2f}% exceeds maximum {self.max_price_move_pct}%"
            )
        elif pct_change > self.max_price_move_pct / 2:
            warnings.append(f"Large price move detected: {pct_change:.2f}%")
    
    def _check_time_monotonicity(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Check time monotonicity (no time travel)."""
        if self._last_time is None:
            return
        
        if tick.time < self._last_time:
            errors.append(f"Time travel detected: {tick.time} < {self._last_time}")
        
        # Check for stale data
        age = datetime.now(timezone.utc) - tick.time
        if age > timedelta(seconds=self.max_gap_seconds * 12):
            warnings.append(f"Stale data: {age.total_seconds():.0f}s old")
    
    def _check_precision(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Check price and quantity precision."""
        if self.symbol.price_to_tick(tick.price) != tick.price:
            errors.append(
                f"Price {tick.price} not aligned with tick_size {self.symbol.tick_size}"
            )
        
        if self.symbol.quantity_to_step(tick.quantity) != tick.quantity:
            errors.append(
                f"Quantity {tick.quantity} not aligned with step_size {self.symbol.step_size}"
            )
    
    def _check_duplicate(
        self,
        tick: Trade,
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Check for duplicate trade ID."""
        if tick.trade_id in self._seen_trade_ids:
            errors.append(f"Duplicate trade ID: {tick.trade_id}")
        
        # Keep last 10000 trade IDs in memory
        self._seen_trade_ids.add(tick.trade_id)
        if len(self._seen_trade_ids) > 10000:
            self._seen_trade_ids.pop()
    
    def _update_state(self, tick: Trade) -> None:
        """Update internal state after valid tick."""
        self._last_price = tick.price
        self._last_time = tick.time
    
    def reset(self) -> None:
        """Reset validator state."""
        self._last_price = None
        self._last_time = None
        self._seen_trade_ids.clear()
