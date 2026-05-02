"""
TradingTCN and Entry Model Backtest API endpoints.

Provides endpoints for:
- TradingTCN model backtesting (neural network with PnL optimization)
- Entry point model backtesting (LightGBM binary classifier)
"""

import logging
import os
import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone

import numpy as np
import torch
import torch.serialization
from fastapi import APIRouter, Query, Depends

from ml.model import TradingTCN, create_model
from ml.entry_model import EntryPointModel
from ml.config import ModelConfig
from src.infrastructure.database import get_db_pool_async

router = APIRouter(prefix="/api/backtest_ml", tags=["backtest_ml"])
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# TradingTCN Model Endpoints
# -------------------------------------------------------------------

async def get_trading_tcn_models() -> List[Dict]:
    """Get list of available TradingTCN models."""
    model_dir = Path('ml/models/trading_tcn')
    models = []

    for file in model_dir.glob('trading_tcn_*.pt'):
        try:
            # Parse filename: trading_tcn_SYMBOL_TIMESTAMP.pt
            parts = file.stem.split('_')
            if len(parts) >= 3:
                symbol = parts[2]  # SYMBOL part
                # Extract timestamp from filename (last part before .pt)
                timestamp_str = parts[-1]
                try:
                    # Assume format YYYYMMDD_HHMM
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M")
                except ValueError:
                    # Fallback to file modification time
                    timestamp = datetime.fromtimestamp(file.stat().st_mtime)

                models.append({
                    'filename': file.name,
                    'name': file.stem,
                    'symbol': symbol,
                    'timestamp': timestamp.isoformat(),
                    'size': file.stat().st_size
                })
        except Exception as e:
            logger.warning(f"Failed to parse model file {file}: {e}")
            continue

    return sorted(models, key=lambda m: m['timestamp'], reverse=True)


@router.get(
    "/models/trading_tcn",
    summary="List available TradingTCN models",
    description="Returns list of trained TradingTCN model files"
)
async def list_trading_tcn_models():
    return await get_trading_tcn_models()


@router.get(
    "/trading_tcn",
    summary="Run backtest for TradingTCN model",
    description="Run historical backtest using TradingTCN return predictions"
)
async def run_trading_tcn_backtest(
    symbol: str = Query(..., description="Symbol name"),
    model: str = Query(..., description="Model filename"),
    seconds: int = Query(604800, description="Backtest time range in seconds"),
    score_threshold: float = Query(0.001, description="Risk-adjusted score threshold for entry")
):
    """
    Run TradingTCN backtest:
    1. Load historical candle data
    2. Load trained TradingTCN model
    3. Generate return/risk predictions
    4. Simulate trading using risk-adjusted scoring
    5. Return trades and performance metrics
    """
    try:
        db_pool = await get_db_pool_async()

        # Get symbol_id and last timestamp
        async with db_pool.acquire() as conn:
            symbol_id = await conn.fetchval("SELECT id FROM symbols WHERE symbol = $1", symbol)
            if not symbol_id:
                return {'error': 'Symbol not found'}

            last_time = await conn.fetchval("""
                SELECT MAX(time) FROM candles_1s WHERE symbol_id = $1
            """, symbol_id)

            start_time = last_time - timedelta(seconds=seconds)

            # Load candle data with wide vectors for sequence prediction
            rows = await conn.fetch("""
                SELECT c.time, c.close, wv.vector, wv.vector_size FROM candles_1s c
                JOIN wide_vectors wv ON wv.time = c.time
                WHERE c.symbol_id = $1 AND c.time >= $2
                ORDER BY c.time ASC
            """, symbol_id, start_time)

        if not rows:
            return {'error': 'No candle data found'}

        closes = np.array([float(r['close']) for r in rows])
        timestamps = np.array([int(r['time'].timestamp()) for r in rows])

        # Parse wide vectors
        vectors = []
        for r in rows:
            if isinstance(r['vector'], str):
                vec = np.array(json.loads(r['vector']), dtype=np.float32)
            else:
                vec = np.array(r['vector'], dtype=np.float32)

            # Sanitize NaN values
            if np.isnan(vec).any():
                vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
            vectors.append(vec)

        vectors = np.array(vectors)

        # Load TradingTCN model
        model_path = str(Path('ml/models/trading_tcn') / model)
        # Load full checkpoint (we trust our own saved models)
        checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)

        # Reconstruct model from saved config
        cfg = checkpoint.get('model_cfg', ModelConfig())
        cfg.hidden_dims = [128]  # Ensure compatibility
        cfg.dropout = 0.2
        cfg.trading_tcn_blocks = 8

        tcn_model = TradingTCN(vectors.shape[1], cfg)
        tcn_model.load_state_dict(checkpoint['model_state_dict'])
        tcn_model.eval()

        # Generate predictions in batches using sliding window sequences
        predictions_ret = []
        predictions_risk = []

        seq_length = 120  # Must match training sequence length
        batch_size = 64

        with torch.no_grad():
            for i in range(seq_length, len(vectors), batch_size):
                batch_end = min(i + batch_size, len(vectors))
                batch_indices = range(i, batch_end)

                # Create sequences for this batch
                batch_sequences = []
                for idx in batch_indices:
                    seq = vectors[idx-seq_length:idx]  # Last 120 timesteps
                    batch_sequences.append(seq)

                if len(batch_sequences) == 0:
                    continue

                batch_tensor = torch.from_numpy(np.stack(batch_sequences)).float()
                pred_ret, pred_risk = tcn_model(batch_tensor)

                # Store predictions aligned with timestamps
                for j, idx in enumerate(batch_indices):
                    if idx < len(predictions_ret):
                        predictions_ret[idx] = pred_ret[j].item()
                        predictions_risk[idx] = pred_risk[j].item()
                    else:
                        predictions_ret.append(pred_ret[j].item())
                        predictions_risk.append(pred_risk[j].item())

        # Pad predictions to match candle length (no prediction for first seq_length-1 candles)
        while len(predictions_ret) < len(closes):
            predictions_ret.insert(0, 0.0)
            predictions_risk.insert(0, 0.1)  # Default risk

        predictions_ret = np.array(predictions_ret)
        predictions_risk = np.array(predictions_risk)

        # Calculate risk-adjusted scores
        scores = predictions_ret / (predictions_risk + 1e-6)

        print(f"\n🔥 TRADINGTCN BACKTEST DEBUG:")
        print(f"   Predictions: ret mean={predictions_ret.mean():.6f}, risk mean={predictions_risk.mean():.6f}")
        print(f"   Scores: mean={scores.mean():.6f}, threshold={score_threshold}")
        print(f"   Entries: {np.sum(scores >= score_threshold)} / {len(scores)}")

        # Simulate trading using risk-adjusted scores
        trades = []
        position = 0
        entry_price = 0.0
        entry_time = 0

        for i in range(len(closes)):
            current_price = closes[i]
            current_time = timestamps[i]
            score = scores[i] if i < len(scores) else 0.0

            # ENTER LONG POSITION based on risk-adjusted score
            if score >= score_threshold and position == 0:
                position = 1
                entry_price = current_price
                entry_time = current_time

            # EXIT POSITION after 10 minutes (600 seconds) or end of data
            elif position == 1 and (current_time - entry_time >= 600 or i == len(closes)-1):
                position = 0
                pnl = (current_price - entry_price) / entry_price - 0.002  # minus fees

                trades.append({
                    'entry_time': int(entry_time),
                    'exit_time': int(current_time),
                    'entry_price': float(entry_price),
                    'exit_price': float(current_price),
                    'pnl': float(pnl),
                    'duration': int(current_time - entry_time),
                    'score': float(score)
                })

        # Calculate metrics
        if trades:
            wins = sum(1 for t in trades if t['pnl'] > 0)
            win_rate = wins / len(trades)
            total_return = sum(t['pnl'] for t in trades)

            gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
            gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

            avg_duration = sum(t['duration'] for t in trades) / len(trades)
        else:
            win_rate = total_return = profit_factor = avg_duration = 0.0

        return {
            'symbol': symbol,
            'model': model,
            'candles': [{"time": int(t), "close": float(c)} for t, c in zip(timestamps, closes)],
            'predictions': {
                'returns': predictions_ret.tolist(),
                'risks': predictions_risk.tolist(),
                'scores': scores.tolist()
            },
            'trades': trades,
            'score_stats': {
                'min': float(np.min(scores)),
                'max': float(np.max(scores)),
                'mean': float(np.mean(scores)),
                'threshold': score_threshold
            },
            'metrics': {
                'total_trades': len(trades),
                'win_rate': win_rate,
                'total_return': total_return,
                'profit_factor': profit_factor,
                'max_drawdown': 0.0,  # TODO: implement drawdown calculation
                'avg_duration': avg_duration
            }
        }

    except Exception as e:
        logger.exception(f"TradingTCN backtest failed: {e}")
        return {'error': str(e)}


@router.post(
    "/train_trading_tcn",
    summary="Train new TradingTCN model",
    description="Train a new TradingTCN model with custom parameters"
)
async def train_trading_tcn_model(
    symbol: str = Query(..., description="Symbol name"),
    hours: int = Query(720, description="Training data hours"),
    horizon: int = Query(600, description="Prediction horizon in seconds"),
    loss: str = Query("pnl", description="Loss function: pnl, sharpe, risk_adjusted"),
    stride: int = Query(60, description="Sequence stride for downsampling")
):
    """
    Train a new TradingTCN model and save it to disk.
    Returns trained model filename and validation metrics.
    """
    try:
        import subprocess
        import sys

        logger.info(f"Starting TradingTCN training for {symbol}")

        # Run training script as separate process
        cmd = [
            sys.executable,
            "train_trading_tcn.py",
            "--symbol", symbol,
            "--hours", str(hours),
            "--horizon", str(horizon),
            "--loss", loss,
            "--stride", str(stride),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Training failed: {result.stderr}")
            return {'error': result.stderr}

        # Find latest trained model file
        models = await get_trading_tcn_models()
        latest_model = models[0] if models else None

        if not latest_model:
            return {'error': 'Model file not found after training'}

        logger.info(f"TradingTCN training complete: {latest_model['filename']}")

        return {
            'filename': latest_model['filename'],
            'symbol': latest_model['symbol'],
            'timestamp': latest_model['timestamp'],
            'success': True
        }

    except Exception as e:
        logger.exception(f"TradingTCN training failed: {e}")
        return {'error': str(e)}


# -------------------------------------------------------------------
# Entry Point Model Endpoints
# -------------------------------------------------------------------

async def get_entry_model_files() -> List[Dict]:
    """Get list of available entry point models.

    Searches for .pkl files in ml/models/entry_point/ directory.
    Expected filename format: entry_model_SYMBOL_BASE_QUOTE_YYYYMMDD_HHMM.pkl
    """
    model_dir = Path('ml/models/entry_point')
    models = []

    for file in model_dir.glob('entry_model_*.pkl'):
        try:
            # Parse filename: entry_model_SYMBOL_BASE_QUOTE_YYYYMMDD_HHMM.pkl
            # Example: entry_model_DASH_USDC_20260418_2052.pkl
            stem = file.stem  # Without .pkl
            parts = stem.split('_')

            if len(parts) >= 5:
                # parts[0] = 'entry', parts[1] = 'model', parts[2] = BASE, parts[3] = QUOTE
                symbol = f"{parts[2]}/{parts[3]}"
                timestamp_str = f"{parts[-2]}_{parts[-1]}"  # YYYYMMDD_HHMM
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M")
                except ValueError:
                    # Fallback to file modification time
                    timestamp = datetime.fromtimestamp(file.stat().st_mtime)

                models.append({
                    'filename': file.name,
                    'name': stem,
                    'symbol': symbol,
                    'timestamp': timestamp.isoformat(),
                    'size': file.stat().st_size
                })
        except Exception as e:
            logger.warning(f"Failed to parse model file {file}: {e}")
            continue

    return sorted(models, key=lambda m: m['timestamp'], reverse=True)


@router.get(
    "/models/entry",
    summary="List available entry point models",
    description="Returns list of trained entry point model (.pkl) files"
)
async def list_entry_models():
    """List all available entry point models in ml/models/entry_point/."""
    return await get_entry_model_files()


@router.get(
    "/entry",
    summary="Run backtest for entry point model",
    description="Run historical backtest using entry point model predictions"
)
async def run_entry_backtest(
    symbol: str = Query(..., description="Symbol name (e.g., BTC/USDC)"),
    model: str = Query(..., description="Model filename (e.g., entry_model_BTC_USDC_20260418_2052.pkl)"),
    seconds: int = Query(604800, description="Backtest time range in seconds (default: 7 days)"),
    threshold: float = Query(0.9, description="Prediction threshold [0.5, 1.0]", ge=0.5, le=1.0)
):
    """
    Run entry model backtest:
    1. Load historical candle data for given time range
    2. Load trained entry point model (LightGBM)
    3. Run predictions on every candle
    4. Simulate trading with entry/exit rules
    5. Return trades list and performance metrics

    The entry model predicts whether a candle is a good entry point (1) or not (0).
    Positions are entered when prediction >= threshold and exited after:
    - Profit target reached (6%)
    - Stop loss triggered (0.35%)
    - 10 minutes elapsed
    - End of data
    """
    try:
        db_pool = await get_db_pool_async()

        # Get symbol_id and last timestamp
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

        closes = np.array([float(r['close']) for r in rows])
        timestamps = np.array([int(r['time'].timestamp()) for r in rows])

        # Handle vector json parsing
        vectors = []
        for r in rows:
            if isinstance(r['vector'], str):
                vec = np.array(json.loads(r['vector']), dtype=np.float32)
            else:
                vec = np.array(r['vector'], dtype=np.float32)

            if np.isnan(vec).any():
                vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
            vectors.append(vec)

        vectors = np.array(vectors)

        # Load model
        model_path = str(Path('ml/models/entry_point') / model)
        loaded_model = EntryPointModel.load(model_path)

        # Apply same feature mask as during training
        if hasattr(loaded_model, 'feature_mask') and loaded_model.feature_mask is not None:
            vectors = vectors[:, loaded_model.feature_mask]

        # Run predictions
        probabilities, predictions = loaded_model.predict(vectors, threshold=threshold)

        # Simulate trading
        trades = []
        position = 0
        entry_price = 0.0
        entry_time = 0

        profit_target = 0.06  # 6%
        stop_loss = 0.0035    # 0.35%
        max_hold_seconds = 600  # 10 minutes

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
                hold_time = current_time - entry_time

                should_exit = (
                    profit_pct >= profit_target or
                    profit_pct <= -stop_loss or
                    hold_time >= max_hold_seconds or
                    i == len(closes) - 1
                )

                if should_exit:
                    # Exit position
                    position = 0
                    pnl = (current_price - entry_price) / entry_price

                    trades.append({
                        'entry_time': int(entry_time),
                        'exit_time': int(current_time),
                        'entry_price': float(entry_price),
                        'exit_price': float(current_price),
                        'pnl': float(pnl),
                        'duration': int(hold_time)
                    })

        # Calculate metrics
        if trades:
            wins = sum(1 for t in trades if t['pnl'] > 0)
            win_rate = wins / len(trades)
            total_return = sum(t['pnl'] for t in trades)

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

            durations = [t['duration'] for t in trades]
            avg_duration = sum(durations) / len(durations)

            metrics = {
                'total_trades': int(len(trades)),
                'win_rate': float(win_rate),
                'total_return': float(total_return),
                'profit_factor': float(profit_factor),
                'max_drawdown': float(max_dd),
                'avg_duration': float(avg_duration)
            }
        else:
            metrics = {
                'total_trades': 0,
                'win_rate': 0.0,
                'total_return': 0.0,
                'profit_factor': 0.0,
                'max_drawdown': 0.0,
                'avg_duration': 0.0
            }

        return {
            'symbol': symbol,
            'model': model,
            'threshold': threshold,
            'candles': [{'time': int(t), 'close': float(c)} for t, c in zip(timestamps, closes)],
            'predictions': {
                'probabilities': probabilities.tolist(),
                'predictions': predictions.tolist()
            },
            'trades': trades,
            'metrics': metrics
        }

    except Exception as e:
        logger.exception(f"Entry model backtest failed: {e}")
        return {'error': str(e)}


@router.post(
    "/train_entry",
    summary="Train new entry point model",
    description="Train a new entry point model with custom parameters"
)
async def train_entry_model(
    symbol: str = Query(..., description="Symbol name (e.g., BTC/USDC)"),
    hours: int = Query(720, description="Training data hours (default: 720)"),
    horizon: int = Query(600, description="Prediction horizon in seconds (default: 600)"),
    loss: str = Query("pnl", description="Loss function: pnl, sharpe, risk_adjusted (default: pnl)"),
    stride: int = Query(60, description="Sequence stride for downsampling (default: 60)")
):
    """
    Train a new entry point model.
    Note: Uses the same training pipeline as TradingTCN but with LightGBM classifier.
    """
    try:
        import subprocess
        import sys

        logger.info(f"Starting Entry Point Model training for {symbol}")

        # Run training script as separate process
        cmd = [
            sys.executable, "-m", "ml.train",
            "--symbol", symbol,
            "--hours", str(hours),
            "--horizon", str(horizon),
            "--loss", loss,
            "--stride", str(stride),
            "--model", "entry"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Training failed: {result.stderr}")
            return {'error': result.stderr}

        # Find latest trained model file
        models = await get_entry_model_files()
        latest_model = models[0] if models else None

        if not latest_model:
            return {'error': 'Model file not found after training'}

        logger.info(f"Entry Point Model training complete: {latest_model['filename']}")

        return {
            'filename': latest_model['filename'],
            'symbol': latest_model['symbol'],
            'timestamp': latest_model['timestamp'],
            'success': True
        }

    except Exception as e:
        logger.exception(f"Entry model training failed: {e}")
        return {'error': str(e)}
