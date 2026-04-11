"""
ML Prediction API endpoints.

Provides REST API for ML model predictions:
- GET /api/ml/models - List available trained models
- GET /api/ml/predict?symbol=BTC/USDC&model=best_model.pt&hours=2 - Run prediction
"""

import os
import json
import sys
import math
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.infrastructure.database import get_db_pool_async

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml"])

# Cache for loaded models
_model_cache: Dict[str, Any] = {}


def _get_torch_and_model():
    """Lazy import torch and model modules to avoid import errors in tests."""
    import numpy as np
    import torch
    from ml.config import DatabaseConfig, ModelConfig
    from ml.model import create_model
    return np, torch, DatabaseConfig, ModelConfig, create_model


def _load_model(model_path: str) -> tuple:
    """
    Load model and normalization parameters.

    Returns:
        (model, mean, std, feature_mask, config, sequence_length)
    """
    np, torch, DatabaseConfig, ModelConfig, create_model = _get_torch_and_model()

    if model_path in _model_cache:
        return _model_cache[model_path]

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")

    # Load checkpoint
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    config = checkpoint["config"]

    # Load normalization params
    norm_path = os.path.join(os.path.dirname(model_path), "norm_params.npz")
    if os.path.exists(norm_path):
        norm_params = np.load(norm_path)
        mean = norm_params["mean"]
        std = norm_params["std"]
        feature_mask = norm_params.get("feature_mask", np.ones(len(mean), dtype=bool))
    else:
        mean = None
        std = None
        feature_mask = None

    # Determine model type and input dim from state dict keys
    state_dict = checkpoint["model_state_dict"]

    if any(k.startswith("network.0.linear.weight") for k in state_dict.keys()):
        # Simple model (SimpleMLPModel)
        input_dim = state_dict["network.0.linear.weight"].shape[1]
        model_type = "simple"
    elif any(k.startswith("feature_proj.") for k in state_dict.keys()):
        # CNN_GRU model (feature_proj = LayerNorm + Linear)
        input_dim = state_dict["feature_proj.1.weight"].shape[1]
        model_type = "cnn_gru"
    elif any(k.startswith("cnn1.") for k in state_dict.keys()) and any(k.startswith("gru.") for k in state_dict.keys()):
        # Old CNN+GRU model
        input_dim = state_dict["cnn1.weight"].shape[1]
        model_type = "cnn_gru"
    elif any(k.startswith("transformer_blocks.") for k in state_dict.keys()):
        # Transformer model (CryptoTransformerModel)
        input_dim = state_dict["input_proj.0.weight"].shape[1]
        model_type = "transformer"
    elif "input_proj.0.weight" in state_dict:
        # Full model (CryptoTargetModel)
        input_dim = state_dict["input_proj.0.weight"].shape[1]
        model_type = "full"
    else:
        # Fallback to simple model
        first_key = list(state_dict.keys())[0]
        weight_shape = state_dict[first_key].shape
        if len(weight_shape) >= 2:
            input_dim = weight_shape[1]
        else:
            raise ValueError(f"Unexpected weight shape {weight_shape} for key {first_key}")
        model_type = "simple"

    # Create model and load weights
    model = create_model(input_dim, config.model, model_type=model_type)
    model.load_state_dict(state_dict)
    model.eval()

    seq_length = config.data.sequence_length

    # Cache the loaded model
    _model_cache[model_path] = (model, mean, std, feature_mask, config, seq_length)

    return model, mean, std, feature_mask, config, seq_length


@router.get(
    "/models",
    summary="List available ML models",
    description="List all trained model files in ml/models/ subdirectories",
)
async def list_models() -> List[Dict[str, Any]]:
    """
    List available ML models from subdirectories (simple/, full/, transformer/).
    """
    models_dir = "ml/models"
    if not os.path.exists(models_dir):
        return []

    models = []
    type_labels = {
        "simple": "Simple",
        "full": "Full",
        "transformer": "Transformer",
        "cnn_gru": "CNN+GRU",  # NEW: Recommended for financial time series
    }

    for subdir_name in sorted(os.listdir(models_dir)):
        subdir_path = os.path.join(models_dir, subdir_name)
        if not os.path.isdir(subdir_path):
            continue
        if subdir_name not in type_labels:
            continue

        for filename in os.listdir(subdir_path):
            if filename.endswith(".pt") and "norm" not in filename:
                filepath = os.path.join(subdir_path, filename)
                stat = os.stat(filepath)
                models.append(
                    {
                        "name": f"{subdir_name}/{filename}",
                        "type": subdir_name,
                        "label": type_labels[subdir_name],
                        "path": filepath,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )

    return sorted(models, key=lambda x: x["modified"], reverse=True)


@router.get(
    "/predict",
    summary="Run ML prediction",
    description="Load model and run prediction for a symbol",
)
async def predict(
    symbol: str = Query(..., description="Symbol name (e.g., 'BTC/USDC')"),
    model: str = Query(default="best_model.pt", description="Model filename"),
    hours: float = Query(default=720, gt=0, le=1440, description="Hours of data to load"),
    ensemble_size: int = Query(default=5, ge=1, le=20, description="Average last N predictions for smoothing"),
) -> Dict[str, Any]:
    """
    Run ML prediction for a symbol.

    Returns candles, target values, and ML predictions.
    Uses ensemble averaging (last N predictions) to reduce noise.
    """
    model_path = os.path.join("ml/models", model)

    try:
        ml_model, mean, std, feature_mask, config, seq_length = _load_model(model_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {e}")

    db_pool = await get_db_pool_async()

    async with db_pool.acquire() as conn:
        # Get symbol_id
        symbol_id = await conn.fetchval(
            "SELECT id FROM symbols WHERE symbol = $1", symbol
        )
        if not symbol_id:
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

        # Time range - use latest available data instead of "now"
        # First get the latest vector time
        latest_vector_time = await conn.fetchval(
            "SELECT MAX(time) FROM wide_vectors"
        )
        if not latest_vector_time:
            raise HTTPException(status_code=404, detail="No wide vectors available")
        
        now = latest_vector_time
        start_time = now - timedelta(hours=hours)
        
        # Debug output
        print(f"DEBUG: Querying vectors from {start_time} to {now} ({hours} hours)")

        # Load candles
        candle_rows = await conn.fetch(
            """
            SELECT time, open, high, low, close, volume
            FROM candles_1s
            WHERE symbol_id = $1 AND time >= $2 AND time < $3
            ORDER BY time
            """,
            symbol_id,
            start_time,
            now,
        )
        
        print(f"DEBUG: Got {len(candle_rows)} candles")

        # Load wide vectors for prediction
        vector_rows = await conn.fetch(
            """
            SELECT time, vector
            FROM wide_vectors
            WHERE time >= $1 AND time < $2
            ORDER BY time
            """,
            start_time,
            now,
        )
        
        print(f"DEBUG: Got {len(vector_rows)} vectors")

    # Prepare candles data
    candles = [
        {
            "time": int(r["time"].timestamp()),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]),
        }
        for r in candle_rows
    ]

    # Get target values as price returns: (close[t+horizon] - close[t]) / close[t]
    if candles:
        # Compute price return targets from candle data
        close_prices = [c["close"] for c in candles]
        horizon = 30  # prediction_horizon
        all_targets = []
        for i in range(len(close_prices) - horizon):
            ret = (close_prices[i + horizon] - close_prices[i]) / close_prices[i]
            all_targets.append({
                "time": candles[i]["time"],
                "value": round(ret, 8),
            })

        targets = all_targets
    else:
        targets = []

    # Run prediction on wide vectors
    np, torch, _, _, _ = _get_torch_and_model()
    predictions = []
    vectors = []  # Initialize vectors list
    
    pred_start = time.time()
    logger.info(f"Starting prediction with {len(vector_rows)} vector rows")
    
    if len(vector_rows) >= seq_length:
        # Parse vectors
        vectors = []
        timestamps = []
        prev_size = None

        parse_start = time.time()
        for row in vector_rows:
            vec_json = row["vector"]
            if isinstance(vec_json, str):
                vec = np.array(json.loads(vec_json), dtype=np.float32)
            else:
                vec = np.array(vec_json, dtype=np.float32)

            # Handle variable length
            if prev_size is None:
                prev_size = len(vec)
            elif len(vec) != prev_size:
                if len(vec) < prev_size:
                    vec = np.pad(vec, (0, prev_size - len(vec)))
                else:
                    vec = vec[:prev_size]

            vectors.append(vec)
            timestamps.append(row["time"])
        
        logger.info(f"Parsed {len(vectors)} vectors in {time.time() - parse_start:.2f}s")

        # Validate vector dimensions before normalization
        if vectors:
            vec_size = len(vectors[0])
            if feature_mask is not None:
                expected_size = len(feature_mask)
                if vec_size != expected_size:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Vector size mismatch: vectors have {vec_size} features but model was trained on {expected_size} features. "
                               f"The model requires vectors with indicators (ATR, EMA, MACD, RSI, SMA, Bollinger Bands). "
                               f"Current vectors only have close/volume data. Recalculate wide vectors with indicators enabled."
                    )
            elif mean is not None:
                expected_size = len(mean)
                if vec_size != expected_size:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Vector size mismatch: vectors have {vec_size} features but model expects {expected_size} features."
                    )

        # Normalize (add epsilon to std to prevent division by zero)
        # Also apply feature mask to keep only informative features
        if mean is not None and std is not None:
            epsilon = 1e-8
            std_safe = np.where(std < epsilon, epsilon, std)
            if feature_mask is not None:
                vectors = [(v[feature_mask] - mean) / std_safe for v in vectors]
            else:
                vectors = [(v - mean) / std_safe for v in vectors]

        # Sliding window prediction
        logger.info(f"Running sliding window prediction: {len(vectors) - seq_length + 1} steps")
        loop_start = time.time()
        
        with torch.no_grad():
            for i in range(seq_length - 1, len(vectors)):
                sequence = np.stack(vectors[i - seq_length + 1 : i + 1])
                X = torch.from_numpy(sequence).unsqueeze(0)

                # Simple model only uses last timestep, but we pass full sequence
                # The model internally handles this
                pred_time = time.time()
                prediction = ml_model(X).item()
                
                if (i - seq_length) % 50 == 0:
                    logger.info(f"  Step {i - seq_length + 1}: model inference took {time.time() - pred_time:.3f}s")

                # Check for NaN or Inf
                if math.isnan(prediction) or math.isinf(prediction):
                    prediction = 0.0

                predictions.append(
                    {
                        "time": int(timestamps[i].timestamp()),
                        "predicted_target": round(prediction, 8),
                    }
                )
        
        logger.info(f"Sliding window prediction completed in {time.time() - loop_start:.2f}s")

    # Predictions are price returns, same scale as target values
    if predictions and candles:

        # Apply ensemble averaging (smooth predictions by averaging last N)
        if ensemble_size > 1 and len(predictions) >= ensemble_size:
            smoothed_predictions = []
            for i in range(len(predictions)):
                if i < ensemble_size - 1:
                    # Not enough history, use available values
                    window_start = max(0, i - ensemble_size + 1)
                    window = predictions[window_start:i + 1]
                else:
                    # Full window
                    window = predictions[i - ensemble_size + 1:i + 1]

                avg_value = sum(p["predicted_target"] for p in window) / len(window)
                smoothed_predictions.append({
                    "time": predictions[i]["time"],
                    "predicted_target": round(avg_value, 8),
                })

            predictions = smoothed_predictions

    return {
        "symbol": symbol,
        "model": model,
        "sequence_length": seq_length,
        "hours_loaded": hours,
        "candles_count": len(candles),
        "targets_count": len(targets),
        "predictions_count": len(predictions),
        "vectors_count": len(vectors),
        "candles": candles,
        "targets": targets,
        "predictions": predictions,
    }
