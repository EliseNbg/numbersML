"""Unit tests for StrategyLifecycleService."""
from typing import Any
from uuid import uuid4

import pytest

from src.application.services.strategy_lifecycle_service import (
    VALID_TRANSITIONS,
    LifecycleAction,
    StrategyLifecycleService,
)


class _MockTransaction:
    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, *args: object) -> None:
        pass


class _MockConn:
    """Mock connection with proper async methods."""

    def __init__(self) -> None:
        self.fetchval_result: Any = None
        self.execute_result: Any = None
        self.fetch_result: list[Any] = []

    async def fetchval(self, *args: object, **kwargs: object) -> Any:
        return self.fetchval_result

    async def execute(self, *args: object, **kwargs: object) -> Any:
        return self.execute_result

    async def fetch(self, *args: object, **kwargs: object) -> list[Any]:
        return self.fetch_result

    def transaction(self) -> _MockTransaction:
        return _MockTransaction()


class _MockAcquire:
    async def __aenter__(self) -> _MockConn:
        return self._conn

    async def __aexit__(self, *args: object) -> None:
        pass

    def __init__(self, conn: _MockConn) -> None:
        self._conn = conn


class _MockPool:
    """Proper async context manager mock for asyncpg pool."""

    def __init__(self, conn: _MockConn) -> None:
        self._conn = conn

    def acquire(self) -> _MockAcquire:
        return _MockAcquire(self._conn)


class TestValidTransitions:
    """Tests for the valid transition matrix."""

    def test_draft_can_validate(self) -> None:
        assert "validated" in VALID_TRANSITIONS["draft"]

    def test_validated_can_activate(self) -> None:
        assert "active" in VALID_TRANSITIONS["validated"]

    def test_active_can_pause(self) -> None:
        assert "paused" in VALID_TRANSITIONS["active"]

    def test_paused_can_resume(self) -> None:
        assert "active" in VALID_TRANSITIONS["paused"]

    def test_archived_is_terminal(self) -> None:
        assert VALID_TRANSITIONS["archived"] == []

    def test_active_can_archive(self) -> None:
        assert "archived" in VALID_TRANSITIONS["active"]

    def test_paused_can_archive(self) -> None:
        assert "archived" in VALID_TRANSITIONS["paused"]


class TestStrategyLifecycleService:
    """Tests for StrategyLifecycleService."""

    def _make_service(self, conn: _MockConn | None = None) -> StrategyLifecycleService:
        mock_conn = conn or _MockConn()
        pool = _MockPool(mock_conn)
        return StrategyLifecycleService(db_pool=pool)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_resolve_validate_from_draft(self) -> None:
        result = StrategyLifecycleService._resolve_action(
            "draft", LifecycleAction.VALIDATE
        )
        assert result == "validated"

    @pytest.mark.asyncio
    async def test_resolve_activate_from_validated(self) -> None:
        result = StrategyLifecycleService._resolve_action(
            "validated", LifecycleAction.ACTIVATE
        )
        assert result == "active"

    @pytest.mark.asyncio
    async def test_resolve_pause_from_active(self) -> None:
        result = StrategyLifecycleService._resolve_action(
            "active", LifecycleAction.PAUSE
        )
        assert result == "paused"

    @pytest.mark.asyncio
    async def test_resolve_resume_from_paused(self) -> None:
        result = StrategyLifecycleService._resolve_action(
            "paused", LifecycleAction.RESUME
        )
        assert result == "active"

    @pytest.mark.asyncio
    async def test_resolve_deactivate_from_active(self) -> None:
        result = StrategyLifecycleService._resolve_action(
            "active", LifecycleAction.DEACTIVATE
        )
        assert result == "draft"

    @pytest.mark.asyncio
    async def test_resolve_archive_from_active(self) -> None:
        result = StrategyLifecycleService._resolve_action(
            "active", LifecycleAction.ARCHIVE
        )
        assert result == "archived"

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot activate"):
            StrategyLifecycleService._resolve_action(
                "archived", LifecycleAction.ACTIVATE
            )

    @pytest.mark.asyncio
    async def test_transition_invalid_action(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = "draft"
        service = self._make_service(mock_conn)
        with pytest.raises(ValueError, match="Cannot archive"):
            await service.transition(uuid4(), LifecycleAction.ARCHIVE)

    @pytest.mark.asyncio
    async def test_get_strategy_status(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = "active"
        service = self._make_service(mock_conn)
        status = await service.get_strategy_status(uuid4())
        assert status == "active"

    @pytest.mark.asyncio
    async def test_get_strategy_status_not_found(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = None
        service = self._make_service(mock_conn)
        status = await service.get_strategy_status(uuid4())
        assert status is None

    @pytest.mark.asyncio
    async def test_transition_strategy_not_found(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = None
        service = self._make_service(mock_conn)
        with pytest.raises(ValueError, match="not found"):
            await service.transition(uuid4(), LifecycleAction.ACTIVATE)

    @pytest.mark.asyncio
    async def test_get_events(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetch_result = []
        service = self._make_service(mock_conn)
        events = await service.get_events(uuid4())
        assert events == []
