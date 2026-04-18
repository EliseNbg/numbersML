"""
Backtest API endpoints for Entry Point Model.
"""

import logging
import os
import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi import APIRouter, Query, Depends

from ml.entry_model import EntryPointModel
from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
logger = logging.getLogger(__name__)


async def get_model_files() -> List[Dict]:
    """Get list of available entry point models.
    """
    model_dir = Path('.')
    models = []

    for file in model_dir.glob('entry_model_*.pkl'):
        try:
            parts = file.stem.split('_')
            symbol = parts[2] + '/' + parts[3]
            timestamp = datetime.strptime(f"{parts[4]}_{parts[5]}", "%Y%m%d_%H%M")

            models.append({
                'filename': file.name,
                'name': file.stem,
                'symbol': symbol,
                'timestamp': timestamp.isoformat(),
                'size': file.stat().st_size
            })
        except:
            continue

    return sorted(models, key=lambda m: m['timestamp'], reverse=True)


@router.get(
    "/models/entry",
    summary="List available entry point models",
    description="Returns list of trained model files"
)
async def list_entry_models():
    return await get_model_files()


@router.get(
    "/entry",
    summary="Run backtest for entry point model",
    description="Run historical backtest and return trades and metrics"
)
async def run_backtest(
    symbol: str = Query(..., description="Symbol name"),
    model: str = Query(..., description="Model filename"),
    seconds: int = Query(604800, description="Backtest time range in seconds"),
    threshold: float = Query(0.9, description="Prediction threshold", ge=0.5, le=1.0)
):
    """
    Run backtest:
    1. Load historical candle data for given time range
    2. Load trained model
    3. Run predictions on every candle
    4. Simulate trading with entry/exit rules
    5. Return trades list and performance metrics
    """
    try:
        db_pool = await get_db_pool_async()

        # Get last timestamp for symbol
        async with db_pool.acquire() as conn:
            symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
            if not symbol_id:
                return {'error': 'Symbol not found'}

            last_time = await conn.fetchval("""
                SELECT MAX(time) FROM candles_1s WHERE symbol_id = $1
            """, symbol_id)

            start_time = last_time - timedelta(seconds=seconds)

            rows = await conn.fetch("""
                SELECT c.time, c.close, wv.vector FROM candles_1s c
                JOIN wide_vectors wv ON wv.time = c.time
                WHERE c.symbol_id = $1 AND c.time >= $2
                ORDER BY c.time ASC
            """, symbol_id, start_time)

        if not rows:
            return {'error': 'No candle data found'}

        # Load model
        loaded_model = EntryPointModel.load(model)

    # Run predictions
    probabilities, predictions = loaded_model.predict(vectors, threshold=threshold)

    # Simulate trading
    trades = []
    position = 0
    entry_price = 0.0
    entry_time = 0

    profit_target = 0.06
    stop_loss = 0.0035

    for i in range(len(closes)):
        current_price = closes[i]
        current_time = timestamps[i]

        if predictions[i] == 1 and position == 0:
            # Enter position
            position = 1
            entry_price = current_price
            entry_time = current_time

        elif position == 1:
            # Check exit conditions
            profit_pct = (current_price - entry_price) / entry_price

            if profit_pct >= profit_target or profit_pct <= -stop_loss or i == len(closes)-1:
                # Exit position
                position = 0
                pnl = (current_price - entry_price) / entry_price

                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'entry_price': entry_price,
                    'exit_price': current_price,
                    'pnl': pnl
                })

    # Calculate metrics
    if trades:
        wins = sum(1 for t in trades if t['pnl'] > 0)
        win_rate = wins / len(trades)
        total_return = np.prod([1 + t['pnl'] for t in trades]) - 1
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Calculate max drawdown
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for t in trades:
            equity *= (1 + t['pnl'])
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        avg_duration = np.mean([t['exit_time'] - t['entry_time'] for t in trades])

        metrics = {
            'total_trades': len(trades),
            'win_rate': win_rate,
            'total_return': total_return,
            'profit_factor': profit_factor,
            'max_drawdown': max_dd,
            'avg_duration': avg_duration
        }
    else:
        metrics = {
            'total_trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'profit_factor': 0,
            'max_drawdown': 0,
            'avg_duration': 0
        }

    return {
        'symbol': symbol,
        'model': model,
        'candles': [{'time': t, 'close': c} for t, c in zip(timestamps, closes)],
        'trades': trades,
        'metrics': metrics
    }

    except Exception as e:
        logger.exception(f"Backtest failed: {e}")
        return {'error': str(e)}
