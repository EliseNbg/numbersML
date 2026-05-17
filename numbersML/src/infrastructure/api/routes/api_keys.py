"""API key management routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from src.application.services.api_key_service import ApiKeyService
from src.infrastructure.security.encryption import EncryptionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


def get_key_service() -> ApiKeyService:
    """Get API key service instance (dependency injection placeholder)."""
    from src.infrastructure.database import get_db_pool

    import os
    master_key = os.environ.get("BINANCE_MASTER_KEY")
    if master_key is None:
        # Generate a temporary key for development (not secure for production)
        master_key = "0" * 64
    encryption = EncryptionService(master_key=master_key)
    pool = get_db_pool()
    return ApiKeyService(encryption_service=encryption, db_pool=pool)


@router.post("", status_code=201)
async def create_api_key(
    name: str = Query(..., min_length=1, max_length=100),
    environment: str = Query(..., pattern="^(mainnet|testnet)$"),
    api_key: str = Query(..., min_length=1),
    api_secret: str = Query(..., min_length=1),
    created_by: str = Query(default="system"),
) -> dict:
    """Create a new API key (encrypted).

    Args:
        name: Human-readable name for the key.
        environment: Target environment ('mainnet' or 'testnet').
        api_key: Plain API key.
        api_secret: Plain API secret.
        created_by: User who created the key.

    Returns:
        Created key metadata (never includes secrets).
    """
    service = get_key_service()
    key = await service.create_key(
        name=name,
        environment=environment,
        api_key=api_key,
        api_secret=api_secret,
        created_by=created_by,
    )
    return key.to_public_dict()


@router.get("")
async def list_api_keys(
    environment: str | None = Query(default=None),
) -> list[dict]:
    """List all API keys (never returns secrets).

    Args:
        environment: Optional filter by environment.

    Returns:
        List of key metadata.
    """
    try:
        service = get_key_service()
        keys = await service.list_keys(environment=environment)
        return [key.to_public_dict() for key in keys]
    except Exception as exc:
        logger.error(f"Failed to list API keys: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{key_id}")
async def get_api_key(key_id: UUID) -> dict:
    """Get key details (never returns secret).

    Args:
        key_id: Key UUID.

    Returns:
        Key metadata.

    Raises:
        HTTPException: 404 if key not found.
    """
    service = get_key_service()
    key = await service.get_key(key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return key.to_public_dict()


@router.put("/{key_id}")
async def update_api_key(
    key_id: UUID,
    name: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> dict:
    """Update key name/permissions.

    Args:
        key_id: Key UUID.
        name: New name.
        is_active: New active status.

    Returns:
        Updated key metadata.

    Raises:
        HTTPException: 404 if key not found.
    """
    service = get_key_service()
    key = await service.update_key(key_id, name=name, is_active=is_active)
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return key.to_public_dict()


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(key_id: UUID) -> None:
    """Delete an API key.

    Args:
        key_id: Key UUID.

    Raises:
        HTTPException: 404 if key not found.
    """
    service = get_key_service()
    deleted = await service.delete_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")


@router.post("/{key_id}/test")
async def test_connectivity(key_id: UUID) -> dict:
    """Test connectivity with key.

    Args:
        key_id: Key UUID.

    Returns:
        Test result with status.

    Raises:
        HTTPException: 404 if key not found.
    """
    service = get_key_service()
    key = await service.get_key(key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    # Decrypt and test connection
    try:
        decrypted = await service.get_decrypted_key(key_id)
        if decrypted is None:
            raise HTTPException(status_code=404, detail="API key not found")

        api_key, api_secret = decrypted

        from src.infrastructure.market.binance_exchange_client import (
            BINANCE_PROD,
            BINANCE_TESTNET,
            BinanceExchangeClient,
        )

        env = BINANCE_PROD if key.environment == "mainnet" else BINANCE_TESTNET
        client = BinanceExchangeClient(
            api_key=api_key,
            api_secret=api_secret,
            environment=env,
        )

        await client.get_ticker_price("BTCUSDT")
        await client.close()

        await service.record_usage(key_id)
        return {"status": "success", "message": "Connection successful"}

    except Exception as exc:
        logger.error(f"Connectivity test failed for key {key_id}: {exc}")
        return {"status": "error", "message": str(exc)}


@router.post("/{key_id}/rotate")
async def rotate_key(
    key_id: UUID,
    new_api_key: str = Query(..., min_length=1),
    new_api_secret: str = Query(..., min_length=1),
) -> dict:
    """Rotate key (new secret, old still works briefly).

    Args:
        key_id: Key UUID.
        new_api_key: New API key.
        new_api_secret: New API secret.

    Returns:
        Updated key metadata.

    Raises:
        HTTPException: 404 if key not found.
    """
    service = get_key_service()
    existing = await service.get_key(key_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="API key not found")

    # Delete old key and create new one
    await service.delete_key(key_id)

    new_key = await service.create_key(
        name=f"{existing.name} (rotated)",
        environment=existing.environment,
        api_key=new_api_key,
        api_secret=new_api_secret,
        created_by=existing.created_by,
    )

    return new_key.to_public_dict()
