"""
Indicator Calculator for real-time indicator computation on 1-second candles.

Loads active indicator definitions from DB, dynamically imports indicator classes,
fetches recent candles, calculates indicators, and writes results to latest_indicators.
"""

import importlib
import json
import logging
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import asyncpg
import numpy as np

from src.domain.services.data_quality import DataQualityGuard
from src.indicators.base import Indicator, IndicatorResult

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
        self._candle_buffers: dict[int, dict[str, Any]] = {}

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

    def _ensure_buffer(self, symbol_id: int) -> None:
        """Ensure ring buffer exists for symbol."""
        if symbol_id not in self._candle_buffers:
            self._candle_buffers[symbol_id] = {
                "times": deque(maxlen=self._max_indicator_period),
                "opens": deque(maxlen=self._max_indicator_period),
                "highs": deque(maxlen=self._max_indicator_period),
                "lows": deque(maxlen=self._max_indicator_period),
                "closes": deque(maxlen=self._max_indicator_period),
                "volumes": deque(maxlen=self._max_indicator_period),
            }

    async def _fetch_candles(
        self,
        symbol_id: int,
        limit: int = DEFAULT_CANDLE_WINDOW,
        before_time: datetime | None = None,
    ) -> dict[str, np.ndarray]:
        """Fetch recent candles using ring buffer, replenishing from DB if needed.

        Uses in-memory ring buffer per symbol to avoid repeated DB queries.
        Fills buffer from DB on first access or when empty.
        """
        self._ensure_buffer(symbol_id)
        buf = self._candle_buffers[symbol_id]

        if len(buf["times"]) < self._max_indicator_period:
            async with self.db_pool.acquire() as conn:
                if before_time is not None:
                    rows = await conn.fetch(
                        """
                        SELECT time, open, high, low, close, volume, quote_volume
                        FROM "candles_1s"
                        WHERE symbol_id = $1 AND time < $2
                        ORDER BY time DESC
                        LIMIT $3
                        """,
                        symbol_id,
                        before_time,
                        self._max_indicator_period,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT time, open, high, low, close, volume, quote_volume
                        FROM "candles_1s"
                        WHERE symbol_id = $1
                        ORDER BY time DESC
                        LIMIT $2
                        """,
                        symbol_id,
                        self._max_indicator_period,
                    )

            if not rows:
                # Return empty arrays instead of None
                return {
                    "time": np.array([], dtype=object),
                    "open": np.array([], dtype=np.float64),
                    "high": np.array([], dtype=np.float64),
                    "low": np.array([], dtype=np.float64),
                    "close": np.array([], dtype=np.float64),
                    "volume": np.array([], dtype=np.float64),
                    "quote_volume": np.array([], dtype=np.float64),
                }

            rows = list(reversed(rows))
            buf["times"].clear()
            buf["opens"].clear()
            buf["highs"].clear()
            buf["lows"].clear()
            buf["closes"].clear()
            buf["volumes"].clear()

            for r in rows:
                buf["times"].append(r["time"])
                buf["opens"].append(float(r["open"]))
                buf["highs"].append(float(r["high"]))
                buf["lows"].append(float(r["low"]))
                buf["closes"].append(float(r["close"]))
                buf["volumes"].append(float(r["volume"]))

        return {
            "time": np.array(list(buf["times"]), dtype=object),
            "open": np.array(buf["opens"], dtype=np.float64),
            "high": np.array(buf["highs"], dtype=np.float64),
            "low": np.array(buf["lows"], dtype=np.float64),
            "close": np.array(buf["closes"], dtype=np.float64),
            "volume": np.array(buf["volumes"], dtype=np.float64),
            "quote_volume": np.array([0.0] * len(buf["times"]), dtype=np.float64),
        }

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

        candles = await self._fetch_candles(symbol_id)
        if candles is None:
            logger.warning(f"No candles in DB for {symbol} (id={symbol_id})")
            return 0
        if len(candles["close"]) < 2:
            logger.warning(f"Only {len(candles['close'])} candles for {symbol}, need >= 2")
            return 0

        prices = candles["close"]
        volumes = candles["volume"]
        highs = candles["high"]
        lows = candles["low"]
        opens = candles["open"]
        latest_time = candles["time"][-1]
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

        Avoids DB read timing issues by accepting the current candle as parameter.
        """
        if symbol_id is None:
            symbol_id = await self._get_symbol_id(symbol)
        if symbol_id is None:
            return 0

        # Flush buffer before fetching to ensure fresh historical context.
        # During recalculation, reusing a stale buffer leads to corrupted indicators
        # because the buffer accumulates a mix of old and new data across calls.
        if symbol_id in self._candle_buffers:
            buf = self._candle_buffers[symbol_id]
            buf["times"].clear()
            buf["opens"].clear()
            buf["highs"].clear()
            buf["lows"].clear()
            buf["closes"].clear()
            buf["volumes"].clear()

        # Fetch historical candles (excluding current) - need enough history for longest indicator
        candles = await self._fetch_candles(
            symbol_id, limit=self._max_indicator_period - 1, before_time=time
        )

        if candles is None or len(candles["close"]) < 1:
            # First candle ever - can't calculate indicators yet
            return 0

        # Add current candle to buffer
        self._ensure_buffer(symbol_id)
        buf = self._candle_buffers[symbol_id]
        buf["times"].append(time)
        buf["opens"].append(float(open))
        buf["highs"].append(float(high))
        buf["lows"].append(float(low))
        buf["closes"].append(float(close))
        buf["volumes"].append(float(volume))

        # Combine historical candles with the current candle
        prices = np.append(candles["close"], close)
        volumes = np.append(candles["volume"], volume)
        highs = np.append(candles["high"], high)
        lows = np.append(candles["low"], low)
        opens = np.append(candles["open"], open)
        latest_time = list(buf["times"])[-1]
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
                    closes=prices,
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
