"""Strategy lifecycle service for managing strategy state transitions.

Provides CRUD operations and strict state transition rules:
  draft → validated → active → paused → active
                            ↓
                         archived
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class LifecycleAction(str, Enum):  # noqa: UP042
    """Allowed lifecycle actions."""

    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    PAUSE = "pause"
    RESUME = "resume"
    ARCHIVE = "archive"
    VALIDATE = "validate"


# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["validated", "active"],
    "validated": ["active", "draft"],
    "active": ["paused", "archived", "draft"],
    "paused": ["active", "archived"],
    "archived": [],
}


@dataclass
class LifecycleEvent:
    """Record of a lifecycle state change."""

    event_id: UUID
    strategy_id: UUID
    action: LifecycleAction
    old_status: str
    new_status: str
    actor: str
    timestamp: datetime
    metadata: dict[str, Any]


class StrategyLifecycleService:
    """Manages strategy lifecycle state transitions.

    Attributes:
        db_pool: Database connection pool
    """

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """Initialize lifecycle service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def get_strategy_status(self, strategy_id: UUID) -> str | None:
        """Get current status of a strategy.

        Args:
            strategy_id: Strategy UUID

        Returns:
            Current status string or None if not found
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT status FROM strategies WHERE id = $1",
                strategy_id,
            )
        return row

    async def transition(
        self,
        strategy_id: UUID,
        action: LifecycleAction,
        actor: str = "system",
    ) -> LifecycleEvent:
        """Execute a lifecycle state transition.

        Args:
            strategy_id: Strategy UUID
            action: Lifecycle action to perform
            actor: Who initiated the action

        Returns:
            LifecycleEvent describing the transition

        Raises:
            ValueError: If strategy not found or transition invalid
        """
        current_status = await self.get_strategy_status(strategy_id)
        if current_status is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        new_status = self._resolve_action(current_status, action)

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE strategies
                    SET status = $1, updated_at = NOW()
                    WHERE id = $2
                    """,
                    new_status,
                    strategy_id,
                )

                event_id = await conn.fetchval(
                    """
                    INSERT INTO strategy_events (
                        strategy_id, event_type, event_payload, actor
                    ) VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    strategy_id,
                    action.value,
                    {
                        "old_status": current_status,
                        "new_status": new_status,
                    },
                    actor,
                )

        event = LifecycleEvent(
            event_id=event_id,
            strategy_id=strategy_id,
            action=action,
            old_status=current_status,
            new_status=new_status,
            actor=actor,
            timestamp=datetime.now(UTC),
            metadata={"old_status": current_status, "new_status": new_status},
        )

        logger.info(
            f"Strategy {strategy_id}: {action.value} "
            f"({current_status} → {new_status})"
        )
        return event

    @staticmethod
    def _resolve_action(current_status: str, action: LifecycleAction) -> str:
        """Resolve action to new status.

        Args:
            current_status: Current strategy status
            action: Requested action

        Returns:
            New status string

        Raises:
            ValueError: If transition is not allowed
        """
        allowed = VALID_TRANSITIONS.get(current_status, [])

        action_to_status = {
            LifecycleAction.VALIDATE: "validated",
            LifecycleAction.ACTIVATE: "active",
            LifecycleAction.PAUSE: "paused",
            LifecycleAction.RESUME: "active",
            LifecycleAction.DEACTIVATE: "draft",
            LifecycleAction.ARCHIVE: "archived",
        }

        target = action_to_status.get(action)
        if target is None:
            raise ValueError(f"Unknown action: {action}")

        if target not in allowed:
            raise ValueError(
                f"Cannot {action.value} from '{current_status}'. "
                f"Allowed transitions: {allowed}"
            )

        return target

    async def get_events(
        self,
        strategy_id: UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get lifecycle events for a strategy.

        Args:
            strategy_id: Strategy UUID
            limit: Maximum events to return

        Returns:
            List of event dictionaries
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, event_type, event_payload, actor, created_at
                FROM strategy_events
                WHERE strategy_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                strategy_id,
                limit,
            )
        return [
            {
                "event_id": row["id"],
                "event_type": row["event_type"],
                "payload": row["event_payload"],
                "actor": row["actor"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
