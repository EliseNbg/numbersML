"""
Wide Vector Service for LLM Model Training.

Generates a flat feature vector from all active symbols' candles and indicators
after each 1-second round. Stores in DB for backtesting/ML training.

Vector format per symbol:
    [close, volume, atr, ema, histogram, lower, macd, middle, rsi, signal, sma, std, upper]

Full vector (sorted by symbol name):
    [sym1_close, sym1_volume, sym1_atr, ..., sym2_close, sym2_volume, ...]

Architecture:
    - Called once per second from _ticker_loop after tick_all() returns
    - Reads from candles_1s and candle_indicators (DB snapshot)
    - No synchronization - reads whatever is in DB at call time
    - Sets processed=true on candles_1s after wide vector is stored
"""

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)


class WideVectorService:
    """
    Generate and store wide vectors for all active symbols.

    Reads candle OHLCV + indicator values from DB, builds a flat vector,
    and stores in wide_vectors table.

    Example:
        >>> service = WideVectorService(db_pool, [(58, 'BTC/USDC'), (59, 'ETH/USDC')])
        >>> result = await service.generate(candle_time=datetime(2026, 3, 29, 12, 0, 0))
    """

    # Features per symbol: close, volume + all indicator keys
    CANDLE_FEATURES = ['close', 'volume']

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        active_symbols: Optional[List[Tuple[int, str]]] = None,
    ) -> None:
        """
        Initialize wide vector service.

        Args:
            db_pool: Database connection pool
            active_symbols: List of (symbol_id, symbol_name) tuples.
                            If None, loaded from DB on first generate().
        """
        self.db_pool = db_pool
        self._active_symbols: List[Tuple[int, str]] = active_symbols or []
        self._indicator_keys: List[str] = []
        self._external_provider = self._load_external_provider()

    async def load_symbols(self) -> None:
        """Load active symbols from DB."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, symbol FROM symbols
                WHERE is_active = true AND is_allowed = true
                ORDER BY symbol
                """
            )
            self._active_symbols = [(r['id'], r['symbol']) for r in rows]

        logger.info(f"Loaded {len(self._active_symbols)} active symbols")

    @staticmethod
    def _load_external_provider():
        """
        Load external data provider function from src/external/data_provider.py.

        Returns:
            get_features(candles, indicators, candle_time) -> Dict[str, float], or None
        """
        try:
            from src.external.data_provider import get_features
            logger.info("Loaded external data provider")
            return get_features
        except (ImportError, AttributeError):
            logger.debug("No external data provider found or function missing")
            return None

    async def generate(
        self,
        candle_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate wide vector for a specific candle time.

        Reads candles_1s and candle_indicators for all active symbols,
        builds a flat vector, stores in wide_vectors, and sets processed flag.

        Args:
            candle_time: The candle timestamp (truncated to second)

        Returns:
            Dict with vector data, or None if insufficient data
        """
        if not self._active_symbols:
            await self.load_symbols()

        if not self._active_symbols:
            logger.warning("No active symbols")
            return None

        symbol_ids = [sid for sid, _ in self._active_symbols]
        symbol_names = [sname for _, sname in self._active_symbols]

        async with self.db_pool.acquire() as conn:
            # 1. Read candles
            candle_rows = await conn.fetch(
                """
                SELECT c.symbol_id, s.symbol, c.close, c.volume
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE c.symbol_id = ANY($1) AND c.time = $2
                """,
                symbol_ids, candle_time,
            )

            if not candle_rows:
                return None

            # 2. Read indicators
            indicator_rows = await conn.fetch(
                """
                SELECT ci.symbol_id, s.symbol, ci.values, ci.indicator_keys
                FROM candle_indicators ci
                JOIN symbols s ON s.id = ci.symbol_id
                WHERE ci.symbol_id = ANY($1) AND ci.time = $2
                """,
                symbol_ids, candle_time,
            )

            # 3. Build lookup dicts
            candle_data: Dict[str, Dict[str, float]] = {}
            for r in candle_rows:
                candle_data[r['symbol']] = {
                    'close': float(r['close']),
                    'volume': float(r['volume']),
                }

            indicator_data: Dict[str, Dict[str, float]] = {}
            all_indicator_keys: set = set()
            for r in indicator_rows:
                values_raw = r['values']
                if isinstance(values_raw, str):
                    values = json.loads(values_raw)
                elif isinstance(values_raw, dict):
                    values = values_raw
                else:
                    values = {}
                indicator_data[r['symbol']] = {
                    k: float(v) if v is not None else 0.0
                    for k, v in values.items()
                }
                if r['indicator_keys']:
                    all_indicator_keys.update(r['indicator_keys'])

            # 4. Build flat vector
            sorted_indicator_keys = sorted(all_indicator_keys)
            vector: List[float] = []
            column_names: List[str] = []

            for sid, sname in self._active_symbols:
                cd = candle_data.get(sname, {})
                ind = indicator_data.get(sname, {})
                col_sname = sname.replace('/', '_')

                # Candle features
                for feat in self.CANDLE_FEATURES:
                    vector.append(cd.get(feat, 0.0))
                    column_names.append(f"{col_sname}_{feat}")

                # Indicator features
                for ikey in sorted_indicator_keys:
                    vector.append(ind.get(ikey, 0.0))
                    column_names.append(f"{col_sname}_{ikey}")

            if not vector:
                return None

            # 5. Call external data provider
            # Pass both candles and indicators to the provider
            external_features: Dict[str, float] = {}
            if self._external_provider:
                try:
                    # Build normalized candles dict for provider (BTC_USDC, ETH_USDC, ...)
                    provider_candles = {
                        sname.replace('/', '_'): cd
                        for sname, cd in candle_data.items()
                    }
                    external_features = self._external_provider(
                        provider_candles, indicator_data, candle_time
                    )
                except Exception as e:
                    logger.error(f"External provider error: {e}")
                    external_features = {}

            # Prepend external features to the vector (at the beginning)
            # This ensures they are always at fixed indices
            if external_features:
                for key, value in sorted(external_features.items()):
                    if value is not None and not (isinstance(value, float) and (
                        math.isnan(value) or math.isinf(value)
                    )):
                        vector.insert(0, float(value))
                        column_names.insert(0, key)

            # 6. Store in wide_vectors
            await conn.execute(
                """
                INSERT INTO wide_vectors (time, vector, column_names, symbols,
                    vector_size, symbol_count, indicator_count)
                VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7)
                ON CONFLICT (time) DO UPDATE SET
                    vector = EXCLUDED.vector,
                    column_names = EXCLUDED.column_names,
                    symbols = EXCLUDED.symbols,
                    vector_size = EXCLUDED.vector_size,
                    symbol_count = EXCLUDED.symbol_count,
                    indicator_count = EXCLUDED.indicator_count,
                    created_at = NOW()
                """,
                candle_time,
                json.dumps(vector),
                column_names,
                symbol_names,
                len(vector),
                len(self._active_symbols),
                len(sorted_indicator_keys),
            )

            # 6. Set processed flag
            await conn.execute(
                """
                UPDATE candles_1s SET processed = true
                WHERE symbol_id = ANY($1) AND time = $2
                """,
                symbol_ids, candle_time,
            )

        logger.debug(
            f"Generated wide vector for {candle_time}: "
            f"{len(vector)} features, {len(self._active_symbols)} symbols"
        )

        return {
            'time': candle_time,
            'vector': vector,
            'column_names': column_names,
            'symbol_count': len(self._active_symbols),
            'indicator_count': len(sorted_indicator_keys),
            'vector_size': len(vector),
        }

    async def get_vector(
        self,
        candle_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Read stored wide vector from DB.

        Args:
            candle_time: The candle timestamp

        Returns:
            Dict with vector data, or None
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT time, vector, column_names, symbols,
                       vector_size, symbol_count, indicator_count
                FROM wide_vectors WHERE time = $1
                """,
                candle_time,
            )

        if not row:
            return None

        vector_raw = row['vector']
        if isinstance(vector_raw, str):
            vector = json.loads(vector_raw)
        elif isinstance(vector_raw, list):
            vector = vector_raw
        else:
            vector = []

        return {
            'time': row['time'],
            'vector': vector,
            'column_names': list(row['column_names']),
            'symbols': list(row['symbols']),
            'vector_size': row['vector_size'],
            'symbol_count': row['symbol_count'],
            'indicator_count': row['indicator_count'],
        }
