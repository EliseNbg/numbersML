"""
Real-time indicator enrichment service.

Listens to incoming ticks from candles_1s and calculates indicators in real-time.

Architecture:
    Uses IIndicatorProvider for indicator loading (dependency injection).
    Production: DatabaseIndicatorProvider (loads from indicator_definitions)
    Tests: PythonIndicatorProvider or MockIndicatorProvider
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import asyncpg
import numpy as np

from src.domain.services.data_quality import DataQualityGuard
from src.indicators.base import Indicator
from src.indicators.providers.provider import IIndicatorProvider

logger = logging.getLogger(__name__)


class EnrichmentService:
    """
    Real-time indicator enrichment service.

    Listens to new ticks via PostgreSQL NOTIFY/LISTEN from candles_1s,
    calculates all configured indicators using Python/NumPy, and stores
    enriched data in candle_indicators table.

    Flow:
    1. candles_1s INSERT fires NOTIFY new_tick
    2. This service receives notification
    3. Loads recent tick history (last 200 candles)
    4. Calculates all indicators (15+)
    5. Stores in candle_indicators table
    6. Fires NOTIFY enrichment_complete for synchronization

    Attributes:
        db_pool: PostgreSQL connection pool
        redis_pool: Redis connection pool (optional)
        window_size: Number of candles to load for calculations
        indicator_names: List of indicator names to calculate

    Example:
        # Production (load from database)
        provider = DatabaseIndicatorProvider(db_pool)
        service = EnrichmentService(db_pool, provider)

        # Tests (explicit registration)
        provider = PythonIndicatorProvider({'rsi_14': RSIIndicator})
        service = EnrichmentService(db_pool, provider)
        >>> await service.start()
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        indicator_provider: IIndicatorProvider,
        redis_pool: Any | None = None,
        window_size: int = 5000,
        min_ticks_for_calc: int = 50,
    ) -> None:
        """
        Initialize enrichment service.

        Args:
            db_pool: PostgreSQL connection pool
            indicator_provider: Provider for loading indicators (dependency injection)
            redis_pool: Redis connection pool (optional, for pub/sub to strategies)
            window_size: Number of ticks to load for calculations (default: 5000)
            min_ticks_for_calc: Minimum ticks required before calculating (default: 50)

        Example:
            # Production (load from database)
            provider = DatabaseIndicatorProvider(db_pool)
            service = EnrichmentService(db_pool, provider)

            # Tests (explicit registration)
            provider = PythonIndicatorProvider({'rsi_14': RSIIndicator})
            service = EnrichmentService(db_pool, provider)
        """
        self.db_pool: asyncpg.Pool = db_pool
        self.indicator_provider: IIndicatorProvider = indicator_provider
        self.redis_pool: Any | None = redis_pool
        self.window_size: int = window_size
        self.min_ticks_for_calc: int = min_ticks_for_calc

        # State per symbol
        self._tick_windows: dict[int, dict[str, np.ndarray]] = {}
        self._indicators: dict[str, Indicator] = {}
        self._running: bool = False
        self._stats: dict[str, int] = {
            "ticks_processed": 0,
            "indicators_calculated": 0,
            "errors": 0,
            "skipped_insufficient_data": 0,
        }
        self._quality_guard = DataQualityGuard()

    async def start(self) -> None:
        """Start enrichment service."""
        logger.info("Starting Enrichment Service...")

        await self._init_indicators()
        self._running = True

        await self._listen_for_ticks()

    async def stop(self) -> None:
        """Stop enrichment service."""
        logger.info("Stopping Enrichment Service...")
        self._running = False

    async def _init_indicators(self) -> None:
        """
        Initialize indicators from provider.

        Uses the injected IIndicatorProvider to load indicators.
        This allows different loading strategies:
        - DatabaseIndicatorProvider (production)
        - PythonIndicatorProvider (tests/dev)
        - MockIndicatorProvider (unit tests)
        """
        logger.info("Initializing indicators from provider...")

        # Get list of indicators from provider
        # Use async version since _init_indicators is already async
        indicator_names = await self.indicator_provider.list_indicators_async()
        logger.info(f"Provider has {len(indicator_names)} indicators: {indicator_names}")

        # Load each indicator
        self._indicators.clear()
        loaded = 0

        for name in indicator_names:
            indicator = await self.indicator_provider.get_indicator_async(name)
            if indicator:
                self._indicators[name] = indicator
                logger.debug(f"Loaded indicator: {name}")
                loaded += 1
            else:
                logger.warning(f"Failed to load indicator: {name}")

        logger.info(f"Loaded {loaded}/{len(indicator_names)} indicators")

        if loaded == 0:
            logger.warning("No indicators loaded - check provider configuration")

    async def _listen_for_ticks(self) -> None:
        """
        Listen for new ticks via PostgreSQL NOTIFY.

        Listens to 'new_tick' channel which is fired when candles_1s receives INSERT.
        """
        async with self.db_pool.acquire() as conn:
            await conn.listen("new_tick")
            logger.info("Listening for new_tick notifications...")

            while self._running:
                try:
                    notification = await asyncio.wait_for(conn.notification(), timeout=60.0)

                    await self._process_notification(notification)

                except asyncio.TimeoutError:
                    # Send heartbeat
                    await self._heartbeat()

                except Exception as e:
                    logger.error(f"Error processing notification: {e}", exc_info=True)
                    self._stats["errors"] += 1

    async def _process_notification(self, notification: Any) -> None:
        """
        Process tick notification from candles_1s.

        Flow:
        1. Parse notification payload (symbol_id, time)
        2. Load tick history from database (last 200 ticks)
        3. Calculate all indicators
        4. Store in candle_indicators table
        5. Fire enrichment_complete notification

        Args:
            notification: PostgreSQL notification object
        """
        start_time = datetime.now(UTC)

        try:
            # Parse notification payload
            payload = json.loads(notification.payload)
            symbol_id = payload.get("symbol_id")
            tick_time = payload.get("time")

            if not symbol_id or not tick_time:
                logger.warning(f"Invalid notification payload: {payload}")
                return

            # Load recent tick history for this symbol
            tick_history = await self._load_tick_history(symbol_id, limit=self.window_size)

            # Get symbol name from the first tick (contains symbol info)
            symbol_name = (
                tick_history[0].get("symbol", str(symbol_id)) if tick_history else str(symbol_id)
            )

            if len(tick_history) < self.min_ticks_for_calc:
                logger.debug(
                    f"Insufficient data for symbol {symbol_id}: "
                    f"got {len(tick_history)}, need {self.min_ticks_for_calc}"
                )
                self._stats["skipped_insufficient_data"] += 1
                return

            # Extract arrays for calculation
            prices, volumes, highs, lows = self._extract_arrays(tick_history)

            # Calculate all indicators
            indicator_values = await self._calculate_indicators(prices, volumes, highs, lows)

            if not indicator_values:
                logger.warning(f"No indicators calculated for symbol {symbol_id}")
                return

            # Get latest tick data
            latest_tick = tick_history[-1]
            latest_time = latest_tick.get("time") or tick_time
            latest_price = float(latest_tick.get("last_price", 0))
            latest_volume = float(latest_tick.get("volume", 0))

            # Store enriched data
            await self._store_enriched_data(
                symbol_id=symbol_id,
                symbol=symbol_name,
                time=latest_time,
                price=latest_price,
                volume=latest_volume,
                indicator_values=indicator_values,
            )

            # Fire enrichment complete notification (for WIDE_Vector synchronization)
            await self._notify_enrichment_complete(symbol_id, str(latest_time))

            # Publish to Redis (if available)
            if self.redis_pool:
                await self._publish_to_redis(symbol_id, latest_price, indicator_values)

            # Calculate processing time
            total_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

            # Update stats
            self._stats["ticks_processed"] += 1
            self._stats["indicators_calculated"] += len(indicator_values)

            # Save pipeline metrics for dashboard monitoring
            await self._save_pipeline_metrics(
                symbol_id=symbol_id,
                enrichment_time_ms=total_time_ms,
                total_time_ms=total_time_ms,
                active_symbols_count=len(self._symbol_ids) if hasattr(self, "_symbol_ids") else 0,
                active_indicators_count=len(self._indicators),
                status="success" if total_time_ms < 1000 else "slow",
            )

            # Log performance
            elapsed_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            logger.debug(f"Enrichment completed for symbol {symbol_id} in {elapsed_ms:.2f}ms")

        except Exception as e:
            logger.error(f"Error processing tick: {e}", exc_info=True)
            self._stats["errors"] += 1
            raise  # Re-raise to allow retry logic if needed

    async def _load_tick_history(self, symbol_id: int, limit: int = 200) -> list[dict[str, Any]]:
        """
        Load recent tick history for symbol from candles_1s.

        Args:
            symbol_id: Symbol ID to load history for
            limit: Number of candles to load (default: 200)

        Returns:
            List of candle dictionaries, ordered by time ascending
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT time, close as last_price, open as open_price,
                       high as high_price, low as low_price,
                       volume, quote_volume
                FROM candles_1s
                WHERE symbol_id = $1
                ORDER BY time ASC
                LIMIT $2
                """,
                symbol_id,
                limit,
            )

            # Return as list of dicts, ordered by time ascending
            return [dict(r) for r in rows]

    def _extract_arrays(
        self, tick_history: list[dict[str, Any]]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract numpy arrays from tick history.

        Args:
            tick_history: List of tick dictionaries

        Returns:
            Tuple of (prices, volumes, highs, lows) as numpy arrays
        """
        prices = np.array([float(t.get("last_price", 0)) for t in tick_history])
        volumes = np.array([float(t.get("volume", 0)) for t in tick_history])
        highs = np.array([float(t.get("high_price", 0)) for t in tick_history])
        lows = np.array([float(t.get("low_price", 0)) for t in tick_history])

        return prices, volumes, highs, lows

    async def _calculate_indicators(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
    ) -> dict[str, float]:
        """
        Calculate all configured indicators.

        Args:
            prices: Array of prices
            volumes: Array of volumes
            highs: Array of high prices
            lows: Array of low prices

        Returns:
            Dictionary of indicator_name -> latest_value
        """
        indicator_values: dict[str, float] = {}

        for name, indicator in self._indicators.items():
            try:
                result = indicator.calculate(
                    prices=prices,
                    volumes=volumes,
                    highs=highs,
                    lows=lows,
                )

                type(indicator).__name__.lower().replace("indicator", "")

                # Get latest value for each indicator output
                # Find the last valid value across all outputs
                val_to_store = None
                for _key, values in result.values.items():
                    if len(values) > 0:
                        latest_value = values[-1]
                        if not np.isnan(latest_value) and not np.isinf(latest_value):
                            val_to_store = float(latest_value)

                # Always store the key, even if value is None (warmup period)
                # Use the indicator name (e.g. 'rsi_14') as the key
                indicator_values[name] = val_to_store

            except Exception as e:
                logger.error(f"Error calculating indicator {name}: {e}", exc_info=True)
                self._stats["errors"] += 1

        return indicator_values

    async def _store_enriched_data(
        self,
        symbol_id: int,
        symbol: str,
        time: Any,
        price: float,
        volume: float,
        indicator_values: dict[str, float],
    ) -> None:
        """
        Store enriched tick data in candle_indicators table.

        Args:
            symbol_id: Symbol ID
            symbol: Symbol name
            time: Tick time
            price: Current price
            volume: Current volume
            indicator_values: Calculated indicator values
        """
        from src.infrastructure.repositories.indicator_repo import IndicatorRepository

        repo = IndicatorRepository(self.db_pool)
        await repo.store_indicator_result(
            symbol_id=symbol_id,
            time=time,
            price=price,
            volume=volume,
            indicator_values=indicator_values,
        )

        logger.debug(f"Stored {len(indicator_values)} indicators for symbol {symbol_id}")

    async def _notify_enrichment_complete(self, symbol_id: int, time: str) -> None:
        """
        Notify that enrichment is complete for this tick.

        Used by WIDE_Vector generator to synchronize and ensure all indicators
        are calculated before generating the vector.

        Args:
            symbol_id: Symbol ID
            time: Tick time
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "SELECT pg_notify('enrichment_complete', $1)",
                json.dumps(
                    {
                        "symbol_id": symbol_id,
                        "time": time,
                        "processed_at": datetime.now(UTC).isoformat(),
                        "indicators_count": len(self._indicators),
                    }
                ),
            )

    async def _publish_to_redis(
        self,
        symbol_id: int,
        price: float,
        indicator_values: dict[str, float],
    ) -> None:
        """
        Publish enriched tick to Redis for strategy consumption.

        Args:
            symbol_id: Symbol ID
            price: Current price
            indicator_values: Indicator values
        """
        try:
            # Get symbol name
            async with self.db_pool.acquire() as conn:
                symbol = await conn.fetchval("SELECT symbol FROM symbols WHERE id = $1", symbol_id)

            # Publish message
            message = {
                "symbol": symbol,
                "symbol_id": symbol_id,
                "price": price,
                "time": datetime.now(UTC).isoformat(),
                "indicators": indicator_values,
            }

            await self.redis_pool.publish(f"enriched_tick:{symbol}", json.dumps(message))

        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")

    async def _heartbeat(self) -> None:
        """Send heartbeat / update stats."""
        if self._stats["ticks_processed"] > 0 and self._stats["ticks_processed"] % 100 == 0:
            logger.info(
                f"Enrichment stats: {self._stats['ticks_processed']} ticks, "
                f"{self._stats['indicators_calculated']} indicators, "
                f"{self._stats['errors']} errors, "
                f"{self._stats['skipped_insufficient_data']} skipped (insufficient data)"
            )

    def get_stats(self) -> dict[str, int]:
        """Get enrichment statistics."""
        return self._stats.copy()

    async def _save_pipeline_metrics(
        self,
        symbol_id: int,
        enrichment_time_ms: int,
        total_time_ms: int,
        active_symbols_count: int,
        active_indicators_count: int,
        status: str = "success",
        error_message: str = None,
    ) -> None:
        """
        Save pipeline performance metrics to database.

        Args:
            symbol_id: Symbol ID that was processed
            enrichment_time_ms: Time to calculate indicators (ms)
            total_time_ms: Total processing time (ms)
            active_symbols_count: Number of active symbols
            active_indicators_count: Number of active indicators
            status: 'success', 'slow', or 'failed'
            error_message: Error message if failed
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO pipeline_metrics (
                        symbol_id, symbol, enrichment_time_ms,
                        total_time_ms, active_symbols_count,
                        active_indicators_count, status, error_message
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    symbol_id,
                    await conn.fetchval("SELECT symbol FROM symbols WHERE id = $1", symbol_id),
                    enrichment_time_ms,
                    total_time_ms,
                    active_symbols_count,
                    active_indicators_count,
                    status,
                    error_message,
                )
        except Exception as e:
            # Don't fail the pipeline if metrics saving fails
            logger.debug(f"Failed to save pipeline metrics: {e}")
