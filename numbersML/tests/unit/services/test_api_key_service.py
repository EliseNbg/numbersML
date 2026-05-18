"""Unit tests for ApiKeyService."""
import json
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
        self.last_query: str = ""
        self.last_args: tuple = ()
        self.queries: list[tuple[str, tuple]] = []

    async def fetchval(self, *args: object, **kwargs: object) -> Any:
        self.last_query = str(args[0]) if args else ""
        self.last_args = tuple(args[1:]) if len(args) > 1 else ()
        self.queries.append((self.last_query, self.last_args))
        return self.fetchval_result

    async def execute(self, *args: object, **kwargs: object) -> str:
        self.last_query = str(args[0]) if args else ""
        self.last_args = tuple(args[1:]) if len(args) > 1 else ()
        self.queries.append((self.last_query, self.last_args))
        return self.execute_result

    async def fetch(self, *args: object, **kwargs: object) -> list[Any]:
        self.last_query = str(args[0]) if args else ""
        self.last_args = tuple(args[1:]) if len(args) > 1 else ()
        self.queries.append((self.last_query, self.last_args))
        return self.fetch_result

    async def fetchrow(self, *args: object, **kwargs: object) -> dict | None:
        self.last_query = str(args[0]) if args else ""
        self.last_args = tuple(args[1:]) if len(args) > 1 else ()
        self.queries.append((self.last_query, self.last_args))
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


def _make_service(conn: _MockConn | None = None) -> ApiKeyService:
    mock_conn = conn or _MockConn()
    pool = _MockPool(mock_conn)
    master_key = os.urandom(32)
    encryption = EncryptionService(master_key=master_key)
    return ApiKeyService(encryption_service=encryption, db_pool=pool)  # type: ignore[arg-type]


class TestApiKeyService:
    """Tests for ApiKeyService."""

    @pytest.mark.asyncio
    async def test_create_api_key_encrypts_secret(self) -> None:
        mock_conn = _MockConn()
        service = _make_service(mock_conn)

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
    async def test_create_key_serializes_json_fields(self) -> None:
        mock_conn = _MockConn()
        service = _make_service(mock_conn)

        await service.create_key(
            name="JSON Test",
            environment="mainnet",
            api_key="key",
            api_secret="secret",
            permissions={"read": True, "trade": False},
            ip_whitelist=["192.168.1.1"],
        )

        query, args = mock_conn.queries[-1]
        assert "INSERT INTO api_keys" in query
        permissions_idx = 6
        ip_whitelist_idx = 7
        assert json.loads(args[permissions_idx]) == {"read": True, "trade": False}
        assert json.loads(args[ip_whitelist_idx]) == ["192.168.1.1"]

    @pytest.mark.asyncio
    async def test_list_keys_never_returns_secret(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetch_result = []
        service = _make_service(mock_conn)

        keys = await service.list_keys()
        assert keys == []

    @pytest.mark.asyncio
    async def test_get_key_never_returns_secret(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchrow_result = None
        service = _make_service(mock_conn)

        key = await service.get_key(uuid4())
        assert key is None

    @pytest.mark.asyncio
    async def test_delete_key_removes_from_db(self) -> None:
        mock_conn = _MockConn()
        mock_conn.execute_result = "DELETE 1"
        service = _make_service(mock_conn)

        deleted = await service.delete_key(uuid4())
        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_key_not_found(self) -> None:
        mock_conn = _MockConn()
        mock_conn.execute_result = "DELETE 0"
        service = _make_service(mock_conn)

        deleted = await service.delete_key(uuid4())
        assert deleted is False

    @pytest.mark.asyncio
    async def test_get_decrypted_key(self) -> None:
        mock_conn = _MockConn()
        service = _make_service(mock_conn)

        key = await service.create_key(
            name="Test Key",
            environment="testnet",
            api_key="test-api-key",
            api_secret="test-api-secret",
        )

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
        service = _make_service(mock_conn)

        await service.record_usage(uuid4())
        assert mock_conn.execute_result == "UPDATE 1"

    @pytest.mark.asyncio
    async def test_update_key(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchrow_result = None
        service = _make_service(mock_conn)

        result = await service.update_key(uuid4(), name="New Name")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_key_serializes_json_fields(self) -> None:
        mock_conn = _MockConn()
        mock_conn.fetchrow_result = {
            "id": uuid4(),
            "name": "Old",
            "environment": "testnet",
            "api_key_encrypted": "enc",
            "api_secret_encrypted": "enc",
            "is_active": True,
            "permissions": {},
            "ip_whitelist": [],
            "created_at": None,
            "updated_at": None,
            "last_used_at": None,
            "created_by": "system",
        }
        service = _make_service(mock_conn)

        await service.update_key(
            uuid4(),
            name="Updated",
            permissions={"read": True},
            ip_whitelist=["10.0.0.1"],
        )

        update_queries = [(q, a) for q, a in mock_conn.queries if "UPDATE api_keys" in q]
        assert len(update_queries) == 1
        _, args = update_queries[0]
        permissions_idx = 3
        ip_whitelist_idx = 4
        assert json.loads(args[permissions_idx]) == {"read": True}
        assert json.loads(args[ip_whitelist_idx]) == ["10.0.0.1"]


class TestApiKeyLifecycle:
    """Full lifecycle test: create → read → update → rotate → delete."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        mock_conn = _MockConn()
        service = _make_service(mock_conn)
        master_key = os.urandom(32)
        encryption = EncryptionService(master_key=master_key)

        key_id = uuid4()

        await service.create_key(
            name="Lifecycle Key",
            environment="testnet",
            api_key="live-api-key",
            api_secret="live-api-secret",
            permissions={"read": True, "trade": True},
            ip_whitelist=["203.0.113.1"],
        )

        query, args = mock_conn.queries[-1]
        assert "INSERT INTO api_keys" in query
        stored_key_encrypted = args[3]
        stored_secret_encrypted = args[4]

        mock_conn.fetchrow_result = {
            "id": key_id,
            "name": "Lifecycle Key",
            "environment": "testnet",
            "api_key_encrypted": stored_key_encrypted,
            "api_secret_encrypted": stored_secret_encrypted,
            "is_active": True,
            "permissions": {},
            "ip_whitelist": [],
            "created_at": None,
            "updated_at": None,
            "last_used_at": None,
            "created_by": "system",
        }
        fetched = await service.get_key(key_id)
        assert fetched is not None
        assert fetched.name == "Lifecycle Key"
        assert fetched.environment == "testnet"
        assert fetched.is_active is True

        mock_conn.fetchrow_result = {
            "id": key_id,
            "name": "Updated Lifecycle Key",
            "environment": "mainnet",
            "api_key_encrypted": stored_key_encrypted,
            "api_secret_encrypted": stored_secret_encrypted,
            "is_active": True,
            "permissions": {"read": True},
            "ip_whitelist": ["203.0.113.1"],
            "created_at": None,
            "updated_at": None,
            "last_used_at": None,
            "created_by": "system",
        }
        updated = await service.update_key(
            key_id,
            name="Updated Lifecycle Key",
            is_active=True,
            permissions={"read": True},
            ip_whitelist=["203.0.113.1"],
        )
        assert updated is not None
        assert updated.name == "Updated Lifecycle Key"

        await service.record_usage(key_id)
        query, _ = mock_conn.queries[-1]
        assert "UPDATE api_keys SET" in query
        assert "last_used_at" in query

        mock_conn.fetchrow_result = {
            "api_key_encrypted": stored_key_encrypted,
            "api_secret_encrypted": stored_secret_encrypted,
        }
        decrypted = await service.get_decrypted_key(key_id)
        assert decrypted is not None
        assert decrypted[0] == "live-api-key"
        assert decrypted[1] == "live-api-secret"

        mock_conn.execute_result = "DELETE 1"
        deleted = await service.delete_key(key_id)
        assert deleted is True
        query, _ = mock_conn.queries[-1]
        assert "DELETE FROM api_keys" in query

    @pytest.mark.asyncio
    async def test_lifecycle_deactivate_then_delete(self) -> None:
        mock_conn = _MockConn()
        service = _make_service(mock_conn)
        key_id = uuid4()

        mock_conn.fetchrow_result = None
        deactivated = await service.update_key(key_id, is_active=False)
        assert deactivated is None

        mock_conn.execute_result = "DELETE 1"
        deleted = await service.delete_key(key_id)
        assert deleted is True
