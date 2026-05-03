"""
Configuration API endpoints.

Provides REST API for configuration management:
- Get table data
- Update entries
- Insert new entries
- Delete entries

Architecture: Infrastructure Layer (API)
Dependencies: Application services
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.config_manager import ConfigManager
from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/config", tags=["config"])


async def get_config_manager() -> ConfigManager:
    """Get ConfigManager instance with database pool."""
    db_pool = await get_db_pool_async()
    return ConfigManager(db_pool)


@router.get(
    "/{table_name}",
    summary="Get table data",
    description="Get data from configuration table",
)
async def get_table_data(
    table_name: str,
    limit: int = 100,
    manager: ConfigManager = Depends(get_config_manager),
) -> list[dict[str, Any]]:
    """
    Get data from configuration table.

    Allowed tables:
        - system_config
        - collection_config
        - symbols
        - indicator_definitions

    Args:
        table_name: Table name
        limit: Maximum rows to return (default: 100)

    Returns:
        List of row dictionaries

    Raises:
        400: Invalid table name
        400: Invalid limit
    """
    # Validate limit
    if limit < 1 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 1000",
        )

    try:
        return await manager.get_table_data(table_name=table_name, limit=limit)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{table_name}/{entry_id}",
    summary="Get entry",
    description="Get single configuration entry",
)
async def get_entry(
    table_name: str,
    entry_id: int,
    manager: ConfigManager = Depends(get_config_manager),
) -> dict[str, Any]:
    """
    Get single configuration entry.

    Args:
        table_name: Table name
        entry_id: Entry ID

    Returns:
        Entry dictionary

    Raises:
        400: Invalid table name
        404: Entry not found
    """
    try:
        entry = await manager.get_entry(table_name=table_name, entry_id=entry_id)

        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entry not found (ID: {entry_id})",
            )

        return entry

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put(
    "/{table_name}/{entry_id}",
    summary="Update entry",
    description="Update configuration entry",
)
async def update_entry(
    table_name: str,
    entry_id: int,
    data: dict[str, Any],
    manager: ConfigManager = Depends(get_config_manager),
) -> dict:
    """
    Update configuration entry.

    Args:
        table_name: Table name
        entry_id: Entry ID
        data: Data to update

    Returns:
        Success message

    Raises:
        400: Invalid table name
        400: No fields to update
        404: Entry not found
        500: Failed to update
    """
    try:
        success = await manager.update_entry(
            table_name=table_name,
            entry_id=entry_id,
            data=data,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update entry",
            )

        return {"message": f"Entry {entry_id} in {table_name} updated"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{table_name}",
    summary="Insert entry",
    description="Insert new configuration entry",
)
async def insert_entry(
    table_name: str,
    data: dict[str, Any],
    manager: ConfigManager = Depends(get_config_manager),
) -> dict:
    """
    Insert new configuration entry.

    Args:
        table_name: Table name
        data: Entry data

    Returns:
        New entry ID

    Raises:
        400: Invalid table name
        400: No fields to insert
        500: Failed to insert
    """
    try:
        entry_id = await manager.insert_entry(
            table_name=table_name,
            data=data,
        )

        if entry_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to insert entry",
            )

        return {"id": entry_id, "message": f"Entry inserted in {table_name}"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{table_name}/{entry_id}",
    summary="Delete entry",
    description="Delete configuration entry",
)
async def delete_entry(
    table_name: str,
    entry_id: int,
    manager: ConfigManager = Depends(get_config_manager),
) -> dict:
    """
    Delete configuration entry.

    Args:
        table_name: Table name
        entry_id: Entry ID

    Returns:
        Success message

    Raises:
        400: Invalid table name
        404: Entry not found
        500: Failed to delete
    """
    try:
        # Verify entry exists
        entry = await manager.get_entry(table_name=table_name, entry_id=entry_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entry not found (ID: {entry_id})",
            )

        success = await manager.delete_entry(
            table_name=table_name,
            entry_id=entry_id,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete entry",
            )

        return {"message": f"Entry {entry_id} in {table_name} deleted"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/system-config/{key}",
    summary="Get config value",
    description="Get configuration value by key from system_config",
)
async def get_config_value(
    key: str,
    default: Any = None,
    manager: ConfigManager = Depends(get_config_manager),
) -> Any:
    """
    Get configuration value by key from system_config.

    Args:
        key: Configuration key
        default: Default value if not found

    Returns:
        Configuration value or default

    Example:
        GET /api/config/system-config/collector.batch_size
        Returns: {"size": 500}
    """
    return await manager.get_config_value(key=key, default=default)


@router.put(
    "/system-config/{key}",
    summary="Set config value",
    description="Set configuration value in system_config",
)
async def set_config_value(
    key: str,
    value: Any,
    description: str = None,
    manager: ConfigManager = Depends(get_config_manager),
) -> dict:
    """
    Set configuration value in system_config.

    Args:
        key: Configuration key
        value: Configuration value
        description: Optional description

    Returns:
        Success message

    Raises:
        500: Failed to set value
    """
    success = await manager.set_config_value(
        key=key,
        value=value,
        description=description,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set config value",
        )

    return {"message": f"Config value {key} set"}
