"""Application service for running and persisting strategy backtests."""

import logging
from collections.abc import Callable
from uuid import UUID

from src.application.services.backtest_engine import (
    BacktestEngine,
    BacktestResult,
    serialize_equity_point,
    serialize_metrics,
    serialize_trade_record,
)
from src.application.services.strategy_loader import load_strategy_instance, resolve_symbols
from src.domain.repositories.strategy_repository import StrategyRepository
from src.domain.strategies.strategy_config import StrategyConfigVersion
from src.infrastructure.repositories.strategy_backtest_repository_pg import (
    StrategyBacktestRepositoryPG,
)

logger = logging.getLogger(__name__)


class StrategyBacktestService:
    """Coordinate backtest execution, serialization, and persistence."""

    def __init__(
        self,
        strategy_repository: StrategyRepository,
        backtest_repository: StrategyBacktestRepositoryPG,
        backtest_engine: BacktestEngine,
        actor: str = "system",
    ) -> None:
        self._strategy_repo = strategy_repository
        self._backtest_repo = backtest_repository
        self._backtest_engine = backtest_engine
        self._actor = actor

    async def run_backtest(
        self,
        strategy_id: UUID,
        strategy_version: int | None,
        start_time,
        end_time,
        initial_balance: float,
        symbol: str | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ) -> BacktestResult:
        """Run and persist a backtest for a stored strategy version."""
        strategy_def = await self._strategy_repo.get_by_id(strategy_id)
        if strategy_def is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        config_version = await self._resolve_version(strategy_id, strategy_version)
        symbols = [symbol] if symbol else resolve_symbols(strategy_def, config_version)
        strategy_instance = load_strategy_instance(strategy_def, config_version)

        result = await self._backtest_engine.run_backtest(
            strategy_id=strategy_id,
            strategy_version=config_version.version,
            config=config_version.config,
            symbols=symbols,
            start_time=start_time,
            end_time=end_time,
            initial_balance=initial_balance,
            progress_callback=progress_callback,
            strategy_instance=strategy_instance,
        )

        if config_version.id is not None:
            # Use the UTC-normalised times from BacktestResult so that the
            # stored time_range_start / time_range_end always reflect the
            # exact UTC window the engine simulated, regardless of whether
            # the caller supplied timezone-naive datetimes (e.g. from an API
            # request or CLI).  BacktestEngine.run_backtest already converts
            # naive inputs to UTC-aware datetimes internally, and the
            # BacktestResult carries those corrected values.
            saved_start_time = result.start_time
            saved_end_time = result.end_time
            await self._backtest_repo.save(
                strategy_id=strategy_id,
                strategy_version_id=config_version.id,
                time_range_start=saved_start_time,
                time_range_end=saved_end_time,
                initial_balance=initial_balance,
                final_balance=result.final_balance,
                metrics=serialize_metrics(result.metrics),
                trades=[serialize_trade_record(trade) for trade in result.trades],
                equity_curve=[serialize_equity_point(point) for point in result.equity_curve],
                metadata={
                    "strategy_version": config_version.version,
                    "parameters": result.parameters,
                    "symbol": symbol,
                },
                created_by=self._actor,
            )
        else:
            logger.warning(
                "Skipping backtest persistence for strategy %s version %s because version id is missing",
                strategy_id,
                config_version.version,
            )

        return result

    async def _resolve_version(
        self,
        strategy_id: UUID,
        requested_version: int | None,
    ) -> StrategyConfigVersion:
        """Resolve the requested or active strategy version."""
        versions = await self._strategy_repo.list_versions(strategy_id)
        if not versions:
            raise ValueError(f"No versions found for strategy {strategy_id}")

        if requested_version is not None:
            for version in versions:
                if version.version == requested_version:
                    return version
            raise ValueError(f"Version {requested_version} not found for strategy {strategy_id}")

        active_version = next((version for version in versions if version.is_active), None)
        if active_version is not None:
            return active_version

        return max(versions, key=lambda version: version.version)
