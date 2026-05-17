"""API key management service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.domain.market.api_key import ApiKey
from src.infrastructure.security.encryption import EncryptionService

logger = logging.getLogger(__name__)


class ApiKeyService:
    """Application service for API key CRUD operations.

    Handles encryption/decryption of API secrets and database persistence.

    Args:
        encryption_service: Encryption service for secrets.
        db_pool: asyncpg connection pool.

    Example:
        >>> service = ApiKeyService(encryption, db_pool)
        >>> key = await service.create_key("Testnet Key", "testnet", "key", "secret")
    """

    def __init__(
        self,
        encryption_service: EncryptionService,
        db_pool: Any,
    ) -> None:
        self._encryption = encryption_service
        self._db_pool = db_pool

    async def create_key(
        self,
        name: str,
        environment: str,
        api_key: str,
        api_secret: str,
        permissions: dict[str, bool] | None = None,
        ip_whitelist: list[str] | None = None,
        created_by: str = "system",
    ) -> ApiKey:
        """Create a new API key with encrypted secrets.

        Args:
            name: Human-readable name.
            environment: 'mainnet' or 'testnet'.
            api_key: Plain API key.
            api_secret: Plain API secret.
            permissions: Optional permissions dict.
            ip_whitelist: Optional IP whitelist.
            created_by: User who created the key.

        Returns:
            Created ApiKey domain model.
        """
        encrypted_key = self._encryption.encrypt(api_key)
        encrypted_secret = self._encryption.encrypt(api_secret)
        now = datetime.now(UTC)

        key = ApiKey(
            name=name,
            environment=environment,
            api_key_encrypted=encrypted_key,
            api_secret_encrypted=encrypted_secret,
            permissions=permissions or {},
            ip_whitelist=ip_whitelist or [],
            created_at=now,
            updated_at=now,
            created_by=created_by,
        )

        async with self._db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (
                    id, name, environment, api_key_encrypted, api_secret_encrypted,
                    is_active, permissions, ip_whitelist, created_at, updated_at, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                key.id,
                key.name,
                key.environment,
                encrypted_key,
                encrypted_secret,
                key.is_active,
                key.permissions,
                key.ip_whitelist,
                key.created_at,
                key.updated_at,
                key.created_by,
            )

        logger.info(f"Created API key: {name} ({environment})")
        return key

    async def get_key(self, key_id: UUID) -> ApiKey | None:
        """Get API key by ID (without decrypting secrets).

        Args:
            key_id: Key UUID.

        Returns:
            ApiKey or None if not found.
        """
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM api_keys WHERE id = $1",
                key_id,
            )

        if row is None:
            return None

        return self._row_to_key(row)

    async def list_keys(self, environment: str | None = None) -> list[ApiKey]:
        """List all API keys (without decrypting secrets).

        Args:
            environment: Optional filter by environment.

        Returns:
            List of ApiKey models.
        """
        async with self._db_pool.acquire() as conn:
            if environment:
                rows = await conn.fetch(
                    "SELECT * FROM api_keys WHERE environment = $1 ORDER BY created_at DESC",
                    environment,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM api_keys ORDER BY created_at DESC"
                )

        return [self._row_to_key(row) for row in rows]

    async def update_key(
        self,
        key_id: UUID,
        name: str | None = None,
        is_active: bool | None = None,
        permissions: dict[str, bool] | None = None,
        ip_whitelist: list[str] | None = None,
    ) -> ApiKey | None:
        """Update API key metadata.

        Args:
            key_id: Key UUID.
            name: New name.
            is_active: New active status.
            permissions: New permissions.
            ip_whitelist: New IP whitelist.

        Returns:
            Updated ApiKey or None if not found.
        """
        existing = await self.get_key(key_id)
        if existing is None:
            return None

        now = datetime.now(UTC)
        updates: dict[str, Any] = {"updated_at": now}

        if name is not None:
            updates["name"] = name
        if is_active is not None:
            updates["is_active"] = is_active
        if permissions is not None:
            updates["permissions"] = permissions
        if ip_whitelist is not None:
            updates["ip_whitelist"] = ip_whitelist

        async with self._db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE api_keys SET
                    name = COALESCE($2, name),
                    is_active = COALESCE($3, is_active),
                    permissions = COALESCE($4, permissions),
                    ip_whitelist = COALESCE($5, ip_whitelist),
                    updated_at = $6
                WHERE id = $1
                """,
                key_id,
                updates.get("name"),
                updates.get("is_active"),
                updates.get("permissions"),
                updates.get("ip_whitelist"),
                now,
            )

        logger.info(f"Updated API key: {key_id}")
        return await self.get_key(key_id)

    async def delete_key(self, key_id: UUID) -> bool:
        """Delete an API key.

        Args:
            key_id: Key UUID.

        Returns:
            True if deleted, False if not found.
        """
        async with self._db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM api_keys WHERE id = $1",
                key_id,
            )

        deleted = result == "DELETE 1"
        if deleted:
            logger.info(f"Deleted API key: {key_id}")
        return deleted

    async def get_decrypted_key(self, key_id: UUID) -> tuple[str, str] | None:
        """Get decrypted API key and secret.

        Args:
            key_id: Key UUID.

        Returns:
            Tuple of (api_key, api_secret) or None.
        """
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT api_key_encrypted, api_secret_encrypted FROM api_keys WHERE id = $1",
                key_id,
            )

        if row is None:
            return None

        api_key = self._encryption.decrypt(row["api_key_encrypted"])
        api_secret = self._encryption.decrypt(row["api_secret_encrypted"])
        return api_key, api_secret

    async def record_usage(self, key_id: UUID) -> None:
        """Record key usage timestamp.

        Args:
            key_id: Key UUID.
        """
        now = datetime.now(UTC)
        async with self._db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE api_keys SET last_used_at = $1 WHERE id = $2",
                now,
                key_id,
            )

    @staticmethod
    def _row_to_key(row: dict) -> ApiKey:
        """Convert database row to ApiKey domain model.

        Args:
            row: Database row dict.

        Returns:
            ApiKey domain model.
        """
        return ApiKey(
            id=row["id"],
            name=row["name"],
            environment=row["environment"],
            api_key_encrypted=row["api_key_encrypted"],
            api_secret_encrypted=row["api_secret_encrypted"],
            is_active=row["is_active"],
            permissions=row.get("permissions") or {},
            ip_whitelist=row.get("ip_whitelist") or [],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used_at=row.get("last_used_at"),
            created_by=row.get("created_by", "system"),
        )
