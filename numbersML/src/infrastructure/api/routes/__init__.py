"""API Routes Package."""

from .dashboard import router as dashboard_router
from .symbols import router as symbols_router
from .indicators import router as indicators_router
from .config import router as config_router
from .pipeline import router as pipeline_router
from .strategies import router as strategies_router
from .market import router as market_router
from .strategy_backtest import router as strategy_backtest_router

__all__ = [
    "dashboard_router",
    "symbols_router",
    "indicators_router",
    "config_router",
    "pipeline_router",
    "strategies_router",
    "market_router",
    "strategy_backtest_router",
]
