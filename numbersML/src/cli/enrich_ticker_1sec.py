#!/usr/bin/env python3
"""
Optimized indicator calculation for 1-second ticker updates.

Calculates indicators once per second per symbol from !miniTicker@arr stream.
Workload optimized for acceptable CPU/memory usage.
"""

import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any
import logging
import json
import time

from src.indicators.registry import IndicatorRegistry
from src.indicators.base import Indicator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OptimizedEnrichmentService:
    """
    Optimized indicator enrichment service for 1-second updates.

    Features:
    - Listens to new_ticker_1sec channel (once per second)
    - Calculates indicators efficiently
    - Batch database writes
    - Memory-efficient circular buffers
    """

    # Optimized for 1-second updates
    DEFAULT_WINDOW_SIZE = 200  # 200 seconds = ~3 minutes (sufficient for most indicators)
    DEFAULT_INDICATORS = [
        'rsiindicator_period14',
        'smaindicator_period20',
        'smaindicator_period50',
        'emaindicator_period12',
        'emaindicator_period26',
    ]

    def __init__(
        self,
        db_url: str,
        window_size: int = 200,
        indicator_names: Optional[List[str]] = None,
        batch_size: int = 10,  # Store indicators every 10 seconds
    ) -> None:
        """
        Initialize optimized enrichment service.

        Args:
            db_url: PostgreSQL connection URL
            window_size: Tick window size (default: 200 for 1-sec updates)
            indicator_names: List of indicators to calculate
            batch_size: Batch store indicators (reduce DB writes)
        """
        self.db_url = db_url
        self.window_size = window_size
        self.indicator_names = indicator_names or self.DEFAULT_INDICATORS
        self.batch_size = batch_size

        self.db_pool = None
        self._indicators: Dict[str, Indicator] = {}
        self._tick_windows: Dict[int, Dict[str, np.ndarray]] = {}
        self._indicator_buffer: List[Dict] = []
        self._running = False
        self._stats = {
            'ticks_processed': 0,
            'indicators_calculated': 0,
            'batches_stored': 0,
            'errors': 0,
            'start_time': None,
        }

    async def start(self) -> None:
        """Start enrichment service."""
        logger.info("=" * 60)
        logger.info("Starting Optimized Enrichment Service (1-sec updates)")
        logger.info("=" * 60)
        logger.info(f"Window size: {self.window_size} seconds")
        logger.info(f"Indicators: {len(self.indicator_names)}")
        logger.info(f"Batch size: {self.batch_size} seconds")
        logger.info(f"Indicators: {self.indicator_names}")

        # Setup
        self.db_pool = await asyncpg.create_pool(
            self.db_url,
            min_size=2,
            max_size=10,
        )
        await self._init_indicators()
        self._stats['start_time'] = time.time()

        self._running = True
        await self._listen_for_tickers()

    async def stop(self) -> None:
        """Stop enrichment service."""
        logger.info("Stopping enrichment service...")
        self._running = False
        
        # Store remaining buffer
        if self._indicator_buffer:
            await self._store_indicators_batch()
        
        if self.db_pool:
            await self.db_pool.close()
        
        self._print_stats()

    def _print_stats(self) -> None:
        """Print final statistics."""
        elapsed = time.time() - self._stats['start_time'] if self._stats['start_time'] else 0
        logger.info("=" * 60)
        logger.info("Final Statistics:")
        logger.info(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f} min)")
        logger.info(f"  Ticks processed: {self._stats['ticks_processed']}")
        logger.info(f"  Indicators calculated: {self._stats['indicators_calculated']}")
        logger.info(f"  Batches stored: {self._stats['batches_stored']}")
        logger.info(f"  Errors: {self._stats['errors']}")
        if elapsed > 0:
            logger.info(f"  Ticks/sec: {self._stats['ticks_processed']/elapsed:.1f}")
        logger.info("=" * 60)

    async def _init_indicators(self) -> None:
        """Initialize indicators from registry."""
        logger.info("Loading indicators...")
        IndicatorRegistry.discover()

        for name in self.indicator_names:
            indicator = IndicatorRegistry.get(name)
            if indicator:
                self._indicators[name] = indicator
                logger.info(f"  ✓ {name}")
            else:
                logger.warning(f"  ✗ Indicator not found: {name}")

        logger.info(f"Loaded {len(self._indicators)} indicators")

    async def _listen_for_tickers(self) -> None:
        """Listen for 1-second ticker updates."""
        logger.info(f"Listening on channel: new_ticker_1sec")

        async with self.db_pool.acquire() as conn:
            await conn.listen('new_ticker_1sec')
            logger.info("Connected - waiting for tickers...")

            while self._running:
                try:
                    notification = await asyncio.wait_for(
                        conn.notification(),
                        timeout=60.0
                    )
                    await self._process_ticker(notification)

                except asyncio.TimeoutError:
                    # Heartbeat every 60 seconds
                    await self._heartbeat()

                except Exception as e:
                    self._stats['errors'] += 1
                    logger.error(f"Error: {e}")

    async def _process_ticker(self, notification: Any) -> None:
        """
        Process ticker notification.

        Called once per second per symbol.
        """
        try:
            payload = json.loads(notification.payload)
            symbol_id = payload.get('symbol_id')
            symbol = payload.get('symbol')
            price = float(payload.get('price', 0))
            time_str = payload.get('time')

            if not symbol_id or not price:
                return

            # Update tick window (circular buffer)
            self._update_window(symbol_id, price)

            # Calculate indicators
            indicator_values = await self._calculate_indicators(symbol_id)

            if indicator_values:
                # Add to batch buffer
                self._indicator_buffer.append({
                    'time': time_str or datetime.now(timezone.utc).isoformat(),
                    'symbol_id': symbol_id,
                    'symbol': symbol,
                    'price': price,
                    'values': indicator_values,
                })

                # Store batch if full
                if len(self._indicator_buffer) >= self.batch_size:
                    await self._store_indicators_batch()

            self._stats['ticks_processed'] += 1

            # Log progress every 100 ticks
            if self._stats['ticks_processed'] % 100 == 0:
                self._log_progress()

        except Exception as e:
            self._stats['errors'] += 1
            logger.error(f"Error processing ticker: {e}")

    def _update_window(self, symbol_id: int, price: float) -> None:
        """Update circular buffer for symbol."""
        if symbol_id not in self._tick_windows:
            # Initialize window
            self._tick_windows[symbol_id] = {
                'prices': np.zeros(self.window_size),
                'count': 0,
                'index': 0,
            }

        window = self._tick_windows[symbol_id]
        idx = window['index']

        # Add new price
        window['prices'][idx] = price

        # Update circular index
        window['index'] = (idx + 1) % self.window_size
        window['count'] = min(window['count'] + 1, self.window_size)

    async def _calculate_indicators(self, symbol_id: int) -> Optional[Dict[str, float]]:
        """
        Calculate all indicators for symbol.

        Optimized: Only calculates when enough data available.
        """
        window = self._tick_windows.get(symbol_id)
        if not window or window['count'] < 50:  # Need minimum data
            return None

        # Get price data from circular buffer
        count = window['count']
        idx = window['index']
        prices = window['prices'][:count] if count < self.window_size else \
                 np.concatenate([window['prices'][idx:], window['prices'][:idx]])

        if len(prices) < 50:
            return None

        # Calculate all indicators
        values = {}
        volumes = np.ones_like(prices)  # Dummy volume for indicators that need it

        for name, indicator in self._indicators.items():
            try:
                result = indicator.calculate(prices, volumes)
                if result and result.values:
                    # Get latest value for each output
                    for key, val_array in result.values.items():
                        if len(val_array) > 0 and not np.isnan(val_array[-1]):
                            values[f"{name}_{key}"] = float(val_array[-1])

                self._stats['indicators_calculated'] += 1
            except Exception as e:
                logger.debug(f"Indicator {name} error: {e}")
                self._stats['errors'] += 1

        return values if values else None

    async def _store_indicators_batch(self) -> None:
        """Store batch of indicator results to database."""
        if not self._indicator_buffer:
            return

        try:
            async with self.db_pool.acquire() as conn:
                # Batch insert
                await conn.executemany(
                    """
                    INSERT INTO candle_indicators (time, symbol_id, price, volume, values, indicator_keys)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (time, symbol_id) DO UPDATE SET
                        values = EXCLUDED.values,
                        indicator_keys = EXCLUDED.indicator_keys
                    """,
                    [
                        (
                            item['time'],
                            item['symbol_id'],
                            item['price'],
                            0.0,  # No volume in miniTicker
                            json.dumps(item['values']),
                            list(item['values'].keys()),
                        )
                        for item in self._indicator_buffer
                    ]
                )

            self._stats['batches_stored'] += 1
            logger.debug(f"Stored batch: {len(self._indicator_buffer)} indicators")
            self._indicator_buffer = []

        except Exception as e:
            self._stats['errors'] += 1
            logger.error(f"Error storing batch: {e}")

    async def _heartbeat(self) -> None:
        """Periodic heartbeat and stats."""
        elapsed = time.time() - self._stats['start_time'] if self._stats['start_time'] else 0
        ticks_per_sec = self._stats['ticks_processed'] / elapsed if elapsed > 0 else 0
        
        logger.info(
            f"Heartbeat: {self._stats['ticks_processed']} ticks, "
            f"{self._stats['indicators_calculated']} indicators, "
            f"{ticks_per_sec:.1f} ticks/sec, "
            f"{len(self._tick_windows)} symbols"
        )

        # Store any remaining buffer
        if self._indicator_buffer:
            await self._store_indicators_batch()


async def main() -> None:
    """Main entry point."""
    db_url = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"

    print("=" * 60)
    print("Optimized Enrichment Service")
    print("Calculates indicators from 1-second ticker updates")
    print("=" * 60)
    print()

    service = OptimizedEnrichmentService(
        db_url=db_url,
        window_size=200,  # 200 seconds window
        indicator_names=[
            'rsiindicator_period14',
            'smaindicator_period20',
            'smaindicator_period50',
            'emaindicator_period12',
            'emaindicator_period26',
            'macdindicator_fast_period12_slow_period26_signal_period9',
        ],
        batch_size=10,  # Store every 10 seconds
    )

    try:
        await service.start()
    except KeyboardInterrupt:
        print("\nStopping...")
        await service.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await service.stop()
        raise


if __name__ == '__main__':
    asyncio.run(main())
