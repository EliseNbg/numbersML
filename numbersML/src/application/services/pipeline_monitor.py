"""
Pipeline monitoring service.

This service monitors the crypto trading data pipeline, including:
- Collector service status (running/stopped)
- SLA metrics from pipeline_metrics table
- Dashboard statistics

Architecture: Application Layer (orchestration)
Dependencies: Domain layer + Infrastructure (asyncpg)
"""

import asyncio
import logging
import os
import signal
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import asyncpg

from src.domain.models.dashboard import CollectorStatus, SLAMetric, DashboardStats

logger = logging.getLogger(__name__)


class PipelineMonitor:
    """
    Monitor pipeline performance and collector status.
    
    Responsibilities:
        - Check if collector process is running
        - Start/stop collector
        - Fetch SLA metrics from database
        - Calculate dashboard statistics
    
    Example:
        >>> monitor = PipelineMonitor(db_pool)
        >>> status = await monitor.get_collector_status()
        >>> if status.is_healthy:
        ...     print("Collector is healthy")
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.
        
        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
    
    async def get_collector_status(self) -> CollectorStatus:
        """
        Get current collector service status.
        
        Checks:
            - Process running (via PID file or process check)
            - Last tick time (from ticker_24hr_stats)
            - Error count (from service_status)
        
        Returns:
            Current collector status
        """
        status = CollectorStatus()
        
        # Check if collector process is running
        status.is_running = await self._is_collector_running()
        
        if status.is_running:
            status.pid = await self._get_collector_pid()
            status.uptime_seconds = await self._get_collector_uptime()
        
        # Get last tick time
        status.last_tick_time = await self._get_last_tick_time()
        
        # Get ticks processed and errors
        stats = await self._get_collector_stats()
        status.ticks_processed = stats.get('ticks_processed', 0)
        status.errors = stats.get('errors', 0)
        
        return status
    
    async def _is_collector_running(self) -> bool:
        """
        Check if pipeline service is running.
        
        Returns:
            True if service is running
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT status, is_healthy FROM service_status
                WHERE service_name = 'pipeline'
                ORDER BY updated_at DESC LIMIT 1
                """
            )
            
            if row:
                return row['status'] == 'running' or row['is_healthy']
            
            return False
    
    async def _get_collector_pid(self) -> Optional[int]:
        """
        Get pipeline service PID.
        
        Returns:
            Process ID or None
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT pid FROM service_status
                WHERE service_name = 'pipeline'
                ORDER BY updated_at DESC LIMIT 1
                """
            )
            
            return row['pid'] if row else None
    
    async def _get_collector_uptime(self) -> Optional[float]:
        """
        Get pipeline service uptime in seconds.
        
        Returns:
            Uptime in seconds or None
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT started_at FROM service_status
                WHERE service_name = 'pipeline'
                ORDER BY updated_at DESC LIMIT 1
                """
            )
            
            if row and row['started_at']:
                start_time = row['started_at']
                uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
                return max(0.0, uptime)
            
            return None
    
    async def _get_last_tick_time(self) -> Optional[datetime]:
        """
        Get timestamp of last processed candle.
        
        Returns:
            Last candle timestamp or None
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT MAX(time) as last_time
                FROM candles_1s
                """
            )
            
            return row['last_time'] if row else None
    
    async def _get_collector_stats(self) -> dict:
        """
        Get pipeline statistics.
        
        Returns:
            Dict with ticks_processed and errors
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    COALESCE(records_processed, 0) as ticks_processed,
                    COALESCE(errors_last_hour, 0) as errors
                FROM service_status
                WHERE service_name = 'pipeline'
                """
            )
            
            if not row:
                return {'ticks_processed': 0, 'errors': 0}
            
            return {
                'ticks_processed': row['ticks_processed'] or 0,
                'errors': row['errors'] or 0,
            }
    
    async def start_collector(self) -> bool:
        """
        Start pipeline service.
        
        Returns:
            True if started successfully
        """
        try:
            # Update service_status
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO service_status (
                        service_name, is_running, started_at, updated_at
                    ) VALUES ($1, $2, NOW(), NOW())
                    ON CONFLICT (service_name) DO UPDATE SET
                        is_running = true,
                        started_at = NOW(),
                        updated_at = NOW()
                    """,
                    'pipeline',
                    True,
                )
            
            logger.info("Started pipeline service")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start pipeline: {e}")
            return False
    
    async def stop_collector(self) -> bool:
        """
        Stop pipeline service.
        
        Returns:
            True if stopped successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE service_status
                    SET is_running = false, pid = NULL, updated_at = NOW()
                    WHERE service_name = 'pipeline'
                    """
                )
            
            logger.info("Stopped pipeline service")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop pipeline: {e}")
            return False
    
    async def get_sla_metrics(self, seconds: int = 60) -> List[SLAMetric]:
        """
        Get SLA metrics for last N seconds.
        
        Args:
            seconds: Number of seconds to fetch (default: 60)
        
        Returns:
            List of SLA metrics, one per second
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('second', timestamp) as second,
                    AVG(total_time_ms) as avg_time_ms,
                    MAX(total_time_ms) as max_time_ms,
                    COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations,
                    COUNT(*) as ticks_processed
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '{seconds} seconds'
                GROUP BY DATE_TRUNC('second', timestamp)
                ORDER BY second
                """.format(seconds=seconds)
            )
            
            return [
                SLAMetric(
                    timestamp=row['second'],
                    avg_time_ms=float(row['avg_time_ms'] or 0),
                    max_time_ms=float(row['max_time_ms'] or 0),
                    sla_violations=row['sla_violations'] or 0,
                    ticks_processed=row['ticks_processed'] or 0,
                )
                for row in rows
            ]
    
    async def get_dashboard_stats(self) -> DashboardStats:
        """
        Get quick dashboard statistics.
        
        Returns:
            Dashboard statistics
        """
        async with self.db_pool.acquire() as conn:
            # Get ticks per minute
            ticks_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as ticks
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '1 minute'
                """
            )
            ticks_per_minute = ticks_row['ticks'] or 0
            
            # Get average processing time
            time_row = await conn.fetchrow(
                """
                SELECT AVG(total_time_ms) as avg_time
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '1 minute'
                """
            )
            avg_time_ms = float(time_row['avg_time'] or 0)
            
            # Get SLA compliance
            compliance_row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE total_time_ms <= 1000) as compliant
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '1 minute'
                """
            )
            total = compliance_row['total'] or 0
            compliant = compliance_row['compliant'] or 0
            sla_compliance_pct = (compliant / total * 100) if total > 0 else 100.0
            
            # Get active symbols count
            symbols_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM symbols
                WHERE is_active = true AND is_allowed = true
                """
            )
            active_symbols_count = symbols_row['count'] or 0
            
            # Get active indicators count
            indicators_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM indicator_definitions
                WHERE is_active = true
                """
            )
            active_indicators_count = indicators_row['count'] or 0
            
            return DashboardStats(
                ticks_per_minute=ticks_per_minute,
                avg_processing_time_ms=avg_time_ms,
                sla_compliance_pct=sla_compliance_pct,
                active_symbols_count=active_symbols_count,
                active_indicators_count=active_indicators_count,
            )
