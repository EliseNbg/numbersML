"""Cleanup service for strategy artifacts.

Removes stale data from database and disk for archived/deleted strategies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """Result of a cleanup operation.

    Attributes:
        strategy_id: Strategy that was cleaned up
        signals_deleted: Number of signal records deleted
        backtests_deleted: Number of backtest records deleted
        events_deleted: Number of event records deleted
        versions_deleted: Number of version records deleted
        disk_artifacts_deleted: Number of disk artifacts deleted
        errors: List of error messages
    """

    strategy_id: UUID | None = None
    signals_deleted: int = 0
    backtests_deleted: int = 0
    events_deleted: int = 0
    versions_deleted: int = 0
    disk_artifacts_deleted: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "strategy_id": str(self.strategy_id) if self.strategy_id else None,
            "signals_deleted": self.signals_deleted,
            "backtests_deleted": self.backtests_deleted,
            "events_deleted": self.events_deleted,
            "versions_deleted": self.versions_deleted,
            "disk_artifacts_deleted": self.disk_artifacts_deleted,
            "errors": self.errors,
        }


class CleanupService:
    """Clean up strategy artifacts from DB and disk.

    Attributes:
        db_pool: Database connection pool
    """

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize cleanup service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def cleanup_strategy(
        self,
        strategy_id: UUID,
        delete_signals: bool = True,
        delete_backtests: bool = True,
        delete_events: bool = True,
        delete_versions: bool = False,
    ) -> CleanupResult:
        """Remove all artifacts for a strategy.

        Args:
            strategy_id: Strategy to clean up
            delete_signals: Delete signal records
            delete_backtests: Delete backtest records
            delete_events: Delete event records
            delete_versions: Delete version records (default False, preserves history)

        Returns:
            CleanupResult with deletion counts
        """
        result = CleanupResult(strategy_id=strategy_id)

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                try:
                    if delete_signals:
                        row = await conn.fetchval(
                            "DELETE FROM strategy_signals WHERE strategy_id = $1 RETURNING COUNT(*)",
                            strategy_id,
                        )
                        result.signals_deleted = row or 0

                    if delete_backtests:
                        row = await conn.fetchval(
                            "DELETE FROM strategy_backtests WHERE strategy_id = $1 RETURNING COUNT(*)",
                            strategy_id,
                        )
                        result.backtests_deleted = row or 0

                    if delete_events:
                        row = await conn.fetchval(
                            "DELETE FROM strategy_events WHERE strategy_id = $1 RETURNING COUNT(*)",
                            strategy_id,
                        )
                        result.events_deleted = row or 0

                    if delete_versions:
                        row = await conn.fetchval(
                            "DELETE FROM strategy_versions WHERE strategy_id = $1 RETURNING COUNT(*)",
                            strategy_id,
                        )
                        result.versions_deleted = row or 0

                except Exception as e:
                    result.errors.append(f"DB cleanup error: {e}")
                    logger.error(f"Cleanup failed for strategy {strategy_id}: {e}")

        return result

    async def cleanup_all_stopped(
        self,
        older_than_hours: int = 24,
        delete_signals: bool = True,
        delete_backtests: bool = True,
        delete_events: bool = True,
    ) -> dict[UUID, CleanupResult]:
        """Clean up all stopped/archived strategies older than N hours.

        Args:
            older_than_hours: Only clean strategies updated before this threshold
            delete_signals: Delete signal records
            delete_backtests: Delete backtest records
            delete_events: Delete event records

        Returns:
            Dict of strategy_id -> CleanupResult
        """
        cutoff = datetime.now(UTC).timestamp() - (older_than_hours * 3600)

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id FROM strategies
                WHERE status IN ('archived', 'draft')
                AND updated_at < TO_TIMESTAMP($1)
            """, cutoff)

        results: dict[UUID, CleanupResult] = {}
        for row in rows:
            strategy_id = row["id"]
            result = await self.cleanup_strategy(
                strategy_id=strategy_id,
                delete_signals=delete_signals,
                delete_backtests=delete_backtests,
                delete_events=delete_events,
                delete_versions=False,
            )
            results[strategy_id] = result
            logger.info(
                f"Cleaned up strategy {strategy_id}: "
                f"signals={result.signals_deleted}, "
                f"backtests={result.backtests_deleted}"
            )

        return results

    async def cleanup_old_signals(
        self,
        older_than_days: int = 30,
        statuses: list[str] | None = None,
    ) -> int:
        """Clean up old signals by age and status.

        Args:
            older_than_days: Delete signals older than this
            statuses: Only delete signals with these statuses (default: REJECTED, FAILED)

        Returns:
            Number of signals deleted
        """
        if statuses is None:
            statuses = ["REJECTED", "FAILED"]

        cutoff = datetime.now(UTC).timestamp() - (older_than_days * 86400)

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM strategy_signals
                WHERE status = ANY($1)
                AND created_at < TO_TIMESTAMP($2)
                """,
                statuses,
                cutoff,
            )

        deleted = int(result.split()[-1]) if result else 0
        logger.info(f"Deleted {deleted} old signals (older than {older_than_days} days)")
        return deleted

    async def cleanup_old_backtests(
        self,
        older_than_days: int = 90,
    ) -> int:
        """Clean up old backtest records.

        Args:
            older_than_days: Delete backtests older than this

        Returns:
            Number of backtests deleted
        """
        cutoff = datetime.now(UTC).timestamp() - (older_than_days * 86400)

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM strategy_backtests WHERE created_at < TO_TIMESTAMP($1)",
                cutoff,
            )

        deleted = int(result.split()[-1]) if result else 0
        logger.info(f"Deleted {deleted} old backtests (older than {older_than_days} days)")
        return deleted

    async def get_cleanup_stats(self) -> dict[str, Any]:
        """Get statistics about cleanup candidates.

        Returns:
            Dictionary with counts of cleanup candidates
        """
        async with self.db_pool.acquire() as conn:
            archived_count = await conn.fetchval(
                "SELECT COUNT(*) FROM strategies WHERE status = 'archived'"
            )
            draft_count = await conn.fetchval(
                "SELECT COUNT(*) FROM strategies WHERE status = 'draft'"
            )
            old_signals = await conn.fetchval(
                """
                SELECT COUNT(*) FROM strategy_signals
                WHERE status IN ('REJECTED', 'FAILED')
                AND created_at < NOW() - INTERVAL '30 days'
                """
            )
            old_backtests = await conn.fetchval(
                """
                SELECT COUNT(*) FROM strategy_backtests
                WHERE created_at < NOW() - INTERVAL '90 days'
                """
            )

        return {
            "archived_strategies": archived_count,
            "draft_strategies": draft_count,
            "old_signals_30d": old_signals,
            "old_backtests_90d": old_backtests,
        }
