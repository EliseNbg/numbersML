"""
Asset Sync Service - Binance metadata synchronization.

Synchronizes symbol metadata from Binance API daily,
including trading pairs, tick sizes, step sizes, and
regional compliance filtering.
"""

import asyncio
import aiohttp
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set
import asyncpg
from src.domain.models.symbol import Symbol

logger = logging.getLogger(__name__)


class AssetSyncService:
    """
    Asset Sync Service for Binance metadata synchronization.

    Purpose:
        Fetches exchange info from Binance API and syncs
        symbol metadata to database daily.

    Features:
        - Fetch all trading pairs from Binance
        - Parse tick_size, step_size, min_notional
        - EU compliance filtering (allowed quote assets)
        - Auto-activate new pairs
        - Auto-deactivate delisted pairs
        - Idempotent updates

    Data Synced:
        - Symbol format (BTC/USDT)
        - Base/quote assets
        - Trading parameters (tick_size, step_size, min_notional)
        - EU compliance flag (is_allowed)
        - Active status (is_active)

    Example:
        >>> service = AssetSyncService(db_pool)
        >>> result = await service.sync()
        >>> print(f"Synced {result['added']} new symbols")
    """

    # Binance API endpoint
    BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"

    # EU allowed quote assets
    EU_ALLOWED_QUOTES: Set[str] = {'USDC', 'BTC', 'ETH', 'EUR', 'GBP'}

    # Quote assets to exclude in EU
    EU_EXCLUDED_QUOTES: Set[str] = {'USDT', 'BUSD', 'TUSD'}

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        auto_activate: bool = True,
        auto_deactivate_delisted: bool = False,
        eu_compliance: bool = True,
    ) -> None:
        """
        Initialize asset sync service.

        Args:
            db_pool: PostgreSQL connection pool
            auto_activate: Auto-activate new symbols (default: True)
            auto_deactivate_delisted: Deactivate delisted symbols (default: False)
            eu_compliance: Apply EU compliance filtering (default: True)

        Raises:
            ValueError: If db_pool is None
        """
        if db_pool is None:
            raise ValueError("db_pool cannot be None")

        self.db_pool: asyncpg.Pool = db_pool
        self.auto_activate: bool = auto_activate
        self.auto_deactivate_delisted: bool = auto_deactivate_delisted
        self.eu_compliance: bool = eu_compliance

        # Statistics
        self._stats: Dict[str, int] = {
            'fetched': 0,
            'added': 0,
            'updated': 0,
            'deactivated': 0,
            'errors': 0,
        }

    async def sync(self) -> Dict[str, int]:
        """
        Synchronize symbol metadata from Binance.

        Fetches exchange info from Binance API and updates
        database with latest symbol metadata.

        Process:
            1. Fetch exchange info from Binance API
            2. Parse symbols and trading parameters
            3. Apply EU compliance filtering (if enabled)
            4. Insert new symbols
            5. Update existing symbols
            6. Deactivate delisted symbols (if enabled)

        Returns:
            Dictionary with sync statistics:
            - fetched: Number of symbols fetched from Binance
            - added: Number of new symbols added
            - updated: Number of symbols updated
            - deactivated: Number of symbols deactivated
            - errors: Number of errors

        Raises:
            AssetSyncError: If sync fails completely
        """
        logger.info("Starting asset synchronization...")
        self._stats = {'fetched': 0, 'added': 0, 'updated': 0, 'deactivated': 0, 'errors': 0}

        try:
            # Fetch from Binance API
            symbols_data = await self._fetch_exchange_info()
            self._stats['fetched'] = len(symbols_data)
            logger.info(f"Fetched {len(symbols_data)} symbols from Binance")

            # Get existing symbols from database
            existing_symbols = await self._get_existing_symbols()

            # Process each symbol
            binance_symbols: Set[str] = set()

            for symbol_data in symbols_data:
                try:
                    symbol = self._parse_symbol(symbol_data)
                    if symbol is None:
                        continue

                    binance_symbols.add(symbol.symbol)

                    # Check if symbol exists
                    if symbol.symbol in existing_symbols:
                        await self._update_symbol(symbol)
                    else:
                        await self._add_symbol(symbol)

                except Exception as e:
                    self._stats['errors'] += 1
                    logger.error(f"Error processing symbol {symbol_data.get('symbol', 'UNKNOWN')}: {e}")

            # Deactivate delisted symbols
            if self.auto_deactivate_delisted:
                deactivated = await self._deactivate_delisted_symbols(binance_symbols)
                self._stats['deactivated'] = deactivated

            logger.info(
                f"Asset sync complete: "
                f"{self._stats['added']} added, "
                f"{self._stats['updated']} updated, "
                f"{self._stats['deactivated']} deactivated, "
                f"{self._stats['errors']} errors"
            )

            return self._stats.copy()

        except Exception as e:
            logger.error(f"Asset sync failed: {e}")
            raise AssetSyncError(f"Asset synchronization failed: {e}") from e

    async def _fetch_exchange_info(self) -> List[Dict]:
        """
        Fetch exchange info from Binance API.

        Returns:
            List of symbol data dictionaries from Binance

        Raises:
            AssetSyncError: If API request fails
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(self.BINANCE_EXCHANGE_INFO_URL) as response:
                if response.status != 200:
                    raise AssetSyncError(
                        f"Binance API returned status {response.status}"
                    )

                data = await response.json()

                if 'symbols' not in data:
                    raise AssetSyncError("Invalid response from Binance API")

                # Filter only TRADING pairs
                symbols = [
                    s for s in data['symbols']
                    if s.get('status') == 'TRADING'
                ]

                return symbols

    def _parse_symbol(self, data: Dict) -> Optional[Symbol]:
        """
        Parse symbol data from Binance format.

        Args:
            data: Symbol data from Binance API

        Returns:
            Symbol entity or None if invalid

        Example:
            Binance data: {
                'symbol': 'BTCUSDT',
                'baseAsset': 'BTC',
                'quoteAsset': 'USDT',
                'filters': [...]
            }
        """
        try:
            # Skip invalid symbols
            if data.get('status') != 'TRADING':
                return None

            base_asset = data.get('baseAsset', '')
            quote_asset = data.get('quoteAsset', '')

            # Skip if missing assets
            if not base_asset or not quote_asset:
                return None

            # Format symbol as BASE/QUOTE
            symbol_str = f"{base_asset}/{quote_asset}"

            # Apply EU compliance filtering
            is_allowed = True
            if self.eu_compliance:
                is_allowed = self._check_eu_compliance(quote_asset)

            # Extract trading parameters from filters
            tick_size, step_size, min_notional = self._extract_filters(data)

            return Symbol(
                symbol=symbol_str,
                base_asset=base_asset,
                quote_asset=quote_asset,
                exchange='binance',
                tick_size=tick_size,
                step_size=step_size,
                min_notional=min_notional,
                is_allowed=is_allowed,
                is_active=self.auto_activate and is_allowed,
            )

        except Exception as e:
            logger.debug(f"Error parsing symbol {data.get('symbol', 'UNKNOWN')}: {e}")
            return None

    def _check_eu_compliance(self, quote_asset: str) -> bool:
        """
        Check if quote asset is allowed in EU.

        Args:
            quote_asset: Quote asset code (e.g., 'USDT')

        Returns:
            True if allowed, False if excluded
        """
        if quote_asset in self.EU_EXCLUDED_QUOTES:
            return False

        return True

    def _extract_filters(
        self,
        data: Dict
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Extract trading parameters from Binance filters.

        Args:
            data: Symbol data from Binance API

        Returns:
            Tuple of (tick_size, step_size, min_notional)
        """
        tick_size = Decimal("0.00000001")
        step_size = Decimal("0.00000001")
        min_notional = Decimal("10")

        filters = data.get('filters', [])

        for f in filters:
            filter_type = f.get('filterType')

            # PRICE_FILTER: tick_size
            if filter_type == 'PRICE_FILTER':
                tick_size = Decimal(f.get('tickSize', tick_size))

            # LOT_SIZE: step_size
            elif filter_type == 'LOT_SIZE':
                step_size = Decimal(f.get('stepSize', step_size))

            # NOTIONAL: min_notional
            elif filter_type == 'NOTIONAL':
                min_notional = Decimal(f.get('minNotional', min_notional))

        return tick_size, step_size, min_notional

    async def _get_existing_symbols(self) -> Set[str]:
        """
        Get existing symbols from database.

        Returns:
            Set of symbol strings
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT symbol FROM symbols")
            return {row['symbol'] for row in rows}

    async def _add_symbol(self, symbol: Symbol) -> None:
        """
        Add new symbol to database.

        Args:
            symbol: Symbol entity to add
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO symbols (
                    symbol, base_asset, quote_asset,
                    tick_size, step_size, min_notional,
                    is_allowed, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                symbol.symbol,
                symbol.base_asset,
                symbol.quote_asset,
                symbol.tick_size,
                symbol.step_size,
                symbol.min_notional,
                symbol.is_allowed,
                symbol.is_active,
            )

        self._stats['added'] += 1
        logger.info(f"Added new symbol: {symbol.symbol}")

    async def _update_symbol(self, symbol: Symbol) -> None:
        """
        Update existing symbol in database.

        Args:
            symbol: Symbol entity to update
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE symbols SET
                    base_asset = $1,
                    quote_asset = $2,
                    tick_size = $3,
                    step_size = $4,
                    min_notional = $5,
                    is_allowed = $6,
                    is_active = $7,
                    updated_at = NOW()
                WHERE symbol = $8
                AND (
                    base_asset != $1 OR
                    quote_asset != $2 OR
                    tick_size != $3 OR
                    step_size != $4 OR
                    min_notional != $5 OR
                    is_allowed != $6 OR
                    is_active != $7
                )
                """,
                symbol.base_asset,
                symbol.quote_asset,
                symbol.tick_size,
                symbol.step_size,
                symbol.min_notional,
                symbol.is_allowed,
                symbol.is_active,
                symbol.symbol,
            )

            if result == "UPDATE 1":
                self._stats['updated'] += 1
                logger.debug(f"Updated symbol: {symbol.symbol}")

    async def _deactivate_delisted_symbols(self, binance_symbols: Set[str]) -> int:
        """
        Deactivate symbols no longer on Binance.

        Args:
            binance_symbols: Set of symbols currently on Binance

        Returns:
            Number of symbols deactivated
        """
        async with self.db_pool.acquire() as conn:
            # Find symbols in DB but not on Binance
            rows = await conn.fetch(
                """
                SELECT symbol FROM symbols
                WHERE symbol != ALL($1)
                AND is_active = true
                """,
                list(binance_symbols),
            )

            deactivated = len(rows)

            # Deactivate them
            for row in rows:
                await conn.execute(
                    """
                    UPDATE symbols SET
                        is_active = false,
                        updated_at = NOW()
                    WHERE symbol = $1
                    """,
                    row['symbol'],
                )

                logger.info(f"Deactivated delisted symbol: {row['symbol']}")

            return deactivated

    def get_stats(self) -> Dict[str, int]:
        """
        Get sync statistics.

        Returns:
            Dictionary with sync statistics
        """
        return self._stats.copy()


class AssetSyncError(Exception):
    """
    Exception raised when asset sync fails.

    Attributes:
        message: Error message
    """

    def __init__(self, message: str) -> None:
        """
        Initialize asset sync error.

        Args:
            message: Error message
        """
        self.message = message
        super().__init__(self.message)
