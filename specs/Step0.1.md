# Step 0.1: Enhanced Testing Infrastructure for Safety Controls

**Status:** ⚠️ REQUIRED
**Effort:** 8-12 hours
**Dependencies:** Step 0 (Critical Safety Infrastructure)

---

## 🎯 Objective

Implement comprehensive testing infrastructure that validates all safety controls work correctly under normal and extreme conditions.

**Key Principle:** Test failure modes more than success modes. In trading, knowing what breaks is more important than knowing what works.

---

## 📁 Test Structure

```
tests/
├── safety/
│   ├── test_market_data_validator.py      # Data quality tests
│   ├── test_order_validator.py            # Fat finger prevention
│   ├── test_risk_manager.py               # Multi-layer risk
│   ├── test_kill_switch.py                # Emergency stops
│   ├── test_position_reconciler.py        # Exchange sync
│   └── test_paper_trading.py              # Simulation mode
├── failure_modes/
│   ├── test_exchange_failure.py           # Exchange goes down
│   ├── test_data_corruption.py            # Bad data injection
│   ├── test_network_partition.py          # Network issues
│   ├── test_latency_spike.py              # Latency anomalies
│   └── test_cascade_failure.py            # Multiple failures
├── stress/
│   ├── test_high_volume.py                # 1000 messages/second
│   ├── test_memory_leak.py                # Extended runtime
│   └── test_queue_overflow.py             # Backpressure
└── integration/
    ├── test_end_to_end_safety.py          # Full safety chain
    └── test_paper_to_live_transition.py   # Mode switching
```

---

## 📝 Test Specifications

### 0.1.1 Market Data Validator Tests

**File:** `tests/safety/test_market_data_validator.py`

```python
"""
Market Data Validator - Comprehensive Test Suite

Coverage Requirements:
- 100% branch coverage
- All validation rules tested
- Edge cases documented
- Failure modes tested
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from app.services.market_data_validator import MarketDataValidator
from app.domain.models import Candle


class TestPriceValidation:
    """Test price bounds validation"""

    @pytest.mark.asyncio
    async def test_accept_normal_price(self):
        """Validator accepts price within normal range"""
        validator = MarketDataValidator()
        
        # Set fair value
        fair_value = Decimal("50000")
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle, fair_value)
        
        assert result is True
        # Verify logged (check logs for correlation_id)

    @pytest.mark.asyncio
    async def test_reject_fat_finger_low(self):
        """Validator rejects price that's too low (fat finger)"""
        validator = MarketDataValidator()
        fair_value = Decimal("50000")
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("1000"),  # 98% drop - clearly wrong
            high=Decimal("1000"),
            low=Decimal("1000"),
            close=Decimal("1000"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle, fair_value)
        
        assert result is False
        # Verify alert logged

    @pytest.mark.asyncio
    async def test_reject_fat_finger_high(self):
        """Validator rejects price that's too high"""
        validator = MarketDataValidator()
        fair_value = Decimal("50000")
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("100000"),  # 100% increase - clearly wrong
            high=Decimal("100000"),
            low=Decimal("100000"),
            close=Decimal("100000"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle, fair_value)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_at_boundary(self):
        """Validator rejects price at exact boundary"""
        validator = MarketDataValidator()
        fair_value = Decimal("50000")
        
        # Exactly 5% deviation (at boundary)
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("52500"),  # 5% above
            high=Decimal("52500"),
            low=Decimal("52500"),
            close=Decimal("52500"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle, fair_value)
        
        assert result is False


class TestTimestampValidation:
    """Test timestamp validation"""

    @pytest.mark.asyncio
    async def test_accept_fresh_candle(self):
        """Validator accepts recent candle"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle)
        assert result is True

    @pytest.mark.asyncio
    async def test_reject_stale_candle(self):
        """Validator rejects old candle"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow() - timedelta(seconds=15),  # 15 seconds old
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle)
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_future_candle(self):
        """Validator rejects candle from future"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow() + timedelta(seconds=10),  # 10 seconds in future
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle)
        assert result is False


class TestVolumeValidation:
    """Test volume sanity checks"""

    @pytest.mark.asyncio
    async def test_reject_zero_volume(self):
        """Validator rejects zero volume candle"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("0"),  # Zero volume
            source="binance"
        )
        
        result = await validator.validate_candle(candle)
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_anomalous_volume(self):
        """Validator rejects anomalously high volume"""
        validator = MarketDataValidator()
        
        # 1000x normal volume
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("1000000"),  # 1M BTC - impossible
            source="binance"
        )
        
        result = await validator.validate_candle(candle)
        assert result is False


class TestOHLCConsistency:
    """Test OHLC relationship validation"""

    @pytest.mark.asyncio
    async def test_reject_high_below_low(self):
        """Validator rejects candle where high < low"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("49000"),  # High below low - impossible
            low=Decimal("50000"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle)
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_close_outside_range(self):
        """Validator rejects candle where close outside high-low range"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50200"),  # Close above high - impossible
            volume=Decimal("100"),
            source="binance"
        )
        
        result = await validator.validate_candle(candle)
        assert result is False


class TestCorrelationIDTracking:
    """Test that all validations include correlation IDs"""

    @pytest.mark.asyncio
    async def test_correlation_id_present_on_success(self):
        """Successful validation includes correlation ID in logs"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            source="binance"
        )
        
        # Capture logs
        with caplog.at_level("DEBUG"):
            await validator.validate_candle(candle)
        
        # Verify correlation_id in logs
        assert any("correlation_id" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_correlation_id_present_on_failure(self):
        """Failed validation includes correlation ID in logs"""
        validator = MarketDataValidator()
        
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow() - timedelta(minutes=1),  # Stale
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
            source="binance"
        )
        
        # Capture logs
        with caplog.at_level("WARNING"):
            await validator.validate_candle(candle)
        
        # Verify correlation_id in logs
        assert any("correlation_id" in record.message for record in caplog.records)
```

---

### 0.1.2 Order Validator Tests

**File:** `tests/safety/test_order_validator.py`

```python
"""
Order Validator - Comprehensive Test Suite

Tests all fat finger prevention and order sanity checks.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from app.services.order_validator import OrderValidator
from app.domain.models import Order, OrderSide, OrderType


class TestQuantityLimits:
    """Test order quantity limits"""

    @pytest.mark.asyncio
    async def test_accept_normal_quantity(self):
        """Validator accepts order within quantity limits"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        order = Order(
            order_id="test-order-1",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.005"),  # Well under limit
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is True

    @pytest.mark.asyncio
    async def test_reject_excessive_quantity(self):
        """Validator rejects order exceeding quantity limit"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        order = Order(
            order_id="test-order-2",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.02"),  # Exceeds 0.01 BTC limit
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_at_quantity_boundary(self):
        """Validator rejects order at exact quantity boundary"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        order = Order(
            order_id="test-order-3",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.01"),  # Exactly at limit
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is False


class TestValueLimits:
    """Test order notional value limits"""

    @pytest.mark.asyncio
    async def test_accept_normal_value(self):
        """Validator accepts order within value limits"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        order = Order(
            order_id="test-order-4",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.005"),  # $250 value
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is True

    @pytest.mark.asyncio
    async def test_reject_excessive_value(self):
        """Validator rejects order exceeding value limit"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        order = Order(
            order_id="test-order-5",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.02"),  # $1000 value - exceeds $500 limit
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is False


class TestRateLimiting:
    """Test order rate limiting"""

    @pytest.mark.asyncio
    async def test_accept_under_rate_limit(self):
        """Validator accepts orders under rate limit"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        # Submit 5 orders (under 10/minute limit)
        for i in range(5):
            order = Order(
                order_id=f"test-order-{i}",
                strategy_id="test-strategy",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("0.001"),
                created_at=datetime.utcnow()
            )
            
            result = await validator.validate_order(order, market_price)
            assert result is True

    @pytest.mark.asyncio
    async def test_reject_over_rate_limit(self):
        """Validator rejects orders exceeding rate limit"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        # Submit 10 orders (at limit)
        for i in range(10):
            order = Order(
                order_id=f"test-order-{i}",
                strategy_id="test-strategy",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("0.001"),
                created_at=datetime.utcnow()
            )
            
            await validator.validate_order(order, market_price)
        
        # 11th order should be rejected
        order = Order(
            order_id="test-order-11",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.001"),
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is False


class TestPriceCollar:
    """Test price collar validation for limit orders"""

    @pytest.mark.asyncio
    async def test_accept_limit_order_within_collar(self):
        """Validator accepts limit order within price collar"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        order = Order(
            order_id="test-order-12",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            price=Decimal("49750"),  # 0.5% below market (within 1% collar)
            quantity=Decimal("0.005"),
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is True

    @pytest.mark.asyncio
    async def test_reject_limit_order_outside_collar(self):
        """Validator rejects limit order outside price collar"""
        validator = OrderValidator()
        market_price = Decimal("50000")
        
        order = Order(
            order_id="test-order-13",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            price=Decimal("45000"),  # 10% below market (outside 1% collar)
            quantity=Decimal("0.005"),
            created_at=datetime.utcnow()
        )
        
        result = await validator.validate_order(order, market_price)
        assert result is False
```

---

### 0.1.3 Risk Manager Tests

**File:** `tests/safety/test_risk_manager.py`

```python
"""
Risk Manager - Comprehensive Test Suite

Tests all layers of risk management.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from app.services.risk_manager import RiskManager, RiskLimits
from app.domain.models import Signal, Position, OrderSide


class TestPreTradeLimits:
    """Test Layer 1: Pre-trade limits"""

    @pytest.mark.asyncio
    async def test_accept_within_limits(self):
        """Risk manager accepts signal within pre-trade limits"""
        risk_manager = RiskManager()
        
        signal = Signal(
            signal_id="test-signal-1",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.005"),  # Under 0.01 limit
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        
        positions = []
        result = await risk_manager.validate_signal(signal, positions)
        assert result is True

    @pytest.mark.asyncio
    async def test_reject_exceeds_quantity_limit(self):
        """Risk manager rejects signal exceeding quantity limit"""
        risk_manager = RiskManager()
        
        signal = Signal(
            signal_id="test-signal-2",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.02"),  # Exceeds 0.01 limit
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        
        positions = []
        result = await risk_manager.validate_signal(signal, positions)
        assert result is False


class TestIntraDayRisk:
    """Test Layer 2: Intra-day risk"""

    @pytest.mark.asyncio
    async def test_reject_after_daily_loss_limit(self):
        """Risk manager rejects signal after daily loss limit hit"""
        risk_manager = RiskManager()
        risk_manager.daily_pnl["test-strategy"] = Decimal("-150")  # Exceeds $100 limit
        
        signal = Signal(
            signal_id="test-signal-3",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.005"),
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        
        positions = []
        result = await risk_manager.validate_signal(signal, positions)
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_after_consecutive_losses(self):
        """Risk manager rejects signal after consecutive losses"""
        risk_manager = RiskManager()
        risk_manager.consecutive_losses["test-strategy"] = 5  # At limit
        
        signal = Signal(
            signal_id="test-signal-4",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.005"),
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        
        positions = []
        result = await risk_manager.validate_signal(signal, positions)
        assert result is False


class TestKillSwitches:
    """Test Layer 5: Kill switches"""

    @pytest.mark.asyncio
    async def test_reject_when_global_kill_switch_active(self):
        """Risk manager rejects all signals when global kill switch active"""
        risk_manager = RiskManager()
        risk_manager.limits.emergency_stop = True
        
        signal = Signal(
            signal_id="test-signal-5",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.005"),
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        
        positions = []
        result = await risk_manager.validate_signal(signal, positions)
        assert result is False

    @pytest.mark.asyncio
    async def test_reject_when_strategy_kill_switch_active(self):
        """Risk manager rejects signals for stopped strategy"""
        risk_manager = RiskManager()
        risk_manager.limits.strategy_stop["test-strategy"] = True
        
        signal = Signal(
            signal_id="test-signal-6",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.005"),
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        
        positions = []
        result = await risk_manager.validate_signal(signal, positions)
        assert result is False

    @pytest.mark.asyncio
    async def test_accept_other_strategy_when_one_stopped(self):
        """Risk manager accepts signals from other strategies when one stopped"""
        risk_manager = RiskManager()
        risk_manager.limits.strategy_stop["test-strategy-1"] = True
        
        signal = Signal(
            signal_id="test-signal-7",
            strategy_id="test-strategy-2",  # Different strategy
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.005"),
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        
        positions = []
        result = await risk_manager.validate_signal(signal, positions)
        assert result is True


class TestCircuitBreakers:
    """Test Layer 4: Circuit breakers"""

    @pytest.mark.asyncio
    async def test_activate_circuit_breaker(self):
        """Circuit breaker activates on trigger"""
        risk_manager = RiskManager()
        
        await risk_manager.activate_circuit_breaker("Test trigger")
        
        assert risk_manager.circuit_breaker_active is True
        assert risk_manager.circuit_breaker_reason == "Test trigger"

    @pytest.mark.asyncio
    async def test_deactivate_circuit_breaker(self):
        """Circuit breaker deactivates on command"""
        risk_manager = RiskManager()
        
        await risk_manager.activate_circuit_breaker("Test trigger")
        await risk_manager.deactivate_circuit_breaker()
        
        assert risk_manager.circuit_breaker_active is False
        assert risk_manager.circuit_breaker_reason == ""
```

---

### 0.1.4 Failure Mode Tests

**File:** `tests/failure_modes/test_cascade_failure.py`

```python
"""
Cascade Failure Tests

Test system behavior when multiple components fail simultaneously.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from app.services.market_data_validator import MarketDataValidator
from app.services.order_validator import OrderValidator
from app.services.risk_manager import RiskManager
from app.domain.models import Candle, Signal


@pytest.mark.asyncio
async def test_data_corruption_plus_network_delay():
    """Test: Bad data + network delay"""
    validator = MarketDataValidator()
    
    # Simulate corrupted data with old timestamp
    candle = Candle(
        symbol="BTCUSDT",
        timeframe="1s",
        timestamp=datetime.utcnow() - timedelta(seconds=30),  # Old
        open=Decimal("1"),  # Corrupted price
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("0"),  # Zero volume
        source="binance"
    )
    
    # Should reject on multiple grounds
    result = await validator.validate_candle(candle)
    assert result is False


@pytest.mark.asyncio
async def test_risk_manager_under_stress():
    """Test: Risk manager with rapid-fire signals"""
    risk_manager = RiskManager()
    
    # Send 100 signals in 1 second
    signals = []
    for i in range(100):
        signal = Signal(
            signal_id=f"stress-signal-{i}",
            strategy_id="test-strategy",
            symbol="BTCUSDT",
            action="BUY",
            quantity=Decimal("0.001"),
            confidence=0.8,
            timestamp=datetime.utcnow()
        )
        signals.append(signal)
    
    # Process all signals
    accepted = 0
    for signal in signals:
        result = await risk_manager.validate_signal(signal, [])
        if result:
            accepted += 1
    
    # Should accept some, reject some (rate limiting)
    assert accepted < 100
    assert accepted > 0  # Should accept at least some
```

---

## ✅ Test Coverage Requirements

| Component | Minimum Coverage | Critical Paths |
|-----------|-----------------|----------------|
| Market Data Validator | 100% | Price, timestamp, volume |
| Order Validator | 100% | Quantity, value, rate limit |
| Risk Manager | 100% | All 5 layers |
| Kill Switch | 100% | Activation, deactivation |
| Position Reconciler | 95% | Sync, discrepancy detection |
| Paper Trading | 90% | Order simulation, PnL |

---

## 🧪 Performance Test Requirements

### Latency Tests

```python
# tests/stress/test_latency.py

@pytest.mark.asyncio
async def test_validator_latency():
    """Validator must complete in <1ms"""
    validator = MarketDataValidator()
    candle = create_test_candle()
    
    start = datetime.utcnow()
    await validator.validate_candle(candle)
    elapsed = (datetime.utcnow() - start).total_seconds() * 1000
    
    assert elapsed < 1.0  # <1ms

@pytest.mark.asyncio
async def test_risk_manager_latency():
    """Risk manager must complete in <5ms"""
    risk_manager = RiskManager()
    signal = create_test_signal()
    
    start = datetime.utcnow()
    await risk_manager.validate_signal(signal, [])
    elapsed = (datetime.utcnow() - start).total_seconds() * 1000
    
    assert elapsed < 5.0  # <5ms
```

### Throughput Tests

```python
# tests/stress/test_throughput.py

@pytest.mark.asyncio
async def test_validator_throughput():
    """Validator must handle 1000 validations/second"""
    validator = MarketDataValidator()
    candles = [create_test_candle() for _ in range(1000)]
    
    start = datetime.utcnow()
    for candle in candles:
        await validator.validate_candle(candle)
    elapsed = datetime.utcnow() - start
    
    # Must complete 1000 validations in <1 second
    assert elapsed.total_seconds() < 1.0
```

---

## 🎯 Next Step

After completing Step 0.1, proceed to **Step 0.2: Operational Runbooks** (`Step0.2.md`).

---

**Testing is not optional. In trading, untested code is live-fire testing with real money.**
