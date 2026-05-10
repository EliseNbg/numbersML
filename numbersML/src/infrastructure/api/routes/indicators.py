"""
Indicator management API endpoints.

Provides REST API for indicator management:
- List indicators
- Register new indicators
- Activate/deactivate indicators
- Update indicator parameters

Architecture: Infrastructure Layer (API)
Dependencies: Application services
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.indicator_manager import IndicatorManager
from src.domain.models.config import IndicatorConfig
from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/indicators", tags=["indicators"])


async def get_indicator_manager() -> IndicatorManager:
    """Get IndicatorManager instance with database pool."""
    db_pool = await get_db_pool_async()
    return IndicatorManager(db_pool)


@router.get(
    "",
    response_model=list[IndicatorConfig],
    summary="List indicators",
    description="List indicators with optional filters",
)
async def list_indicators(
    active_only: bool = False,
    category: Optional[str] = None,
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> list[IndicatorConfig]:
    """
    List indicators with optional filters.

    Args:
        active_only: If True, return only active indicators
        category: Filter by category (momentum, trend, volatility, volume)

    Returns:
        List of indicator configurations

    Example:
        [
            {
                "name": "rsi_14",
                "class_name": "RSIIndicator",
                "module_path": "src.indicators.momentum",
                "category": "momentum",
                "params": {"period": 14},
                "is_active": true
            }
        ]
    """
    return await manager.list_indicators(
        active_only=active_only,
        category=category,
    )


@router.get(
    "/categories",
    summary="Get categories",
    description="Get all indicator categories",
)
async def get_categories(
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> list[str]:
    """
    Get all indicator categories.

    Returns:
        List of category names

    Example:
        ["momentum", "trend", "volatility", "volume"]
    """
    return await manager.get_categories()


@router.get(
    "/{name}",
    response_model=IndicatorConfig,
    summary="Get indicator",
    description="Get indicator by name",
)
async def get_indicator(
    name: str,
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> IndicatorConfig:
    """
    Get indicator by name.

    Args:
        name: Indicator name (e.g., 'rsi_14')

    Returns:
        Indicator configuration

    Raises:
        404: Indicator not found
    """
    indicator = await manager.get_by_name(name)

    if not indicator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indicator not found: {name}",
        )

    return indicator


@router.post(
    "",
    summary="Register indicator",
    description="Register a new indicator",
)
async def register_indicator(
    indicator: IndicatorConfig,
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> dict:
    """
    Register a new indicator.

    Args:
        indicator: Indicator configuration

    Returns:
        Success message

    Raises:
        400: Invalid indicator data
        409: Indicator already exists
        500: Failed to register
    """
    # Check if already exists
    existing = await manager.get_by_name(indicator.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Indicator already exists: {indicator.name}",
        )

    success = await manager.register_indicator(
        name=indicator.name,
        class_name=indicator.class_name,
        module_path=indicator.module_path,
        category=indicator.category,
        params=indicator.params,
        is_active=indicator.is_active,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register indicator",
        )

    return {"message": f"Indicator {indicator.name} registered"}


@router.put(
    "/{name}/activate",
    summary="Activate indicator",
    description="Activate an indicator",
)
async def activate_indicator(
    name: str,
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> dict:
    """
    Activate an indicator.

    Args:
        name: Indicator name

    Returns:
        Success message

    Raises:
        404: Indicator not found
        500: Failed to activate
    """
    # Verify indicator exists
    indicator = await manager.get_by_name(name)
    if not indicator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indicator not found: {name}",
        )

    success = await manager.activate_indicator(name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate indicator",
        )

    return {"message": f"Indicator {name} activated"}


@router.put(
    "/{name}/deactivate",
    summary="Deactivate indicator",
    description="Deactivate an indicator",
)
async def deactivate_indicator(
    name: str,
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> dict:
    """
    Deactivate an indicator.

    Args:
        name: Indicator name

    Returns:
        Success message

    Raises:
        404: Indicator not found
        500: Failed to deactivate
    """
    # Verify indicator exists
    indicator = await manager.get_by_name(name)
    if not indicator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indicator not found: {name}",
        )

    success = await manager.deactivate_indicator(name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate indicator",
        )

    return {"message": f"Indicator {name} deactivated"}


@router.put(
    "/{name}",
    summary="Update indicator",
    description="Update indicator configuration",
)
async def update_indicator(
    name: str,
    params: Optional[dict[str, Any]] = None,
    is_active: Optional[bool] = None,
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> dict:
    """
    Update indicator configuration.

    Args:
        name: Indicator name
        params: New parameters (optional)
        is_active: New active status (optional)

    Returns:
        Success message

    Raises:
        404: Indicator not found
        400: No fields to update
        500: Failed to update
    """
    # Verify indicator exists
    indicator = await manager.get_by_name(name)
    if not indicator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indicator not found: {name}",
        )

    # Verify at least one field to update
    if params is None and is_active is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field (params or is_active) must be provided",
        )

    success = await manager.update_indicator(
        name=name,
        params=params,
        is_active=is_active,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update indicator",
        )

    return {"message": f"Indicator {name} updated"}


@router.delete(
    "/{name}",
    summary="Unregister indicator",
    description="Unregister an indicator (soft delete)",
)
async def unregister_indicator(
    name: str,
    manager: IndicatorManager = Depends(get_indicator_manager),
) -> dict:
    """
    Unregister an indicator (soft delete - sets is_active=false).

    Args:
        name: Indicator name

    Returns:
        Success message

    Raises:
        404: Indicator not found
        500: Failed to unregister
    """
    # Verify indicator exists
    indicator = await manager.get_by_name(name)
    if not indicator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indicator not found: {name}",
        )

    success = await manager.unregister_indicator(name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unregister indicator",
        )

    return {"message": f"Indicator {name} unregistered"}
