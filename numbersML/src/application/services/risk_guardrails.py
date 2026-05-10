"""
Risk Guardrails Service - Hard safety controls for strategy execution.

Provides:
- Daily loss kill switches
- Max position and exposure limits
- Stale data blocking
- Symbol-level notional caps
- Configurable rules with explicit enforcement
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class GuardrailType(Enum):
    """Types of guardrails."""

    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_POSITIONS = "max_positions"
    MAX_EXPOSURE_PCT = "max_exposure_pct"
    STALE_DATA = "stale_data"
    SYMBOL_NOTIONAL_CAP = "symbol_notional_cap"
    GLOBAL_KILL = "global_kill"


class GuardrailAction(Enum):
    """Actions when guardrail is breached."""

    BLOCK_ORDER = "block_order"
    CLOSE_POSITIONS = "close_positions"
    PAUSE_STRATEGY = "pause_strategy"
    EMERGENCY_STOP = "emergency_stop"
    LOG_ONLY = "log_only"


@dataclass
class GuardrailConfig:
    """Configuration for a guardrail rule."""

    enabled: bool = True
    threshold: float = 0.0
    action: GuardrailAction = GuardrailAction.BLOCK_ORDER
    cooldown_minutes: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardrailBreach:
    """Record of a guardrail breach."""

    timestamp: datetime
    guardrail_type: GuardrailType
    strategy_id: Optional[UUID]
    details: dict[str, Any]
    action_taken: GuardrailAction
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class RiskState:
    """Current risk state for a strategy."""

    strategy_id: UUID
    initial_balance: float = 10000.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    open_positions: int = 0
    total_exposure: float = 0.0
    exposure_pct: float = 0.0
    last_data_timestamp: Optional[datetime] = None
    symbol_exposure: dict[str, float] = field(default_factory=dict)
    breach_history: list[GuardrailBreach] = field(default_factory=list)
    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None
    paused_until: Optional[datetime] = None


class RiskGuardrailService:
    """
    Service for enforcing hard risk limits on strategy execution.

    Features:
    - Per-strategy and global risk state tracking
    - Real-time guardrail evaluation
    - Configurable breach actions
    - Kill switch management
    - Comprehensive breach logging
    """

    # Default configurations
    DEFAULT_CONFIGS: dict[GuardrailType, GuardrailConfig] = {
        GuardrailType.DAILY_LOSS_LIMIT: GuardrailConfig(
            enabled=True,
            threshold=-5.0,  # 5% daily loss limit
            action=GuardrailAction.EMERGENCY_STOP,
            cooldown_minutes=60,
        ),
        GuardrailType.MAX_POSITIONS: GuardrailConfig(
            enabled=True,
            threshold=5.0,  # Max 5 open positions
            action=GuardrailAction.BLOCK_ORDER,
        ),
        GuardrailType.MAX_EXPOSURE_PCT: GuardrailConfig(
            enabled=True,
            threshold=50.0,  # Max 50% of capital exposed
            action=GuardrailAction.BLOCK_ORDER,
        ),
        GuardrailType.STALE_DATA: GuardrailConfig(
            enabled=True,
            threshold=60.0,  # 60 seconds max staleness
            action=GuardrailAction.PAUSE_STRATEGY,
            cooldown_minutes=1,
        ),
        GuardrailType.SYMBOL_NOTIONAL_CAP: GuardrailConfig(
            enabled=True,
            threshold=10000.0,  # $10k per symbol
            action=GuardrailAction.BLOCK_ORDER,
        ),
        GuardrailType.GLOBAL_KILL: GuardrailConfig(
            enabled=True,
            threshold=1.0,  # Binary on/off
            action=GuardrailAction.EMERGENCY_STOP,
        ),
    }

    def __init__(
        self,
        configs: Optional[dict[GuardrailType, GuardrailConfig]] = None,
        state_callback: Optional[Callable[[RiskState], None]] = None,
    ) -> None:
        self.configs = configs or self.DEFAULT_CONFIGS.copy()
        self.state_callback = state_callback

        # Risk state per strategy
        self._risk_states: dict[UUID, RiskState] = {}

        # Global kill switch
        self._global_kill_switch = False
        self._global_kill_reason: Optional[str] = None
        self._global_kill_time: Optional[datetime] = None

        # Breach history (last 1000)
        self._breach_history: list[GuardrailBreach] = []
        self._max_history = 1000

        # Daily reset tracking
        self._last_reset_date: Optional[datetime] = None

        logger.info("RiskGuardrailService initialized")

    def register_strategy(
        self,
        strategy_id: UUID,
        initial_balance: float = 10000.0,
    ) -> RiskState:
        """Register a new strategy for risk tracking."""
        if strategy_id in self._risk_states:
            return self._risk_states[strategy_id]

        state = RiskState(
            strategy_id=strategy_id,
            initial_balance=initial_balance,
        )
        self._risk_states[strategy_id] = state

        logger.info(f"Registered strategy {strategy_id} for risk tracking")
        return state

    def unregister_strategy(self, strategy_id: UUID) -> None:
        """Unregister a strategy and clean up state."""
        if strategy_id in self._risk_states:
            del self._risk_states[strategy_id]
            logger.info(f"Unregistered strategy {strategy_id} from risk tracking")

    async def check_order_allowed(
        self,
        strategy_id: UUID,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        notional: float,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if an order is allowed under current risk constraints.

        Returns:
            (allowed: bool, reason: Optional[str])
        """
        # Get or create risk state
        state = self._get_or_create_state(strategy_id)

        # Check global kill switch
        if self._global_kill_switch:
            return False, f"GLOBAL_KILL_SWITCH_ACTIVE: {self._global_kill_reason}"

        # Check strategy kill switch
        if state.kill_switch_active:
            return False, f"STRATEGY_KILL_SWITCH_ACTIVE: {state.kill_switch_reason}"

        # Check cooldown period
        if state.paused_until and datetime.utcnow() < state.paused_until:
            remaining = (state.paused_until - datetime.utcnow()).total_seconds()
            return False, f"STRATEGY_PAUSED: {remaining:.0f}s remaining"

        # Daily loss limit
        daily_loss_config = self.configs.get(GuardrailType.DAILY_LOSS_LIMIT)
        if daily_loss_config and daily_loss_config.enabled:
            if state.daily_pnl_pct < daily_loss_config.threshold:
                await self._trigger_breach(
                    GuardrailType.DAILY_LOSS_LIMIT,
                    strategy_id,
                    {
                        "daily_pnl_pct": state.daily_pnl_pct,
                        "threshold": daily_loss_config.threshold,
                    },
                    daily_loss_config.action,
                )
                return False, f"DAILY_LOSS_LIMIT_EXCEEDED: {state.daily_pnl_pct:.2f}%"

        # Max positions
        max_pos_config = self.configs.get(GuardrailType.MAX_POSITIONS)
        if max_pos_config and max_pos_config.enabled:
            if state.open_positions >= max_pos_config.threshold:
                return False, f"MAX_POSITIONS_REACHED: {state.open_positions}"

        # Max exposure
        max_exp_config = self.configs.get(GuardrailType.MAX_EXPOSURE_PCT)
        if max_exp_config and max_exp_config.enabled:
            new_exposure = state.total_exposure + notional
            new_exposure_pct = (new_exposure / state.initial_balance) * 100
            if new_exposure_pct > max_exp_config.threshold:
                return False, f"MAX_EXPOSURE_WOULD_EXCEED: {new_exposure_pct:.1f}%"

        # Symbol notional cap
        symbol_cap_config = self.configs.get(GuardrailType.SYMBOL_NOTIONAL_CAP)
        if symbol_cap_config and symbol_cap_config.enabled:
            current_symbol_exposure = state.symbol_exposure.get(symbol, 0)
            new_symbol_exposure = current_symbol_exposure + notional
            if new_symbol_exposure > symbol_cap_config.threshold:
                return False, f"SYMBOL_NOTIONAL_CAP: {symbol} at {new_symbol_exposure:.0f}"

        return True, None

    async def check_data_freshness(
        self,
        strategy_id: UUID,
        data_timestamp: datetime,
        max_staleness_seconds: Optional[float] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if data is fresh enough for strategy execution.

        Returns:
            (fresh: bool, reason: Optional[str])
        """
        state = self._get_or_create_state(strategy_id)

        stale_config = self.configs.get(GuardrailType.STALE_DATA)
        threshold = max_staleness_seconds or stale_config.threshold

        now = datetime.utcnow()
        staleness = (now - data_timestamp).total_seconds()

        state.last_data_timestamp = data_timestamp

        if staleness > threshold:
            await self._trigger_breach(
                GuardrailType.STALE_DATA,
                strategy_id,
                {
                    "staleness_seconds": staleness,
                    "threshold": threshold,
                    "data_timestamp": data_timestamp.isoformat(),
                },
                stale_config.action if stale_config else GuardrailAction.PAUSE_STRATEGY,
            )
            return False, f"STALE_DATA: {staleness:.0f}s old (max {threshold:.0f}s)"

        return True, None

    async def update_position_state(
        self,
        strategy_id: UUID,
        open_positions: int,
        total_exposure: float,
        exposure_pct: float,
        symbol_exposure: dict[str, float],
    ) -> None:
        """Update position state for a strategy."""
        state = self._get_or_create_state(strategy_id)

        state.open_positions = open_positions
        state.total_exposure = total_exposure
        state.exposure_pct = exposure_pct
        state.symbol_exposure = symbol_exposure

        if self.state_callback:
            self.state_callback(state)

    async def record_pnl(
        self,
        strategy_id: UUID,
        trade_pnl: float,
        balance: float,
    ) -> None:
        """Record PnL for daily tracking."""
        self._check_daily_reset()

        state = self._get_or_create_state(strategy_id)
        state.daily_pnl += trade_pnl

        if balance > 0:
            state.daily_pnl_pct = (state.daily_pnl / balance) * 100

        # Check if we hit daily loss limit
        daily_loss_config = self.configs.get(GuardrailType.DAILY_LOSS_LIMIT)
        if daily_loss_config and daily_loss_config.enabled:
            if state.daily_pnl_pct < daily_loss_config.threshold:
                await self._trigger_breach(
                    GuardrailType.DAILY_LOSS_LIMIT,
                    strategy_id,
                    {
                        "daily_pnl": state.daily_pnl,
                        "daily_pnl_pct": state.daily_pnl_pct,
                        "balance": balance,
                    },
                    daily_loss_config.action,
                )

    async def trigger_global_kill(
        self,
        reason: str,
        triggered_by: str,
    ) -> None:
        """Trigger global emergency kill switch."""
        self._global_kill_switch = True
        self._global_kill_reason = f"{reason} (by {triggered_by})"
        self._global_kill_time = datetime.utcnow()

        # Record breach without triggering recursive action
        breach = GuardrailBreach(
            timestamp=datetime.utcnow(),
            guardrail_type=GuardrailType.GLOBAL_KILL,
            strategy_id=None,
            details={"reason": reason, "triggered_by": triggered_by},
            action_taken=GuardrailAction.EMERGENCY_STOP,
        )
        self._breach_history.append(breach)
        if len(self._breach_history) > self._max_history:
            self._breach_history = self._breach_history[-self._max_history :]

        logger.critical(f"GLOBAL KILL SWITCH ACTIVATED: {self._global_kill_reason}")

    async def release_global_kill(self, released_by: str) -> None:
        """Release global kill switch."""
        if self._global_kill_switch:
            logger.info(f"GLOBAL KILL SWITCH RELEASED by {released_by}")
            self._global_kill_switch = False
            self._global_kill_reason = None

    async def trigger_strategy_kill(
        self,
        strategy_id: UUID,
        reason: str,
    ) -> None:
        """Trigger kill switch for a specific strategy."""
        state = self._get_or_create_state(strategy_id)
        state.kill_switch_active = True
        state.kill_switch_reason = reason

        # Record breach without triggering recursive action
        breach = GuardrailBreach(
            timestamp=datetime.utcnow(),
            guardrail_type=GuardrailType.GLOBAL_KILL,
            strategy_id=strategy_id,
            details={"reason": reason},
            action_taken=GuardrailAction.EMERGENCY_STOP,
        )
        self._breach_history.append(breach)
        if len(self._breach_history) > self._max_history:
            self._breach_history = self._breach_history[-self._max_history :]

        logger.critical(f"Strategy {strategy_id} KILL SWITCH: {reason}")

    async def release_strategy_kill(self, strategy_id: UUID) -> None:
        """Release kill switch for a strategy."""
        state = self._get_or_create_state(strategy_id)
        if state.kill_switch_active:
            logger.info(f"Strategy {strategy_id} kill switch released")
            state.kill_switch_active = False
            state.kill_switch_reason = None

    def get_risk_state(self, strategy_id: UUID) -> Optional[RiskState]:
        """Get current risk state for a strategy."""
        return self._risk_states.get(strategy_id)

    def get_all_risk_states(self) -> dict[UUID, RiskState]:
        """Get all risk states."""
        return self._risk_states.copy()

    def get_global_status(self) -> dict[str, Any]:
        """Get global risk status."""
        return {
            "global_kill_active": self._global_kill_switch,
            "global_kill_reason": self._global_kill_reason,
            "global_kill_time": (
                self._global_kill_time.isoformat() if self._global_kill_time else None
            ),
            "monitored_strategies": len(self._risk_states),
            "total_breaches_24h": len(
                [
                    b
                    for b in self._breach_history
                    if b.timestamp > datetime.utcnow() - timedelta(hours=24)
                ]
            ),
        }

    def get_breach_history(
        self,
        strategy_id: Optional[UUID] = None,
        since: Optional[datetime] = None,
    ) -> list[GuardrailBreach]:
        """Get breach history, optionally filtered."""
        breaches = self._breach_history

        if strategy_id:
            breaches = [b for b in breaches if b.strategy_id == strategy_id]

        if since:
            breaches = [b for b in breaches if b.timestamp >= since]

        return sorted(breaches, key=lambda b: b.timestamp, reverse=True)

    async def _trigger_breach(
        self,
        guardrail_type: GuardrailType,
        strategy_id: Optional[UUID],
        details: dict[str, Any],
        action: GuardrailAction,
    ) -> None:
        """Record and handle a guardrail breach."""
        breach = GuardrailBreach(
            timestamp=datetime.utcnow(),
            guardrail_type=guardrail_type,
            strategy_id=strategy_id,
            details=details,
            action_taken=action,
        )

        self._breach_history.append(breach)

        # Trim history
        if len(self._breach_history) > self._max_history:
            self._breach_history = self._breach_history[-self._max_history :]

        # Execute action
        if action == GuardrailAction.PAUSE_STRATEGY and strategy_id:
            state = self._risk_states.get(strategy_id)
            if state:
                config = self.configs.get(guardrail_type)
                cooldown = config.cooldown_minutes if config else 5
                state.paused_until = datetime.utcnow() + timedelta(minutes=cooldown)
                logger.warning(
                    f"Strategy {strategy_id} paused for {cooldown}m due to {guardrail_type.value}"
                )

        elif action == GuardrailAction.EMERGENCY_STOP:
            if strategy_id:
                await self.trigger_strategy_kill(
                    strategy_id, f"Guardrail breach: {guardrail_type.value}"
                )
            else:
                await self.trigger_global_kill(
                    f"Guardrail breach: {guardrail_type.value}", "guardrail_service"
                )

        # Log based on severity
        if action in (GuardrailAction.EMERGENCY_STOP, GuardrailAction.CLOSE_POSITIONS):
            logger.critical(
                f"GUARDRAIL BREACH: {guardrail_type.value} "
                f"strategy={strategy_id} action={action.value} "
                f"details={details}"
            )
        else:
            logger.warning(
                f"Guardrail breach: {guardrail_type.value} "
                f"strategy={strategy_id} action={action.value}"
            )

    def _get_or_create_state(self, strategy_id: UUID) -> RiskState:
        """Get existing risk state or create new one."""
        if strategy_id not in self._risk_states:
            return self.register_strategy(strategy_id)
        return self._risk_states[strategy_id]

    def _check_daily_reset(self) -> None:
        """Reset daily PnL tracking at midnight UTC."""
        now = datetime.utcnow()
        today = now.date()

        if self._last_reset_date != today:
            logger.info("Resetting daily PnL tracking")
            for state in self._risk_states.values():
                state.daily_pnl = 0.0
                state.daily_pnl_pct = 0.0
            self._last_reset_date = today


# Singleton instance for application-wide access
_risk_guardrail_service: Optional[RiskGuardrailService] = None


def get_risk_guardrail_service() -> RiskGuardrailService:
    """Get or create the global risk guardrail service."""
    global _risk_guardrail_service
    if _risk_guardrail_service is None:
        _risk_guardrail_service = RiskGuardrailService()
    return _risk_guardrail_service


def set_risk_guardrail_service(service: RiskGuardrailService) -> None:
    """Set the global risk guardrail service (for testing)."""
    global _risk_guardrail_service
    _risk_guardrail_service = service
