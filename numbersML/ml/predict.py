"""
Inference script for ML target prediction.

Usage:
    python -m ml.predict --model ml/models/best_model.pt --hours 2
    python -m ml.predict --model ml/models/best_model.pt --symbol BTC/USDC
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import psycopg2

from ml.config import DatabaseConfig, ModelConfig, get_default_config
from ml.model import create_model

logger = logging.getLogger(__name__)


class Predictor:
    """Load trained model and make predictions."""

    def __init__(
        self,
        model_path: str,
        db_config: Optional[DatabaseConfig] = None,
        device: str = "cpu",
    ):
        self.device = torch.device(device)
        self.db_config = db_config or DatabaseConfig()

        # Load checkpoint
        checkpoint = torch.load(model_path, map_location=self.device)
        self.config = checkpoint["config"]

        # Load normalization params
        norm_path = os.path.join(os.path.dirname(model_path), "norm_params.npz")
        if os.path.exists(norm_path):
            norm_params = np.load(norm_path)
            self.mean = norm_params["mean"]
            self.std = norm_params["std"]
            self.feature_mask = norm_params.get("feature_mask", None)
        else:
            logger.warning(f"No normalization params found at {norm_path}")
            self.mean = None
            self.std = None
            self.feature_mask = None

        # Detect model type and input dim from state dict keys
        state_keys = set(checkpoint["model_state_dict"].keys())
        
        if any("transformer_blocks" in k for k in state_keys):
            model_type = "transformer"
            first_weight = checkpoint["model_state_dict"]["input_proj.0.weight"]
        elif any("attention_layers" in k for k in state_keys):
            model_type = "full"
            first_weight = checkpoint["model_state_dict"]["input_proj.0.weight"]
        elif any("feature_proj" in k for k in state_keys):
            # CNN_GRU model: feature_proj is LayerNorm (0) + Linear (1)
            model_type = "simple"
            first_weight = checkpoint["model_state_dict"]["feature_proj.1.weight"]
        elif any("network" in k for k in state_keys):
            # Old SimpleMLP model
            model_type = "simple"
            first_weight = checkpoint["model_state_dict"]["network.0.linear.weight"]
        else:
            raise ValueError(
                f"Unknown model type. State dict keys: {list(state_keys)[:10]}"
            )
        
        # Handle weight tensors that might have unexpected shapes
        weight_shape = first_weight.shape
        if len(weight_shape) >= 2:
            input_dim = weight_shape[1]
        else:
            raise ValueError(
                f"Unexpected weight shape {weight_shape}, expected at least 2D"
            )

        # Create model and load weights
        self.model = create_model(input_dim, self.config.model, model_type=model_type)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()

        logger.info(f"Model loaded from {model_path}")
        logger.info(f"Input dim: {input_dim}")
        logger.info(f"Sequence length: {self.config.data.sequence_length}")

    def load_recent_vectors(
        self,
        hours: int = 2,
        symbol: Optional[str] = None,
    ) -> Tuple[List[np.ndarray], List[datetime]]:
        """
        Load recent wide_vectors from database.

        Args:
            hours: Hours of data to load
            symbol: Optional symbol filter (not implemented yet)

        Returns:
            List of vectors and timestamps
        """
        conn = psycopg2.connect(
            host=self.db_config.host,
            port=self.db_config.port,
            dbname=self.db_config.dbname,
            user=self.db_config.user,
            password=self.db_config.password,
        )

        try:
            with conn.cursor() as cur:
                since = datetime.now(timezone.utc) - timedelta(
                    hours=hours
                )

                query = """
                    SELECT time, vector, vector_size
                    FROM wide_vectors
                    WHERE time >= %s
                    ORDER BY time
                """
                cur.execute(query, (since,))

                vectors = []
                timestamps = []
                expected_size = None

                for row in cur.fetchall():
                    ts, vector_json, vec_size = row

                    # Parse vector
                    if isinstance(vector_json, str):
                        vec = np.array(json.loads(vector_json), dtype=np.float32)
                    else:
                        vec = np.array(vector_json, dtype=np.float32)

                    # Handle variable length
                    if expected_size is None:
                        expected_size = len(vec)
                    elif len(vec) != expected_size:
                        if len(vec) < expected_size:
                            vec = np.pad(vec, (0, expected_size - len(vec)))
                        else:
                            vec = vec[:expected_size]

                    vectors.append(vec)
                    timestamps.append(ts)

        finally:
            conn.close()

        return vectors, timestamps

    @torch.no_grad()
    def predict(
        self,
        vectors: List[np.ndarray],
        timestamps: List[datetime],
    ) -> List[Dict]:
        """
        Make predictions on a sequence of vectors.

        Args:
            vectors: List of wide_vectors
            timestamps: Corresponding timestamps

        Returns:
            List of dicts with timestamp and predicted target_value
        """
        if len(vectors) < self.config.data.sequence_length:
            raise ValueError(
                f"Need at least {self.config.data.sequence_length} vectors, "
                f"got {len(vectors)}"
            )

        # Normalize
        if self.mean is not None and self.std is not None:
            vectors = [(v - self.mean) / self.std for v in vectors]

        results = []

        # Sliding window prediction
        for i in range(self.config.data.sequence_length - 1, len(vectors)):
            # Get sequence
            sequence = np.stack(
                vectors[i - self.config.data.sequence_length + 1 : i + 1]
            )

            # Convert to tensor
            X = torch.from_numpy(sequence).unsqueeze(0).to(self.device)

            # Predict
            prediction = self.model(X).item()

            results.append(
                {
                    "time": timestamps[i].isoformat(),
                    "predicted_target": prediction,
                }
            )

        return results

    def predict_latest(self, hours: int = 2) -> Dict:
        """
        Load recent data and predict the latest target_value.

        Returns:
            Dict with latest prediction and metadata
        """
        vectors, timestamps = self.load_recent_vectors(hours=hours)

        if not vectors:
            return {"error": "No data available"}

        results = self.predict(vectors, timestamps)

        if not results:
            return {"error": "Not enough data for prediction"}

        latest = results[-1]

        return {
            "time": latest["time"],
            "predicted_target": latest["predicted_target"],
            "sequence_length": self.config.data.sequence_length,
            "hours_loaded": hours,
            "n_predictions": len(results),
        }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Predict target values")
    parser.add_argument(
        "--model",
        type=str,
        default="ml/models/best_model.pt",
        help="Path to model checkpoint",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=2,
        help="Hours of data to load (default: 2)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Symbol filter (not implemented)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for predictions (JSON)",
    )

    args = parser.parse_args()

    # Load predictor
    predictor = Predictor(args.model)

    # Predict
    result = predictor.predict_latest(hours=args.hours)

    # Output
    print(json.dumps(result, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nPredictions saved to {args.output}")


if __name__ == "__main__":
    main()
