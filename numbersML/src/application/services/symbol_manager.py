"""
Symbol management service.

This service manages symbol activation and deactivation for data collection.

Architecture: Application Layer (orchestration)
Dependencies: Domain layer + Infrastructure (asyncpg)
"""

import logging
from typing import Optional

import asyncpg

from src.domain.models.config import SymbolConfig

logger = logging.getLogger(__name__)


class SymbolManager:
    """
    Manage symbol activation/deactivation.

    Responsibilities:
        - List all symbols
        - Activate/deactivate symbols
        - Update symbol configuration

    Example:
        >>> manager = SymbolManager(db_pool)
        >>> symbols = await manager.list_symbols()
        >>> await manager.activate_symbol(1)
    """

    def __init__(self, db_pool: asyncpg.Pool) -> None:
        """
        Initialize with database pool.

        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool

    async def list_symbols(
        self,
        active_only: bool = False,
    ) -> list[SymbolConfig]:
        """
        List all symbols, optionally filtered by active status.

        Args:
            active_only: If True, return only active symbols

        Returns:
            List of symbol configurations
        """
        async with self.db_pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch("""
                    SELECT
                        id as symbol_id, symbol, base_asset, quote_asset,
                        is_active, is_allowed,
                        tick_size, step_size, min_notional
                    FROM symbols
                    WHERE is_active = true AND is_allowed = true
                    ORDER BY symbol
                    """)
            else:
                rows = await conn.fetch("""
                    SELECT
                        id as symbol_id, symbol, base_asset, quote_asset,
                        is_active, is_allowed,
                        tick_size, step_size, min_notional
                    FROM symbols
                    ORDER BY is_active DESC, symbol
                    """)

            return [self._row_to_symbol(row) for row in rows]

    def _row_to_symbol(self, row: asyncpg.Record) -> SymbolConfig:
        """
        Convert database row to SymbolConfig.

        Args:
            row: Database record

        Returns:
            Symbol configuration
        """
        return SymbolConfig(
            symbol_id=row["symbol_id"],
            symbol=row["symbol"],
            base_asset=row["base_asset"],
            quote_asset=row["quote_asset"],
            is_active=row["is_active"],
            is_allowed=row["is_allowed"],
            tick_size=float(row["tick_size"] or 0.01),
            step_size=float(row["step_size"] or 0.00001),
            min_notional=float(row["min_notional"] or 10.0),
        )

    async def activate_symbol(self, symbol_id: int) -> bool:
        """
        Activate a symbol for data collection.

        Args:
            symbol_id: Symbol ID to activate

        Returns:
            True if activated successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE symbols
                    SET is_active = true, updated_at = NOW()
                    WHERE id = $1
                    """,
                    symbol_id,
                )

            logger.info(f"Activated symbol (ID: {symbol_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to activate symbol {symbol_id}: {e}")
            return False

    async def deactivate_symbol(self, symbol_id: int) -> bool:
        """
        Deactivate a symbol (stop data collection).

        Args:
            symbol_id: Symbol ID to deactivate

        Returns:
            True if deactivated successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE symbols
                    SET is_active = false, updated_at = NOW()
                    WHERE id = $1
                    """,
                    symbol_id,
                )

            logger.info(f"Deactivated symbol (ID: {symbol_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to deactivate symbol {symbol_id}: {e}")
            return False

    async def allow_symbol(self, symbol_id: int) -> bool:
        """
        Allow a symbol (mark as EU-compliant).

        Args:
            symbol_id: Symbol ID to allow

        Returns:
            True if allowed successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE symbols
                    SET is_allowed = true, updated_at = NOW()
                    WHERE id = $1
                    """,
                    symbol_id,
                )

            logger.info(f"Allowed symbol (ID: {symbol_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to allow symbol {symbol_id}: {e}")
            return False

    async def disallow_symbol(self, symbol_id: int) -> bool:
        """
        Disallow a symbol (mark as not EU-compliant).

        Args:
            symbol_id: Symbol ID to disallow

        Returns:
            True if disallowed successfully
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE symbols
                    SET is_allowed = false, updated_at = NOW()
                    WHERE id = $1
                    """,
                    symbol_id,
                )

            logger.info(f"Disallowed symbol (ID: {symbol_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to disallow symbol {symbol_id}: {e}")
            return False

    async def update_symbol(self, symbol: SymbolConfig) -> bool:
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

    async def get_symbol_by_id(self, symbol_id: int) -> Optional[SymbolConfig]:
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

    async def get_symbol_by_name(self, symbol: str) -> Optional[SymbolConfig]:
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

    async def bulk_activate(self, symbol_ids: list[int]) -> int:
        """
        Activate multiple symbols at once.

        Args:
            symbol_ids: List of symbol IDs to activate

        Returns:
            Number of symbols activated
        """
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE symbols
                    SET is_active = true, updated_at = NOW()
                    WHERE id = ANY($1)
                    """,
                    symbol_ids,
                )

            # Parse result string (e.g., "UPDATE 5")
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Bulk activated {count} symbols")
            return count

        except Exception as e:
            logger.error(f"Failed to bulk activate symbols: {e}")
            return 0

    async def bulk_deactivate(self, symbol_ids: list[int]) -> int:
        """
        Deactivate multiple symbols at once.

        Args:
            symbol_ids: List of symbol IDs to deactivate

        Returns:
            Number of symbols deactivated
        """
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE symbols
                    SET is_active = false, updated_at = NOW()
                    WHERE id = ANY($1)
                    """,
                    symbol_ids,
                )

            # Parse result string
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Bulk deactivated {count} symbols")
            return count

        except Exception as e:
            logger.error(f"Failed to bulk deactivate symbols: {e}")
            return 0

    async def activate_eu_compliant(self) -> int:
        """
        Activate all EU-compliant symbols.

        EU-compliant = USDC, EUR, BTC, ETH quote assets (not USDT, BUSD, TUSD)

        Returns:
            Number of symbols activated
        """
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE symbols
                    SET is_active = true, updated_at = NOW()
                    WHERE (
                        quote_asset IN ('USDC', 'EUR', 'BTC', 'ETH')
                    )
                    AND is_allowed = true
                    """)

            count = int(result.split()[-1]) if result else 0
            logger.info(f"Activated {count} EU-compliant symbols")
            return count

        except Exception as e:
            logger.error(f"Failed to activate EU-compliant symbols: {e}")
            return 0
