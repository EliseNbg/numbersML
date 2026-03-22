"""
Symbol entity - Trading pair representation.

Represents a cryptocurrency trading pair (e.g., BTC/USDT) with
all configuration, validation rules, and regional compliance.
"""

from dataclasses import dataclass
from decimal import Decimal
from src.domain.models.base import Entity


@dataclass
class Symbol(Entity):
    """
    Trading pair symbol (e.g., BTC/USDT).
    
    Attributes:
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        base_asset: Base asset code (e.g., "BTC")
        quote_asset: Quote asset code (e.g., "USDT")
        tick_size: Price precision (e.g., 0.01)
        step_size: Quantity precision (e.g., 0.00001)
        min_notional: Minimum order value (e.g., 10 USDT)
        is_allowed: EU compliance flag
        is_active: Collection active flag
    """
    
    symbol: str = ""
    base_asset: str = ""
    quote_asset: str = ""
    exchange: str = "binance"
    tick_size: Decimal = Decimal("0.00000001")
    step_size: Decimal = Decimal("0.00000001")
    min_notional: Decimal = Decimal("10")
    is_allowed: bool = True
    is_active: bool = False
    
    def __post_init__(self) -> None:
        """Validate invariants."""
        self._validate_symbol_format()
        self._validate_trading_params()
    
    def _validate_symbol_format(self) -> None:
        """Validate symbol format (BASE/QUOTE)."""
        if not self.symbol or '/' not in self.symbol:
            raise ValueError(f"Invalid symbol format: {self.symbol}")
    
    def _validate_trading_params(self) -> None:
        """Validate trading parameters."""
        if self.tick_size <= 0:
            raise ValueError(f"tick_size must be positive: {self.tick_size}")
        if self.step_size <= 0:
            raise ValueError(f"step_size must be positive: {self.step_size}")
        if self.min_notional < 0:
            raise ValueError(f"min_notional must be non-negative: {self.min_notional}")
    
    def activate(self) -> None:
        """Activate symbol for data collection."""
        self.is_active = True
    
    def deactivate(self) -> None:
        """Deactivate symbol."""
        self.is_active = False
    
    def price_to_tick(self, price: Decimal) -> Decimal:
        """Round price to tick size."""
        return (price / self.tick_size).quantize(Decimal('1')) * self.tick_size
    
    def quantity_to_step(self, quantity: Decimal) -> Decimal:
        """Round quantity to step size."""
        return (quantity / self.step_size).quantize(Decimal('1')) * self.step_size
    
    def is_valid_order(self, price: Decimal, quantity: Decimal) -> tuple[bool, str]:
        """
        Validate order parameters.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        notional = price * quantity
        
        if notional < self.min_notional:
            return False, f"Order value {notional} below minimum {self.min_notional}"
        
        return True, ""
