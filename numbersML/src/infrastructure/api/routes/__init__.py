"""API Routes Package."""

from .backup import router as backup_router
from .candles import router as candles_router
from .config import router as config_router
from .config_sets import router as config_sets_router
from .dashboard import router as dashboard_router
from .indicators import router as indicators_router
from .market import router as market_router
from .ml import router as ml_router
from .pipeline import router as pipeline_router
from .algorithms import router as algorithms_router
from .algorithm_backtest import router as algorithm_backtest_router
from .algorithm_instances import router as algorithm_instances_router
from .symbols import router as symbols_router
from .target_values import router as target_values_router

__all__ = [
    "dashboard_router",
    "symbols_router",
    "indicators_router",
    "config_router",
    "pipeline_router",
    "algorithms_router",
    "market_router",
    "algorithm_backtest_router",
    "candles_router",
    "target_values_router",
    "ml_router",
    "backup_router",
    "config_sets_router",
    "algorithm_instances_router",
]
