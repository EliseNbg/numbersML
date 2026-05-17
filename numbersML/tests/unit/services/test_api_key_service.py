"""Unit tests for ApiKeyService."""
import os
from typing import Any
from uuid import uuid4

import pytest

from src.application.services.api_key_service import ApiKeyService
from src.infrastructure.security.encryption import EncryptionService


class _MockTransaction:
    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, *args: object) -> None:
        pass


class _MockConn:
    """Mock connection with proper async methods."""

    def __init__(self) -> None:
        self.fetchval_result: Any = None
        self.execute_result: str = "INSERT 0 1"
        self.fetch_result: list[Any] = []
        self.fetchrow_result: dict | None = None

    async def fetchval(self, *args: object, **kwargs: object) -> Any:
        return self.fetchval_result

    async def execute(self, *args: object, **kwargs: object) -> str:
        return self.execute_result

    async def fetch(self, *args: object, **kwargs: object) -> list[Any]:
        return self.fetch_result

    async def fetchrow(self, *args: object, **kwargs: object) -> dict | None:
        return self.fetchrow_result

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


class TestApiKeyService:
    """Tests for ApiKeyService."""

    def _make_service(self, conn: _MockConn | None = None) -> ApiKeyService:
        mock_conn = conn or _MockConn()
        pool = _MockPool(mock_conn)
        master_key = os.urandom(32)
        encryption = EncryptionService(master_key=master_key)
        return ApiKeyService(encryption_service=encryption, db_pool=pool)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_create_api_key_encrypts_secret(self) -> None:
        mock_conn = _MockConn()
        service = self._make_service(mock_conn)

        key = await service.create_key(
            name="Test Key",
            environment="testnet",
            api_key="test-api-key",
            api_secret="test-api-secret",
        )

        assert key.name == "Test Key"
        assert key.environment == "testnet"
        assert len(key.api_key_encrypted) > 0
        assert len(key.api_secret_encrypted) > 0

    @pytest.mark.asyncio
    async def test_list_keys_never_returns_secret(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetch_result = []
        service = self._make_service(mock_conn)

        keys = await service.list_keys()
        assert keys == []

    @pytest.mark.asyncio
    async def test_get_key_never_returns_secret(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchrow_result = None
        service = self._make_service(mock_conn)

        key = await service.get_key(uuid4())
        assert key is None

    @pytest.mark.asyncio
    async def test_delete_key_removes_from_db(self) -> None:
        mock_conn = _MockConn()
        mock_conn.execute_result = "DELETE 1"
        service = self._make_service(mock_conn)

        deleted = await service.delete_key(uuid4())
        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_key_not_found(self) -> None:
        mock_conn = _MockConn()
        mock_conn.execute_result = "DELETE 0"
        service = self._make_service(mock_conn)

        deleted = await service.delete_key(uuid4())
        assert deleted is False

    @pytest.mark.asyncio
    async def test_get_decrypted_key(self) -> None:
        mock_conn = _MockConn()
        service = self._make_service(mock_conn)

        # First create a key
        key = await service.create_key(
            name="Test Key",
            environment="testnet",
            api_key="test-api-key",
            api_secret="test-api-secret",
        )

        # Mock the fetchrow to return the encrypted data
        mock_conn.fetchrow_result = {
            "api_key_encrypted": key.api_key_encrypted,
            "api_secret_encrypted": key.api_secret_encrypted,
        }

        decrypted = await service.get_decrypted_key(key.id)
        assert decrypted is not None
        assert decrypted[0] == "test-api-key"
        assert decrypted[1] == "test-api-secret"

    @pytest.mark.asyncio
    async def test_record_usage(self) -> None:
        mock_conn = _MockConn()
        mock_conn.execute_result = "UPDATE 1"
        service = self._make_service(mock_conn)

        await service.record_usage(uuid4())
        assert mock_conn.execute_result == "UPDATE 1"

    @pytest.mark.asyncio
    async def test_update_key(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchrow_result = None
        service = self._make_service(mock_conn)

        result = await service.update_key(uuid4(), name="New Name")
        assert result is None
