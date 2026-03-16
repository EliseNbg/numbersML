# Step 6: Order Management & Execution

**Status:** ⏳ Pending
**Effort:** 12-16 hours
**Dependencies:** Steps 1-5 (All previous steps)

---

## 🎯 Objective

Implement order management system (OMS) with order lifecycle, execution, and risk controls. This is the final step to complete the MVP.

**Key Outcomes:**
- Order manager handling full lifecycle (PENDING → SUBMITTED → FILLED/CANCELLED)
- Binance order execution adapter
- Risk manager with pre-trade checks and circuit breakers
- Position tracker for real-time PnL
- Complete integration: Data → Strategy → Signal → Order → Execution

---

## 📁 Deliverables

```
app/
├── adapters/
│   └── exchanges/
│       └── binance_trading.py    # Binance order execution
├── services/
│   ├── order_manager.py          # Order lifecycle management
│   ├── risk_manager.py           # Risk controls
│   └── position_tracker.py       # Real-time position tracking
└── api/
    └── routes.py                 # Optional: REST API for manual orders

tests/
├── services/
│   ├── test_order_manager.py
│   ├── test_risk_manager.py
│   └── test_position_tracker.py
└── adapters/
    └── exchanges/
        └── test_binance_trading.py
```

---

## 📝 Specifications

### Logging Requirements for Step 6

**All order management operations MUST use structured logging with:**
- **Correlation IDs**: Generate unique ID per order/signal for tracing from signal to execution
- **Component label**: Always set `component="order_management"`, `component="risk"`, or `component="execution"`
- **Operation context**: Include order_id, signal_id, strategy_id, symbol, action in all logs
- **Latency tracking**: Log execution time for order placement, risk validation, and position updates (target: <40ms end-to-end)
- **Error context**: Include full error details with exc_info=True
- **Order lifecycle**: Log all status transitions (PENDING → SUBMITTED → FILLED/CANCELLED) with correlation IDs

**Example logging pattern:**
```python
correlation_id = generate_correlation_id()
start_time = datetime.utcnow()

try:
    # Order operation
    executed_order = await exchange.place_order(order)
    logger.info(
        "Order placed",
        correlation_id=correlation_id,
        order_id=order.order_id,
        strategy_id=order.strategy_id,
        symbol=order.symbol,
        action=order.side.value,
        component="execution",
        latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
    )
except Exception as e:
    logger.error(
        "Order placement failed",
        correlation_id=correlation_id,
        order_id=order.order_id,
        component="execution",
        error=str(e),
        exc_info=True
    )
```

**Loki Labels Required:**
- `correlation_id` - Unique operation ID (traces signal → order → trade → position)
- `component` - Always "order_management", "risk", "execution", or "position"
- `order_id` - Order identifier
- `strategy_id` - Strategy identifier
- `symbol` - Trading pair
- `action` - Order action (BUY/SELL)

### 6.1 Order Manager (`app/services/order_manager.py`)

```python
# app/services/order_manager.py
import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from app.domain.models import Order, Trade, Signal, Position
from app.ports.strategies import StrategyPort
from app.ports.exchanges import ExchangeAdapter
from app.adapters.repositories.orders import PostgresOrderRepository
from app.adapters.repositories.trades import PostgresTradeRepository
from app.adapters.repositories.positions import PostgresPositionRepository
from app.adapters.cache.redis_cache import RedisCacheAdapter
from app.logging_config import get_logger, generate_correlation_id

logger = get_logger(__name__)


class OrderManager:
    """
    Order Management System (OMS) for trading backend.

    Handles:
    - Signal to order conversion
    - Order lifecycle management
    - Execution via exchange adapter
    - Risk validation
    - Position updates
    - Structured logging with correlation IDs
    """

    def __init__(
        self,
        exchange: ExchangeAdapter,
        order_repo: PostgresOrderRepository,
        trade_repo: PostgresTradeRepository,
        position_repo: PostgresPositionRepository,
        cache: RedisCacheAdapter,
        risk_manager: 'RiskManager'
    ):
        self.exchange = exchange
        self.order_repo = order_repo
        self.trade_repo = trade_repo
        self.position_repo = position_repo
        self.cache = cache
        self.risk_manager = risk_manager
        self.signal_channels: Dict[str, str] = {}  # strategy_id:symbol -> channel
        self.running = False

    async def start(self) -> None:
        """Start order manager and subscribe to signal channels with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        self.running = True

        try:
            # Subscribe to signal channels
            for strategy_id in self.risk_manager.strategies.keys():
                channel = f"signals:{strategy_id}"
                self.signal_channels[strategy_id] = channel
                await self.cache.subscribe(channel, self._handle_signal)

            logger.info(
                "Order manager started",
                correlation_id=correlation_id,
                strategy_count=len(self.risk_manager.strategies),
                component="order_management",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(
                "Failed to start order manager",
                correlation_id=correlation_id,
                component="order_management",
                error=str(e),
                exc_info=True
            )
            raise

    async def stop(self) -> None:
        """Stop order manager with correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        self.running = False

        try:
            # Unsubscribe from channels
            for channel, callback in self.signal_channels.items():
                await self.cache.unsubscribe(channel, callback)

            logger.info(
                "Order manager stopped",
                correlation_id=correlation_id,
                component="order_management",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )
        except Exception as e:
            logger.error(
                "Failed to stop order manager",
                correlation_id=correlation_id,
                component="order_management",
                error=str(e),
                exc_info=True
            )
            raise

    async def _handle_signal(self, signal_data: dict) -> None:
        """Handle incoming signal from Redis pub/sub with full correlation tracking"""
        correlation_id = generate_correlation_id()
        start_time = datetime.utcnow()

        if not self.running:
            return

        try:
            # Convert to Signal object
            signal = Signal(
                signal_id=signal_data["signal_id"],
                strategy_id=signal_data["strategy_id"],
                symbol=signal_data["symbol"],
                action=signal_data["action"],
                quantity=Decimal(signal_data["quantity"]),
                price=Decimal(signal_data["price"]) if signal_data.get("price") else None,
                confidence=signal_data["confidence"],
                timestamp=datetime.fromisoformat(signal_data["timestamp"]),
                metadata=signal_data.get("metadata", {})
            )

            logger.debug(
                "Signal received",
                correlation_id=correlation_id,
                signal_id=signal.signal_id,
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                action=signal.action,
                component="order_management"
            )

            # Validate signal with risk manager
            if not await self.risk_manager.validate_signal(signal):
                logger.warning(
                    "Signal rejected by risk manager",
                    correlation_id=correlation_id,
                    signal_id=signal.signal_id,
                    strategy_id=signal.strategy_id,
                    component="risk"
                )
                return

            # Create order
            order = await self._create_order_from_signal(signal)

            # Save to database
            await self.order_repo.save(order)

            logger.debug(
                "Order created",
                correlation_id=correlation_id,
                order_id=order.order_id,
                strategy_id=order.strategy_id,
                symbol=order.symbol,
                side=order.side.value,
                component="order_management"
            )

            # Submit to exchange
            try:
                executed_order = await self._submit_order(order, correlation_id)

                # Update order status
                if executed_order.status == "FILLED":
                    await self.order_repo.update_status(order.order_id, "FILLED")

                    # Create trade
                    trade = await self._create_trade_from_order(executed_order)
                    await self.trade_repo.save(trade)

                    # Update position
                    await self._update_position(trade, correlation_id)

                    logger.info(
                        "Order filled",
                        correlation_id=correlation_id,
                        order_id=order.order_id,
                        strategy_id=order.strategy_id,
                        symbol=order.symbol,
                        action=signal.action,
                        quantity=float(signal.quantity),
                        component="order_management",
                        latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
                    )

                elif executed_order.status in ["SUBMITTED", "PARTIALLY_FILLED"]:
                    await self.order_repo.update_status(order.order_id, executed_order.status)

                    logger.info(
                        "Order submitted",
                        correlation_id=correlation_id,
                        order_id=order.order_id,
                        strategy_id=order.strategy_id,
                        symbol=order.symbol,
                        status=executed_order.status,
                        component="order_management",
                        latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
                    )

            except Exception as e:
                logger.error(
                    "Order submission failed",
                    correlation_id=correlation_id,
                    order_id=order.order_id,
                    strategy_id=order.strategy_id,
                    component="execution",
                    error=str(e),
                    exc_info=True
                )
                await self.order_repo.update_status(order.order_id, "REJECTED")

        except Exception as e:
            logger.error(
                "Error handling signal",
                correlation_id=correlation_id,
                component="order_management",
                error=str(e),
                exc_info=True
            )

    async def _create_order_from_signal(self, signal: Signal) -> Order:
        """Create order from signal"""
        return Order(
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            side="BUY" if signal.action == "BUY" else "SELL",
            type="MARKET" if signal.price is None else "LIMIT",
            price=signal.price,
            quantity=signal.quantity,
            status="PENDING",
            exchange="binance",
            created_at=signal.timestamp
        )

    async def _submit_order(self, order: Order, correlation_id: str) -> Order:
        """Submit order to exchange with correlation tracking"""
        start_time = datetime.utcnow()

        try:
            # Get current price for market orders
            if order.type == "MARKET" and order.price is None:
                # Get latest price from cache
                tick = await self.cache.get_latest_tick(order.symbol)
                if tick:
                    order.price = tick.last

            # Submit to exchange
            executed_order = await self.exchange.place_order(order)

            # Update order with exchange response
            if hasattr(executed_order, 'client_order_id'):
                order.client_order_id = executed_order.client_order_id

            logger.info(
                "Order placed on exchange",
                correlation_id=correlation_id,
                order_id=order.order_id,
                strategy_id=order.strategy_id,
                symbol=order.symbol,
                side=order.side.value,
                component="execution",
                latency_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
            )

            return executed_order

        except Exception as e:
            logger.error(
                "Exchange order placement failed",
                correlation_id=correlation_id,
                order_id=order.order_id,
                strategy_id=order.strategy_id,
                component="execution",
                error=str(e),
                exc_info=True
            )
            raise

    async def _create_trade_from_order(self, order: Order) -> Trade:
        """Create trade from filled order"""
        return Trade(
            order_id=order.order_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side,
            price=order.avg_fill_price or order.price,
            quantity=order.total_filled,
            fee=Decimal("0"),  # Will be updated after execution
            fee_currency="USDT",
            executed_at=order.filled_at or datetime.utcnow(),
            is_maker=False
        )

    async def _update_position(self, trade: Trade, correlation_id: str) -> None:
        """Update position based on trade with correlation tracking"""
        start_time = datetime.utcnow()

        try:
                quantity=trade.quantity if trade.side == "BUY" else -trade.quantity,
                avg_entry_price=trade.price,
                current_price=trade.price,
                opened_at=trade.executed_at
            )
        else:
            # Update existing position
            if trade.side == "BUY":
                new_quantity = position.quantity + trade.quantity
                if position.quantity > 0:
                    # Same direction
                    new_avg_price = (
                        (position.quantity * position.avg_entry_price) + 
                        (trade.quantity * trade.price)
                    ) / new_quantity
                else:
                    # Opposite direction (partial close)
                    new_avg_price = trade.price
            else:  # SELL
                new_quantity = position.quantity - trade.quantity
                if position.quantity < 0:
                    # Same direction
                    new_avg_price = (
                        (position.quantity * position.avg_entry_price) + 
                        (-trade.quantity * trade.price)
                    ) / new_quantity
                else:
                    # Opposite direction (partial close)
                    new_avg_price = trade.price
            
            position.quantity = new_quantity
            position.avg_entry_price = new_avg_price
            position.current_price = trade.price
            position.updated_at = trade.executed_at
        
        # Save position
        await self.position_repo.save(position)
        
        # Update cache
        if self.cache:
            await self.cache.set_position(position)
```

### 6.2 Risk Manager (`app/services/risk_manager.py`)

```python
# app/services/risk_manager.py
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from app.domain.models import Signal, Order, Position, StrategyConfig
from app.adapters.repositories.positions import PostgresPositionRepository
from app.logging_config import get_logger

logger = get_logger(__name__)


class RiskLimits:
    """Risk limits configuration"""
    
    def __init__(self):
        self.max_order_quantity: Decimal = Decimal("1.0")
        self.max_daily_loss: Decimal = Decimal("-1000.0")
        self.max_orders_per_minute: int = 10
        self.max_position_value: Decimal = Decimal("10000.0")
        self.allowed_symbols: List[str] = ["BTCUSDT", "ETHUSDT"]
        self.max_leverage: Decimal = Decimal("10.0")


class RiskManager:
    """
    Risk management system for trading backend.
    
    Features:
    - Pre-trade validation
    - Circuit breakers
    - Position limits
    - Daily loss limits
    """
    
    def __init__(
        self,
        position_repo: PostgresPositionRepository,
        strategies: Dict[str, StrategyConfig],
        limits: Optional[RiskLimits] = None
    ):
        self.position_repo = position_repo
        self.strategies = strategies
        self.limits = limits or RiskLimits()
        self.order_count: Dict[str, int] = {}
        self.daily_losses: Dict[str, Decimal] = {}
        self.last_reset = datetime.utcnow().date()
        self.circuit_breaker_active: bool = False
        self.circuit_breaker_reason: str = ""
    
    async def validate_signal(self, signal: Signal) -> bool:
        """Validate signal before order creation"""
        try:
            # Check strategy exists
            if signal.strategy_id not in self.strategies:
                logger.warning("Unknown strategy", strategy_id=signal.strategy_id)
                return False
            
            strategy = self.strategies[signal.strategy_id]
            
            # Check symbol allowed
            if signal.symbol not in self.limits.allowed_symbols:
                logger.warning("Symbol not allowed", symbol=signal.symbol)
                return False
            
            # Check quantity limit
            if signal.quantity > self.limits.max_order_quantity:
                logger.warning(
                    "Order quantity exceeds limit",
                    quantity=float(signal.quantity),
                    limit=float(self.limits.max_order_quantity)
                )
                return False
            
            # Check position size
            position = await self.position_repo.get_by_id(signal.strategy_id, signal.symbol)
            if position:
                new_quantity = position.quantity + (signal.quantity if signal.action == "BUY" else -signal.quantity)
                position_value = abs(new_quantity) * signal.price if signal.price else Decimal("0")
                if position_value > self.limits.max_position_value:
                    logger.warning(
                        "Position value exceeds limit",
                        position_value=float(position_value),
                        limit=float(self.limits.max_position_value)
                    )
                    return False
            
            # Check daily loss limit
            today = datetime.utcnow().date()
            if today != self.last_reset:
                self.last_reset = today
                self.daily_losses.clear()
            
            if signal.strategy_id:  # Only check for known strategies
                if signal.strategy_id in self.daily_losses:
                    if self.daily_losses[signal.strategy_id] < self.limits.max_daily_loss:
                        logger.warning(
                            "Daily loss limit exceeded",
                            loss=float(self.daily_losses[signal.strategy_id]),
                            limit=float(self.limits.max_daily_loss)
                        )
                        return False
            
            # Check order rate limit
            now = datetime.utcnow()
            minute_key = f"{signal.strategy_id}:{now.minute}"
            if minute_key in self.order_count:
                if self.order_count[minute_key] >= self.limits.max_orders_per_minute:
                    logger.warning(
                        "Order rate limit exceeded",
                        count=self.order_count[minute_key],
                        limit=self.limits.max_orders_per_minute
                    )
                    return False
                self.order_count[minute_key] += 1
            else:
                self.order_count[minute_key] = 1
            
            # Check circuit breaker
            if self.circuit_breaker_active:
                logger.warning("Circuit breaker active", reason=self.circuit_breaker_reason)
                return False
            
            return True
            
        except Exception as e:
            logger.error("Risk validation failed", error=str(e), exc_info=True)
            return False
    
    async def update_daily_loss(self, strategy_id: str, pnl: Decimal) -> None:
        """Update daily loss tracking"""
        if strategy_id not in self.daily_losses:
            self.daily_losses[strategy_id] = Decimal("0")
        self.daily_losses[strategy_id] += pnl
    
    async def activate_circuit_breaker(self, reason: str) -> None:
        """Activate circuit breaker"""
        self.circuit_breaker_active = True
        self.circuit_breaker_reason = reason
        logger.warning("Circuit breaker activated", reason=reason)
    
    async def deactivate_circuit_breaker(self) -> None:
        """Deactivate circuit breaker"""
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = ""
        logger.info("Circuit breaker deactivated")
    
    async def check_circuit_breaker(self, strategy_id: str, pnl: Decimal) -> bool:
        """Check if circuit breaker should be activated"""
        # Example: Activate if loss > 5% in 5 minutes
        if pnl < Decimal("-0.05"):  # 5% loss
            await self.activate_circuit_breaker(f"Loss > 5% for strategy {strategy_id}")
            return True
        return False
```

### 6.3 Binance Trading Adapter (`app/adapters/exchanges/binance_trading.py`)

```python
# app/adapters/exchanges/binance_trading.py
import json
import logging
import hmac
import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

import aiohttp
from app.domain.models import Order, Trade, OrderSide, OrderType, OrderStatus
from app.ports.exchanges import ExchangeAdapter
from app.logging_config import get_logger

logger = get_logger(__name__)


class BinanceTrading(ExchangeAdapter):
    """
    Binance trading adapter for order execution.
    
    Supports:
    - Market orders
    - Limit orders
    - Stop-loss orders
    - Take-profit orders
    """
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.binance.com"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def connect(self) -> None:
        """Connect to Binance API"""
        self.session = aiohttp.ClientSession()
        logger.info("Binance trading connected")
    
    async def disconnect(self) -> None:
        """Disconnect from Binance API"""
        if self.session:
            await self.session.close()
        logger.info("Binance trading disconnected")
    
    async def place_order(self, order: Order) -> Order:
        """Place order on Binance"""
        if not self.session:
            await self.connect()
        
        # Build request
        params = {
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.type.value,
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "recvWindow": 5000
        }
        
        # Add price for limit orders
        if order.type == OrderType.LIMIT and order.price:
            params["price"] = float(order.price)
        
        # Add quantity
        params["quantity"] = float(order.quantity)
        
        # Sign request
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        url = f"{self.base_url}/api/v3/order"
        headers = {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            async with self.session.post(
                url,
                data=f"{query_string}&signature={signature}",
                headers=headers
            ) as response:
                data = await response.json()
                
                if response.status != 200:
                    error_msg = data.get("msg", "Unknown error")
                    raise Exception(f"Binance order error: {error_msg}")
                
                # Map response to Order object
                executed_order = Order(
                    order_id=data.get("orderId", order.order_id),
                    strategy_id=order.strategy_id,
                    symbol=order.symbol,
                    side=OrderSide(data["side"]),
                    type=OrderType(data["type"]),
                    price=Decimal(str(data.get("price", 0))),
                    quantity=Decimal(str(data.get("origQty", 0))),
                    status=OrderStatus(data["status"]),
                    created_at=datetime.fromtimestamp(data["time"] / 1000),
                    client_order_id=data.get("clientOrderId"),
                    exchange="binance"
                )
                
                return executed_order
                
        except Exception as e:
            logger.error("Binance order placement failed", order_id=order.order_id, error=str(e))
            raise
    
    async def cancel_order(self, order_id: str) -> None:
        """Cancel order on Binance"""
        if not self.session:
            await self.connect()
        
        params = {
            "symbol": "BTCUSDT",  # TODO: get from order
            "orderId": order_id,
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "recvWindow": 5000
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        url = f"{self.base_url}/api/v3/order"
        headers = {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        async with self.session.delete(
            f"{url}?{query_string}&signature={signature}",
            headers=headers
        ) as response:
            data = await response.json()
            if response.status != 200:
                raise Exception(f"Cancel order failed: {data.get('msg', 'Unknown')}")
    
    async def get_order_status(self, order_id: str) -> Order:
        """Get order status from Binance"""
        if not self.session:
            await self.connect()
        
        params = {
            "symbol": "BTCUSDT",  # TODO: get from order
            "orderId": order_id,
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "recvWindow": 5000
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        url = f"{self.base_url}/api/v3/order"
        headers = {
            "X-MBX-APIKEY": self.api_key
        }
        
        async with self.session.get(
            f"{url}?{query_string}&signature={signature}",
            headers=headers
        ) as response:
            data = await response.json()
            
            return Order(
                order_id=data.get("orderId"),
                strategy_id="",  # Not available from Binance
                symbol=data["symbol"],
                side=OrderSide(data["side"]),
                type=OrderType(data["type"]),
                price=Decimal(str(data.get("price", 0))),
                quantity=Decimal(str(data.get("origQty", 0))),
                status=OrderStatus(data["status"]),
                created_at=datetime.fromtimestamp(data["time"] / 1000),
                filled_at=datetime.fromtimestamp(data["updateTime"] / 1000) if data.get("updateTime") else None,
                exchange="binance",
                client_order_id=data.get("clientOrderId")
            )
```

---

## ✅ Acceptance Criteria

- [ ] Order manager handles full lifecycle (PENDING → SUBMITTED → FILLED/CANCELLED) with correlation ID tracking
- [ ] Orders submitted to Binance correctly with proper logging
- [ ] Order status updates tracked with correlation IDs
- [ ] Risk checks performed before every order with logging
- [ ] Circuit breakers working with proper logging
- [ ] Position tracking accurate (real-time PnL) with correlation IDs
- [ ] PostgreSQL persistence for all orders/trades
- [ ] Redis cache for active orders/positions
- [ ] All components have unit tests with logging verification
- [ ] Integration tests with Binance testnet
- [ ] Performance: End-to-end <40ms (logged)
- [ ] All logs include correlation_id, component ("order_management", "risk", "execution", "position")
- [ ] Latency tracking on all operations
- [ ] Error logging includes exc_info=True

---

## 🧪 Testing Requirements

### Order Manager Tests
```python
# tests/services/test_order_manager.py
import pytest
from decimal import Decimal
from datetime import datetime
from app.logging_config import get_logger

logger = get_logger(__name__)

@pytest.mark.asyncio
async def test_order_lifecycle():
    """Test full order lifecycle with correlation tracking"""
    # Setup mock dependencies
    order_repo = MockOrderRepository()
    trade_repo = MockTradeRepository()
    position_repo = MockPositionRepository()
    cache = MockRedisCache()
    risk_manager = MockRiskManager()

    om = OrderManager(
        exchange=MockExchange(),
        order_repo=order_repo,
        trade_repo=trade_repo,
        position_repo=position_repo,
        cache=cache,
        risk_manager=risk_manager
    )

    # Create signal
    signal = Signal(
        strategy_id="test",
        symbol="BTCUSDT",
        action="BUY",
        quantity=Decimal("0.01"),
        confidence=0.8
    )

    # Handle signal
    await om._handle_signal({
        "signal_id": "test-signal",
        "strategy_id": "test",
        "symbol": "BTCUSDT",
        "action": "BUY",
        "quantity": "0.01",
        "confidence": 0.8,
        "timestamp": datetime.utcnow().isoformat()
    })

    # Verify order created
    assert len(order_repo.orders) == 1
    assert order_repo.orders[0].status == "SUBMITTED"

    # Verify trade created
    assert len(trade_repo.trades) == 1
    assert trade_repo.trades[0].side == "BUY"

    # Verify position updated
    assert len(position_repo.positions) == 1
    assert position_repo.positions[0].quantity == Decimal("0.01")

@pytest.mark.asyncio
async def test_order_manager_start_stop_logging():
    """Test order manager start/stop generates proper logs"""
    om = OrderManager(
        exchange=MockExchange(),
        order_repo=MockOrderRepository(),
        trade_repo=MockTradeRepository(),
        position_repo=MockPositionRepository(),
        cache=MockRedisCache(),
        risk_manager=MockRiskManager()
    )

    await om.start()
    assert om.running

    await om.stop()
    assert not om.running

@pytest.mark.asyncio
async def test_risk_manager_validation():
    """Test risk manager validation with correlation tracking"""
    risk_manager = RiskManager(
        position_repo=MockPositionRepository(),
        strategies={"test": StrategyConfig(strategy_id="test")}
    )

    signal = Signal(
        strategy_id="test",
        symbol="BTCUSDT",
        action="BUY",
        quantity=Decimal("0.01"),
        confidence=0.8
    )

    result = await risk_manager.validate_signal(signal)
    assert result is True

@pytest.mark.asyncio
async def test_circuit_breaker():
    """Test circuit breaker activation/deactivation"""
    risk_manager = RiskManager(
        position_repo=MockPositionRepository(),
        strategies={"test": StrategyConfig(strategy_id="test")}
    )

    await risk_manager.activate_circuit_breaker("Test reason")
    assert risk_manager.circuit_breaker_active

    await risk_manager.deactivate_circuit_breaker()
    assert not risk_manager.circuit_breaker_active
```

### Binance Trading Tests
```python
# tests/adapters/exchanges/test_binance_trading.py
@pytest.mark.asyncio
async def test_binance_order_placement():
    """Test Binance order placement with correlation tracking"""
    trading = BinanceTrading(api_key="test", secret_key="test")

    order = Order(
        strategy_id="test",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        exchange="binance"
    )

    # Mock the session for testing
    trading.session = MockSession()

    result = await trading.place_order(order)
    assert result is not None
```

---

## 📚 References

- Binance Trading API: https://binance-docs.github.io/apidocs/spot/en/#account-endpoints
- Order Lifecycle: https:

---

## 🎯 MVP Complete

After completing Step 6, the trading backend MVP is complete with:
- ✅ Real-time 1-second candles from Binance
- ✅ Strategy engine with example SMA
- ✅ Order management with risk controls
- ✅ Position tracking and PnL calculation
- ✅ PostgreSQL persistence
- ✅ Redis caching and pub/sub
- ✅ Docker deployment ready

---

**Ready to implement? Start coding!** 🐾
