# Step 5: Strategy Engine & Signal Generation

**Status:** ⏳ Pending  
**Effort:** 8-12 hours  
**Dependencies:** Step 1 (Foundation), Step 2 (Database), Step 3 (Binance Ingest), Step 4 (Redis Cache)

---

## 🎯 Objective

Implement strategy execution engine with signal generation and Redis pub/sub integration for real-time trading signals.

**Key Outcomes:**
- Strategy interface and base class
- Strategy runner managing multiple strategies
- Signal processing and validation
- Example SMA strategy working
- Real-time signal distribution via Redis

---

## 📁 Deliverables

```
app/
├── domain/
│   ├── models.py              # Add Signal, StrategyState
│   └── services.py            # Strategy domain logic
├── ports/
│   └── strategies.py          # Strategy interface
├── adapters/
│   └── strategies/
│       ├── __init__.py
│       └── base_strategy.py   # Base strategy implementation
├── services/
│   ├── strategy_runner.py     # Strategy execution engine
│   └── signal_processor.py    # Signal handling
└── strategies/
    ├── __init__.py
    ├── base.py                # User-facing base class
    └── example_sma.py         # Example: Simple Moving Average

tests/
├── services/
│   ├── test_strategy_runner.py
│   └── test_signal_processor.py
└── strategies/
    └── test_example_sma.py
```

---

## 📝 Specifications

### 5.1 Domain Models Update (`app/domain/models.py`)

```python
@dataclass
class Signal:
    """Trading signal from strategy"""
    signal_id: str = field(default_factory=lambda: str(uuid4()))
    strategy_id: str = ""
    symbol: str = ""
    action: str = "HOLD"  # "BUY" | "SELL" | "HOLD" | "CLOSE"
    quantity: Decimal = Decimal("0")
    price: Optional[Decimal] = None  # None for market orders
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    confidence: float = 0.5  # 0.0 to 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyState:
    """Runtime state for a strategy"""
    strategy_id: str = ""
    is_running: bool = False
    last_candle_time: Optional[datetime] = None
    last_signal_time: Optional[datetime] = None
    total_signals: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    performance: dict = field(default_factory=dict)
```

### 5.2 Strategy Interface (`app/ports/strategies.py`)

```python
from abc import ABC, abstractmethod
from typing import Optional

from app.domain.models import Candle, Tick, Signal

class StrategyPort(ABC):
    @abstractmethod
    async def on_candle(self, candle: Candle) -> Optional[Signal]:
        """Called when new candle arrives"""
        pass
    
    @abstractmethod
    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        """Called on real-time tick (for scalping)"""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Called when strategy is activated"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Called when strategy is deactivated"""
        pass
```

### 5.3 Base Strategy (`strategies/base.py`)

```python
# strategies/base.py
import asyncio
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Optional, List
from uuid import uuid4

from app.domain.models import Candle, Tick, Signal, StrategyConfig
from app.logging_config import get_logger

logger = get_logger(__name__)


class BaseStrategy(ABC):
    """
    Base class for all trading strategies.
    Users inherit from this and implement on_candle() and/or on_tick().
    """
    
    def __init__(self, config: dict):
        self.strategy_id: str = config.get("strategy_id", str(uuid4()))
        self.symbol: str = config.get("symbol", "BTCUSDT")
        self.timeframe: str = config.get("timeframe", "1s")
        self.config: dict = config
        self.is_running: bool = False
        self.last_candle_time: Optional[datetime] = None
        self.total_signals: int = 0
        self.errors: List[str] = []
        self.logger = get_logger(f"strategy.{self.strategy_id}")
    
    @property
    def name(self) -> str:
        return self.config.get("name", f"Strategy-{self.strategy_id[:8]}")
    
    @abstractmethod
    async def on_candle(self, candle: Candle) -> Optional[Signal]:
        """
        Called when new candle arrives.
        
        Args:
            candle: OHLCV candle data
            
        Returns:
            Optional[Signal] - Trading signal or None
        """
        pass
    
    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        """
        Called on real-time tick (optional, for tick-based strategies).
        
        Args:
            tick: Real-time price tick
            
        Returns:
            Optional[Signal] - Trading signal or None
        """
        return None
    
    async def start(self) -> None:
        """Called when strategy is activated"""
        self.is_running = True
        self.logger.info("Strategy started", strategy_id=self.strategy_id)
        await self._on_start()
    
    async def stop(self) -> None:
        """Called when strategy is deactivated"""
        self.is_running = False
        self.logger.info("Strategy stopped", strategy_id=self.strategy_id)
        await self._on_stop()
    
    async def _on_start(self) -> None:
        """Hook for subclass initialization"""
        pass
    
    async def _on_stop(self) -> None:
        """Hook for subclass cleanup"""
        pass
    
    def add_error(self, error: str) -> None:
        """Add error to strategy error log"""
        self.errors.append(f"{datetime.utcnow()}: {error}")
        if len(self.errors) > 100:
            self.errors.pop(0)
    
    async def validate_signal(self, signal: Signal) -> bool:
        """
        Validate signal before submission.
        
        Args:
            signal: Signal to validate
            
        Returns:
            bool: True if valid
        """
        try:
            # Basic validation
            if signal.quantity <= 0:
                raise ValueError("Quantity must be positive")
            
            if signal.confidence < 0 or signal.confidence > 1:
                raise ValueError("Confidence must be between 0 and 1")
            
            if signal.action not in ["BUY", "SELL", "HOLD", "CLOSE"]:
                raise ValueError("Invalid action")
            
            # Strategy-specific validation
            return await self._validate_signal(signal)
            
        except Exception as e:
            self.add_error(f"Signal validation failed: {e}")
            return False
    
    async def _validate_signal(self, signal: Signal) -> bool:
        """Subclass can override for custom validation"""
        return True
    
    async def execute_signal(self, signal: Signal) -> bool:
        """
        Execute signal (can be overridden for simulation mode).
        
        Args:
            signal: Validated signal
            
        Returns:
            bool: True if executed successfully
        """
        try:
            # Default: just log and increment counter
            self.total_signals += 1
            self.logger.info(
                "Signal executed",
                action=signal.action,
                quantity=float(signal.quantity),
                price=float(signal.price) if signal.price else None,
                confidence=signal.confidence
            )
            return True
            
        except Exception as e:
            self.add_error(f"Signal execution failed: {e}")
            return False
```

### 5.4 Strategy Runner (`app/services/strategy_runner.py`)

```python
# app/services/strategy_runner.py
import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime

from app.domain.models import Candle, Signal, StrategyState
from app.ports.strategies import StrategyPort
from app.adapters.cache.redis_cache import RedisCacheAdapter
from app.adapters.repositories.candles import PostgresCandleRepository
from app.logging_config import get_logger

logger = get_logger(__name__)


class StrategyRunner:
    """
    Manages multiple strategy instances and routes events to them.
    
    Features:
    - Concurrent strategy execution
    - Error isolation (one strategy failure doesn't crash others)
    - Signal routing to Redis pub/sub
    - Performance monitoring
    """
    
    def __init__(
        self,
        cache: RedisCacheAdapter,
        candle_repository: PostgresCandleRepository,
        strategies: List[StrategyPort]
    ):
        self.cache = cache
        self.candle_repository = candle_repository
        self.strategies: Dict[str, StrategyPort] = {s.strategy_id: s for s in strategies}
        self.strategy_states: Dict[str, StrategyState] = {}
        self.running = False
        self.signal_channel = "signals"
        self.candle_channels: Dict[str, str] = {}  # symbol:channel mapping
        self.lock = asyncio.Lock()
    
    async def start(self) -> None:
        """Start all strategies and subscribe to candle streams"""
        self.running = True
        
        # Initialize strategy states
        for strategy_id, strategy in self.strategies.items():
            self.strategy_states[strategy_id] = StrategyState(strategy_id=strategy_id)
            
            # Start strategy
            try:
                await strategy.start()
                logger.info("Strategy started", strategy_id=strategy_id)
            except Exception as e:
                logger.error("Failed to start strategy", strategy_id=strategy_id, error=str(e))
                self.strategy_states[strategy_id].errors.append(f"Start failed: {e}")
        
        # Subscribe to candle streams via Redis
        for strategy_id, strategy in self.strategies.items():
            channel = f"candles:{strategy.symbol}:{strategy.timeframe}"
            self.candle_channels[strategy.symbol] = channel
            await self.cache.subscribe(channel, self._handle_candle)
        
        logger.info("Strategy runner started", strategy_count=len(self.strategies))
    
    async def stop(self) -> None:
        """Stop all strategies"""
        self.running = False
        
        # Stop strategies
        for strategy_id, strategy in self.strategies.items():
            try:
                await strategy.stop()
                logger.info("Strategy stopped", strategy_id=strategy_id)
            except Exception as e:
                logger.error("Failed to stop strategy", strategy_id=strategy_id, error=str(e))
        
        # Unsubscribe from channels
        for channel, callback in self.candle_channels.items():
            await self.cache.unsubscribe(channel, callback)
        
        logger.info("Strategy runner stopped")
    
    async def _handle_candle(self, candle_data: dict) -> None:
        """Handle incoming candle from Redis pub/sub"""
        if not self.running:
            return
        
        try:
            # Convert to Candle object
            candle = Candle(
                symbol=candle_data["symbol"],
                timeframe=candle_data["timeframe"],
                timestamp=candle_data["timestamp"],
                open=candle_data["open"],
                high=candle_data["high"],
                low=candle_data["low"],
                close=candle_data["close"],
                volume=candle_data["volume"],
                source=candle_data["source"],
                trade_count=candle_data.get("trade_count", 0),
                quote_volume=candle_data.get("quote_volume", 0)
            )
            
            # Route to appropriate strategies
            tasks = []
            for strategy_id, strategy in self.strategies.items():
                if strategy.symbol == candle.symbol and strategy.timeframe == candle.timeframe:
                    task = asyncio.create_task(self._process_candle(strategy, candle))
                    tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error("Error handling candle", error=str(e), exc_info=True)
    
    async def _process_candle(self, strategy: StrategyPort, candle: Candle) -> None:
        """Process candle for a single strategy"""
        strategy_state = self.strategy_states[strategy.strategy_id]
        
        try:
            # Update state
            strategy_state.last_candle_time = candle.timestamp
            strategy_state.total_signals += 1
            
            # Call strategy method
            signal = await strategy.on_candle(candle)
            
            # Process signal
            if signal:
                # Validate signal
                if await strategy.validate_signal(signal):
                    # Execute signal
                    success = await strategy.execute_signal(signal)
                    
                    if success:
                        # Publish to Redis
                        await self.cache.publish(
                            f"signals:{strategy.strategy_id}:{candle.symbol}",
                            {
                                "signal_id": signal.signal_id,
                                "strategy_id": signal.strategy_id,
                                "symbol": signal.symbol,
                                "action": signal.action,
                                "quantity": float(signal.quantity),
                                "price": float(signal.price) if signal.price else None,
                                "confidence": signal.confidence,
                                "timestamp": signal.timestamp.isoformat(),
                                "metadata": signal.metadata
                            }
                        )
                        
                        logger.debug(
                            "Signal published",
                            strategy_id=strategy.strategy_id,
                            action=signal.action,
                            quantity=float(signal.quantity)
                        )
                    else:
                        logger.warning("Signal execution failed", strategy_id=strategy.strategy_id)
                else:
                    logger.warning("Signal validation failed", strategy_id=strategy.strategy_id)
            
        except Exception as e:
            error_msg = f"Strategy {strategy.strategy_id} error: {e}"
            logger.error(error_msg, exc_info=True)
            strategy_state.errors.append(error_msg)
            strategy.add_error(str(e))
    
    async def get_strategy_state(self, strategy_id: str) -> Optional[StrategyState]:
        """Get strategy runtime state"""
        return self.strategy_states.get(strategy_id)
    
    async def get_all_states(self) -> Dict[str, StrategyState]:
        """Get all strategy states"""
        return self.strategy_states.copy()
    
    async def reload_strategy(self, strategy_id: str) -> bool:
        """Reload a strategy (stop + start)"""
        if strategy_id not in self.strategies:
            return False
        
        try:
            await self.strategies[strategy_id].stop()
            await self.strategies[strategy_id].start()
            return True
        except Exception as e:
            logger.error("Failed to reload strategy", strategy_id=strategy_id, error=str(e))
            return False
```

### 5.5 Example Strategy (`strategies/example_sma.py`)

```python
# strategies/example_sma.py
from decimal import Decimal
from typing import List
from datetime import datetime

from .base import BaseStrategy
from app.domain.models import Candle, Signal


class SimpleMovingAverageStrategy(BaseStrategy):
    """
    Simple Moving Average crossover strategy.
    
    Buy when fast SMA crosses above slow SMA.
    Sell when fast SMA crosses below slow SMA.
    
    Parameters:
        fast_period: Fast SMA period (default: 10)
        slow_period: Slow SMA period (default: 30)
        min_confidence: Minimum confidence (default: 0.7)
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.fast_period: int = config.get("fast_period", 10)
        self.slow_period: int = config.get("slow_period", 30)
        self.min_confidence: float = config.get("min_confidence", 0.7)
        self.prices: List[float] = []
        self.fast_sma: float = 0.0
        self.slow_sma: float = 0.0
        self.last_action: str = "HOLD"
    
    async def _on_start(self) -> None:
        """Initialize strategy state"""
        # Load recent prices for warm-up
        self.logger.info(
            "SMA strategy initialized",
            fast_period=self.fast_period,
            slow_period=self.slow_period
        )
    
    async def on_candle(self, candle: Candle) -> Signal:
        """
        Called when new candle arrives.
        
        Args:
            candle: OHLCV candle data
            
        Returns:
            Signal - Trading signal or None
        """
        # Add current price to history
        price = float(candle.close)
        self.prices.append(price)
        
        # Keep only last N prices
        max_len = max(self.fast_period, self.slow_period) * 2
        if len(self.prices) > max_len:
            self.prices = self.prices[-max_len:]
        
        # Calculate SMAs
        if len(self.prices) >= self.slow_period:
            self.fast_sma = sum(self.prices[-self.fast_period:]) / self.fast_period
            self.slow_sma = sum(self.prices[-self.slow_period:]) / self.slow_period
            
            # Generate signal
            if self.fast_sma > self.slow_sma and self.last_action != "BUY":
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=self.symbol,
                    action="BUY",
                    quantity=Decimal("0.01"),
                    confidence=min(0.9, abs(self.fast_sma - self.slow_sma) / self.slow_sma),
                    metadata={
                        "fast_sma": self.fast_sma,
                        "slow_sma": self.slow_sma,
                        "price": price
                    }
                )
                self.last_action = "BUY"
                return signal
            
            elif self.fast_sma < self.slow_sma and self.last_action != "SELL":
                signal = Signal(
                    strategy_id=self.strategy_id,
                    symbol=self.symbol,
                    action="SELL",
                    quantity=Decimal("0.01"),
                    confidence=min(0.9, abs(self.fast_sma - self.slow_sma) / self.slow_sma),
                    metadata={
                        "fast_sma": self.fast_sma,
                        "slow_sma": self.slow_sma,
                        "price": price
                    }
                )
                self.last_action = "SELL"
                return signal
        
        return None
```

---

## ✅ Acceptance Criteria

- [ ] Strategy interface defined
- [ ] Base strategy class implemented with validation
- [ ] Strategy runner manages multiple strategies concurrently
- [ ] Candles routed to strategies correctly
- [ ] Signals published to Redis pub/sub
- [ ] Example SMA strategy works
- [ ] Strategies run concurrently without blocking
- [ ] Error isolation (one strategy failure doesn't crash others)
- [ ] All components have unit tests
- [ ] Integration tests with Binance data

---

## 🧪 Testing Requirements

### Strategy Tests
```python
# tests/strategies/test_example_sma.py
@pytest.mark.asyncio
async def test_sma_buy_signal():
    config = {"symbol": "BTCUSDT", "timeframe": "1s"}
    strategy = SimpleMovingAverageStrategy(config)
    
    # Simulate price rising
    candles = []
    for i in range(40):
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1s",
            timestamp=datetime.utcnow(),
            open=Decimal("50000") + Decimal(i * 10),
            high=Decimal("50010") + Decimal(i * 10),
            low=Decimal("49990") + Decimal(i * 10),
            close=Decimal("50005") + Decimal(i * 10),
            volume=Decimal("100"),
            source="test"
        )
        candles.append(candle)
    
    # Get signal after enough candles
    signal = await strategy.on_candle(candles[-1])
    assert signal is not None
    assert signal.action == "BUY"
```

---

## 🎯 Next Step

After completing Step 5, proceed to **Step 6: Order Management & Execution** (`Step6.md`).

---

**Ready to implement? Start coding!** 🐾
