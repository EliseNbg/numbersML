"""
Real-time indicator enrichment service.

Listens to incoming ticks and calculates indicators in real-time.
"""

import asyncio
import asyncpg
import numpy as np
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
import logging
import json

from src.indicators.registry import IndicatorRegistry
from src.indicators.base import Indicator

logger = logging.getLogger(__name__)


class EnrichmentService:
    """
    Real-time indicator enrichment service.
    
    Listens to new ticks via PostgreSQL NOTIFY/LISTEN,
    calculates all configured indicators, and stores
    enriched data.
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_pool: Optional[Any] = None,
        window_size: int = 1000,
        indicator_names: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize enrichment service.
        
        Args:
            db_pool: PostgreSQL connection pool
            redis_pool: Redis connection pool (optional)
            window_size: Tick window size (default: 1000)
            indicator_names: List of indicator names to calculate
        """
        self.db_pool: asyncpg.Pool = db_pool
        self.redis_pool: Optional[Any] = redis_pool
        self.window_size: int = window_size
        self.indicator_names: List[str] = indicator_names or []
        
        # State per symbol
        self._tick_windows: Dict[int, Dict] = {}
        self._indicators: Dict[str, Indicator] = {}
        self._running: bool = False
        self._stats: Dict[str, int] = {
            'ticks_processed': 0,
            'indicators_calculated': 0,
            'errors': 0
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
        """Initialize indicators from registry."""
        IndicatorRegistry.discover()
        
        # Default indicators if not specified
        if not self.indicator_names:
            self.indicator_names = [
                'rsiindicator_period14',
                'smaindicator_period20',
                'smaindicator_period50',
                'emaindicator_period20',
                'bbindicator_period20_std_dev2.0',
            ]
        
        # Create indicator instances
        for name in self.indicator_names:
            indicator = IndicatorRegistry.get(name)
            if indicator:
                self._indicators[name] = indicator
                logger.info(f"Loaded indicator: {name}")
            else:
                logger.warning(f"Indicator not found: {name}")
    
    async def _listen_for_ticks(self) -> None:
        """Listen for new ticks via PostgreSQL NOTIFY."""
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
                    logger.error(f"Error processing notification: {e}")
                    self._stats['errors'] += 1
    
    async def _process_notification(self, notification: Any) -> None:
        """Process tick notification."""
        try:
            # Parse notification payload
            payload = json.loads(notification.payload)
            symbol_id = payload.get('symbol_id')
            tick_data = payload.get('tick', {})
            
            if not symbol_id:
                return
            
            # Update tick window
            await self._update_tick_window(symbol_id, tick_data)
            
            # Calculate indicators
            await self._calculate_indicators(symbol_id)
            
            self._stats['ticks_processed'] += 1
        
        except Exception as e:
            logger.error(f"Error processing tick: {e}")
            self._stats['errors'] += 1
    
    async def _update_tick_window(
        self,
        symbol_id: int,
        tick_data: Dict,
    ) -> None:
        """Update tick window for symbol."""
        if symbol_id not in self._tick_windows:
            self._tick_windows[symbol_id] = {
                'prices': np.zeros(self.window_size),
                'volumes': np.zeros(self.window_size),
                'highs': np.zeros(self.window_size),
                'lows': np.zeros(self.window_size),
                'count': 0,
                'index': 0,
            }
        
        window = self._tick_windows[symbol_id]
        idx = window['index']
        
        # Add new tick
        window['prices'][idx] = float(tick_data.get('price', 0))
        window['volumes'][idx] = float(tick_data.get('quantity', 0))
        window['highs'][idx] = float(tick_data.get('high', tick_data.get('price', 0)))
        window['lows'][idx] = float(tick_data.get('low', tick_data.get('price', 0)))
        
        # Update index
        window['index'] = (idx + 1) % self.window_size
        window['count'] = min(window['count'] + 1, self.window_size)
    
    async def _calculate_indicators(self, symbol_id: int) -> None:
        """Calculate all indicators for symbol."""
        window = self._tick_windows.get(symbol_id)
        
        if not window or window['count'] < 2:
            return
        
        # Get valid data
        count = window['count']
        idx = window['index']
        
        # Extract circular buffer data
        if count < self.window_size:
            prices = window['prices'][:count]
            volumes = window['volumes'][:count]
            highs = window['highs'][:count]
            lows = window['lows'][:count]
        else:
            prices = np.concatenate([
                window['prices'][idx:],
                window['prices'][:idx]
            ])
            volumes = np.concatenate([
                window['volumes'][idx:],
                window['volumes'][:idx]
            ])
            highs = np.concatenate([
                window['highs'][idx:],
                window['highs'][:idx]
            ])
            lows = np.concatenate([
                window['lows'][idx:],
                window['lows'][:idx]
            ])
        
        # Calculate all indicators
        indicator_values = {}
        
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
                    if len(values) > 0 and not np.isnan(values[-1]):
                        indicator_values[f"{name}_{key}"] = float(values[-1])
                
                self._stats['indicators_calculated'] += 1
            
            except Exception as e:
                logger.error(f"Error calculating {name}: {e}")
                self._stats['errors'] += 1
        
        # Store enriched data
        await self._store_enriched_data(
            symbol_id,
            prices[-1] if len(prices) > 0 else 0,
            volumes[-1] if len(volumes) > 0 else 0,
            indicator_values,
        )
        
        # Publish to Redis
        if self.redis_pool:
            await self._publish_to_redis(
                symbol_id,
                prices[-1] if len(prices) > 0 else 0,
                indicator_values,
            )
    
    async def _store_enriched_data(
        self,
        symbol_id: int,
        price: float,
        volume: float,
        indicator_values: Dict[str, float],
    ) -> None:
        """Store enriched tick data in database."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tick_indicators (
                    time, symbol_id, price, volume,
                    values, indicator_keys, indicator_version
                ) VALUES (
                    NOW(), $1, $2, $3, $4, $5, 1
                )
                ON CONFLICT (time, symbol_id) DO UPDATE SET
                    price = EXCLUDED.price,
                    volume = EXCLUDED.volume,
                    values = EXCLUDED.values,
                    indicator_keys = EXCLUDED.indicator_keys,
                    updated_at = NOW()
                """,
                symbol_id,
                Decimal(str(price)),
                Decimal(str(volume)),
                json.dumps(indicator_values),
                list(indicator_values.keys()),
            )
    
    async def _publish_to_redis(
        self,
        symbol_id: int,
        price: float,
        indicator_values: Dict[str, float],
    ) -> None:
        """Publish enriched tick to Redis."""
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
        if self._stats['ticks_processed'] % 1000 == 0:
            logger.info(
                f"Enrichment stats: {self._stats['ticks_processed']} ticks, "
                f"{self._stats['indicators_calculated']} indicators, "
                f"{self._stats['errors']} errors"
            )
    
    def get_stats(self) -> Dict[str, int]:
        """Get enrichment statistics."""
        return self._stats.copy()
