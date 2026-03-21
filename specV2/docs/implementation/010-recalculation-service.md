# Step 010: Recalculation Service - Implementation Guide

**Phase**: 4 - Enrichment  
**Effort**: 8 hours  
**Dependencies**: Step 006 (Indicator Framework), Step 008 (Enrichment Service) ✅ Complete  
**Status**: Ready to implement

---

## Overview

This step implements the **automatic indicator recalculation service** that:
- Listens for indicator definition changes via PostgreSQL NOTIFY
- Triggers batch recalculation for affected symbols
- Processes historical data in chunks
- Updates tick_indicators table
- Tracks recalculation progress and job status
- Comprehensive tests (80%+ coverage)

---

## Implementation Tasks

### Task 1: Recalculation Service

**File**: `src/application/services/recalculation_service.py`

```python
"""
Automatic indicator recalculation service.

Listens for indicator definition changes and triggers
batch recalculation of historical data.
"""

import asyncio
import asyncpg
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
import logging
import json

from src.indicators.registry import IndicatorRegistry
from src.indicators.base import Indicator

logger = logging.getLogger(__name__)


class RecalculationService:
    """
    Automatic indicator recalculation service.
    
    Listens for indicator_changed notifications from PostgreSQL
    and recalculates indicators for historical data.
    
    Attributes:
        db_pool: PostgreSQL connection pool
        batch_size: Number of ticks to process per batch
        max_workers: Maximum concurrent recalculation jobs
    
    Example:
        >>> service = RecalculationService(db_pool)
        >>> await service.start()
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        batch_size: int = 10000,
        max_workers: int = 2,
    ) -> None:
        """
        Initialize recalculation service.
        
        Args:
            db_pool: PostgreSQL connection pool
            batch_size: Ticks per batch (default: 10000)
            max_workers: Max concurrent jobs (default: 2)
        """
        self.db_pool: asyncpg.Pool = db_pool
        self.batch_size: int = batch_size
        self.max_workers: int = max_workers
        
        self._running: bool = False
        self._active_jobs: Dict[str, asyncio.Task] = {}
        self._stats: Dict[str, int] = {
            'jobs_started': 0,
            'jobs_completed': 0,
            'jobs_failed': 0,
            'ticks_recalculated': 0,
        }
    
    async def start(self) -> None:
        """Start recalculation service."""
        logger.info("Starting Recalculation Service...")
        
        IndicatorRegistry.discover()
        self._running = True
        
        await self._listen_for_changes()
    
    async def stop(self) -> None:
        """Stop recalculation service."""
        logger.info("Stopping Recalculation Service...")
        
        self._running = False
        
        # Cancel active jobs
        for job_id, task in self._active_jobs.items():
            task.cancel()
            logger.info(f"Cancelled job {job_id}")
    
    async def _listen_for_changes(self) -> None:
        """Listen for indicator_changed notifications."""
        async with self.db_pool.acquire() as conn:
            await conn.listen('indicator_changed')
            logger.info("Listening for indicator_changed notifications...")
            
            while self._running:
                try:
                    notification = await asyncio.wait_for(
                        conn.notification(),
                        timeout=60.0
                    )
                    
                    await self._process_change_notification(notification)
                
                except asyncio.TimeoutError:
                    await self._heartbeat()
                
                except Exception as e:
                    logger.error(f"Error processing notification: {e}")
    
    async def _process_change_notification(
        self,
        notification: Any,
    ) -> None:
        """
        Process indicator change notification.
        
        Args:
            notification: PostgreSQL notification
        """
        try:
            payload = json.loads(notification.payload)
            
            indicator_name = payload.get('indicator_name')
            change_type = payload.get('change_type')
            
            logger.info(
                f"Indicator changed: {indicator_name} ({change_type})"
            )
            
            # Create recalculation job
            job_id = await self._create_recalculation_job(
                indicator_name,
                change_type,
            )
            
            # Start recalculation task
            task = asyncio.create_task(
                self._run_recalculation(job_id, indicator_name)
            )
            
            self._active_jobs[job_id] = task
            self._stats['jobs_started'] += 1
        
        except Exception as e:
            logger.error(f"Error processing change notification: {e}")
    
    async def _create_recalculation_job(
        self,
        indicator_name: str,
        change_type: str,
    ) -> str:
        """
        Create recalculation job record.
        
        Args:
            indicator_name: Indicator name
            change_type: Type of change
        
        Returns:
            Job ID
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO recalculation_jobs (
                    indicator_name, status, triggered_by,
                    created_at
                ) VALUES ($1, 'pending', 'auto', NOW())
                RETURNING id
                """,
                indicator_name,
            )
            
            return str(result['id'])
    
    async def _run_recalculation(
        self,
        job_id: str,
        indicator_name: str,
    ) -> None:
        """
        Run recalculation job.
        
        Args:
            job_id: Job ID
            indicator_name: Indicator name
        """
        try:
            # Update job status
            await self._update_job_status(job_id, 'running')
            
            # Get indicator instance
            indicator = IndicatorRegistry.get(indicator_name)
            
            if not indicator:
                raise ValueError(f"Indicator not found: {indicator_name}")
            
            # Get all active symbols
            symbols = await self._get_active_symbols()
            
            total_ticks = 0
            
            # Recalculate for each symbol
            for symbol_id, symbol in symbols:
                ticks_processed = await self._recalculate_symbol(
                    symbol_id,
                    symbol,
                    indicator,
                    job_id,
                )
                total_ticks += ticks_processed
            
            # Mark job as completed
            await self._update_job_status(
                job_id,
                'completed',
                ticks_processed=total_ticks,
            )
            
            self._stats['jobs_completed'] += 1
            self._stats['ticks_recalculated'] += total_ticks
            
            logger.info(
                f"Recalculation completed: {job_id} "
                f"({total_ticks} ticks)"
            )
        
        except Exception as e:
            logger.error(f"Recalculation failed: {e}")
            await self._update_job_status(job_id, 'failed', error=str(e))
            self._stats['jobs_failed'] += 1
        
        finally:
            # Remove from active jobs
            if job_id in self._active_jobs:
                del self._active_jobs[job_id]
    
    async def _recalculate_symbol(
        self,
        symbol_id: int,
        symbol: str,
        indicator: Indicator,
        job_id: str,
    ) -> int:
        """
        Recalculate indicator for symbol.
        
        Args:
            symbol_id: Symbol ID
            symbol: Symbol name
            indicator: Indicator instance
            job_id: Job ID
        
        Returns:
            Number of ticks processed
        """
        logger.info(f"Recalculating {indicator.name} for {symbol}")
        
        ticks_processed = 0
        offset = 0
        
        while True:
            # Load batch of ticks
            ticks = await self._load_ticks(symbol_id, offset, self.batch_size)
            
            if not ticks:
                break
            
            # Calculate indicator
            prices = np.array([float(t['price']) for t in ticks])
            volumes = np.array([float(t['quantity']) for t in ticks])
            
            result = indicator.calculate(prices, volumes)
            
            # Store results
            await self._store_indicator_results(
                symbol_id,
                ticks,
                result,
            )
            
            ticks_processed += len(ticks)
            offset += self.batch_size
            
            # Update progress
            await self._update_job_progress(job_id, ticks_processed)
            
            logger.debug(
                f"Processed {ticks_processed} ticks for {symbol}"
            )
        
        return ticks_processed
    
    async def _load_ticks(
        self,
        symbol_id: int,
        offset: int,
        limit: int,
    ) -> List[Dict]:
        """
        Load ticks from database.
        
        Args:
            symbol_id: Symbol ID
            offset: Offset for pagination
            limit: Number of ticks to load
        
        Returns:
            List of tick dictionaries
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT time, price, quantity
                FROM trades
                WHERE symbol_id = $1
                ORDER BY time
                LIMIT $2 OFFSET $3
                """,
                symbol_id,
                limit,
                offset,
            )
            
            return [dict(row) for row in rows]
    
    async def _store_indicator_results(
        self,
        symbol_id: int,
        ticks: List[Dict],
        result: Any,
    ) -> None:
        """
        Store indicator results.
        
        Args:
            symbol_id: Symbol ID
            ticks: List of ticks
            result: Indicator result
        """
        async with self.db_pool.acquire() as conn:
            for i, tick in enumerate(ticks):
                # Get indicator values for this tick
                indicator_values = {}
                
                for key, values in result.values.items():
                    if i < len(values) and not np.isnan(values[i]):
                        indicator_values[f"{result.name}_{key}"] = float(values[i])
                
                if indicator_values:
                    await conn.execute(
                        """
                        INSERT INTO tick_indicators (
                            time, symbol_id, price, volume,
                            values, indicator_keys, indicator_version
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, 1
                        )
                        ON CONFLICT (time, symbol_id) DO UPDATE SET
                            values = EXCLUDED.values,
                            indicator_keys = EXCLUDED.indicator_keys,
                            updated_at = NOW()
                        """,
                        tick['time'],
                        symbol_id,
                        tick['price'],
                        tick['quantity'],
                        json.dumps(indicator_values),
                        list(indicator_values.keys()),
                    )
    
    async def _get_active_symbols(self) -> List[tuple]:
        """
        Get all active symbols.
        
        Returns:
            List of (symbol_id, symbol) tuples
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, symbol
                FROM symbols
                WHERE is_active = true
                ORDER BY symbol
                """
            )
            
            return [(row['id'], row['symbol']) for row in rows]
    
    async def _update_job_status(
        self,
        job_id: str,
        status: str,
        ticks_processed: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Update job status."""
        async with self.db_pool.acquire() as conn:
            if status == 'completed':
                await conn.execute(
                    """
                    UPDATE recalculation_jobs
                    SET status = $1,
                        ticks_processed = $2,
                        completed_at = NOW(),
                        duration_seconds = NOW() - started_at
                    WHERE id = $3
                    """,
                    status,
                    ticks_processed,
                    job_id,
                )
            elif status == 'failed':
                await conn.execute(
                    """
                    UPDATE recalculation_jobs
                    SET status = $1,
                        last_error = $2,
                        completed_at = NOW()
                    WHERE id = $3
                    """,
                    status,
                    error,
                    job_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE recalculation_jobs
                    SET status = $1,
                        started_at = NOW()
                    WHERE id = $2
                    """,
                    status,
                    job_id,
                )
    
    async def _update_job_progress(
        self,
        job_id: str,
        ticks_processed: int,
    ) -> None:
        """Update job progress."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE recalculation_jobs
                SET ticks_processed = $1
                WHERE id = $2
                """,
                ticks_processed,
                job_id,
            )
    
    async def _heartbeat(self) -> None:
        """Send heartbeat / update stats."""
        if self._stats['jobs_started'] % 10 == 0:
            logger.info(
                f"Recalculation stats: "
                f"{self._stats['jobs_started']} jobs started, "
                f"{self._stats['jobs_completed']} completed, "
                f"{self._stats['jobs_failed']} failed, "
                f"{self._stats['ticks_recalculated']} ticks"
            )
    
    def get_stats(self) -> Dict[str, int]:
        """Get recalculation statistics."""
        return self._stats.copy()

```

---

## Acceptance Criteria

- [ ] RecalculationService implemented
- [ ] PostgreSQL LISTEN/NOTIFY for changes
- [ ] Batch processing of historical data
- [ ] Progress tracking
- [ ] Error handling and retry
- [ ] Unit tests (80%+ coverage)
- [ ] Integration test with indicator framework

---

## Next Steps

After completing this step, proceed to **Step 011: CLI Tools**
