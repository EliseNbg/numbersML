"""
Indicator Calculator for real-time indicator computation on 1-second candles.

Loads active indicator definitions from DB, dynamically imports indicator classes,
fetches recent candles, calculates indicators, and writes results to latest_indicators.
"""

import importlib
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import asyncpg
import numpy as np

from src.domain.services.data_quality import DataQualityGuard
from src.indicators.base import Indicator, IndicatorResult
from src.pipeline.indicators_buffer import IndicatorsBuffer

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """
    Calculates registered indicators on incoming candles.

    Loads indicator definitions from DB, caches indicator class instances,
    fetches candle history, runs calculations, and writes results.

    Example:
        >>> calc = IndicatorCalculator(db_pool)
        >>> await calc.load_definitions()
        >>> await calc.calculate('BTC/USDC', symbol_id=58)
    """

    # How many recent candles to use for calculation (minimum)
    # Will be expanded based on active indicator periods
    DEFAULT_CANDLE_WINDOW = 200

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        self.db_pool = db_pool
        self._definitions: list[dict[str, Any]] = []
        self._class_cache: dict[str, type[Indicator]] = {}
        self._symbol_id_cache: dict[str, int] = {}
        self._quality_guard = DataQualityGuard()
        self._max_indicator_period: int = self.DEFAULT_CANDLE_WINDOW
        self._buffers: dict[str, IndicatorsBuffer] = {}

    async def load_definitions(self) -> None:
        """Load active indicator definitions from DB."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT name, class_name, module_path, params
                FROM indicator_definitions
                WHERE is_active = true
                ORDER BY name
                """
            )
            self._definitions = []
            for r in rows:
                params = r["params"]
                if isinstance(params, str):
                    params = json.loads(params)
                elif not isinstance(params, dict):
                    params = {}
                self._definitions.append(
                    {
                        "name": r["name"],
                        "class_name": r["class_name"],
                        "module_path": r["module_path"],
                        "params": params,
                    }
                )
        # Update max indicator period based on loaded definitions
        self._max_indicator_period = self._calculate_max_period()
        logger.info(
            f"Loaded {len(self._definitions)} indicator definitions (max period: {self._max_indicator_period})"
        )

    def _get_indicator_class(self, class_name: str, module_path: str) -> type[Indicator] | None:
        """Dynamically import and cache indicator class."""
        cache_key = f"{module_path}.{class_name}"
        if cache_key in self._class_cache:
            return self._class_cache[cache_key]

        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            self._class_cache[cache_key] = cls
            return cls
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to import {module_path}.{class_name}: {e}")
            return None

    def _calculate_max_period(self) -> int:
        """Calculate the maximum period needed from all indicator definitions."""
        import re

        max_period = self.DEFAULT_CANDLE_WINDOW
        for defn in self._definitions:
            params = defn.get("params", {})
            class_name = defn.get("class_name", "")
            for key, value in params.items():
                if isinstance(value, int | float):
                    if "macd" in class_name.lower():
                        if "slow" in key or "fast" in key:
                            signal = params.get("signal_period", 9)
                            total = int(value) + int(signal) + 50
                            max_period = max(max_period, total)
                        elif "signal" in key:
                            max_period = max(max_period, int(value) + 50)
                    else:
                        max_period = max(max_period, int(value) + 20)
            name_nums = [int(n) for n in re.findall(r"\d+", defn.get("name", ""))]
            if name_nums:
                max_period = max(max_period, max(name_nums) + 50)
        return max_period

    async def _get_symbol_id(self, symbol: str) -> int | None:
        """Get symbol ID from cache or DB."""
        if symbol in self._symbol_id_cache:
            return self._symbol_id_cache[symbol]

        async with self.db_pool.acquire() as conn:
            symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
            if symbol_id:
                self._symbol_id_cache[symbol] = symbol_id
            return symbol_id

    def _ensure_buffer(self, symbol: str) -> IndicatorsBuffer:
        """Ensure IndicatorsBuffer exists for symbol."""
        if symbol not in self._buffers:
            self._buffers[symbol] = IndicatorsBuffer(
                dbconn=self.db_pool,
                symbol=symbol,
                max_indicator_period=self._max_indicator_period,
            )
        return self._buffers[symbol]

    async def _init_buffer_for_candle(
        self, buffer: IndicatorsBuffer, candle_time: datetime, candle: dict[str, Any]
    ) -> None:
        """Initialize buffer with historical data if not already filled."""
        if len(buffer.closes_buff) == 0:
            await buffer.initialization(current_time=candle_time, current_candle=candle)

    async def calculate(self, symbol: str, symbol_id: int | None = None) -> int:
        """
        Calculate all active indicators for a symbol.

        Args:
            symbol: Symbol name (e.g., 'BTC/USDC')
            symbol_id: Symbol ID (fetched if not provided)

        Returns:
            Number of indicators calculated
        """
        if symbol_id is None:
            symbol_id = await self._get_symbol_id(symbol)
        if symbol_id is None:
            logger.warning(f"Symbol ID not found for {symbol}")
            return 0

        buffer = self._ensure_buffer(symbol)
        await self._init_buffer_for_candle(
            buffer, datetime.now(timezone.utc), {"close": 0, "volume": 0, "high": 0, "low": 0}
        )

        if len(buffer.closes_buff) < 2:
            logger.warning(f"Only {len(buffer.closes_buff)} candles for {symbol}, need >= 2")
            return 0

        prices = np.array(buffer.closes_buff)
        volumes = np.array(buffer.volumes_buff)
        highs = np.array(buffer.highs_buff)
        lows = np.array(buffer.lows_buff)
        opens = np.array([0.0] * len(prices))  # open not stored in IndicatorsBuffer
        latest_time = datetime.now(timezone.utc)
        latest_price = float(prices[-1])
        latest_volume = float(volumes[-1])

        return await self._run_indicators(
            symbol=symbol,
            symbol_id=symbol_id,
            prices=prices,
            volumes=volumes,
            highs=highs,
            lows=lows,
            opens=opens,
            latest_time=latest_time,
            latest_price=latest_price,
            latest_volume=latest_volume,
        )

    async def calculate_with_candle(
        self,
        symbol: str,
        time: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        symbol_id: int | None = None,
    ) -> int:
        """
        Calculate indicators using historical data + current candle directly.

        Uses IndicatorsBuffer for O(1) updates and immediate indicator calculation.
        """
        if symbol_id is None:
            symbol_id = await self._get_symbol_id(symbol)
        if symbol_id is None:
            return 0

        buffer = self._ensure_buffer(symbol)

        # Initialize buffer with historical data if not already done
        candle_dict = {"open": open, "high": high, "low": low, "close": close, "volume": volume}
        await self._init_buffer_for_candle(buffer, time, candle_dict)

        # Add current candle to buffer (O(1) ring buffer append)
        buffer.add_candle(candle_dict)

        # Get data from buffer for indicator calculation
        prices = np.array(buffer.closes_buff)
        volumes = np.array(buffer.volumes_buff)
        highs = np.array(buffer.highs_buff)
        lows = np.array(buffer.lows_buff)
        opens = np.array([0.0] * len(prices))  # open not stored in IndicatorsBuffer
        latest_time = time
        latest_price = float(close)
        latest_volume = float(volume)

        return await self._run_indicators(
            symbol=symbol,
            symbol_id=symbol_id,
            prices=prices,
            volumes=volumes,
            highs=highs,
            lows=lows,
            opens=opens,
            latest_time=latest_time,
            latest_price=latest_price,
            latest_volume=latest_volume,
        )

    async def _run_indicators(
        self,
        symbol: str,
        symbol_id: int,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        latest_time: datetime,
        latest_price: float,
        latest_volume: float,
    ) -> int:
        """
        Run all active indicators on prepared data arrays.

        Shared implementation used by both calculate() and calculate_with_candle().
        """
        calculated = 0
        results: dict[str, Any] = {}

        for defn in self._definitions:
            try:
                cls = self._get_indicator_class(defn["class_name"], defn["module_path"])
                if cls is None:
                    continue

                indicator = cls(**defn["params"])
                result: IndicatorResult = indicator.calculate(
                    prices=prices,
                    volumes=volumes,
                    highs=highs,
                    lows=lows,
                    opens=opens,
                )

                # Use the name from the indicator definition (e.g. 'rsi_14', 'macd_12_26_9')
                # instead of the generated class name.  Flatten all sub‑keys so multi‑output
                # indicators (BollingerBands, MACD…) contribute every series.
                base_key = defn["name"]

                for sub_key, values in result.values.items():
                    # Build the full key: base + sub_key (e.g. 'bb_20_2_upper')
                    if sub_key == "value" or len(result.values) == 1:
                        flat_key = base_key
                    else:
                        flat_key = f"{base_key}_{sub_key}"

                    if len(values) > 0:
                        val = values[-1]
                        if not np.isnan(val) and not np.isinf(val):
                            results[flat_key] = float(val)
                        else:
                            results[flat_key] = None  # null in JSON
                    else:
                        results[flat_key] = None

                calculated += 1

            except Exception as e:
                logger.error(f"Error calculating {defn['name']} for {symbol}: {e}")

        if results:
            # Validate data quality before storing
            quality_report = self._quality_guard.validate_indicator_values(
                symbol_id=symbol_id,
                symbol=symbol,
                time=latest_time,
                values=results,
            )

            if quality_report.is_critical:
                logger.error(
                    f"CRITICAL quality issue for {symbol} at {latest_time}: "
                    f"{quality_report.issue_count} issues, score={quality_report.quality_score}"
                )

            await self._write_results(
                symbol=symbol,
                symbol_id=symbol_id,
                time=latest_time,
                price=latest_price,
                volume=latest_volume,
                values=results,
            )

        return calculated

    async def _write_results(
        self,
        symbol: str,
        symbol_id: int,
        time: datetime,
        price: float,
        volume: float,
        values: dict[str, Any],
    ) -> None:
        """Write indicator results to candle_indicators table."""
        # Use repository for centralized write logic
        from src.infrastructure.repositories.indicator_repo import IndicatorRepository

        repo = IndicatorRepository(self.db_pool)
        await repo.store_indicator_result(
            symbol_id=symbol_id,
            time=time,
            price=price,
            volume=volume,
            indicator_values=values,
        )
