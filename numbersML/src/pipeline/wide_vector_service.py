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
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Optional

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
    CANDLE_FEATURES = ["close", "volume"]

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        active_symbols: Optional[list[tuple[int, str]]] = None,
    ) -> None:
        """
        Initialize wide vector service.

        Args:
            db_pool: Database connection pool
            active_symbols: List of (symbol_id, symbol_name) tuples.
                            If None, loaded from DB on first generate().
        """
        self.db_pool = db_pool
        self._active_symbols: list[tuple[int, str]] = active_symbols or []
        self._indicator_keys: Optional[list[str]] = None  # None=unloaded, []=no indicators
        self._external_provider = self._load_external_provider()
        self._last_known: dict[str, dict[str, float]] = {}

    async def load_symbols(self) -> None:
        """Load active symbols from DB."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, symbol FROM symbols
                WHERE is_active = true AND is_allowed = true
                ORDER BY symbol
                """)
            self._active_symbols = [(r["id"], r["symbol"]) for r in rows]

        logger.info(f"Loaded {len(self._active_symbols)} active symbols")

    async def _load_indicator_schema(self) -> None:
        """Load fixed global indicator key list from active definitions (run once).

        Queries active indicator definitions and computes all expected output keys,
        ensuring the wide-vector schema is stable and matches what indicators produce.
        Multi-output indicators (BollingerBands, MACD) contribute multiple keys.
        """
        if self._indicator_keys:
            return
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT name, class_name, params
                FROM indicator_definitions
                WHERE is_active = true
                ORDER BY name
                """)
            indicator_keys: list[str] = []
            for r in rows:
                name = r["name"]
                class_name = r["class_name"]
                # Determine expected output keys based on indicator type
                if class_name == "BollingerBandsIndicator":
                    # Produces: upper, middle, lower, std (4 sub-keys, no base 'value')
                    params = r["params"]
                    if isinstance(params, str):
                        import json as json_module

                        params = json_module.loads(params)
                    elif not isinstance(params, dict):
                        params = {}
                    period = params.get("period", 20)
                    std_dev = params.get("std_dev", 2)
                    base = f"bb_{period}_{std_dev}"
                    indicator_keys.extend(
                        [
                            f"{base}_upper",
                            f"{base}_middle",
                            f"{base}_lower",
                            f"{base}_std",
                        ]
                    )
                elif class_name == "MACDIndicator":
                    # Produces: macd, signal, histogram (3 sub-keys, no base 'value')
                    params = r["params"]
                    if isinstance(params, str):
                        import json as json_module

                        params = json_module.loads(params)
                    elif not isinstance(params, dict):
                        params = {}
                    fast = params.get("fast_period", 12)
                    slow = params.get("slow_period", 26)
                    signal = params.get("signal_period", 9)
                    base = f"macd_{fast}_{slow}_{signal}"
                    indicator_keys.extend(
                        [
                            f"{base}_macd",
                            f"{base}_signal",
                            f"{base}_histogram",
                        ]
                    )
                else:
                    # Single-output indicators: ATR, EMA, RSI, SMA, etc.
                    # They produce a single 'value' key which uses the base name
                    indicator_keys.append(name)
            self._indicator_keys = sorted(indicator_keys)
        logger.info(f"Loaded fixed indicator schema: {len(self._indicator_keys)} keys")

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
    ) -> Optional[dict[str, Any]]:
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

        # Load fixed indicator schema once — prevents column index shifts
        # when different timesteps have different subsets of indicators.
        if self._indicator_keys is None:
            await self._load_indicator_schema()

        symbol_ids = [sid for sid, _ in self._active_symbols]
        symbol_names = [sname for _, sname in self._active_symbols]

        async with self.db_pool.acquire() as conn:
            # 1. Read candles for current second
            candle_rows = await conn.fetch(
                """
                SELECT c.symbol_id, s.symbol, c.close, c.volume
                FROM candles_1s c
                JOIN symbols s ON s.id = c.symbol_id
                WHERE c.symbol_id = ANY($1) AND c.time = $2
                """,
                symbol_ids,
                candle_time,
            )

            # 2. Read indicators for current second
            indicator_rows = await conn.fetch(
                """
                SELECT ci.symbol_id, s.symbol, ci.values
                FROM candle_indicators ci
                JOIN symbols s ON s.id = ci.symbol_id
                WHERE ci.symbol_id = ANY($1) AND ci.time = $2
                """,
                symbol_ids,
                candle_time,
            )

            # 3. Forward-fill missing data: use last known values for symbols without candles
            symbols_with_candles = {r["symbol"] for r in candle_rows} if candle_rows else set()
            symbols_without_candles = [
                sname for _, sname in self._active_symbols if sname not in symbols_with_candles
            ]

            # 4. Build lookup dicts for current second data
            candle_data: dict[str, dict[str, float]] = {}
            for r in candle_rows:
                candle_data[r["symbol"]] = {
                    "close": float(r["close"]),
                    "volume": float(r["volume"]),
                }

            indicator_data: dict[str, dict[str, float]] = {}
            for r in indicator_rows:
                values_raw = r["values"]
                if isinstance(values_raw, str):
                    values = json.loads(values_raw)
                elif isinstance(values_raw, dict):
                    values = values_raw
                else:
                    values = {}
                indicator_data[r["symbol"]] = {
                    k: float(v) if v is not None else 0.0 for k, v in values.items()
                }

            # 5. Forward-fill: use last known values for symbols without candles
            if symbols_without_candles:
                missing_ids = [
                    sid for sid, sname in self._active_symbols if sname in symbols_without_candles
                ]
                # Last known candles
                last_candle_rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (c.symbol_id) c.symbol_id, s.symbol,
                           c.close, c.volume
                    FROM candles_1s c
                    JOIN symbols s ON s.id = c.symbol_id
                    WHERE c.symbol_id = ANY($1) AND c.time < $2
                    ORDER BY c.symbol_id, c.time DESC
                    """,
                    missing_ids,
                    candle_time,
                )
                for r in last_candle_rows:
                    symbol_name = r["symbol"]
                    candle_data[symbol_name] = {
                        "close": float(r["close"]),
                        "volume": float(r["volume"]),
                    }

                # Last known indicators
                last_indicator_rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (ci.symbol_id) ci.symbol_id, s.symbol,
                           ci.values
                    FROM candle_indicators ci
                    JOIN symbols s ON s.id = ci.symbol_id
                    WHERE ci.symbol_id = ANY($1) AND ci.time < $2
                    ORDER BY ci.symbol_id, ci.time DESC
                    """,
                    missing_ids,
                    candle_time,
                )
                for r in last_indicator_rows:
                    symbol_name = r["symbol"]
                    values_raw = r["values"]
                    if isinstance(values_raw, str):
                        values = json.loads(values_raw)
                    elif isinstance(values_raw, dict):
                        values = values_raw
                    else:
                        values = {}
                    indicator_data[symbol_name] = {
                        k: float(v) if v is not None else 0.0 for k, v in values.items()
                    }

            # 4. Update forward-fill cache with current + fallback data
            for sname, cd in candle_data.items():
                if sname not in self._last_known:
                    self._last_known[sname] = {}
                for feat in self.CANDLE_FEATURES:
                    val = cd.get(feat)
                    if val is not None and not (isinstance(val, float) and math.isnan(val)):
                        self._last_known[sname][feat] = float(val)

            for sname, ind in indicator_data.items():
                if sname not in self._last_known:
                    self._last_known[sname] = {}
                for ikey, val in ind.items():
                    if val is not None and not (isinstance(val, float) and math.isnan(val)):
                        self._last_known[sname][ikey] = float(val)

            # 5. Build flat vector from cache using FIXED schema
            # (self._indicator_keys was loaded once at startup)
            sorted_indicator_keys = self._indicator_keys
            vector: list[float] = []
            column_names: list[str] = []

            for _sid, sname in self._active_symbols:
                lk = self._last_known.get(sname, {})
                col_sname = sname.replace("/", "_")

                # Candle features
                for feat in self.CANDLE_FEATURES:
                    vector.append(lk.get(feat, 0.0))
                    column_names.append(f"{col_sname}_{feat}")

                # Indicator features
                for ikey in sorted_indicator_keys:
                    vector.append(lk.get(ikey, 0.0))
                    column_names.append(f"{col_sname}_{ikey}")

            if not vector:
                return None

            # 6. Call external data provider
            # Pass both candles and indicators to the provider
            external_features: dict[str, float] = {}
            if self._external_provider:
                try:
                    # Build normalized candles dict for provider (BTC_USDC, ETH_USDC, ...)
                    provider_candles = {
                        sname.replace("/", "_"): cd for sname, cd in candle_data.items()
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
                    if value is not None and not (
                        isinstance(value, float) and (math.isnan(value) or math.isinf(value))
                    ):
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

            logger.debug(
                f"Generated wide vector for {candle_time}: "
                f"{len(vector)} features, {len(self._active_symbols)} symbols"
            )

        return {
            "time": candle_time,
            "vector": vector,
            "column_names": column_names,
            "symbol_count": len(self._active_symbols),
            "indicator_count": len(sorted_indicator_keys),
            "vector_size": len(vector),
        }

    async def get_vector(
        self,
        candle_time: datetime,
    ) -> Optional[dict[str, Any]]:
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

        vector_raw = row["vector"]
        if isinstance(vector_raw, str):
            vector = json.loads(vector_raw)
        elif isinstance(vector_raw, list):
            vector = vector_raw
        else:
            vector = []

        return {
            "time": row["time"],
            "vector": vector,
            "column_names": list(row["column_names"]),
            "symbols": list(row["symbols"]),
            "vector_size": row["vector_size"],
            "symbol_count": row["symbol_count"],
            "indicator_count": row["indicator_count"],
        }
