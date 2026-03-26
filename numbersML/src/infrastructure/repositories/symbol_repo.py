"""
Symbol data access repository.

This repository provides data access for symbols table.

Architecture: Infrastructure Layer (data access)
Dependencies: Domain layer + asyncpg
"""

import logging
from typing import List, Optional

import asyncpg

from src.domain.models.config import SymbolConfig

logger = logging.getLogger(__name__)


class SymbolRepository:
    """
    Repository for symbols table.
    
    Responsibilities:
        - List symbols with filtering
        - Get symbol by ID or name
        - Update symbol configuration
        - Activate/deactivate symbols
    
    Example:
        >>> repo = SymbolRepository(db_pool)
        >>> symbols = await repo.list_all()
    """
    
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.
        
        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
    
    async def list_all(
        self,
        active_only: bool = False,
    ) -> List[SymbolConfig]:
        """
        List all symbols, optionally filtered by active status.
        
        Args:
            active_only: If True, return only active symbols
        
        Returns:
            List of symbol configurations
        """
        async with self.db_pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch(
                    """
                    SELECT 
                        id as symbol_id, symbol, base_asset, quote_asset,
                        is_active, is_allowed,
                        tick_size, step_size, min_notional
                    FROM symbols
                    WHERE is_active = true AND is_allowed = true
                    ORDER BY symbol
                    """
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT 
                        id as symbol_id, symbol, base_asset, quote_asset,
                        is_active, is_allowed,
                        tick_size, step_size, min_notional
                    FROM symbols
                    ORDER BY is_active DESC, symbol
                    """
                )
            
            return [self._row_to_symbol(row) for row in rows]
    
    async def get_by_id(self, symbol_id: int) -> Optional[SymbolConfig]:
        """
        Get symbol by ID.
        
        Args:
            symbol_id: Symbol ID
        
        Returns:
            Symbol configuration or None if not found
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    id as symbol_id, symbol, base_asset, quote_asset,
                    is_active, is_allowed,
                    tick_size, step_size, min_notional
                FROM symbols
                WHERE id = $1
                """,
                symbol_id,
            )
            
            return self._row_to_symbol(row) if row else None
    
    async def get_by_name(self, symbol: str) -> Optional[SymbolConfig]:
        """
        Get symbol by name.
        
        Args:
            symbol: Symbol name (e.g., 'BTC/USDT')
        
        Returns:
            Symbol configuration or None if not found
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    id as symbol_id, symbol, base_asset, quote_asset,
                    is_active, is_allowed,
                    tick_size, step_size, min_notional
                FROM symbols
                WHERE symbol = $1
                """,
                symbol,
            )
            
            return self._row_to_symbol(row) if row else None
    
    async def update_active(
        self,
        symbol_id: int,
        is_active: bool,
    ) -> bool:
        """
        Update symbol active status.
        
        Args:
            symbol_id: Symbol ID
            is_active: New active status
        
        Returns:
            True if updated successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE symbols
                    SET is_active = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    symbol_id,
                    is_active,
                )
            
            status = "activated" if is_active else "deactivated"
            logger.info(f"{status.capitalize()} symbol (ID: {symbol_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update symbol {symbol_id}: {e}")
            return False
    
    async def update(self, symbol: SymbolConfig) -> bool:
        """
        Update symbol configuration.
        
        Args:
            symbol: Symbol configuration with updated values
        
        Returns:
            True if updated successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE symbols
                    SET 
                        is_active = $2,
                        is_allowed = $3,
                        tick_size = $4,
                        step_size = $5,
                        min_notional = $6,
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    symbol.symbol_id,
                    symbol.is_active,
                    symbol.is_allowed,
                    symbol.tick_size,
                    symbol.step_size,
                    symbol.min_notional,
                )
            
            logger.info(f"Updated symbol (ID: {symbol.symbol_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update symbol {symbol.symbol_id}: {e}")
            return False
    
    async def count_active(self) -> int:
        """
        Count active symbols.
        
        Returns:
            Number of active symbols
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM symbols
                WHERE is_active = true AND is_allowed = true
                """
            )
            
            return row['count'] or 0
    
    async def count_total(self) -> int:
        """
        Count total symbols.
        
        Returns:
            Total number of symbols
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM symbols
                """
            )
            
            return row['count'] or 0
    
    def _row_to_symbol(self, row: asyncpg.Record) -> SymbolConfig:
        """
        Convert database row to SymbolConfig.
        
        Args:
            row: Database record
        
        Returns:
            Symbol configuration
        """
        return SymbolConfig(
            symbol_id=row['symbol_id'],
            symbol=row['symbol'],
            base_asset=row['base_asset'],
            quote_asset=row['quote_asset'],
            is_active=row['is_active'],
            is_allowed=row['is_allowed'],
            tick_size=float(row['tick_size'] or 0.01),
            step_size=float(row['step_size'] or 0.00001),
            min_notional=float(row['min_notional'] or 10.0),
        )
