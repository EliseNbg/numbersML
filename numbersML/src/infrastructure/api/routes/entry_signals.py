"""
Live Entry Signal API endpoint.

Provides real time entry probability from the trained model.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Query, Depends
from typing import Optional

import numpy as np

from ml.entry_model import EntryPointModel
from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/signals", tags=["signals"])
logger = logging.getLogger(__name__)

model: Optional[EntryPointModel] = None


async def load_model():
    global model
    if model is None:
        try:
            model = EntryPointModel.load('entry_model.pkl')
            logger.info("Entry signal model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load entry model: {e}")
    return model


@router.get(
    "/entry",
    summary="Get entry probability for symbol",
    description="Returns probability [0..1] that current candle is a good entry point"
)
async def get_entry_signal(
    symbol: str = Query(..., description="Symbol name"),
    threshold: float = Query(0.6, description="Classification threshold"),
    model = Depends(load_model)
):
    if model is None:
        return {
            'symbol': symbol,
            'error': 'Model not loaded',
            'probability': 0.0,
            'signal': False
        }

    # Load latest wide vector
    db_pool = await get_db_pool_async()
    async with db_pool.acquire() as conn:
        symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
        if not symbol_id:
            return {'error': 'Symbol not found'}

        row = await conn.fetchrow("""
            SELECT vector FROM wide_vectors ORDER BY time DESC LIMIT 1
        """)

        if not row:
            return {'error': 'No data available'}

    vector = row['vector']

    # Predict
    probability, signal = model.predict(np.array([vector]), threshold=threshold)

    return {
        'symbol': symbol,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'probability': float(probability[0]),
        'signal': bool(signal[0]),
        'threshold': threshold
    }
