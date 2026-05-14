"""
Symbol management API endpoints.

Provides REST API for symbol management:
- List symbols
- Activate/deactivate symbols
- Update symbol configuration

Architecture: Infrastructure Layer (API)
Dependencies: Application services
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services.symbol_manager import SymbolManager
from src.domain.models.config import SymbolConfig
from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


async def get_symbol_manager() -> SymbolManager:
    """Get SymbolManager instance with database pool."""
    db_pool = await get_db_pool_async()
    return SymbolManager(db_pool)


@router.get(
    "",
    response_model=list[SymbolConfig],
    summary="List symbols",
    description="List all symbols, optionally filtered by active status",
)
async def list_symbols(
    active_only: bool = False,
    manager: SymbolManager = Depends(get_symbol_manager),
) -> list[SymbolConfig]:
    """
    List all symbols.

    Args:
        active_only: If True, return only active symbols

    Returns:
        List of symbol configurations

    Example:
        [
            {
                "symbol_id": 1,
                "symbol": "BTC/USDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "is_active": true,
                "is_allowed": true,
                "tick_size": 0.01,
                "step_size": 0.00001,
                "min_notional": 10.0
            }
        ]
    """
    return await manager.list_symbols(active_only=active_only)


@router.get(
    "/{symbol_id}",
    response_model=SymbolConfig,
    summary="Get symbol",
    description="Get symbol by ID",
)
async def get_symbol(
    symbol_id: int,
    manager: SymbolManager = Depends(get_symbol_manager),
) -> SymbolConfig:
    """
    Get symbol by ID.

    Args:
        symbol_id: Symbol ID

    Returns:
        Symbol configuration

    Raises:
        404: Symbol not found
    """
    symbol = await manager.get_symbol_by_id(symbol_id)

    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol not found (ID: {symbol_id})",
        )

    return symbol


@router.put(
    "/{symbol_id}/activate",
    summary="Activate symbol",
    description="Activate a symbol for data collection",
)
async def activate_symbol(
    symbol_id: int,
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Activate a symbol.

    Args:
        symbol_id: Symbol ID to activate

    Returns:
        Success message

    Raises:
        404: Symbol not found
        500: Failed to activate
    """
    # Verify symbol exists
    symbol = await manager.get_symbol_by_id(symbol_id)
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol not found (ID: {symbol_id})",
        )

    success = await manager.activate_symbol(symbol_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate symbol",
        )

    return {"message": f"Symbol {symbol.symbol} activated"}


@router.put(
    "/{symbol_id}/deactivate",
    summary="Deactivate symbol",
    description="Deactivate a symbol (stop data collection)",
)
async def deactivate_symbol(
    symbol_id: int,
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Deactivate a symbol.

    Args:
        symbol_id: Symbol ID to deactivate

    Returns:
        Success message

    Raises:
        404: Symbol not found
        500: Failed to deactivate
    """
    # Verify symbol exists
    symbol = await manager.get_symbol_by_id(symbol_id)
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol not found (ID: {symbol_id})",
        )

    success = await manager.deactivate_symbol(symbol_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate symbol",
        )

    return {"message": f"Symbol {symbol.symbol} deactivated"}


@router.put(
    "/{symbol_id}/allow",
    summary="Allow symbol",
    description="Allow a symbol (mark as EU-compliant)",
)
async def allow_symbol(
    symbol_id: int,
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Allow a symbol.

    Args:
        symbol_id: Symbol ID to allow

    Returns:
        Success message

    Raises:
        404: Symbol not found
        500: Failed to allow
    """
    # Verify symbol exists
    symbol = await manager.get_symbol_by_id(symbol_id)
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol not found (ID: {symbol_id})",
        )

    success = await manager.allow_symbol(symbol_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to allow symbol",
        )

    return {"message": f"Symbol {symbol.symbol} allowed"}


@router.put(
    "/{symbol_id}/disallow",
    summary="Disallow symbol",
    description="Disallow a symbol (mark as not EU-compliant)",
)
async def disallow_symbol(
    symbol_id: int,
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Disallow a symbol.

    Args:
        symbol_id: Symbol ID to disallow

    Returns:
        Success message

    Raises:
        404: Symbol not found
        500: Failed to disallow
    """
    # Verify symbol exists
    symbol = await manager.get_symbol_by_id(symbol_id)
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol not found (ID: {symbol_id})",
        )

    success = await manager.disallow_symbol(symbol_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disallow symbol",
        )

    return {"message": f"Symbol {symbol.symbol} disallowed"}


@router.put(
    "/{symbol_id}",
    summary="Update symbol",
    description="Update symbol configuration",
)
async def update_symbol(
    symbol_id: int,
    symbol: SymbolConfig,
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Update symbol configuration.

    Args:
        symbol_id: Symbol ID to update
        symbol: New symbol configuration

    Returns:
        Success message

    Raises:
        404: Symbol not found
        400: Symbol ID mismatch
        500: Failed to update
    """
    # Verify symbol exists
    existing = await manager.get_symbol_by_id(symbol_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol not found (ID: {symbol_id})",
        )

    # Verify ID matches
    if symbol.symbol_id != symbol_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol ID in path and body must match",
        )

    success = await manager.update_symbol(symbol)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update symbol",
        )

    return {"message": f"Symbol {symbol.symbol} updated"}


@router.post(
    "/bulk/activate",
    summary="Bulk activate",
    description="Activate multiple symbols at once",
)
async def bulk_activate(
    symbol_ids: list[int],
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Activate multiple symbols.

    Args:
        symbol_ids: List of symbol IDs to activate

    Returns:
        Number of symbols activated

    Example:
        {"activated": 5}
    """
    count = await manager.bulk_activate(symbol_ids)

    return {"activated": count}


@router.post(
    "/bulk/deactivate",
    summary="Bulk deactivate",
    description="Deactivate multiple symbols at once",
)
async def bulk_deactivate(
    symbol_ids: list[int],
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Deactivate multiple symbols.

    Args:
        symbol_ids: List of symbol IDs to deactivate

    Returns:
        Number of symbols deactivated

    Example:
        {"deactivated": 3}
    """
    count = await manager.bulk_deactivate(symbol_ids)

    return {"deactivated": count}


@router.post(
    "/activate-eu-compliant",
    summary="Activate EU-compliant",
    description="Activate all EU-compliant symbols (USDC, EUR, BTC, ETH quotes)",
)
async def activate_eu_compliant(
    manager: SymbolManager = Depends(get_symbol_manager),
) -> dict:
    """
    Activate all EU-compliant symbols.

    EU-compliant = USDC, EUR, BTC, ETH quote assets (not USDT, BUSD, TUSD)

    Returns:
        Number of symbols activated

    Example:
        {"activated": 15}
    """
    count = await manager.activate_eu_compliant()

    return {"activated": count}
