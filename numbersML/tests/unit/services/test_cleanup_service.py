"""Unit tests for CleanupService."""
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.services.cleanup_service import CleanupResult, CleanupService


class _MockTransaction:
    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, *args: object) -> None:
        pass


class _MockConn:
    """Mock connection with proper async methods."""

    def __init__(self) -> None:
        self.fetchval_result: Any = None
        self.execute_result: str = "DELETE 0"
        self.fetch_result: list[Any] = []

    async def fetchval(self, *args: object, **kwargs: object) -> Any:
        return self.fetchval_result

    async def execute(self, *args: object, **kwargs: object) -> str:
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


class TestCleanupResult:
    """Tests for CleanupResult dataclass."""

    def test_default_values(self) -> None:
        result = CleanupResult()
        assert result.signals_deleted == 0
        assert result.backtests_deleted == 0
        assert result.errors == []

    def test_to_dict(self) -> None:
        sid = uuid4()
        result = CleanupResult(
            strategy_id=sid,
            signals_deleted=5,
            backtests_deleted=2,
            errors=["test error"],
        )
        d = result.to_dict()
        assert d["strategy_id"] == str(sid)
        assert d["signals_deleted"] == 5
        assert d["errors"] == ["test error"]


class TestCleanupService:
    """Tests for CleanupService."""

    def _make_service(self, conn: _MockConn | None = None) -> CleanupService:
        mock_conn = conn or _MockConn()
        pool = _MockPool(mock_conn)
        return CleanupService(db_pool=pool)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_cleanup_strategy_deletes_signals(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = 5
        service = self._make_service(mock_conn)
        result = await service.cleanup_strategy(uuid4(), delete_signals=True)
        assert result.signals_deleted == 5

    @pytest.mark.asyncio
    async def test_cleanup_strategy_deletes_backtests(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = 3
        service = self._make_service(mock_conn)
        result = await service.cleanup_strategy(uuid4(), delete_backtests=True)
        assert result.backtests_deleted == 3

    @pytest.mark.asyncio
    async def test_cleanup_strategy_deletes_events(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = 10
        service = self._make_service(mock_conn)
        result = await service.cleanup_strategy(uuid4(), delete_events=True)
        assert result.events_deleted == 10

    @pytest.mark.asyncio
    async def test_cleanup_strategy_skips_versions_by_default(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = 0
        service = self._make_service(mock_conn)
        result = await service.cleanup_strategy(uuid4())
        assert result.versions_deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_strategy_deletes_versions_when_requested(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = 2
        service = self._make_service(mock_conn)
        result = await service.cleanup_strategy(uuid4(), delete_versions=True)
        assert result.versions_deleted == 2

    @pytest.mark.asyncio
    async def test_cleanup_all_stopped(self) -> None:
        mock_conn = _MockConn()
        sid = uuid4()
        mock_conn.fetch_result = [{"id": sid}]
        mock_conn.fetchval_result = 5
        mock_conn.execute_result = "DELETE 5"
        service = self._make_service(mock_conn)
        results = await service.cleanup_all_stopped(older_than_hours=24)
        assert sid in results
        assert results[sid].signals_deleted == 5

    @pytest.mark.asyncio
    async def test_cleanup_old_signals(self) -> None:
        mock_conn = _MockConn()
        mock_conn.execute_result = "DELETE 15"
        service = self._make_service(mock_conn)
        deleted = await service.cleanup_old_signals(older_than_days=30)
        assert deleted == 15

    @pytest.mark.asyncio
    async def test_cleanup_old_backtests(self) -> None:
        mock_conn = _MockConn()
        mock_conn.execute_result = "DELETE 8"
        service = self._make_service(mock_conn)
        deleted = await service.cleanup_old_backtests(older_than_days=90)
        assert deleted == 8

    @pytest.mark.asyncio
    async def test_get_cleanup_stats(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval_result = 3
        service = self._make_service(mock_conn)
        stats = await service.get_cleanup_stats()
        assert stats["archived_strategies"] == 3
        assert stats["draft_strategies"] == 3
        assert stats["old_signals_30d"] == 3
        assert stats["old_backtests_90d"] == 3

    @pytest.mark.asyncio
    async def test_cleanup_error_handling(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchval = AsyncMock(side_effect=Exception("DB error"))
        service = self._make_service(mock_conn)
        result = await service.cleanup_strategy(uuid4())
        assert len(result.errors) == 1
        assert "DB error" in result.errors[0]
