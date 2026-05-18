"""API Routes Package."""

from .api_keys import router as api_keys_router
from .backup import router as backup_router
from .candles import router as candles_router
from .config import router as config_router
from .dashboard import router as dashboard_router
from .indicators import router as indicators_router
from .market import router as market_router
from .ml import router as ml_router
from .orders_gui import router as orders_gui_router
from .pipeline import router as pipeline_router
from .signals import router as signals_router
from .strategies import router as strategies_router
from .strategies_gui import router as strategies_gui_router
from .strategy_backtest import router as strategy_backtest_router
from .symbols import router as symbols_router
from .target_values import router as target_values_router

__all__ = [
    "dashboard_router",
    "symbols_router",
    "indicators_router",
    "config_router",
    "pipeline_router",
    "strategies_router",
    "strategies_gui_router",
    "market_router",
    "strategy_backtest_router",
    "candles_router",
    "target_values_router",
    "ml_router",
    "backup_router",
    "signals_router",
    "api_keys_router",
    "orders_gui_router",
]
