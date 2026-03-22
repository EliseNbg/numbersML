"""
Wait for enrichment to complete before generating wide vector.

This module provides synchronization between the EnrichmentService
and WIDE_Vector generator to ensure all indicators are calculated
before generating the vector.

Usage:
    waiter = EnrichmentWaiter(db_pool, dsn, timeout=10.0)
    enriched = await waiter.wait_for_enrichment(symbol_ids=[1, 2, 3])
    if enriched:
        vector = await generate_wide_vector()
"""

import asyncio
import asyncpg
import json
import logging
from typing import Set, Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EnrichmentWaiter:
    """
    Wait for enrichment to complete for specific symbols.

    Uses asyncpg's add_listener() API (asyncpg >= 0.30.0).

    Attributes:
        db_pool: PostgreSQL connection pool
        dsn: Database connection string for dedicated LISTEN connection
        timeout: Max seconds to wait for enrichment (default: 10.0)

    Example:
        >>> waiter = EnrichmentWaiter(db_pool, dsn, timeout=10.0)
        >>> enriched = await waiter.wait_for_enrichment(symbol_ids=[1, 2, 3])
        >>> if enriched:
        ...     print("All symbols enriched, generating vector...")
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        dsn: str,
        timeout: float = 10.0
    ) -> None:
        """
        Initialize waiter.

        Args:
            db_pool: PostgreSQL connection pool
            dsn: Database connection string for dedicated LISTEN connection
            timeout: Max seconds to wait for enrichment (default: 10.0)
        """
        self.db_pool = db_pool
        self.dsn = dsn
        self.timeout = timeout
        self._notifications: asyncio.Queue = asyncio.Queue()

    async def wait_for_enrichment(
        self,
        symbol_ids: List[int],
        timeout: Optional[float] = None
    ) -> bool:
        """
        Wait for enrichment to complete for all specified symbols.

        This method:
        1. Gets the latest tick time for each symbol
        2. Listens for enrichment_complete notifications
        3. Returns when all symbols are enriched or timeout occurs

        Args:
            symbol_ids: List of symbol IDs to wait for
            timeout: Override default timeout (seconds)

        Returns:
            True if all symbols enriched, False if timeout
        """
        timeout = timeout or self.timeout
        start_time = datetime.now(timezone.utc)

        # Get latest tick times first (using pool)
        async with self.db_pool.acquire() as conn:
            expected = await self._get_latest_ticks(conn, symbol_ids)

        if not expected:
            logger.warning("No ticks found to wait for")
            return True

        logger.info(
            f"Waiting for enrichment for {len(expected)} symbols "
            f"(timeout: {timeout}s)"
        )

        # Create a dedicated connection for LISTEN
        listen_conn: Optional[asyncpg.Connection] = None
        try:
            listen_conn = await asyncpg.connect(self.dsn)

            # Use an event to signal when we receive a notification
            notification_event = asyncio.Event()
            received_keys: Set[tuple] = set()

            def notification_handler(
                connection: asyncpg.Connection,
                pid: int,
                channel: str,
                payload: str
            ) -> None:
                """Handle incoming notifications."""
                try:
                    payload_dict = json.loads(payload)
                    key = (payload_dict['symbol_id'], payload_dict['time'])
                    received_keys.add(key)
                    notification_event.set()
                except Exception as e:
                    logger.error(f"Error parsing notification: {e}")

            # Add listener
            await listen_conn.add_listener('enrichment_complete', notification_handler)
            logger.debug("Listening for enrichment_complete notifications")

            # Wait for notifications
            while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout:
                try:
                    # Wait for notification with timeout
                    await asyncio.wait_for(notification_event.wait(), timeout=1.0)
                    notification_event.clear()

                    # Check if any expected keys were received
                    for key in list(expected):
                        if key in received_keys:
                            expected.discard(key)
                            logger.debug(f"✓ Enriched: symbol_id={key[0]}")

                    if not expected:
                        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                        logger.info(f"All symbols enriched in {elapsed:.2f}s")
                        return True

                except asyncio.TimeoutError:
                    continue

            # Timeout - some symbols not enriched
            pending_count = len(expected)
            logger.warning(
                f"Timeout waiting for enrichment: {pending_count} symbols pending"
            )
            return False

        except Exception as e:
            logger.error(f"Error in wait_for_enrichment: {e}")
            return False

        finally:
            if listen_conn:
                await listen_conn.close()

    async def wait_for_single_enrichment(
        self,
        symbol_id: int,
        timeout: Optional[float] = None
    ) -> bool:
        """
        Wait for enrichment for a single symbol.

        Args:
            symbol_id: Symbol ID to wait for
            timeout: Override default timeout (seconds)

        Returns:
            True if enriched, False if timeout
        """
        return await self.wait_for_enrichment([symbol_id], timeout)

    async def _get_latest_ticks(
        self,
        conn: asyncpg.Connection,
        symbol_ids: List[int]
    ) -> Set[tuple]:
        """
        Get latest tick time for each symbol.

        Args:
            conn: Database connection
            symbol_ids: List of symbol IDs

        Returns:
            Set of (symbol_id, time) tuples
        """
        if not symbol_ids:
            return set()

        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (symbol_id)
                symbol_id, time
            FROM ticker_24hr_stats
            WHERE symbol_id = ANY($1)
            ORDER BY symbol_id, time DESC
            """,
            symbol_ids
        )

        return {(row['symbol_id'], str(row['time'])) for row in rows}

    async def get_enrichment_status(
        self,
        symbol_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get current enrichment status.

        Args:
            symbol_ids: Optional list of symbol IDs to check

        Returns:
            Dictionary with enrichment status information
        """
        async with self.db_pool.acquire() as conn:
            if symbol_ids:
                placeholders = ','.join(f'${i}' for i in range(1, len(symbol_ids) + 1))
                tick_query = f"""
                    SELECT COUNT(*) as total_ticks
                    FROM ticker_24hr_stats
                    WHERE symbol_id IN ({placeholders})
                """
                rows = await conn.fetch(tick_query, *symbol_ids)
                total_ticks = rows[0]['total_ticks'] if rows else 0

                indicator_query = f"""
                    SELECT COUNT(*) as enriched_ticks
                    FROM tick_indicators
                    WHERE symbol_id IN ({placeholders})
                """
                rows = await conn.fetch(indicator_query, *symbol_ids)
                enriched_ticks = rows[0]['enriched_ticks'] if rows else 0
            else:
                total_ticks = await conn.fetchval("SELECT COUNT(*) FROM ticker_24hr_stats")
                enriched_ticks = await conn.fetchval("SELECT COUNT(*) FROM tick_indicators")

            enrichment_rate = (enriched_ticks / total_ticks * 100) if total_ticks > 0 else 0

            return {
                'total_ticks': total_ticks,
                'enriched_ticks': enriched_ticks,
                'enrichment_rate_pct': round(enrichment_rate, 2),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }


async def wait_for_enrichment(
    db_pool: asyncpg.Pool,
    dsn: str,
    symbol_ids: List[int],
    timeout: float = 10.0
) -> bool:
    """
    Convenience function to wait for enrichment.

    Args:
        db_pool: PostgreSQL connection pool
        dsn: Database connection string for LISTEN connection
        symbol_ids: List of symbol IDs to wait for
        timeout: Max seconds to wait

    Returns:
        True if all enriched, False if timeout

    Example:
        >>> from src.application.services.enrichment_waiter import wait_for_enrichment
        >>> enriched = await wait_for_enrichment(db_pool, dsn, [1, 2, 3], timeout=5.0)
    """
    waiter = EnrichmentWaiter(db_pool, dsn, timeout=timeout)
    return await waiter.wait_for_enrichment(symbol_ids)
