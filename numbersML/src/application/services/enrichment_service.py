"""
Real-time indicator enrichment service.

Listens to incoming ticks from ticker_24hr_stats and calculates indicators in real-time.
"""

import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import logging
import json

from src.indicators.registry import IndicatorRegistry
from src.indicators.base import Indicator

logger = logging.getLogger(__name__)


class EnrichmentService:
    """
    Real-time indicator enrichment service.

    Listens to new ticks via PostgreSQL NOTIFY/LISTEN from ticker_24hr_stats,
    calculates all configured indicators using Python/NumPy, and stores
    enriched data in tick_indicators table.

    Flow:
    1. ticker_24hr_stats INSERT fires NOTIFY new_tick
    2. This service receives notification
    3. Loads recent tick history (last 200 ticks)
    4. Calculates all indicators (15+)
    5. Stores in tick_indicators table
    6. Fires NOTIFY enrichment_complete for synchronization

    Attributes:
        db_pool: PostgreSQL connection pool
        redis_pool: Redis connection pool (optional)
        window_size: Number of ticks to load for calculations
        indicator_names: List of indicator names to calculate

    Example:
        >>> service = EnrichmentService(db_pool, indicator_names=['rsi_14', 'sma_20'])
        >>> await service.start()
    """

    # Default indicators to calculate (all available Python indicators)
    DEFAULT_INDICATORS = [
        'rsiindicator_period14',
        'smaindicator_period20',
        'smaindicator_period50',
        'emaindicator_period12',
        'emaindicator_period26',
        'bbindicator_period20_std_dev2.0',
        'macdindicator_fast_period12_slow_period26_signal_period9',
        'stochasticindicator_k_period14_d_period3',
        'adxindicator_period14',
        'aroonindicator_period25',
        'atrinticator_period14',
        'obvindicator',
        'vwapindicator',
        'mfiindicator_period14',
    ]

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_pool: Optional[Any] = None,
        window_size: int = 200,
        indicator_names: Optional[List[str]] = None,
        min_ticks_for_calc: int = 50,
    ) -> None:
        """
        Initialize enrichment service.

        Args:
            db_pool: PostgreSQL connection pool
            redis_pool: Redis connection pool (optional, for pub/sub to strategies)
            window_size: Number of ticks to load for calculations (default: 200)
            indicator_names: List of indicator names to calculate
            min_ticks_for_calc: Minimum ticks required before calculating (default: 50)
        """
        self.db_pool: asyncpg.Pool = db_pool
        self.redis_pool: Optional[Any] = redis_pool
        self.window_size: int = window_size
        self.indicator_names: List[str] = indicator_names or self.DEFAULT_INDICATORS.copy()
        self.min_ticks_for_calc: int = min_ticks_for_calc

        # State per symbol
        self._tick_windows: Dict[int, Dict[str, np.ndarray]] = {}
        self._indicators: Dict[str, Indicator] = {}
        self._running: bool = False
        self._stats: Dict[str, int] = {
            'ticks_processed': 0,
            'indicators_calculated': 0,
            'errors': 0,
            'skipped_insufficient_data': 0,
        }

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
        Initialize active indicators from database.
        
        Loads only indicators where is_active = true from indicator_definitions table.
        Supports dynamic activation/deactivation at runtime.
        """
        logger.info("Loading active indicators from database...")

        async with self.db_pool.acquire() as conn:
            # Fetch active indicators from database
            rows = await conn.fetch(
                """
                SELECT name, params
                FROM indicator_definitions
                WHERE is_active = true
                ORDER BY name
                """
            )
            
            IndicatorRegistry.discover()
            
            # Clear existing indicators
            self._indicators.clear()
            self.indicator_names = []
            
            loaded = 0
            for row in rows:
                name = row['name']
                params = row['params'] or {}
                
                indicator = IndicatorRegistry.get(name, **params)
                if indicator:
                    self._indicators[name] = indicator
                    self.indicator_names.append(name)
                    logger.debug(f"Loaded active indicator: {name}")
                    loaded += 1
                else:
                    logger.warning(f"Active indicator not found: {name}")
            
            logger.info(f"Loaded {loaded} active indicators from database")
            
            if loaded == 0:
                logger.warning("No active indicators configured - add some via:")
                logger.warning("  UPDATE indicator_definitions SET is_active = true WHERE name = 'rsiindicator_period14';")

    async def _listen_for_ticks(self) -> None:
        """
        Listen for new ticks via PostgreSQL NOTIFY.

        Listens to 'new_tick' channel which is fired when ticker_24hr_stats receives INSERT.
        """
        async with self.db_pool.acquire() as conn:
            await conn.listen('new_tick')
            logger.info("Listening for new_tick notifications...")

            while self._running:
                try:
                    notification = await asyncio.wait_for(
                        conn.notification(),
                        timeout=60.0
                    )

                    await self._process_notification(notification)

                except asyncio.TimeoutError:
                    # Send heartbeat
                    await self._heartbeat()

                except Exception as e:
                    logger.error(f"Error processing notification: {e}", exc_info=True)
                    self._stats['errors'] += 1

    async def _process_notification(self, notification: Any) -> None:
        """
        Process tick notification from ticker_24hr_stats.

        Flow:
        1. Parse notification payload (symbol_id, time)
        2. Load tick history from database (last 200 ticks)
        3. Calculate all indicators
        4. Store in tick_indicators table
        5. Fire enrichment_complete notification

        Args:
            notification: PostgreSQL notification object
        """
        start_time = datetime.utcnow()

        try:
            # Parse notification payload
            payload = json.loads(notification.payload)
            symbol_id = payload.get('symbol_id')
            tick_time = payload.get('time')

            if not symbol_id or not tick_time:
                logger.warning(f"Invalid notification payload: {payload}")
                return

            # Load recent tick history for this symbol
            tick_history = await self._load_tick_history(symbol_id, limit=self.window_size)

            if len(tick_history) < self.min_ticks_for_calc:
                logger.debug(
                    f"Insufficient data for symbol {symbol_id}: "
                    f"got {len(tick_history)}, need {self.min_ticks_for_calc}"
                )
                self._stats['skipped_insufficient_data'] += 1
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
            latest_time = latest_tick.get('time') or tick_time
            latest_price = float(latest_tick.get('last_price', 0))
            latest_volume = float(latest_tick.get('volume', 0))

            # Store enriched data
            await self._store_enriched_data(
                symbol_id=symbol_id,
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
            total_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Update stats
            self._stats['ticks_processed'] += 1
            self._stats['indicators_calculated'] += len(indicator_values)

            # Save pipeline metrics for dashboard monitoring
            await self._save_pipeline_metrics(
                symbol_id=symbol_id,
                enrichment_time_ms=total_time_ms,
                total_time_ms=total_time_ms,
                active_symbols_count=len(self._symbol_ids) if hasattr(self, '_symbol_ids') else 0,
                active_indicators_count=len(self._indicators),
                status='success' if total_time_ms < 1000 else 'slow',
            )

            # Log performance
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.debug(f"Enrichment completed for symbol {symbol_id} in {elapsed_ms:.2f}ms")

        except Exception as e:
            logger.error(f"Error processing tick: {e}", exc_info=True)
            self._stats['errors'] += 1
            raise  # Re-raise to allow retry logic if needed

    async def _load_tick_history(
        self,
        symbol_id: int,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Load recent tick history for symbol from ticker_24hr_stats.

        Args:
            symbol_id: Symbol ID to load history for
            limit: Number of ticks to load (default: 200)

        Returns:
            List of tick dictionaries, ordered by time ascending
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT time, last_price, open_price, high_price, low_price,
                       volume, quote_volume, price_change, price_change_pct
                FROM ticker_24hr_stats
                WHERE symbol_id = $1
                ORDER BY time ASC
                LIMIT $2
                """,
                symbol_id,
                limit
            )

            # Return as list of dicts, ordered by time ascending
            return [dict(row) for row in rows]

    def _extract_arrays(
        self,
        tick_history: List[Dict[str, Any]]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract numpy arrays from tick history.

        Args:
            tick_history: List of tick dictionaries

        Returns:
            Tuple of (prices, volumes, highs, lows) as numpy arrays
        """
        prices = np.array([float(t.get('last_price', 0)) for t in tick_history])
        volumes = np.array([float(t.get('volume', 0)) for t in tick_history])
        highs = np.array([float(t.get('high_price', 0)) for t in tick_history])
        lows = np.array([float(t.get('low_price', 0)) for t in tick_history])

        return prices, volumes, highs, lows

    async def _calculate_indicators(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
    ) -> Dict[str, float]:
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
        indicator_values: Dict[str, float] = {}

        for name, indicator in self._indicators.items():
            try:
                result = indicator.calculate(
                    prices=prices,
                    volumes=volumes,
                    highs=highs,
                    lows=lows,
                )

                # Get latest value for each indicator output
                for key, values in result.values.items():
                    if len(values) > 0:
                        latest_value = values[-1]
                        if not np.isnan(latest_value):
                            indicator_values[f"{name}_{key}"] = float(latest_value)

            except Exception as e:
                logger.error(f"Error calculating indicator {name}: {e}", exc_info=True)
                self._stats['errors'] += 1

        return indicator_values

    async def _store_enriched_data(
        self,
        symbol_id: int,
        time: Any,
        price: float,
        volume: float,
        indicator_values: Dict[str, float],
    ) -> None:
        """
        Store enriched tick data in tick_indicators table.

        Args:
            symbol_id: Symbol ID
            time: Tick time
            price: Current price
            volume: Current volume
            indicator_values: Calculated indicator values
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tick_indicators (
                    time, symbol_id, price, volume,
                    values, indicator_keys, indicator_version
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, 1
                )
                ON CONFLICT (time, symbol_id) DO UPDATE SET
                    price = EXCLUDED.price,
                    volume = EXCLUDED.volume,
                    values = EXCLUDED.values,
                    indicator_keys = EXCLUDED.indicator_keys,
                    updated_at = NOW()
                """,
                time,
                symbol_id,
                Decimal(str(price)),
                Decimal(str(volume)),
                json.dumps(indicator_values),
                list(indicator_values.keys()),
            )

            logger.debug(f"Stored {len(indicator_values)} indicators for symbol {symbol_id}")

    async def _notify_enrichment_complete(
        self,
        symbol_id: int,
        time: str
    ) -> None:
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
                json.dumps({
                    'symbol_id': symbol_id,
                    'time': time,
                    'processed_at': datetime.utcnow().isoformat(),
                    'indicators_count': len(self._indicators),
                })
            )

    async def _publish_to_redis(
        self,
        symbol_id: int,
        price: float,
        indicator_values: Dict[str, float],
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
                symbol = await conn.fetchval(
                    "SELECT symbol FROM symbols WHERE id = $1",
                    symbol_id
                )

            # Publish message
            message = {
                'symbol': symbol,
                'symbol_id': symbol_id,
                'price': price,
                'time': datetime.utcnow().isoformat(),
                'indicators': indicator_values,
            }

            await self.redis_pool.publish(
                f'enriched_tick:{symbol}',
                json.dumps(message)
            )

        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")

    async def _heartbeat(self) -> None:
        """Send heartbeat / update stats."""
        if self._stats['ticks_processed'] > 0 and self._stats['ticks_processed'] % 100 == 0:
            logger.info(
                f"Enrichment stats: {self._stats['ticks_processed']} ticks, "
                f"{self._stats['indicators_calculated']} indicators, "
                f"{self._stats['errors']} errors, "
                f"{self._stats['skipped_insufficient_data']} skipped (insufficient data)"
            )

    def get_stats(self) -> Dict[str, int]:
        """Get enrichment statistics."""
        return self._stats.copy()

    async def _save_pipeline_metrics(
        self,
        symbol_id: int,
        enrichment_time_ms: int,
        total_time_ms: int,
        active_symbols_count: int,
        active_indicators_count: int,
        status: str = 'success',
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

    def set_indicators(self, indicator_names: List[str]) -> None:
        """
        Update list of indicators to calculate.
        
        DEPRECATED: Use database activation instead:
            UPDATE indicator_definitions SET is_active = true/false WHERE name = '...';
        
        Args:
            indicator_names: New list of indicator names
        """
        logger.warning("set_indicators() is deprecated - use database activation instead")
        logger.info(f"Updating indicators: {len(self.indicator_names)} -> {len(indicator_names)}")
        self.indicator_names = indicator_names
        self._indicators.clear()

        # Reinitialize indicators
        IndicatorRegistry.discover()
        for name in self.indicator_names:
            indicator = IndicatorRegistry.get(name)
            if indicator:
                self._indicators[name] = indicator
