"""
Pipeline metrics data access repository.

This repository provides data access for pipeline_metrics table.

Architecture: Infrastructure Layer (data access)
Dependencies: Domain layer + asyncpg
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import asyncpg

from src.domain.models.dashboard import SLAMetric

logger = logging.getLogger(__name__)


class PipelineMetricsRepository:
    """
    Repository for pipeline_metrics table.
    
    Responsibilities:
        - Fetch SLA metrics from database
        - Get collector status information
        - Query pipeline performance data
    
    Example:
        >>> repo = PipelineMetricsRepository(db_pool)
        >>> metrics = await repo.get_sla_metrics(seconds=60)
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.
        
        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
    
    async def get_sla_metrics(
        self,
        seconds: int = 60,
    ) -> List[SLAMetric]:
        """
        Get SLA metrics for last N seconds.
        
        Groups metrics by second and calculates:
            - Average processing time
            - Maximum processing time
            - SLA violations (>1000ms)
            - Total ticks processed
        
        Args:
            seconds: Number of seconds to fetch (default: 60)
        
        Returns:
            List of SLA metrics, one per second
        
        SQL:
            SELECT 
                DATE_TRUNC('second', timestamp) as second,
                AVG(total_time_ms) as avg_time_ms,
                MAX(total_time_ms) as max_time_ms,
                COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations,
                COUNT(*) as ticks_processed
            FROM pipeline_metrics
            WHERE timestamp > NOW() - INTERVAL 'N seconds'
            GROUP BY DATE_TRUNC('second', timestamp)
            ORDER BY second
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
    
    async def get_collector_pid(self) -> Optional[int]:
        """
        Get collector process PID from service_status table.
        
        Returns:
            Process ID or None if not running
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT pid FROM service_status
                WHERE service_name = 'ticker_collector'
                ORDER BY updated_at DESC LIMIT 1
                """
            )
            
            return row['pid'] if row else None
    
    async def get_last_tick_time(self) -> Optional[datetime]:
        """
        Get last tick timestamp from ticker_24hr_stats table.
        
        Returns:
            Last tick timestamp or None if no ticks
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT MAX(time) as last_time
                FROM ticker_24hr_stats
                """
            )
            
            return row['last_time'] if row else None
    
    async def get_ticks_per_minute(self) -> int:
        """
        Get ticks processed in last minute.
        
        Returns:
            Number of ticks in last minute
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) as ticks
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '1 minute'
                """
            )
            
            return row['ticks'] or 0
    
    async def get_average_processing_time(self, seconds: int = 60) -> float:
        """
        Get average processing time for last N seconds.
        
        Args:
            seconds: Number of seconds to average
        
        Returns:
            Average processing time in milliseconds
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT AVG(total_time_ms) as avg_time
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '{seconds} seconds'
                """.format(seconds=seconds)
            )
            
            return float(row['avg_time'] or 0)
    
    async def get_sla_compliance(self, seconds: int = 60) -> float:
        """
        Get SLA compliance percentage for last N seconds.
        
        Args:
            seconds: Number of seconds to calculate
        
        Returns:
            Compliance percentage (0-100)
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE total_time_ms <= 1000) as compliant
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '{seconds} seconds'
                """.format(seconds=seconds)
            )
            
            total = row['total'] or 0
            compliant = row['compliant'] or 0
            
            if total == 0:
                return 100.0
            
            return (compliant / total) * 100.0
    
    async def get_recent_errors(self, limit: int = 10) -> List[dict]:
        """
        Get recent pipeline errors.
        
        Args:
            limit: Maximum errors to return
        
        Returns:
            List of error records
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    timestamp,
                    symbol_id,
                    total_time_ms,
                    error_message
                FROM pipeline_metrics
                WHERE error_message IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT $1
                """,
                limit,
            )
            
            return [dict(row) for row in rows]
    
    async def get_metrics_summary(
        self,
        seconds: int = 60,
    ) -> dict:
        """
        Get comprehensive metrics summary.
        
        Args:
            seconds: Time window for summary
        
        Returns:
            Dictionary with summary statistics
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total_ticks,
                    AVG(total_time_ms) as avg_time_ms,
                    MIN(total_time_ms) as min_time_ms,
                    MAX(total_time_ms) as max_time_ms,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (
                        ORDER BY total_time_ms
                    ) as p95_time_ms,
                    PERCENTILE_CONT(0.99) WITHIN GROUP (
                        ORDER BY total_time_ms
                    ) as p99_time_ms,
                    COUNT(*) FILTER (WHERE total_time_ms > 1000) as sla_violations
                FROM pipeline_metrics
                WHERE timestamp > NOW() - INTERVAL '{seconds} seconds'
                """.format(seconds=seconds)
            )
            
            if not row:
                return {}
            
            return {
                'total_ticks': row['total_ticks'] or 0,
                'avg_time_ms': float(row['avg_time_ms'] or 0),
                'min_time_ms': float(row['min_time_ms'] or 0),
                'max_time_ms': float(row['max_time_ms'] or 0),
                'p95_time_ms': float(row['p95_time_ms'] or 0),
                'p99_time_ms': float(row['p99_time_ms'] or 0),
                'sla_violations': row['sla_violations'] or 0,
            }
