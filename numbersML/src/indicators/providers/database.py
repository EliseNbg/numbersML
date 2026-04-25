"""
Database Indicator Provider - Production Loading from PostgreSQL

Loads indicator definitions from the indicator_definitions table.
This is the production implementation that reads indicator configurations
from the database and instantiates them dynamically.
"""

import importlib
import logging
from typing import Dict, List, Optional, Type, Any
from typing_extensions import override

from ..base import Indicator
from .provider import IIndicatorProvider

logger = logging.getLogger(__name__)


class DatabaseIndicatorProvider(IIndicatorProvider):
    """Indicator provider that loads indicator definitions from PostgreSQL."""

    def __init__(self, db_pool: Any) -> None:
        self.db_pool = db_pool
        self._indicator_cache: Dict[str, Type[Indicator]] = {}
        logger.debug("DatabaseIndicatorProvider initialized")

    @override
    def get_indicator(self, name: str, **params: Any) -> Optional[Indicator]:
        # Try cache first
        indicator_class = self._indicator_cache.get(name)
        if indicator_class is None:
            indicator_class = self._load_from_database(name)
            if indicator_class is None:
                logger.warning(f"Indicator not found in database: {name}")
                return None
            self._indicator_cache[name] = indicator_class
        try:
            return indicator_class(**params)
        except Exception as e:
            logger.error(f"Failed to instantiate indicator {name}: {e}", exc_info=True)
            return None

    def _load_from_database(self, name: str) -> Optional[Type[Indicator]]:
        import asyncio
        try:
            return asyncio.run(self._load_indicator_class_async(name))
        except RuntimeError:
            logger.error(f"Cannot load indicator {name} - event loop conflict")
            return None
        except Exception as e:
            logger.error(f"Error loading indicator {name}: {e}", exc_info=True)
            return None

    async def _load_indicator_class_async(self, name: str) -> Optional[Type[Indicator]]:
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT class_name, module_path, params, is_active
                    FROM indicator_definitions WHERE name = $1
                    """,
                    name
                )
                if row is None or not row["is_active"]:
                    return None
                module = importlib.import_module(row["module_path"])
                return getattr(module, row["class_name"])
        except Exception as e:
            logger.error(f"Error loading indicator {name}: {e}")
            return None

    @override
    def get_indicator_class(self, name: str) -> Optional[Type[Indicator]]:
        return self._load_from_database(name)

    @override
    def list_indicators(self) -> List[str]:
        import asyncio
        try:
            return asyncio.run(self.list_indicators_async())
        except RuntimeError as e:
            logger.error(f"Cannot list indicators from async context")
            return []
        except Exception as e:
            logger.error(f"Error listing indicators: {e}")
            return []

    @override
    async def list_indicators_async(self) -> List[str]:
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT name FROM indicator_definitions
                       WHERE is_active = true ORDER BY name"""
                )
                return [row["name"] for row in rows]
        except Exception as e:
            logger.error(f"Error listing indicators: {e}")
            return []

    @override
    def is_available(self, name: str) -> bool:
        import asyncio
        try:
            return asyncio.run(self._is_available_async(name))
        except RuntimeError:
            return False
        except Exception as e:
            logger.error(f"Error checking indicator {name}: {e}")
            return False

    @override
    async def get_indicator_async(self, name: str, **params: Any) -> Optional[Indicator]:
        indicator_class = self._indicator_cache.get(name)
        if indicator_class is None:
            indicator_class = await self._load_indicator_class_async(name)
            if indicator_class is None:
                return None
            self._indicator_cache[name] = indicator_class
        try:
            return indicator_class(**params)
        except Exception as e:
            logger.error(f"Failed to instantiate indicator {name}: {e}")
            return None

    async def _is_available_async(self, name: str) -> bool:
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT is_active FROM indicator_definitions WHERE name = $1",
                    name
                )
                return result is True
        except Exception as e:
            logger.error(f"Error checking {name}: {e}")
            return False

    def clear_cache(self) -> None:
        self._indicator_cache.clear()
