"""Helpers for loading executable strategy instances from stored definitions."""

import logging

from src.domain.strategies.base import EnrichedTick, Signal, SignalType, Strategy, TimeFrame
from src.domain.strategies.strategy_config import StrategyConfigVersion, StrategyDefinition

logger = logging.getLogger(__name__)


class ConfigDrivenStrategy(Strategy):
    """Minimal config-driven strategy implementation for runtime and backtesting."""

    def __init__(
        self,
        strategy_id: str,
        symbols: list[str],
        time_frame: TimeFrame = TimeFrame.TICK,
    ) -> None:
        super().__init__(strategy_id, symbols, time_frame)
        self._position_open = False

    def on_tick(self, tick: EnrichedTick) -> Signal | None:
        """Evaluate the configured signal logic on a market tick."""
        signal_config = self._config.get("signal", {})
        signal_type = signal_config.get("type", "rsi")
        params = signal_config.get("params", {})

        if signal_type == "rsi":
            indicator_name = params.get(
                "indicator_name",
                f'rsiindicator_period{params.get("period", 14)}_rsi',
            )
            rsi_value = tick.get_indicator(indicator_name, None)
            if rsi_value is None:
                return None

            oversold = params.get("oversold", 30)
            overbought = params.get("overbought", 70)

            if rsi_value < oversold and not self._position_open:
                self._position_open = True
                return Signal(
                    strategy_id=self.id,
                    symbol=tick.symbol,
                    signal_type=SignalType.BUY,
                    price=tick.price,
                    confidence=min(1.0, (oversold - rsi_value) / max(oversold, 1)),
                    metadata={"rsi": rsi_value, "signal_reason": "rsi_oversold"},
                )

            if rsi_value > overbought and self._position_open:
                self._position_open = False
                return Signal(
                    strategy_id=self.id,
                    symbol=tick.symbol,
                    signal_type=SignalType.SELL,
                    price=tick.price,
                    confidence=min(1.0, (rsi_value - overbought) / max(100 - overbought, 1)),
                    metadata={"rsi": rsi_value, "signal_reason": "rsi_overbought"},
                )

            return None

        logger.warning(
            "Unsupported config-driven signal type %s for strategy %s",
            signal_type,
            self.id,
        )
        return None


def resolve_symbols(
    strategy_def: StrategyDefinition,
    config_version: StrategyConfigVersion,
) -> list[str]:
    """Resolve traded symbols from versioned config with legacy fallbacks."""
    universe = config_version.config.get("universe", {})
    symbols = universe.get("symbols") or config_version.config.get("symbols")
    if symbols:
        return list(symbols)

    legacy_universe = strategy_def.config.get("universe", {})
    legacy_symbols = legacy_universe.get("symbols") or strategy_def.config.get("symbols")
    if legacy_symbols:
        return list(legacy_symbols)

    return ["BTC/USDC"]


def load_strategy_instance(
    strategy_def: StrategyDefinition,
    config_version: StrategyConfigVersion,
) -> Strategy:
    """Instantiate a strategy from a stored versioned configuration."""
    effective_config = strategy_def.config.copy()
    effective_config.update(config_version.config)

    strategy_type = effective_config.get("strategy_type", strategy_def.strategy_type)
    class_path = effective_config.get("class_path", strategy_def.class_path)
    symbols = resolve_symbols(strategy_def, config_version)

    if strategy_type == "class":
        if not class_path:
            raise ValueError("Strategy type is 'class' but no class_path provided")

        try:
            module_path, class_name = class_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            strategy_class = getattr(module, class_name)
        except (ValueError, ImportError, AttributeError) as exc:
            raise ValueError(f"Failed to load strategy class {class_path}: {exc}") from exc

        strategy = strategy_class(
            strategy_id=str(strategy_def.id),
            symbols=symbols,
        )
    else:
        strategy = ConfigDrivenStrategy(
            strategy_id=str(strategy_def.id),
            symbols=symbols,
            time_frame=TimeFrame.TICK,
        )

    strategy._config = effective_config.copy()

    logger.info(
        "Loaded strategy %s (type=%s, version=%s, class=%s)",
        strategy_def.id,
        strategy_type,
        config_version.version,
        strategy.__class__.__name__,
    )
    return strategy
