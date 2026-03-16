# Step 0: Critical Safety Infrastructure

**Status:** ⚠️ REQUIRED BEFORE ANY TRADING
**Effort:** 16-24 hours
**Dependencies:** None (implement before Step 1-6)

---

## 🎯 Objective

Implement critical safety infrastructure that MUST be in place before any live trading. This step addresses the architectural weaknesses that could cause catastrophic losses.

**Key Outcomes:**
- Market data validation layer
- Order validation layer  
- Comprehensive risk management
- Paper trading mode
- Kill switches

---

## ⚠️ Why This Comes First

**95% of trading systems fail because they skip safety controls.** They build:
- ✅ Strategy engine
- ✅ Order execution
- ✅ Data ingestion
- ❌ Risk management (too late!)

**This specification ensures you're in the 5% that survive.**

---

## 📁 Deliverables

```
app/
├── domain/
│   ├── models.py              # Add ValidationResult, RiskLimits
│   └── exceptions.py          # Add ValidationException, RiskException
├── services/
│   ├── market_data_validator.py    # NEW: Data quality checks
│   ├── order_validator.py          # NEW: Order sanity checks
│   ├── risk_manager.py             # ENHANCED: Multi-layer risk
│   ├── position_reconciler.py      # NEW: Exchange reconciliation
│   └── kill_switch.py              # NEW: Emergency stops
├── adapters/
│   └── validators/
│       ├── price_bounds_validator.py
│       ├── timestamp_validator.py
│       └── volume_validator.py
└── modes/
    ├── paper_trading.py            # NEW: Simulation mode
    └── live_trading.py             # NEW: Real trading mode

tests/
├── services/
│   ├── test_market_data_validator.py
│   ├── test_order_validator.py
│   ├── test_risk_manager.py
│   ├── test_position_reconciler.py
│   └── test_kill_switch.py
└── modes/
    └── test_paper_trading.py
```

---

## 📝 Specifications

### 0.1 Market Data Validator (`app/services/market_data_validator.py`)

**Purpose:** Validate all market data before it reaches strategies.

**Implementation:**

```python
# app/services/market_data_validator.py
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, List

from app.domain.models import Candle, Tick
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class MarketDataValidator:
    """
    Validates market data quality before it reaches strategies.
    
    Prevents:
    - Strategies acting on bad data
    - Fat finger data (e.g., BTC at $1)
    - Stale data (WebSocket silent failure)
    - Anomalous volume
    """

    def __init__(self):
        # Price bounds: % deviation from fair value
        self.max_price_deviation = Decimal("0.05")  # 5%
        
        # Timestamp: max age allowed
        self.max_candle_age = timedelta(seconds=10)
        
        # Volume: sanity checks
        self.min_volume = Decimal("0.001")
        self.max_volume_multiplier = Decimal("100")  # vs. average
        
        # Spread: max bid-ask spread
        self.max_spread = Decimal("0.01")  # 1%
        
        # Track recent prices for validation
        self.recent_prices: Dict[str, List[Decimal]] = {}
        self.price_history_size = 100

    async def validate_candle(self, candle: Candle, fair_value: Optional[Decimal] = None) -> bool:
        """
        Validate candle data.
        
        Args:
            candle: Candle to validate
            fair_value: Expected price (e.g., from other exchanges)
            
        Returns:
            bool: True if valid
        """
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()
        
        try:
            # Check 1: Price bounds
            if not self._validate_price_bounds(candle, fair_value):
                logger.warning(
                    "Candle failed price validation",
                    correlation_id=correlation_id,
                    symbol=candle.symbol,
                    close=float(candle.close),
                    fair_value=float(fair_value) if fair_value else None,
                    component="market_data_validator"
                )
                return False
            
            # Check 2: Timestamp validity
            if not self._validate_timestamp(candle):
                logger.warning(
                    "Candle failed timestamp validation",
                    correlation_id=correlation_id,
                    symbol=candle.symbol,
                    timestamp=candle.timestamp.isoformat(),
                    component="market_data_validator"
                )
                return False
            
            # Check 3: Volume sanity
            if not self._validate_volume(candle):
                logger.warning(
                    "Candle failed volume validation",
                    correlation_id=correlation_id,
                    symbol=candle.symbol,
                    volume=float(candle.volume),
                    component="market_data_validator"
                )
                return False
            
            # Check 4: OHLC consistency
            if not self._validate_ohlc_consistency(candle):
                logger.warning(
                    "Candle failed OHLC validation",
                    correlation_id=correlation_id,
                    symbol=candle.symbol,
                    open=float(candle.open),
                    high=float(candle.high),
                    low=float(candle.low),
                    close=float(candle.close),
                    component="market_data_validator"
                )
                return False
            
            logger.debug(
                "Candle validated",
                correlation_id=correlation_id,
                symbol=candle.symbol,
                component="market_data_validator",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Candle validation error",
                correlation_id=correlation_id,
                symbol=candle.symbol,
                error=str(e),
                component="market_data_validator",
                exc_info=True
            )
            return False

    def _validate_price_bounds(self, candle: Candle, fair_value: Optional[Decimal]) -> bool:
        """Check if price is within reasonable bounds"""
        if fair_value is None:
            # Use recent average as fair value
            if candle.symbol in self.recent_prices and len(self.recent_prices[candle.symbol]) > 0:
                fair_value = sum(self.recent_prices[candle.symbol]) / len(self.recent_prices[candle.symbol])
            else:
                return True  # No reference, accept
        
        deviation = abs(candle.close - fair_value) / fair_value
        
        if deviation > self.max_price_deviation:
            return False
        
        # Track price for future validation
        if candle.symbol not in self.recent_prices:
            self.recent_prices[candle.symbol] = []
        self.recent_prices[candle.symbol].append(candle.close)
        
        if len(self.recent_prices[candle.symbol]) > self.price_history_size:
            self.recent_prices[candle.symbol].pop(0)
        
        return True

    def _validate_timestamp(self, candle: Candle) -> bool:
        """Check if candle timestamp is recent"""
        now = datetime.utcnow()
        age = now - candle.timestamp
        
        return age <= self.max_candle_age

    def _validate_volume(self, candle: Candle) -> bool:
        """Check if volume is reasonable"""
        if candle.volume < self.min_volume:
            return False
        
        # Check for anomalous volume vs. recent average
        # (implementation omitted for brevity)
        
        return True

    def _validate_ohlc_consistency(self, candle: Candle) -> bool:
        """Check OHLC relationships"""
        # High must be >= open, close, low
        if candle.high < candle.open or candle.high < candle.close or candle.high < candle.low:
            return False
        
        # Low must be <= open, close, high
        if candle.low > candle.open or candle.low > candle.close or candle.low > candle.high:
            return False
        
        return True

    async def validate_tick(self, tick: Tick) -> bool:
        """Validate tick data"""
        # Similar validation as candles
        pass
```

---

### 0.2 Order Validator (`app/services/order_validator.py`)

**Purpose:** Validate all orders before submission to prevent catastrophic mistakes.

**Implementation:**

```python
# app/services/order_validator.py
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict

from app.domain.models import Order, Signal
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class OrderValidator:
    """
    Validates orders before submission to exchange.
    
    Prevents:
    - Fat finger orders (wrong quantity)
    - Stale signals (old signals executed late)
    - Duplicate orders
    - Excessive risk per trade
    """

    def __init__(self):
        # Hard limits - NEVER exceed
        self.max_order_quantity = Decimal("0.01")  # BTC
        self.max_order_value = Decimal("500")  # USD
        self.max_orders_per_minute = 10
        
        # Price collars
        self.max_price_deviation = Decimal("0.01")  # 1% from market
        
        # Signal age limit
        self.max_signal_age = timedelta(seconds=5)
        
        # Track recent orders
        self.recent_orders: Dict[str, datetime] = {}  # order_id -> timestamp

    async def validate_order(self, order: Order, market_price: Decimal) -> bool:
        """
        Validate order before submission.
        
        Args:
            order: Order to validate
            market_price: Current market price
            
        Returns:
            bool: True if valid
        """
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()
        
        try:
            # Check 1: Quantity limits
            if not self._validate_quantity(order):
                logger.error(
                    "Order failed quantity validation",
                    correlation_id=correlation_id,
                    order_id=order.order_id,
                    quantity=float(order.quantity),
                    max_quantity=float(self.max_order_quantity),
                    component="order_validator"
                )
                return False
            
            # Check 2: Value limits
            if not self._validate_value(order, market_price):
                logger.error(
                    "Order failed value validation",
                    correlation_id=correlation_id,
                    order_id=order.order_id,
                    value=float(order.quantity * market_price),
                    max_value=float(self.max_order_value),
                    component="order_validator"
                )
                return False
            
            # Check 3: Rate limiting
            if not self._validate_rate_limit(order.strategy_id):
                logger.error(
                    "Order failed rate limit validation",
                    correlation_id=correlation_id,
                    order_id=order.order_id,
                    strategy_id=order.strategy_id,
                    component="order_validator"
                )
                return False
            
            # Check 4: Price collar (for limit orders)
            if order.price and not self._validate_price_collar(order, market_price):
                logger.error(
                    "Order failed price collar validation",
                    correlation_id=correlation_id,
                    order_id=order.order_id,
                    limit_price=float(order.price),
                    market_price=float(market_price),
                    component="order_validator"
                )
                return False
            
            logger.info(
                "Order validated",
                correlation_id=correlation_id,
                order_id=order.order_id,
                component="order_validator",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Order validation error",
                correlation_id=correlation_id,
                order_id=order.order_id,
                error=str(e),
                component="order_validator",
                exc_info=True
            )
            return False

    def _validate_quantity(self, order: Order) -> bool:
        """Check quantity limits"""
        return order.quantity <= self.max_order_quantity

    def _validate_value(self, order: Order, market_price: Decimal) -> bool:
        """Check notional value limits"""
        order_value = order.quantity * market_price
        return order_value <= self.max_order_value

    def _validate_rate_limit(self, strategy_id: str) -> bool:
        """Check order rate limit"""
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        
        # Count recent orders for this strategy
        recent_count = sum(
            1 for ts in self.recent_orders.values()
            if ts > minute_ago
        )
        
        return recent_count < self.max_orders_per_minute

    def _validate_price_collar(self, order: Order, market_price: Decimal) -> bool:
        """Check limit order is within price collar"""
        deviation = abs(order.price - market_price) / market_price
        return deviation <= self.max_price_deviation
```

---

### 0.3 Enhanced Risk Manager (`app/services/risk_manager.py`)

**Purpose:** Multi-layer risk management with circuit breakers.

**Implementation:**

```python
# app/services/risk_manager.py
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from app.domain.models import Signal, Order, Position
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class RiskLimits:
    """Multi-layer risk limits"""
    
    def __init__(self):
        # === Layer 1: Pre-Trade Limits ===
        self.max_order_quantity: Decimal = Decimal("0.01")  # BTC
        self.max_order_value: Decimal = Decimal("500")  # USD
        self.max_position_value: Decimal = Decimal("5000")  # USD per strategy
        
        # === Layer 2: Intra-Day Risk ===
        self.max_daily_loss: Decimal = Decimal("100")  # USD
        self.max_consecutive_losses: int = 5
        self.max_drawdown: Decimal = Decimal("0.05")  # 5%
        self.max_open_positions: int = 10
        
        # === Layer 3: Portfolio Risk ===
        self.max_total_exposure: Decimal = Decimal("10000")  # USD across all
        self.max_concentration: Decimal = Decimal("0.30")  # 30% in one symbol
        self.max_leverage: Decimal = Decimal("2.0")  # 2x max
        
        # === Layer 4: Circuit Breakers ===
        self.volatility_threshold: Decimal = Decimal("0.05")  # 5% move in 5 min
        self.spread_threshold: Decimal = Decimal("0.01")  # 1% spread
        self.loss_rate_threshold: Decimal = Decimal("0.10")  # 10% loss rate
        
        # === Layer 5: Kill Switches ===
        self.emergency_stop: bool = False
        self.exchange_stop: Dict[str, bool] = {}
        self.strategy_stop: Dict[str, bool] = {}


class RiskManager:
    """
    Multi-layer risk management system.
    
    Layers:
    1. Pre-trade limits (per order)
    2. Intra-day risk (real-time)
    3. Portfolio risk (daily)
    4. Circuit breakers (automatic)
    5. Kill switches (emergency)
    """

    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        
        # Track metrics
        self.daily_pnl: Dict[str, Decimal] = {}  # strategy_id -> PnL
        self.consecutive_losses: Dict[str, int] = {}
        self.total_trades: Dict[str, int] = {}
        self.losing_trades: Dict[str, int] = {}
        
        # Circuit breaker state
        self.circuit_breaker_active: bool = False
        self.circuit_breaker_reason: str = ""

    async def validate_signal(self, signal: Signal, positions: List[Position]) -> bool:
        """Validate signal with all risk layers"""
        correlation_id = generate_correlation_id()
        
        try:
            # Layer 5: Check kill switches first
            if self.limits.emergency_stop:
                logger.warning(
                    "Emergency stop active",
                    correlation_id=correlation_id,
                    component="risk_manager"
                )
                return False
            
            if signal.strategy_id in self.limits.strategy_stop:
                logger.warning(
                    "Strategy stopped",
                    correlation_id=correlation_id,
                    strategy_id=signal.strategy_id,
                    component="risk_manager"
                )
                return False
            
            # Layer 1: Pre-trade limits
            if not self._validate_pre_trade(signal):
                return False
            
            # Layer 2: Intra-day risk
            if not self._validate_intra_day(signal):
                return False
            
            # Layer 3: Portfolio risk
            if not self._validate_portfolio(signal, positions):
                return False
            
            # Layer 4: Circuit breakers
            if not self._validate_circuit_breakers(signal):
                return False
            
            return True
            
        except Exception as e:
            logger.error(
                "Risk validation error",
                correlation_id=correlation_id,
                error=str(e),
                component="risk_manager",
                exc_info=True
            )
            return False

    def _validate_pre_trade(self, signal: Signal) -> bool:
        """Layer 1: Pre-trade limits"""
        if signal.quantity > self.limits.max_order_quantity:
            logger.warning(
                "Order quantity exceeds limit",
                quantity=float(signal.quantity),
                limit=float(self.limits.max_order_quantity),
                component="risk_manager"
            )
            return False
        
        return True

    def _validate_intra_day(self, signal: Signal) -> bool:
        """Layer 2: Intra-day risk"""
        # Check daily loss
        if signal.strategy_id in self.daily_pnl:
            if self.daily_pnl[signal.strategy_id] < self.limits.max_daily_loss:
                logger.warning(
                    "Daily loss limit exceeded",
                    strategy_id=signal.strategy_id,
                    pnl=float(self.daily_pnl[signal.strategy_id]),
                    limit=float(self.limits.max_daily_loss),
                    component="risk_manager"
                )
                return False
        
        # Check consecutive losses
        if signal.strategy_id in self.consecutive_losses:
            if self.consecutive_losses[signal.strategy_id] >= self.limits.max_consecutive_losses:
                logger.warning(
                    "Consecutive loss limit exceeded",
                    strategy_id=signal.strategy_id,
                    losses=self.consecutive_losses[signal.strategy_id],
                    limit=self.limits.max_consecutive_losses,
                    component="risk_manager"
                )
                return False
        
        return True

    def _validate_portfolio(self, signal: Signal, positions: List[Position]) -> bool:
        """Layer 3: Portfolio risk"""
        # Check total exposure
        total_exposure = sum(abs(p.quantity * p.current_price) for p in positions)
        if total_exposure > self.limits.max_total_exposure:
            logger.warning(
                "Total exposure limit exceeded",
                exposure=float(total_exposure),
                limit=float(self.limits.max_total_exposure),
                component="risk_manager"
            )
            return False
        
        return True

    def _validate_circuit_breakers(self, signal: Signal) -> bool:
        """Layer 4: Circuit breakers"""
        if self.circuit_breaker_active:
            logger.warning(
                "Circuit breaker active",
                reason=self.circuit_breaker_reason,
                component="risk_manager"
            )
            return False
        
        return True

    async def activate_circuit_breaker(self, reason: str) -> None:
        """Activate circuit breaker"""
        self.circuit_breaker_active = True
        self.circuit_breaker_reason = reason
        
        logger.critical(
            "CIRCUIT BREAKER ACTIVATED",
            reason=reason,
            component="risk_manager"
        )

    async def deactivate_circuit_breaker(self) -> None:
        """Deactivate circuit breaker"""
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = ""
        
        logger.info(
            "Circuit breaker deactivated",
            component="risk_manager"
        )

    async def activate_kill_switch(self, strategy_id: Optional[str] = None) -> None:
        """Activate kill switch (global or strategy-specific)"""
        if strategy_id:
            self.limits.strategy_stop[strategy_id] = True
            logger.critical(
                "STRATEGY KILL SWITCH ACTIVATED",
                strategy_id=strategy_id,
                component="risk_manager"
            )
        else:
            self.limits.emergency_stop = True
            logger.critical(
                "GLOBAL KILL SWITCH ACTIVATED",
                component="risk_manager"
            )
```

---

### 0.4 Kill Switch (`app/services/kill_switch.py`)

**Purpose:** Emergency stop mechanism for immediate position closure.

**Implementation:**

```python
# app/services/kill_switch.py
import logging
from typing import Optional
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class KillSwitch:
    """
    Emergency stop mechanism for trading system.
    
    Activation methods:
    - API endpoint (manual)
    - Risk manager (automatic)
    - Health check failure (automatic)
    """

    def __init__(self):
        self.global_stop: bool = False
        self.exchange_stops: dict = {}
        self.strategy_stops: dict = {}
        self.activation_reason: str = ""
        self.activated_at: Optional[datetime] = None

    async def activate_global(self, reason: str) -> None:
        """Activate global kill switch"""
        correlation_id = generate_correlation_id()
        
        self.global_stop = True
        self.activation_reason = reason
        self.activated_at = datetime.utcnow()
        
        logger.critical(
            "GLOBAL KILL SWITCH ACTIVATED",
            correlation_id=correlation_id,
            reason=reason,
            component="kill_switch"
        )
        
        # TODO: Close all positions immediately

    async def activate_exchange(self, exchange: str, reason: str) -> None:
        """Activate exchange-specific kill switch"""
        self.exchange_stops[exchange] = True
        
        logger.critical(
            "EXCHANGE KILL SWITCH ACTIVATED",
            exchange=exchange,
            reason=reason,
            component="kill_switch"
        )

    async def activate_strategy(self, strategy_id: str, reason: str) -> None:
        """Activate strategy-specific kill switch"""
        self.strategy_stops[strategy_id] = True
        
        logger.critical(
            "STRATEGY KILL SWITCH ACTIVATED",
            strategy_id=strategy_id,
            reason=reason,
            component="kill_switch"
        )

    async def deactivate_all(self) -> None:
        """Deactivate all kill switches"""
        self.global_stop = False
        self.exchange_stops = {}
        self.strategy_stops = {}
        self.activation_reason = ""
        self.activated_at = None
        
        logger.info(
            "All kill switches deactivated",
            component="kill_switch"
        )

    def is_active(self, exchange: Optional[str] = None, 
                  strategy_id: Optional[str] = None) -> bool:
        """Check if kill switch is active"""
        if self.global_stop:
            return True
        if exchange and self.exchange_stops.get(exchange):
            return True
        if strategy_id and self.strategy_stops.get(strategy_id):
            return True
        return False
```

---

### 0.5 Paper Trading Mode (`app/modes/paper_trading.py`)

**Purpose:** Simulate trading without real capital.

**Implementation:**

```python
# app/modes/paper_trading.py
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from app.domain.models import Order, Trade
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class PaperTradingEngine:
    """
    Simulates order execution without real capital.
    
    Features:
    - Simulated fills based on market data
    - Tracks hypothetical PnL
    - Same order flow as live trading
    - No real money at risk
    """

    def __init__(self, initial_capital: Decimal = Decimal("10000")):
        self.capital = initial_capital
        self.positions: Dict[str, Decimal] = {}  # symbol -> quantity
        self.trades: list = []
        self.pnl: Decimal = Decimal("0")

    async def submit_order(self, order: Order, market_price: Decimal) -> Order:
        """Simulate order submission"""
        correlation_id = generate_correlation_id()
        
        logger.info(
            "Paper order submitted",
            correlation_id=correlation_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side.value,
            quantity=float(order.quantity),
            component="paper_trading"
        )
        
        # Simulate fill at market price (with slight slippage)
        slippage = Decimal("0.001")  # 0.1% slippage
        fill_price = market_price * (1 + slippage if order.side.value == "BUY" else 1 - slippage)
        
        # Create simulated trade
        trade = Trade(
            order_id=order.order_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side,
            price=fill_price,
            quantity=order.quantity,
            executed_at=datetime.utcnow()
        )
        
        self.trades.append(trade)
        
        # Update position
        if order.side.value == "BUY":
            self.positions[order.symbol] = self.positions.get(order.symbol, Decimal("0")) + order.quantity
        else:
            self.positions[order.symbol] = self.positions.get(order.symbol, Decimal("0")) - order.quantity
        
        # Update PnL
        self.pnl += (fill_price - market_price) * order.quantity if order.side.value == "BUY" else (market_price - fill_price) * order.quantity
        
        order.status = "FILLED"
        order.filled_at = datetime.utcnow()
        
        logger.info(
            "Paper order filled",
            correlation_id=correlation_id,
            order_id=order.order_id,
            fill_price=float(fill_price),
            pnl=float(self.pnl),
            component="paper_trading"
        )
        
        return order

    def get_performance(self) -> dict:
        """Get paper trading performance"""
        return {
            "capital": float(self.capital),
            "pnl": float(self.pnl),
            "trades": len(self.trades),
            "positions": {k: float(v) for k, v in self.positions.items()}
        }
```

---

## ✅ Acceptance Criteria

- [ ] Market data validator rejects bad candles (test with malformed data)
- [ ] Order validator rejects fat finger orders
- [ ] Risk manager enforces all limits
- [ ] Kill switch stops trading immediately
- [ ] Paper trading mode works (2 weeks minimum before live)
- [ ] All validators have correlation ID tracking
- [ ] All validators have latency tracking
- [ ] All validators log to Loki with proper labels

---

## 🧪 Testing Requirements

```python
# tests/services/test_market_data_validator.py
@pytest.mark.asyncio
async def test_reject_stale_candle():
    """Validator rejects old candles"""
    validator = MarketDataValidator()
    
    stale_candle = Candle(
        symbol="BTCUSDT",
        timeframe="1s",
        timestamp=datetime.utcnow() - timedelta(minutes=1),  # 1 minute old
        open=Decimal("50000"),
        high=Decimal("50100"),
        low=Decimal("49900"),
        close=Decimal("50050"),
        volume=Decimal("100"),
        source="binance"
    )
    
    result = await validator.validate_candle(stale_candle)
    assert result is False

@pytest.mark.asyncio
async def test_reject_fat_finger_price():
    """Validator rejects anomalous prices"""
    validator = MarketDataValidator()
    
    fat_finger_candle = Candle(
        symbol="BTCUSDT",
        timeframe="1s",
        timestamp=datetime.utcnow(),
        open=Decimal("1"),  # BTC at $1? No.
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("100"),
        source="binance"
    )
    
    result = await validator.validate_candle(fat_finger_candle)
    assert result is False
```

---

## 🎯 Next Step

After completing Step 0, proceed to **Step 1: Project Foundation** (`Step1.md`).

**DO NOT SKIP STEP 0.** Trading without these controls is gambling.

---

**Ready to implement? Start coding!** 🐾
