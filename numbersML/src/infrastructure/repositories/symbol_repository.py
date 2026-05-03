"""
Symbol repository interface and implementation.

Provides data access for Symbol entities.
"""

from typing import Optional

import asyncpg

from src.domain.models.symbol import Symbol
from src.domain.repositories.base import Repository


class SymbolRepository(Repository[Symbol, int]):
    """
    PostgreSQL implementation of SymbolRepository.

    This repository provides data access for Symbol entities,
    implementing the repository pattern (port/adapter).

    Attributes:
        conn: PostgreSQL connection

    Example:
        >>> repo = SymbolRepository(connection)
        >>> symbols = await repo.get_active_symbols()
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        """
        Initialize symbol repository.

        Args:
            connection: PostgreSQL connection
        """
        self.conn: asyncpg.Connection = connection

    async def get_by_id(self, id: int) -> Optional[Symbol]:
        """
        Get symbol by ID.

        Args:
            id: Symbol ID

        Returns:
            Symbol if found, None otherwise
        """
        row = await self.conn.fetchrow("SELECT * FROM symbols WHERE id = $1", id)
        return self._map_to_entity(row) if row else None

    async def get_all(self) -> list[Symbol]:
        """
        Get all symbols.

        Returns:
            List of all symbols
        """
        rows = await self.conn.fetch("SELECT * FROM symbols")
        return [self._map_to_entity(row) for row in rows]

    async def get_active_symbols(self) -> list[Symbol]:
        """
        Get all active symbols.

        Returns:
            List of active symbols (is_active=True)
        """
        rows = await self.conn.fetch("SELECT * FROM symbols WHERE is_active = true")
        return [self._map_to_entity(row) for row in rows]

    async def save(self, symbol: Symbol) -> Symbol:
        """
        Save symbol.

        Args:
            symbol: Symbol to save

        Returns:
            Saved symbol with updated ID
        """
        row = await self.conn.fetchrow(
            """
            INSERT INTO symbols (
                symbol, base_asset, quote_asset, exchange,
                tick_size, step_size, min_notional,
                is_allowed, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (symbol) DO UPDATE SET
                base_asset = EXCLUDED.base_asset,
                quote_asset = EXCLUDED.quote_asset,
                tick_size = EXCLUDED.tick_size,
                step_size = EXCLUDED.step_size,
                min_notional = EXCLUDED.min_notional,
                is_allowed = EXCLUDED.is_allowed,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            RETURNING id
            """,
            symbol.symbol,
            symbol.base_asset,
            symbol.quote_asset,
            symbol.exchange,
            symbol.tick_size,
            symbol.step_size,
            symbol.min_notional,
            symbol.is_allowed,
            symbol.is_active,
        )
        symbol.id = row["id"]
        return symbol

    async def delete(self, id: int) -> bool:
        """
        Delete symbol by ID.

        Args:
            id: Symbol ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.conn.execute("DELETE FROM symbols WHERE id = $1", id)
        return result == "DELETE 1"

    def _map_to_entity(self, row: asyncpg.Record) -> Symbol:
        """
        Map database row to Symbol entity.

        Args:
            row: Database row

        Returns:
            Symbol entity
        """
        return Symbol(
            id=row["id"],
            symbol=row["symbol"],
            base_asset=row["base_asset"],
            quote_asset=row["quote_asset"],
            exchange=row["exchange"],
            tick_size=row["tick_size"],
            step_size=row["step_size"],
            min_notional=row["min_notional"],
            is_allowed=row["is_allowed"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
