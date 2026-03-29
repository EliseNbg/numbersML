"""
Indicator Calculator for real-time indicator computation on 1-second candles.

Loads active indicator definitions from DB, dynamically imports indicator classes,
fetches recent candles, calculates indicators, and writes results to latest_indicators.
"""

import importlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Type
import json

import asyncpg
import numpy as np

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
    
    # How many recent candles to use for calculation
    DEFAULT_CANDLE_WINDOW = 200

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        self.db_pool = db_pool
        self._definitions: List[Dict[str, Any]] = []
        self._class_cache: Dict[str, Type[Indicator]] = {}
        self._symbol_id_cache: Dict[str, int] = {}

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
                params = r['params']
                if isinstance(params, str):
                    params = json.loads(params)
                elif not isinstance(params, dict):
                    params = {}
                self._definitions.append({
                    'name': r['name'],
                    'class_name': r['class_name'],
                    'module_path': r['module_path'],
                    'params': params,
                })
        logger.info(f"Loaded {len(self._definitions)} indicator definitions")

    def _get_indicator_class(self, class_name: str, module_path: str) -> Optional[Type[Indicator]]:
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

    async def _get_symbol_id(self, symbol: str) -> Optional[int]:
        """Get symbol ID from cache or DB."""
        if symbol in self._symbol_id_cache:
            return self._symbol_id_cache[symbol]

        async with self.db_pool.acquire() as conn:
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1", symbol
            )
            if symbol_id:
                self._symbol_id_cache[symbol] = symbol_id
            return symbol_id

    async def _fetch_candles(
        self, symbol_id: int, limit: int = DEFAULT_CANDLE_WINDOW
    ) -> Optional[Dict[str, np.ndarray]]:
        """Fetch recent candles and return as numpy arrays."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT time, open, high, low, close, volume, quote_volume
                FROM "candles_1s"
                WHERE symbol_id = $1
                ORDER BY time DESC
                LIMIT $2
                """,
                symbol_id, limit,
            )

        if not rows:
            return None

        # Reverse to chronological order
        rows = list(reversed(rows))

        return {
            'time': [r['time'] for r in rows],
            'open': np.array([float(r['open']) for r in rows]),
            'high': np.array([float(r['high']) for r in rows]),
            'low': np.array([float(r['low']) for r in rows]),
            'close': np.array([float(r['close']) for r in rows]),
            'volume': np.array([float(r['volume']) for r in rows]),
            'quote_volume': np.array([float(r['quote_volume']) for r in rows]),
        }

    async def calculate(self, symbol: str, symbol_id: Optional[int] = None) -> int:
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
        if len(candles['close']) < 2:
            logger.warning(f"Only {len(candles['close'])} candles for {symbol}, need >= 2")
            return 0

        prices = candles['close']
        volumes = candles['volume']
        highs = candles['high']
        lows = candles['low']
        opens = candles['open']
        latest_time = candles['time'][-1]
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
        symbol_id: Optional[int] = None,
    ) -> int:
        """
        Calculate indicators using historical data + current candle directly.
        
        Avoids DB read timing issues by accepting the current candle as parameter.
        """
        if symbol_id is None:
            symbol_id = await self._get_symbol_id(symbol)
        if symbol_id is None:
            return 0

        # Fetch historical candles (excluding current)
        candles = await self._fetch_candles(symbol_id, limit=self.DEFAULT_CANDLE_WINDOW - 1)

        if candles is None or len(candles['close']) < 1:
            # First candle ever - can't calculate indicators yet
            return 0

        # Append current candle to historical data
        candles['time'].append(time)
        candles['open'] = np.append(candles['open'], open)
        candles['high'] = np.append(candles['high'], high)
        candles['low'] = np.append(candles['low'], low)
        candles['close'] = np.append(candles['close'], close)
        candles['volume'] = np.append(candles['volume'], volume)

        prices = candles['close']
        volumes = candles['volume']
        highs = candles['high']
        lows = candles['low']
        opens = candles['open']
        latest_time = candles['time'][-1]
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
        results: Dict[str, Any] = {}
        indicator_keys: List[str] = []

        for defn in self._definitions:
            try:
                cls = self._get_indicator_class(defn['class_name'], defn['module_path'])
                if cls is None:
                    continue

                indicator = cls(**defn['params'])
                result: IndicatorResult = indicator.calculate(
                    prices=prices,
                    volumes=volumes,
                    highs=highs,
                    lows=lows,
                    opens=opens,
                    closes=prices,
                )

                for key, values in result.values.items():
                    if len(values) > 0:
                        val = values[-1]
                        if np.isnan(val) or np.isinf(val):
                            continue
                        results[key] = float(val)
                        indicator_keys.append(key)

                calculated += 1

            except Exception as e:
                logger.error(f"Error calculating {defn['name']} for {symbol}: {e}")

        if results:
            await self._write_results(
                symbol=symbol,
                symbol_id=symbol_id,
                time=latest_time,
                price=latest_price,
                volume=latest_volume,
                values=results,
                indicator_keys=indicator_keys,
            )

        return calculated

    async def _write_results(
        self,
        symbol: str,
        symbol_id: int,
        time: datetime,
        price: float,
        volume: float,
        values: Dict[str, Any],
        indicator_keys: List[str],
    ) -> None:
        """Write indicator results to candle_indicators table."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO candle_indicators (symbol_id, time, price, volume, values, indicator_keys)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                ON CONFLICT (symbol_id, time) DO UPDATE SET
                    price = EXCLUDED.price,
                    volume = EXCLUDED.volume,
                    values = EXCLUDED.values,
                    indicator_keys = EXCLUDED.indicator_keys,
                    updated_at = NOW()
                """,
                symbol_id,
                time.replace(tzinfo=None),
                price,
                volume,
                json.dumps(values),
                indicator_keys,
            )
